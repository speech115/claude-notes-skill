from __future__ import annotations

import argparse
from collections.abc import Callable, Collection
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class AutoCommandDependencies:
    is_youtube_url: Callable[[str], bool]
    cmd_youtube: Callable[[argparse.Namespace], int]
    cmd_audio: Callable[[argparse.Namespace], int]
    cmd_local: Callable[[argparse.Namespace], int]
    audio_extensions: Collection[str]
    video_extensions: Collection[str]


def _ensure_default(args: argparse.Namespace, name: str, value: object) -> None:
    if not hasattr(args, name):
        setattr(args, name, value)


def run_auto_command(args: argparse.Namespace, *, deps: AutoCommandDependencies) -> int:
    """Auto-detect input type and route to the appropriate command."""
    input_value = args.input

    if deps.is_youtube_url(input_value):
        args.url = input_value
        args.command = "youtube"
        _ensure_default(args, "refresh", False)
        _ensure_default(args, "transcribe_backend", "auto")
        return deps.cmd_youtube(args)

    file_path = Path(input_value).expanduser().resolve()
    if not file_path.is_file():
        raise FileNotFoundError(f"Input file not found: {file_path}")

    args.path = str(file_path)
    args.command = "local"
    _ensure_default(args, "refresh", False)

    if file_path.suffix.lower() in deps.audio_extensions or file_path.suffix.lower() in deps.video_extensions:
        args.command = "audio"
        return deps.cmd_audio(args)

    return deps.cmd_local(args)
