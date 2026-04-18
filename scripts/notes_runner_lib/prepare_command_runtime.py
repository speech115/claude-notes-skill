from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class PrepareCommandDependencies:
    ensure_file: Callable[[Path, str], Path]
    run_prepare_logic: Callable[[list[Path]], dict]
    load_prepare_payload: Callable[[Path], dict]
    stdout: TextIO | None = None


def run_prepare_command(args: argparse.Namespace, *, deps: PrepareCommandDependencies) -> int:
    files = [deps.ensure_file(Path(item), "Transcript file") for item in args.files]
    result = deps.run_prepare_logic(files)
    work_dir = Path(result["work_dir"])
    payload = deps.load_prepare_payload(work_dir)
    stdout = deps.stdout if deps.stdout is not None else sys.stdout

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    print(f"Work dir: {payload['work_dir']}", file=stdout)
    print(f"Files: {payload['files']}", file=stdout)
    print(f"Lines: {payload['total_lines']}", file=stdout)
    print(f"Chunks: {payload['total_chunks']}", file=stdout)
    print(f"Speakers: {payload['unique_speakers']}", file=stdout)
    print(f"Duration: {payload['duration_estimate']}", file=stdout)
    return 0


cmd_prepare = run_prepare_command


__all__ = ["PrepareCommandDependencies", "cmd_prepare", "run_prepare_command"]
