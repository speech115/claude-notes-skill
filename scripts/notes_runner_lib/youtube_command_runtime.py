from __future__ import annotations

import argparse
import json
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path


def run_youtube_command(
    args: argparse.Namespace,
    *,
    ensure_parent_dir: Callable[[Path], Path],
    find_existing_youtube_bundle: Callable[[Path, str], Path | None],
    load_bundle_metadata: Callable[[Path | None], dict | None],
    extract_youtube_metadata: Callable[[str], dict],
    bundle_dir_for: Callable[[dict, Path], Path],
    bundle_paths: Callable[[Path], dict[str, Path]],
    start_bundle_run: Callable[..., dict],
    write_json: Callable[[Path, object], None],
    write_text: Callable[[Path, str], None],
    extract_youtube_chapters: Callable[[dict], list[dict]],
    build_youtube_source_hints: Callable[[dict], dict],
    try_youtube_transcript_api: Callable[[str, int | None], tuple[list[dict], str | None, str | None]],
    transcript_markdown_from_cues: Callable[[list[dict]], str],
    select_best_subtitle: Callable[[Path, int | None], tuple[Path | None, list[dict], str | None]],
    download_subtitles: Callable[[str, Path], str | None],
    choose_transcribe_backend: Callable[[str], str],
    normalize_language_hint: Callable[[str], str | None],
    download_audio: Callable[[str, Path], Path],
    call_groq_transcribe: Callable[..., dict],
    advanced_setup_message: Callable[[str, str | None], str],
    groq_payload_to_transcript_markdown: Callable[[dict], str],
    run_prepare_for_transcript: Callable[..., dict],
    attach_prepare_outputs: Callable[[dict[str, object], dict, Path], None],
    extract_prepare_duration_ms: Callable[[dict | None], int],
    write_bundle_state_snapshot: Callable[[Path, dict], dict],
    append_trace_event: Callable[..., object],
    finish_bundle_run: Callable[..., object],
    ms_since: Callable[[float], int],
) -> int:
    command_started = time.monotonic()
    output_root = ensure_parent_dir(Path(args.output_root))
    existing_bundle = None if args.refresh else find_existing_youtube_bundle(output_root, args.url)
    metadata = load_bundle_metadata(existing_bundle) if existing_bundle is not None else None
    if metadata is None:
        metadata = extract_youtube_metadata(args.url)
    bundle_dir = existing_bundle or bundle_dir_for(metadata, output_root)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    paths = bundle_paths(bundle_dir)
    paths["subs_dir"].mkdir(parents=True, exist_ok=True)
    paths["audio_dir"].mkdir(parents=True, exist_ok=True)
    run_context = start_bundle_run(
        bundle_dir,
        command="youtube",
        state_seed={
            "source_kind": "youtube",
            "source_url": args.url,
            "video_id": metadata.get("id"),
            "title": metadata.get("title"),
        },
    )

    try:
        write_json(paths["metadata"], metadata)
        write_text(paths["source_url"], args.url + "\n")

        chapters = extract_youtube_chapters(metadata)
        source_hints = build_youtube_source_hints(metadata)
        chapters_path = bundle_dir / "chapters.json"
        if chapters:
            write_json(chapters_path, {"chapters": chapters})

        duration_seconds = metadata.get("duration")
        duration_value = int(duration_seconds) if isinstance(duration_seconds, (int, float)) else None
        transcript_source: dict[str, object]
        audio_path: Path | None = None
        transcript_path = paths["transcript"]
        warnings: list[str] = []
        metadata_warning = str(metadata.pop("_metadata_warning", "") or "").strip()
        if metadata_warning:
            warnings.append(metadata_warning)

        if transcript_path.is_file() and not args.refresh:
            transcript_source = {
                "kind": "existing",
                "path": str(transcript_path),
            }
        else:
            video_id = str(metadata.get("id") or "").strip()
            api_cues, api_language, api_error = ([], None, "no video_id")
            if video_id:
                api_cues, api_language, api_error = try_youtube_transcript_api(video_id, duration_value)

            if api_cues and api_error is None:
                write_text(transcript_path, transcript_markdown_from_cues(api_cues))
                transcript_source = {
                    "kind": "youtube-transcript-api",
                    "language": api_language,
                }
            else:
                if api_error:
                    warnings.append(f"youtube-transcript-api: {api_error}")
                subtitle_path, cues, subtitle_language = select_best_subtitle(paths["subs_dir"], duration_value)
                if subtitle_path is None or args.refresh:
                    subtitle_error = download_subtitles(args.url, paths["subs_dir"])
                    if subtitle_error:
                        warnings.append(subtitle_error)
                    subtitle_path, cues, subtitle_language = select_best_subtitle(paths["subs_dir"], duration_value)

                if subtitle_path is not None and cues:
                    write_text(transcript_path, transcript_markdown_from_cues(cues))
                    transcript_source = {
                        "kind": "subtitles",
                        "path": str(subtitle_path),
                        "language": subtitle_language,
                    }
                else:
                    try:
                        backend = choose_transcribe_backend(args.transcribe_backend)
                        language_hint = normalize_language_hint(args.language)
                        if not language_hint and subtitle_language in {"en", "ru"}:
                            language_hint = subtitle_language
                        audio_matches = sorted(paths["audio_dir"].glob("source.*"))
                        audio_path = audio_matches[0] if audio_matches and not args.refresh else None
                        if audio_path is None:
                            audio_path = download_audio(args.url, paths["audio_dir"])
                        if backend == "groq":
                            raw_payload = call_groq_transcribe(
                                audio_path,
                                paths["raw_transcript"],
                                language=language_hint,
                            )
                        else:
                            raise ValueError(f"Unsupported transcription backend: {backend}")
                    except FileNotFoundError as exc:
                        raise FileNotFoundError(
                            advanced_setup_message(
                                "YouTube transcription fallback",
                                "Starter mode only supports videos with subtitles/autosubs. To process subtitle-free videos, configure NOTES_RUNNER_TRANSCRIBE_CLI and a transcription backend",
                            )
                        ) from exc
                    except ValueError as exc:
                        if "No transcription API key available" in str(exc):
                            raise ValueError(
                                advanced_setup_message(
                                    "YouTube transcription fallback",
                                    "Set OPENAI_API_KEY or DEEPGRAM_API_KEY to use API transcription when subtitles are missing",
                                )
                            ) from exc
                        raise
                    if backend == "groq":
                        write_text(transcript_path, groq_payload_to_transcript_markdown(raw_payload))
                    else:
                        raise ValueError(f"Unsupported transcription backend: {backend}")
                    transcript_source = {
                        "kind": "api",
                        "backend": backend,
                        "model": {"groq": "whisper-large-v3-turbo"}.get(backend, backend),
                        "path": str(paths["raw_transcript"]),
                        "language": language_hint or "auto",
                    }

        transcript_acquisition_ms = ms_since(command_started)
        title = str(metadata.get("title") or metadata.get("id") or "YouTube notes")
        payload: dict[str, object] = {
            "bundle_dir": str(bundle_dir),
            "title": title,
            "video_id": metadata.get("id"),
            "source_url": args.url,
            "metadata_path": str(paths["metadata"]),
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "audio_path": str(audio_path) if audio_path else None,
            "suggested_output_md": str(paths["notes_md"]),
            "suggested_output_html": str(paths["notes_html"]),
            "source_identity": source_hints,
        }
        if warnings:
            payload["warnings"] = warnings
        if chapters:
            payload["chapters"] = chapters
            payload["chapters_path"] = str(chapters_path)

        if args.prepare:
            prepare_payload = run_prepare_for_transcript(
                transcript_path,
                bundle_dir=bundle_dir,
                refresh=args.refresh,
                source_hints=source_hints,
            )
            attach_prepare_outputs(payload, prepare_payload, bundle_dir)

        prepare_ms = extract_prepare_duration_ms(payload.get("prepare") if isinstance(payload.get("prepare"), dict) else None)
        state_payload = {
            "updated_at": datetime.now().isoformat(),
            "bundle_dir": str(bundle_dir),
            "title": title,
            "video_id": metadata.get("id"),
            "source_kind": "youtube",
            "source_url": args.url,
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "audio_path": str(audio_path) if audio_path else None,
            "source_identity": source_hints,
            "telemetry": {
                "transcript_acquisition_ms": transcript_acquisition_ms,
                "prepare_ms": prepare_ms,
                "prepare_reused": bool(payload.get("prepare", {}).get("reused")) if isinstance(payload.get("prepare"), dict) else False,
                "warnings": len(warnings),
            },
        }
        if warnings:
            state_payload["warnings"] = warnings
        if chapters:
            state_payload["chapters_count"] = len(chapters)
        if "prepare" in payload:
            state_payload["prepare"] = payload["prepare"]
        state_payload["trace_path"] = str(paths["trace"])
        state_payload = write_bundle_state_snapshot(bundle_dir, state_payload)
        payload["trace_path"] = str(paths["trace"])
        payload["note_id"] = state_payload["note_id"]
        append_trace_event(
            bundle_dir,
            "youtube.ready",
            source_url=args.url,
            transcript_path=str(transcript_path),
            transcript_kind=transcript_source.get("kind") if isinstance(transcript_source, dict) else None,
            prepare=bool(args.prepare),
            prepare_reused=bool(payload.get("prepare", {}).get("reused")) if isinstance(payload.get("prepare"), dict) else False,
            warnings=len(warnings),
        )
        finish_bundle_run(bundle_dir, run_context, status="source-ready")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        print(f"Bundle: {bundle_dir}")
        print(f"Title: {title}")
        print(f"Transcript: {transcript_path}")
        print(f"Transcript source: {transcript_source}")
        print(f"Suggested markdown: {paths['notes_md']}")
        print(f"Suggested HTML: {paths['notes_html']}")
        if args.prepare and "prepare" in payload:
            print(f"Work dir: {payload['prepare']['work_dir']}")
        return 0
    except Exception as exc:
        finish_bundle_run(bundle_dir, run_context, status="failed", error=str(exc))
        raise


__all__ = ["run_youtube_command"]
