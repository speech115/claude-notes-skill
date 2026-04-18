from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class StatusCommandDependencies:
    ensure_dir: Callable[[Path, str], Path]
    build_status: Callable[[Path], dict]
    stdout: TextIO | None = None


def run_status_command(args: argparse.Namespace, *, deps: StatusCommandDependencies) -> int:
    work_dir = deps.ensure_dir(Path(args.work_dir), "Work directory")
    payload = deps.build_status(work_dir)
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    print(f"Work dir: {payload['work_dir']}", file=stdout)
    print(f"Next action: {payload['next_action']}", file=stdout)
    for name, exists in payload["exists"].items():
        print(f"- {name}: {'ready' if exists else 'missing'}", file=stdout)
    for name, count in payload["counts"].items():
        print(f"- {name}: {count}", file=stdout)
    return 0


@dataclass(frozen=True)
class TldrCommandDependencies:
    ensure_dir: Callable[[Path, str], Path]
    build_tldr_deterministically: Callable[[Path], dict]
    bundle_dir_from_work_dir: Callable[[Path], Path | None]
    record_bundle_stage_metric: Callable[..., object]
    ms_since: Callable[[float], int]
    stdout: TextIO | None = None


def run_build_tldr_command(args: argparse.Namespace, *, deps: TldrCommandDependencies) -> int:
    work_dir = deps.ensure_dir(Path(args.work_dir), "Work directory")
    started_at = time.monotonic()
    payload = deps.build_tldr_deterministically(work_dir)
    payload["duration_ms"] = deps.ms_since(started_at)
    bundle_dir = deps.bundle_dir_from_work_dir(work_dir)
    if bundle_dir is not None:
        deps.record_bundle_stage_metric(bundle_dir, "tldr", payload["duration_ms"], strategy="deterministic-merge")
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    print(f"TL;DR: {payload['tldr_path']}", file=stdout)
    return 0


@dataclass(frozen=True)
class ReplaceSpeakersCommandDependencies:
    ensure_dir: Callable[[Path, str], Path]
    replace_speakers: Callable[[Path], dict]
    stage_sentinel_path: Callable[[Path, str], Path]
    write_stage_sentinel: Callable[[Path, dict], None]
    bundle_dir_from_work_dir: Callable[[Path], Path | None]
    record_bundle_stage_metric: Callable[..., object]
    ms_since: Callable[[float], int]
    iso_now: Callable[[], str]
    stdout: TextIO | None = None


def run_replace_speakers_command(
    args: argparse.Namespace,
    *,
    deps: ReplaceSpeakersCommandDependencies,
) -> int:
    work_dir = deps.ensure_dir(Path(args.work_dir), "Work directory")
    started_at = time.monotonic()
    result = deps.replace_speakers(work_dir)
    if not result.get("skipped"):
        sentinel_path = deps.stage_sentinel_path(work_dir, "replace-speakers")
        deps.write_stage_sentinel(
            sentinel_path,
            {
                "stage": "replace-speakers",
                "completed": True,
                "completed_at": deps.iso_now(),
                "modified_files": result.get("modified"),
                "mappings": result.get("mappings"),
            },
        )
        result["sentinel"] = str(sentinel_path)
        bundle_dir = deps.bundle_dir_from_work_dir(work_dir)
        if bundle_dir is not None:
            deps.record_bundle_stage_metric(
                bundle_dir,
                "replace-speakers",
                deps.ms_since(started_at),
                modified_files=result.get("modified"),
                mappings=result.get("mappings"),
            )
    result["duration_ms"] = deps.ms_since(started_at)
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2), file=stdout)
        return 0
    if result.get("skipped"):
        print(result.get("reason", "skipped"), file=stdout)
    else:
        print(f"Replaced {result['mappings']} speaker labels in {result['modified']} files", file=stdout)
    return 0


@dataclass(frozen=True)
class AppendixCommandDependencies:
    ensure_dir: Callable[[Path, str], Path]
    merge_manifest_parts: Callable[[Path], Path | None]
    build_deterministic_appendix: Callable[[Path], Path]
    stdout: TextIO | None = None


def run_ensure_appendix_command(args: argparse.Namespace, *, deps: AppendixCommandDependencies) -> int:
    work_dir = deps.ensure_dir(Path(args.work_dir), "Work directory")
    merged_manifest = deps.merge_manifest_parts(work_dir)
    appendix_path = deps.build_deterministic_appendix(work_dir)
    payload = {
        "work_dir": str(work_dir),
        "appendix_path": str(appendix_path),
        "manifest_path": str(merged_manifest) if merged_manifest else None,
        "generated": True,
    }
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    print(appendix_path, file=stdout)
    return 0


__all__ = [
    "AppendixCommandDependencies",
    "ReplaceSpeakersCommandDependencies",
    "StatusCommandDependencies",
    "TldrCommandDependencies",
    "run_build_tldr_command",
    "run_ensure_appendix_command",
    "run_replace_speakers_command",
    "run_status_command",
]
