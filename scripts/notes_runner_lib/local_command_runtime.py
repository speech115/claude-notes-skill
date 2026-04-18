from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class LocalCommandDependencies:
    ensure_file: Callable[[Path, str], Path]
    file_looks_binary: Callable[[Path], bool]
    ensure_parent_dir: Callable[[Path], Path]
    infer_local_title: Callable[[Path], str]
    local_bundle_dir_for: Callable[[Path, str, Path], Path]
    bundle_paths: Callable[[Path], dict[str, Path]]
    start_bundle_run: Callable[..., dict]
    copy_local_source: Callable[[Path, Path], Path]
    write_text: Callable[[Path, str], None]
    write_json: Callable[[Path, object], None]
    normalize_transcript_text: Callable[[str], str]
    read_text_file: Callable[[Path], str]
    run_prepare_for_transcript: Callable[..., dict]
    attach_prepare_outputs: Callable[[dict[str, object], dict, Path], None]
    extract_prepare_duration_ms: Callable[[dict | None], int]
    write_bundle_state_snapshot: Callable[[Path, dict], dict]
    append_trace_event: Callable[..., object]
    finish_bundle_run: Callable[..., object]
    ms_since: Callable[[float], int]
    audio_extensions: set[str] | frozenset[str] = field(default_factory=frozenset)
    video_extensions: set[str] | frozenset[str] = field(default_factory=frozenset)
    stdout: TextIO | None = None


def run_local_command(args: argparse.Namespace, *, deps: LocalCommandDependencies) -> int:
    command_started = time.monotonic()
    source_path = deps.ensure_file(Path(args.path), "Source file")
    source_extension = source_path.suffix.lower()
    if source_extension in (deps.audio_extensions | deps.video_extensions):
        raise ValueError(
            f"Local mode only accepts text/markdown files. Received media file: {source_path.name}. "
            "Use `notes-runner audio ...` or `notes-runner auto ...` instead."
        )
    if deps.file_looks_binary(source_path):
        raise ValueError(
            f"Local mode only accepts text/markdown files. File appears to be binary: {source_path}"
        )

    output_root = deps.ensure_parent_dir(Path(args.output_root))
    title = args.title if getattr(args, "title", None) else deps.infer_local_title(source_path)
    bundle_dir = deps.local_bundle_dir_for(source_path, title, output_root)
    bundle_dir.mkdir(parents=True, exist_ok=True)
    paths = deps.bundle_paths(bundle_dir)
    run_context = deps.start_bundle_run(
        bundle_dir,
        command="local",
        state_seed={
            "source_kind": "local",
            "source_path": str(source_path),
            "title": title,
        },
    )
    stdout = deps.stdout

    try:
        source_copy = deps.copy_local_source(source_path, bundle_dir)
        deps.write_text(paths["source_file"], str(source_path) + "\n")
        deps.write_json(
            paths["metadata"],
            {
                "title": title,
                "source_path": str(source_path),
                "source_name": source_path.name,
                "source_extension": source_extension,
            },
        )

        transcript_path = paths["transcript"]
        if args.refresh or not transcript_path.is_file():
            deps.write_text(
                transcript_path,
                deps.normalize_transcript_text(deps.read_text_file(source_path)),
            )

        transcript_source = {
            "kind": "local-file",
            "path": str(source_path),
        }
        payload: dict[str, object] = {
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "local",
            "source_path": str(source_path),
            "source_name": source_path.name,
            "source_copy_path": str(source_copy),
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
            )
            deps.attach_prepare_outputs(payload, prepare_payload, bundle_dir)

        source_acquisition_ms = deps.ms_since(command_started)
        prepare_ms = deps.extract_prepare_duration_ms(
            payload.get("prepare") if isinstance(payload.get("prepare"), dict) else None
        )
        state_payload = {
            "updated_at": datetime.now().isoformat(),
            "bundle_dir": str(bundle_dir),
            "title": title,
            "source_kind": "local",
            "source_path": str(source_path),
            "source_name": source_path.name,
            "transcript_path": str(transcript_path),
            "transcript_source": transcript_source,
            "telemetry": {
                "source_acquisition_ms": source_acquisition_ms,
                "prepare_ms": prepare_ms,
                "prepare_reused": bool(payload.get("prepare", {}).get("reused"))
                if isinstance(payload.get("prepare"), dict)
                else False,
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
            "local.ready",
            source_path=str(source_path),
            transcript_path=str(transcript_path),
            prepare=bool(args.prepare),
            prepare_reused=bool(payload.get("prepare", {}).get("reused"))
            if isinstance(payload.get("prepare"), dict)
            else False,
        )
        deps.finish_bundle_run(bundle_dir, run_context, status="source-ready")

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
            return 0

        print(f"Bundle: {bundle_dir}", file=stdout)
        print(f"Title: {title}", file=stdout)
        print(f"Source: {source_path}", file=stdout)
        print(f"Transcript: {transcript_path}", file=stdout)
        print(f"Suggested markdown: {paths['notes_md']}", file=stdout)
        print(f"Suggested HTML: {paths['notes_html']}", file=stdout)
        if args.prepare and "prepare" in payload:
            print(f"Work dir: {payload['prepare']['work_dir']}", file=stdout)
        return 0
    except Exception as exc:
        deps.finish_bundle_run(bundle_dir, run_context, status="failed", error=str(exc))
        raise


cmd_local = run_local_command


__all__ = ["LocalCommandDependencies", "cmd_local", "run_local_command"]
