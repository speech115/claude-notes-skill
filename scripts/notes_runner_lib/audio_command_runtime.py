from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class AudioCommandDependencies:
    ensure_file: Callable[[Path, str], Path]
    ensure_parent_dir: Callable[[Path], Path]
    humanize_path_title_hint: Callable[[str], str]
    audio_extensions: set[str] | frozenset[str]
    video_extensions: set[str] | frozenset[str]
    extract_audio_from_video: Callable[[Path, Path], Path]
    local_bundle_dir_for: Callable[[Path, str, Path], Path]
    bundle_paths: Callable[[Path], dict[str, Path]]
    start_bundle_run: Callable[..., dict]
    write_json: Callable[[Path, object], None]
    load_json: Callable[[Path], object]
    whisper_json_to_transcript_markdown: Callable[[Path], str]
    write_text: Callable[[Path, str], None]
    normalize_transcript_text: Callable[[str], str]
    probe_media_duration_seconds: Callable[[Path], int]
    choose_transcribe_backend: Callable[[str], str]
    normalize_language_hint: Callable[[str], str | None]
    call_groq_transcribe: Callable[..., dict]
    groq_payload_to_transcript_markdown: Callable[[dict], str]
    groq_rate_limit_error: type[BaseException]
    is_macos: Callable[[], bool]
    mlx_whisper_available: Callable[[], bool]
    ensure_audio_transcription_available: Callable[[str], None]
    local_backend_language: Callable[[str], str | None]
    run_whisperx_diarize: Callable[..., Path]
    whisperx_json_to_transcript_markdown: Callable[[Path], str]
    run_mlx_whisper: Callable[..., Path]
    call_parakeet_transcribe: Callable[..., str]
    call_transcribe_helper: Callable[..., dict]
    transcript_markdown_from_api_payload: Callable[[dict], str]
    run_prepare_for_transcript: Callable[..., dict]
    attach_prepare_outputs: Callable[[dict[str, object], dict, Path], None]
    extract_prepare_duration_ms: Callable[[dict | None], int]
    write_bundle_state_snapshot: Callable[[Path, dict], dict]
    append_trace_event: Callable[..., object]
    finish_bundle_run: Callable[..., object]
    ms_since: Callable[[float], int]
    stderr: TextIO | None = None
    groq_model: str = "whisper-large-v3-turbo"
    parakeet_model: str = "parakeet-tdt-0.6b-v3"
    transcription_feature_name: str = "Audio transcription"


def cmd_audio(args: argparse.Namespace, *, deps: AudioCommandDependencies) -> int:
    source_path = deps.ensure_file(Path(args.path), "Audio/video file")
    all_supported = deps.audio_extensions | deps.video_extensions
    if source_path.suffix.lower() not in all_supported:
        raise ValueError(
            f"Unsupported format: {source_path.suffix}. "
            f"Supported: {', '.join(sorted(all_supported))}"
        )

    output_root = deps.ensure_parent_dir(Path(args.output_root))
    title = args.title if getattr(args, "title", None) else (deps.humanize_path_title_hint(source_path.stem) or source_path.stem)

    extracted_tmp_dir = None
    if source_path.suffix.lower() in deps.video_extensions:
        extracted_tmp_dir = tempfile.mkdtemp(prefix="notes-video-extract-")
        audio_path = deps.extract_audio_from_video(source_path, Path(extracted_tmp_dir))
    else:
        audio_path = source_path

    try:
        return _cmd_audio_inner(args, source_path, audio_path, extracted_tmp_dir, output_root, title, deps=deps)
    finally:
        if extracted_tmp_dir and os.path.isdir(extracted_tmp_dir):
            shutil.rmtree(extracted_tmp_dir, ignore_errors=True)


def _cmd_audio_inner(
    args: argparse.Namespace,
    source_path: Path,
    audio_path: Path,
    _extracted_tmp_dir: str | None,
    output_root: Path,
    title: str,
    *,
    deps: AudioCommandDependencies,
) -> int:
    del _extracted_tmp_dir
    command_started = time.monotonic()
    stderr = deps.stderr if deps.stderr is not None else sys.stderr
    bundle_dir = deps.local_bundle_dir_for(source_path, title, output_root)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    paths = deps.bundle_paths(bundle_dir)
    is_video = source_path.suffix.lower() in deps.video_extensions
    run_context = deps.start_bundle_run(
        bundle_dir,
        command="audio",
        state_seed={
            "source_kind": "video" if is_video else "audio",
            "source_path": str(source_path),
            "title": title,
        },
    )

    try:
        source_dir = bundle_dir / "source"
        source_dir.mkdir(parents=True, exist_ok=True)
        source_copy = source_dir / source_path.name
        if not source_copy.exists() or args.refresh:
            shutil.copy2(source_path, source_copy)

        deps.write_json(
            paths["metadata"],
            {
                "title": title,
                "source_path": str(source_path),
                "source_name": source_path.name,
                "source_extension": source_path.suffix.lower(),
                "source_kind": "video" if is_video else "audio",
                "whisper_model": args.model,
                "whisper_language": args.language,
            },
        )

        transcript_path = paths["transcript"]
        whisper_json_path = bundle_dir / "whisper_output.json"
        transcript_source: dict[str, object] | None = None
        source_hints = {
            "source_kind": "video" if is_video else "audio",
            "duration_seconds": deps.probe_media_duration_seconds(source_path),
        }

        use_diarize = getattr(args, "diarize", False)
        use_api_backend = getattr(args, "transcribe_backend", "auto")
        api_backend: str | None = None
        if use_api_backend != "auto" or os.environ.get("GROQ_API_KEY"):
            try:
                api_backend = deps.choose_transcribe_backend(use_api_backend)
            except ValueError:
                api_backend = None

        adjacent_json = source_path.with_suffix(".json")
        if not transcript_path.is_file() and adjacent_json.is_file() and not args.refresh:
            try:
                adjacent_data = deps.load_json(adjacent_json)
                if isinstance(adjacent_data, dict) and "segments" in adjacent_data:
                    print(f"Reusing adjacent whisper JSON: {adjacent_json}", file=stderr)
                    shutil.copy2(adjacent_json, whisper_json_path)
                    raw_markdown = deps.whisper_json_to_transcript_markdown(whisper_json_path)
                    deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
                    transcript_source = {
                        "kind": "reused-adjacent-json",
                        "model": "unknown",
                        "language": args.language,
                        "whisper_json": str(whisper_json_path),
                        "original_json": str(adjacent_json),
                    }
            except (json.JSONDecodeError, ValueError, KeyError):
                pass

        if transcript_path.is_file() and not args.refresh:
            transcript_source = {
                "kind": "existing",
                "path": str(transcript_path),
            }
        elif api_backend == "groq":
            raw_json_path = bundle_dir / "groq_output.json"
            language_hint = deps.normalize_language_hint(args.language) if hasattr(args, "language") else "ru"
            try:
                raw_payload = deps.call_groq_transcribe(audio_path, raw_json_path, language=language_hint)
                raw_markdown = deps.groq_payload_to_transcript_markdown(raw_payload)
                deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
                transcript_source = {
                    "kind": "groq",
                    "model": deps.groq_model,
                    "language": language_hint or "auto",
                    "raw_json": str(raw_json_path),
                }
            except (deps.groq_rate_limit_error, ValueError) as exc:
                if deps.is_macos() and deps.mlx_whisper_available():
                    print(f"Groq failed ({exc}), falling back to MLX Whisper...", file=stderr)
                    api_backend = None
                else:
                    raise ValueError(
                        f"Groq transcription failed: {exc}. "
                        f"No local fallback available on this platform. "
                        f"Check your GROQ_API_KEY and try again."
                    ) from exc
        elif api_backend == "parakeet":
            language_hint = deps.normalize_language_hint(args.language) if hasattr(args, "language") else "ru"
            print("Transcribing with Parakeet v3 (MLX)...", file=stderr)
            raw_markdown = deps.call_parakeet_transcribe(audio_path, language=language_hint)
            deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
            transcript_source = {
                "kind": "parakeet",
                "model": deps.parakeet_model,
                "language": language_hint or "auto",
            }
        elif api_backend in ("deepgram", "openai"):
            raw_json_path = bundle_dir / "api_output.json"
            language_hint = deps.normalize_language_hint(args.language) if hasattr(args, "language") else "ru"
            raw_payload = deps.call_transcribe_helper(
                audio_path,
                raw_json_path,
                backend=api_backend,
                language=language_hint,
            )
            raw_markdown = deps.transcript_markdown_from_api_payload(raw_payload)
            deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
            transcript_source = {
                "kind": "api",
                "backend": api_backend,
                "language": language_hint or "auto",
                "raw_json": str(raw_json_path),
            }
        elif use_diarize and shutil.which("whisperx"):
            deps.ensure_audio_transcription_available(deps.transcription_feature_name)
            with tempfile.TemporaryDirectory(prefix="notes-whisperx-") as tmp_dir:
                tmp_output = Path(tmp_dir)
                whisper_output = deps.run_whisperx_diarize(
                    audio_path,
                    tmp_output,
                    model=args.model,
                    language=deps.local_backend_language(args.language),
                )
                shutil.copy2(whisper_output, whisper_json_path)
            raw_markdown = deps.whisperx_json_to_transcript_markdown(whisper_json_path)
            deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
            transcript_source = {
                "kind": "whisperx_diarize",
                "model": args.model,
                "language": args.language,
                "whisper_json": str(whisper_json_path),
            }

        if transcript_source is None:
            if not deps.is_macos():
                raise FileNotFoundError(
                    "No transcription backend succeeded. "
                    "Set GROQ_API_KEY (free at console.groq.com) to transcribe audio on this platform."
                )
            deps.ensure_audio_transcription_available(deps.transcription_feature_name)
            if use_diarize:
                print("Warning: --diarize requested but whisperx is not installed. Falling back to mlx_whisper.", file=stderr)
            with tempfile.TemporaryDirectory(prefix="notes-whisper-") as tmp_dir:
                tmp_output = Path(tmp_dir)
                whisper_output = deps.run_mlx_whisper(
                    audio_path,
                    tmp_output,
                    model=args.model,
                    language=deps.local_backend_language(args.language),
                )
                shutil.copy2(whisper_output, whisper_json_path)
            raw_markdown = deps.whisper_json_to_transcript_markdown(whisper_json_path)
            deps.write_text(transcript_path, deps.normalize_transcript_text(raw_markdown))
            transcript_source = {
                "kind": "mlx_whisper",
                "model": args.model,
                "language": args.language,
                "whisper_json": str(whisper_json_path),
            }

        payload: dict[str, object] = {
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "video" if is_video else "audio",
            "source_path": str(source_path),
            "source_name": source_path.name,
            "source_copy_path": str(source_copy),
            "title_hint": source_path.stem,
            "metadata_path": str(paths["metadata"]),
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "suggested_output_md": str(paths["notes_md"]),
            "suggested_output_html": str(paths["notes_html"]),
        }

        if args.prepare:
            prepare_payload = deps.run_prepare_for_transcript(
                transcript_path,
                bundle_dir=bundle_dir,
                refresh=args.refresh,
                source_hints=source_hints,
            )
            deps.attach_prepare_outputs(payload, prepare_payload, bundle_dir)

        transcription_duration_ms = deps.ms_since(command_started)
        prepare_ms = deps.extract_prepare_duration_ms(payload.get("prepare") if isinstance(payload.get("prepare"), dict) else None)
        state_payload = {
            "updated_at": datetime.now().isoformat(),
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "video" if is_video else "audio",
            "source_path": str(source_path),
            "source_name": source_path.name,
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
            "audio.ready",
            source_path=str(source_path),
            transcript_path=str(transcript_path),
            source_kind="video" if is_video else "audio",
            transcript_kind=transcript_source.get("kind") if isinstance(transcript_source, dict) else None,
            prepare=bool(args.prepare),
            prepare_reused=bool(payload.get("prepare", {}).get("reused")) if isinstance(payload.get("prepare"), dict) else False,
        )
        deps.finish_bundle_run(bundle_dir, run_context, status="source-ready")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        print(f"Bundle: {bundle_dir}")
        print(f"Title: {title}")
        print(f"Source: {audio_path}")
        print(f"Transcript: {transcript_path}")
        print(f"Suggested markdown: {paths['notes_md']}")
        print(f"Suggested HTML: {paths['notes_html']}")
        if args.prepare and "prepare" in payload:
            print(f"Work dir: {payload['prepare']['work_dir']}")
        return 0
    except Exception as exc:
        deps.finish_bundle_run(bundle_dir, run_context, status="failed", error=str(exc))
        raise


__all__ = ["AudioCommandDependencies", "cmd_audio"]
