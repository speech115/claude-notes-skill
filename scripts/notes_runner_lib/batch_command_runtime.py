from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Iterable, TextIO


@dataclass(frozen=True)
class BatchCommandDependencies:
    ensure_parent_dir: Callable[[Path], Path]
    append_trace_event: Callable[..., Path]
    process_batch_file: Callable[..., dict]
    write_batch_indexes: Callable[..., dict[str, object]]
    cmd_local: Callable[[argparse.Namespace], int]
    cmd_audio: Callable[[argparse.Namespace], int]
    audio_extensions: set[str] | frozenset[str]
    video_extensions: set[str] | frozenset[str]
    text_extensions: Iterable[str]
    write_json: Callable[[Path, object], None]
    write_text: Callable[[Path, str], None]
    stdout: TextIO | None = None
    stderr: TextIO | None = None


def run_batch_command(args: argparse.Namespace, *, deps: BatchCommandDependencies) -> int:
    """Process all supported files in a directory."""
    directory = Path(args.directory).expanduser().resolve()
    if not directory.is_dir():
        raise FileNotFoundError(f"Directory not found: {directory}")
    output_root = deps.ensure_parent_dir(Path(args.output_root))
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    stderr = deps.stderr if deps.stderr is not None else sys.stderr

    supported = deps.audio_extensions | deps.video_extensions | set(deps.text_extensions)
    files = sorted(
        file_path for file_path in directory.iterdir()
        if file_path.is_file() and file_path.suffix.lower() in supported
    )
    if not files:
        print(f"No supported files found in {directory}", file=stderr)
        return 1

    results: list[dict] = []
    total = len(files)
    batch_trace_path = deps.append_trace_event(
        output_root,
        "batch.started",
        directory=str(directory),
        total=total,
    )
    for position, file_path in enumerate(files, 1):
        label = file_path.name
        print(f"[{position}/{total}] {label}...", file=stderr)
        deps.append_trace_event(
            output_root,
            "batch.file.started",
            file=label,
            position=position,
            total=total,
        )

        try:
            result = deps.process_batch_file(
                file_path,
                args,
                audio_extensions=deps.audio_extensions,
                video_extensions=deps.video_extensions,
                text_extensions=deps.text_extensions,
                cmd_local=deps.cmd_local,
                cmd_audio=deps.cmd_audio,
            )
            results.append({"file": label, "status": "ok", **result})
            deps.append_trace_event(
                output_root,
                "batch.file.completed",
                file=label,
                status="ok",
                bundle_dir=result.get("bundle_dir"),
                trace_path=result.get("trace_path"),
            )
            print(f"  ✓ {result.get('bundle_dir', 'done')}", file=stderr)
        except Exception as exc:
            results.append({"file": label, "status": "error", "error": str(exc)})
            deps.append_trace_event(
                output_root,
                "batch.file.failed",
                file=label,
                status="error",
                error=str(exc),
            )
            print(f"  ✗ {exc}", file=stderr)

    batch_index = deps.write_batch_indexes(
        output_root,
        results,
        write_json=deps.write_json,
        write_text=deps.write_text,
    )
    ok = batch_index["ok"]
    failed = batch_index["failed"]
    index_path = batch_index["index_path"]
    html_index_path = batch_index["html_index_path"]
    if html_index_path is not None and not args.json:
        print(f"HTML index: {html_index_path}", file=stdout)

    deps.append_trace_event(
        output_root,
        "batch.completed",
        total=total,
        ok=ok,
        failed=failed,
        index=str(index_path),
        trace_path=str(batch_trace_path),
    )
    exit_code = 0 if ok > 0 else 1
    if args.json:
        print(
            json.dumps(
                {
                    "results": results,
                    "index": str(index_path),
                    "trace_path": str(batch_trace_path),
                    "ok": ok,
                    "failed": failed,
                },
                ensure_ascii=False,
                indent=2,
            ),
            file=stdout,
        )
    else:
        print(f"\nBatch complete: {ok}/{total} succeeded. Index: {index_path}", file=stdout)
    return exit_code


cmd_batch = run_batch_command


__all__ = ["BatchCommandDependencies", "cmd_batch", "run_batch_command"]
