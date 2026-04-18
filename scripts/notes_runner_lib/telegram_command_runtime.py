from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class TelegramCommandDependencies:
    ensure_parent_dir: Callable[[Path], Path]
    download_telegram_media: Callable[[str, int, str], Path]
    audio_extensions: set[str] | frozenset[str]
    local_bundle_dir_for: Callable[[Path, str, Path], Path]
    bundle_paths: Callable[[Path], dict[str, Path]]
    start_bundle_run: Callable[..., dict]
    write_json: Callable[[Path, dict], None]
    ensure_audio_transcription_available: Callable[[str], None]
    run_whisperx_diarize: Callable[..., Path]
    local_backend_language: Callable[[str], str | None]
    whisperx_json_to_transcript_markdown: Callable[[Path], str]
    write_text: Callable[[Path, str], None]
    normalize_transcript_text: Callable[[str], str]
    choose_transcribe_backend: Callable[[str], str]
    normalize_language_hint: Callable[[str], str | None]
    call_groq_transcribe: Callable[..., object]
    groq_payload_to_transcript_markdown: Callable[[object], str]
    is_macos: Callable[[], bool]
    run_mlx_whisper: Callable[..., Path]
    whisper_json_to_transcript_markdown: Callable[[Path], str]
    run_prepare_for_transcript: Callable[..., dict]
    attach_prepare_outputs: Callable[[dict[str, object], dict, Path], None]
    ms_since: Callable[[float], int]
    extract_prepare_duration_ms: Callable[[dict | None], int]
    write_bundle_state_snapshot: Callable[[Path, dict], dict]
    append_trace_event: Callable[..., Path]
    finish_bundle_run: Callable[..., object]
    stderr: TextIO | None = None
    groq_model: str = "whisper-large-v3-turbo"
    transcription_feature_name: str = "Telegram voice notes"


def run_telegram_command(args: argparse.Namespace, *, deps: TelegramCommandDependencies) -> int:
    """Download a Telegram voice/audio message and create a notes bundle."""
    command_started = time.monotonic()
    stderr = deps.stderr if deps.stderr is not None else sys.stderr
    output_root = deps.ensure_parent_dir(Path(args.output_root))
    media_path = deps.download_telegram_media(args.chat, args.message_id, args.mcp_url)

    if media_path.suffix.lower() not in deps.audio_extensions:
        raise ValueError(
            f"Downloaded file is not a supported audio format: {media_path.suffix} ({media_path}). "
            f"Supported: {', '.join(sorted(deps.audio_extensions))}"
        )

    title = f"telegram-{args.chat}-{args.message_id}"
    bundle_dir = deps.local_bundle_dir_for(media_path, title, output_root)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    paths = deps.bundle_paths(bundle_dir)
    run_context = deps.start_bundle_run(
        bundle_dir,
        command="telegram",
        state_seed={
            "source_kind": "telegram",
            "source_path": str(media_path),
            "telegram_chat": args.chat,
            "telegram_message_id": args.message_id,
            "title": title,
        },
    )

    try:
        source_dir = bundle_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_copy = source_dir / media_path.name
        shutil.copy2(media_path, source_copy)

        deps.write_json(
            paths["metadata"],
            {
                "title": title,
                "source_path": str(media_path),
                "source_name": media_path.name,
                "source_extension": media_path.suffix.lower(),
                "source_kind": "telegram",
                "telegram_chat": args.chat,
                "telegram_message_id": args.message_id,
                "whisper_model": args.model,
                "whisper_language": args.language,
            },
        )

        transcript_path = paths["transcript"]
        whisper_json_path = bundle_dir / "whisper_output.json"
        use_diarize = getattr(args, "diarize", False)

        if use_diarize and shutil.which("whisperx"):
            deps.ensure_audio_transcription_available(deps.transcription_feature_name)
            with tempfile.TemporaryDirectory(prefix="notes-whisperx-") as tmp_dir:
                tmp_output = Path(tmp_dir)
                whisper_output = deps.run_whisperx_diarize(
                    media_path, tmp_output, model=args.model, language=deps.local_backend_language(args.language),
                )
                shutil.copy2(whisper_output, whisper_json_path)

            raw_markdown = deps.whisperx_json_to_transcript_markdown(whisper_json_path)
            deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
            transcript_source: dict[str, object] = {
                "kind": "telegram-voice-diarize",
                "chat": args.chat,
                "message_id": args.message_id,
                "model": args.model,
                "language": args.language,
                "whisper_json": str(whisper_json_path),
                "downloaded_path": str(media_path),
            }
        else:
            api_backend = None
            try:
                api_backend = deps.choose_transcribe_backend(getattr(args, "transcribe_backend", "auto"))
            except ValueError:
                pass

            if api_backend == "groq":
                raw_json_path = bundle_dir / "groq_output.json"
                language_hint = deps.normalize_language_hint(args.language) if hasattr(args, "language") else "ru"
                raw_payload = deps.call_groq_transcribe(media_path, raw_json_path, language=language_hint)
                raw_markdown = deps.groq_payload_to_transcript_markdown(raw_payload)
                deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
                transcript_source = {
                    "kind": "telegram-voice-groq",
                    "chat": args.chat,
                    "message_id": args.message_id,
                    "model": deps.groq_model,
                    "language": language_hint or "auto",
                    "raw_json": str(raw_json_path),
                    "downloaded_path": str(media_path),
                }
            elif deps.is_macos():
                deps.ensure_audio_transcription_available(deps.transcription_feature_name)
                if use_diarize:
                    print("Warning: --diarize requested but whisperx is not installed. Falling back to mlx_whisper.", file=stderr)
                with tempfile.TemporaryDirectory(prefix="notes-whisper-") as tmp_dir:
                    tmp_output = Path(tmp_dir)
                    whisper_output = deps.run_mlx_whisper(
                        media_path, tmp_output, model=args.model, language=deps.local_backend_language(args.language),
                    )
                    shutil.copy2(whisper_output, whisper_json_path)
                raw_markdown = deps.whisper_json_to_transcript_markdown(whisper_json_path)
                deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
                transcript_source = {
                    "kind": "telegram-voice",
                    "chat": args.chat,
                    "message_id": args.message_id,
                    "model": args.model,
                    "language": args.language,
                    "whisper_json": str(whisper_json_path),
                    "downloaded_path": str(media_path),
                }
            else:
                raise FileNotFoundError(
                    "No transcription backend available. "
                    "Set GROQ_API_KEY (free at console.groq.com)."
                )

        payload: dict[str, object] = {
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "telegram",
            "source_path": str(media_path),
            "source_name": media_path.name,
            "source_copy_path": str(source_copy),
            "metadata_path": str(paths["metadata"]),
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "suggested_output_md": str(paths["notes_md"]),
            "suggested_output_html": str(paths["notes_html"]),
            "telegram_chat": args.chat,
            "telegram_message_id": args.message_id,
        }

        if args.prepare:
            prepare_payload = deps.run_prepare_for_transcript(transcript_path, bundle_dir=bundle_dir, refresh=args.refresh)
            deps.attach_prepare_outputs(payload, prepare_payload, bundle_dir)

        transcription_duration_ms = deps.ms_since(command_started)
        prepare_ms = deps.extract_prepare_duration_ms(payload.get("prepare") if isinstance(payload.get("prepare"), dict) else None)
        state_payload = {
            "updated_at": datetime.now().isoformat(),
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "telegram",
            "source_path": str(media_path),
            "source_name": media_path.name,
            "telegram_chat": args.chat,
            "telegram_message_id": args.message_id,
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "whisper_model": args.model,
            "whisper_language": args.language,
            "telemetry": {
                "transcription_ms": transcription_duration_ms,
                "prepare_ms": prepare_ms,
                "prepare_reused": bool(payload.get("prepare", {}).get("reused")) if isinstance(payload.get("prepare"), dict) else False,
            },
        }
        if "prepare" in payload:
            state_payload["prepare"] = payload["prepare"]
        state_payload["trace_path"] = str(paths["trace"])
        state_payload = deps.write_bundle_state_snapshot(bundle_dir, state_payload)
        payload["trace_path"] = str(paths["trace"])
        payload["note_id"] = state_payload["note_id"]
        deps.append_trace_event(
            bundle_dir,
            "telegram.ready",
            source_path=str(media_path),
            transcript_path=str(transcript_path),
            transcript_kind=transcript_source.get("kind") if isinstance(transcript_source, dict) else None,
            telegram_chat=args.chat,
            telegram_message_id=args.message_id,
            prepare=bool(args.prepare),
            prepare_reused=bool(payload.get("prepare", {}).get("reused")) if isinstance(payload.get("prepare"), dict) else False,
        )
        deps.finish_bundle_run(bundle_dir, run_context, status="source-ready")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        print(f"Bundle: {bundle_dir}")
        print(f"Title: {title}")
        print(f"Source: {media_path}")
        print(f"Transcript: {transcript_path}")
        print(f"Suggested markdown: {paths['notes_md']}")
        print(f"Suggested HTML: {paths['notes_html']}")
        if args.prepare and "prepare" in payload:
            print(f"Work dir: {payload['prepare']['work_dir']}")
        return 0
    except Exception as exc:
        deps.finish_bundle_run(bundle_dir, run_context, status="failed", error=str(exc))
        raise
