from __future__ import annotations

import argparse
import html
import io
import json
import os
import sys
from pathlib import Path
from typing import Callable, Iterable

TEXT_EXTENSIONS = {".md", ".txt"}


def _normalize_extensions(values: Iterable[str]) -> set[str]:
    return {str(value).lower() for value in values}


def _capture_json_command(
    command: Callable[[argparse.Namespace], int],
    command_args: argparse.Namespace,
) -> dict:
    old_stdout = sys.stdout
    stdout_buffer = io.StringIO()
    sys.stdout = stdout_buffer
    try:
        command(command_args)
    finally:
        sys.stdout = old_stdout
    return json.loads(stdout_buffer.getvalue())


def process_batch_file(
    file_path: Path,
    args: argparse.Namespace,
    *,
    cmd_local: Callable[[argparse.Namespace], int],
    cmd_audio: Callable[[argparse.Namespace], int],
    text_extensions: Iterable[str] = TEXT_EXTENSIONS,
    audio_extensions: Iterable[str],
    video_extensions: Iterable[str],
    namespace_factory: Callable[..., argparse.Namespace] = argparse.Namespace,
) -> dict:
    """Run the correct batch sub-command for a single file and return parsed JSON."""
    text_exts = _normalize_extensions(text_extensions)
    audio_exts = _normalize_extensions(audio_extensions)
    video_exts = _normalize_extensions(video_extensions)
    file_ext = file_path.suffix.lower()

    sub_args = namespace_factory(
        path=str(file_path),
        output_root=str(args.output_root),
        title=None,
        prepare=args.prepare,
        refresh=args.refresh,
        json=True,
    )

    if file_ext in text_exts:
        return _capture_json_command(cmd_local, sub_args)

    if file_ext in (audio_exts | video_exts):
        sub_args.model = args.model
        sub_args.language = args.language
        sub_args.transcribe_backend = args.transcribe_backend
        sub_args.diarize = False
        return _capture_json_command(cmd_audio, sub_args)

    raise ValueError(f"Unsupported batch file: {file_path}")


def write_batch_indexes(
    output_root: Path,
    results: list[dict],
    *,
    write_json: Callable[[Path, dict], None],
    write_text: Callable[[Path, str], None],
    html_glob: Callable[[Path], list[Path]] | None = None,
) -> dict[str, object]:
    """Write batch-index.json and batch-index.html using the current batch format."""
    total = len(results)
    ok = sum(1 for result in results if result.get("status") == "ok")
    failed = total - ok

    index_path = output_root / "batch-index.json"
    write_json(index_path, {"files": results, "total": total, "ok": ok})

    html_index_path = output_root / "batch-index.html"
    ok_results = [result for result in results if result.get("status") == "ok"]
    if ok_results:
        html_lines = [
            "<!DOCTYPE html><html><head><meta charset='utf-8'>",
            "<title>Course Notes Index</title>",
            "<style>body{font-family:system-ui;max-width:800px;margin:2em auto;padding:0 1em}",
            "a{color:#2563eb;text-decoration:none}a:hover{text-decoration:underline}",
            "li{margin:0.5em 0}.meta{color:#666;font-size:0.85em}</style></head>",
            "<body><h1>Course Notes</h1><ol>",
        ]
        for result in ok_results:
            title = result.get("title", result.get("file", "Unknown"))
            bundle_dir = Path(str(result.get("bundle_dir") or ""))
            html_candidates = (
                html_glob(bundle_dir)
                if html_glob is not None
                else sorted(bundle_dir.glob("*.html"))
            )
            html_path = html_candidates[0] if html_candidates else None
            if html_path is not None:
                rel_path = os.path.relpath(html_path, output_root)
                html_lines.append(f'<li><a href="{rel_path}">{html.escape(str(title))}</a></li>')
            else:
                html_lines.append(
                    f"<li>{html.escape(str(title))} <span class='meta'>(no HTML)</span></li>"
                )
        html_lines.append("</ol></body></html>")
        write_text(html_index_path, "\n".join(html_lines))
    else:
        html_index_path = None

    return {
        "index_path": index_path,
        "html_index_path": html_index_path,
        "ok": ok,
        "failed": failed,
    }


__all__ = ["TEXT_EXTENSIONS", "process_batch_file", "write_batch_indexes"]
