from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PrepareTranscriptDependencies:
    resolve_bundle_work_dir: Callable[[Path], Path | None]
    load_prepare_payload: Callable[[Path], dict]
    prepare_fingerprint_for_files: Callable[[list[Path]], tuple[list[object], str]]
    run_prepare_logic: Callable[..., dict]
    enrich_work_dir_with_source_hints: Callable[[Path, dict | None], None]


def load_reusable_prepare_payload(
    bundle_dir: Path,
    transcript_path: Path,
    *,
    deps: PrepareTranscriptDependencies,
) -> dict | None:
    work_dir = deps.resolve_bundle_work_dir(bundle_dir)
    if work_dir is None:
        return None

    try:
        payload = deps.load_prepare_payload(work_dir)
    except (FileNotFoundError, json.JSONDecodeError, ValueError):
        return None

    _, fingerprint = deps.prepare_fingerprint_for_files([transcript_path])
    if str(payload.get("fingerprint") or "").strip() != fingerprint:
        return None

    payload["work_dir"] = str(work_dir)
    payload["reused"] = True
    return payload


def run_prepare_for_transcript(
    transcript_path: Path,
    *,
    bundle_dir: Path | None = None,
    refresh: bool = False,
    source_hints: dict | None = None,
    deps: PrepareTranscriptDependencies,
) -> dict:
    if bundle_dir is not None and not refresh:
        reused = load_reusable_prepare_payload(bundle_dir, transcript_path, deps=deps)
        if reused is not None:
            work_dir = Path(reused["work_dir"]).resolve()
            if source_hints:
                deps.enrich_work_dir_with_source_hints(work_dir, source_hints)
                refreshed = deps.load_prepare_payload(work_dir)
                refreshed["work_dir"] = str(work_dir)
                refreshed["reused"] = True
                return refreshed
            return reused

    result = deps.run_prepare_logic([transcript_path], source_hints=source_hints)
    work_dir = Path(result["work_dir"]).resolve()
    if source_hints:
        deps.enrich_work_dir_with_source_hints(work_dir, source_hints)
    payload = deps.load_prepare_payload(work_dir)
    payload["work_dir"] = str(work_dir)
    payload["reused"] = False
    return payload


__all__ = [
    "PrepareTranscriptDependencies",
    "load_reusable_prepare_payload",
    "run_prepare_for_transcript",
]
