from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path
from typing import Callable


SUMMARY_LINE_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")


def read_summary_points(summary_path: Path) -> list[str]:
    points: list[str] = []
    for raw_line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SUMMARY_LINE_RE.match(raw_line)
        if match:
            point = re.sub(r"\s+", " ", match.group(1)).strip()
            if point:
                points.append(point)
    if points:
        return points
    fallback = [
        re.sub(r"\s+", " ", line.strip())
        for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return fallback[:7]


def target_tldr_count(summary_files: list[Path], *, prepare_payload: dict | None = None) -> int:
    prepare_payload = prepare_payload or {}
    note_contract = prepare_payload.get("note_contract") if isinstance(prepare_payload.get("note_contract"), dict) else {}
    if isinstance(note_contract.get("tldr"), dict):
        min_items = int(note_contract["tldr"].get("min_items") or 0)
        max_items = int(note_contract["tldr"].get("max_items") or 0)
        if min_items and max_items:
            if len(summary_files) <= min_items:
                return min_items
            return max(min_items, min(max_items, len(summary_files) * 2))

    count = len(summary_files)
    if count <= 1:
        return 5
    if count == 2:
        return 7
    if count == 3:
        return 8
    if count == 4:
        return 9
    return 10


def build_tldr_deterministically(
    work_dir: Path,
    *,
    load_prepare_payload: Callable[[Path], dict],
    write_text: Callable[[Path, str], None],
    stage_sentinel_path: Callable[[Path, str], Path],
    write_stage_sentinel: Callable[[Path, dict], None],
    update_prepare_state_fields: Callable[[Path, dict], dict],
    bundle_dir_from_work_dir: Callable[[Path], Path | None],
    record_bundle_stage_metric: Callable[..., dict],
    read_summary_points_fn: Callable[[Path], list[str]] = read_summary_points,
    target_tldr_count_fn: Callable[..., int] = target_tldr_count,
) -> dict:
    summary_files = sorted(work_dir.glob("summary_chunk_*.md"))
    if not summary_files:
        raise FileNotFoundError(f"No summary_chunk_*.md files found in {work_dir}")

    prepare_payload = load_prepare_payload(work_dir)
    per_file_points = [read_summary_points_fn(path) for path in summary_files]
    target_count = target_tldr_count_fn(summary_files, prepare_payload=prepare_payload)
    chosen: list[str] = []
    seen: set[str] = set()
    offset = 0
    while len(chosen) < target_count:
        added = False
        for points in per_file_points:
            if offset >= len(points):
                continue
            point = points[offset].strip()
            key = re.sub(r"\s+", " ", point).casefold()
            if not point or key in seen:
                continue
            chosen.append(point)
            seen.add(key)
            added = True
            if len(chosen) >= target_count:
                break
        if not added:
            break
        offset += 1

    if not chosen:
        raise ValueError("Could not derive any TL;DR points from summary files")

    tldr_path = work_dir / "tldr.md"
    write_text(
        tldr_path,
        "\n".join(f"{index}. {point}" for index, point in enumerate(chosen, start=1)) + "\n",
    )

    sentinel_path_value = stage_sentinel_path(work_dir, "tldr")
    write_stage_sentinel(
        sentinel_path_value,
        {
            "stage": "tldr",
            "strategy": "deterministic-merge",
            "fingerprint": prepare_payload.get("fingerprint"),
            "output": "tldr.md",
            "completed": True,
            "completed_at": datetime.now().isoformat(),
            "summary_files": [path.name for path in summary_files],
            "count": len(chosen),
        },
    )
    update_prepare_state_fields(work_dir, {"stage_statuses": {"tldr": "ready"}})

    bundle_dir = bundle_dir_from_work_dir(work_dir)
    if bundle_dir is not None:
        record_bundle_stage_metric(
            bundle_dir,
            "tldr",
            0,
            strategy="deterministic-merge",
            summary_files=len(summary_files),
            output="tldr.md",
        )

    return {
        "work_dir": str(work_dir),
        "tldr_path": str(tldr_path),
        "strategy": "deterministic-merge",
        "summary_files": [str(path) for path in summary_files],
        "takeaways": len(chosen),
        "sentinel": str(sentinel_path_value),
    }


__all__ = [
    "SUMMARY_LINE_RE",
    "read_summary_points",
    "target_tldr_count",
    "build_tldr_deterministically",
]
