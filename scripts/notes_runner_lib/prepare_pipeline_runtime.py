from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .prepare_bundle_runtime import attach_prepare_outputs
from .prepare_transcript_runtime import (
    PrepareTranscriptDependencies,
    run_prepare_for_transcript,
)


@dataclass(frozen=True)
class PreparePipelineDependencies:
    transcript: PrepareTranscriptDependencies
    header_seed_filename: str
    ensure_dir: Callable[[Path, str], Path]
    build_status: Callable[[Path], dict]
    link_bundle_work_dir: Callable[[Path, Path], Path]
    clean_title: Callable[[str], str]
    is_informative_title: Callable[[str], bool]
    work_prompt_dir: Callable[[Path], Path]
    work_stage_dir: Callable[[Path], Path]
    record_bundle_stage_metric: Callable[..., None]


def run_prepare_and_attach(
    payload: dict[str, object],
    transcript_path: Path,
    bundle_dir: Path,
    *,
    refresh: bool = False,
    source_hints: dict | None = None,
    deps: PreparePipelineDependencies,
) -> dict:
    prepare_payload = run_prepare_for_transcript(
        transcript_path,
        bundle_dir=bundle_dir,
        refresh=refresh,
        source_hints=source_hints,
        deps=deps.transcript,
    )
    attach_prepare_outputs(
        payload,
        prepare_payload,
        bundle_dir,
        header_seed_filename=deps.header_seed_filename,
        ensure_dir=deps.ensure_dir,
        build_status=deps.build_status,
        link_bundle_work_dir=deps.link_bundle_work_dir,
        clean_title=deps.clean_title,
        is_informative_title=deps.is_informative_title,
        work_prompt_dir=deps.work_prompt_dir,
        work_stage_dir=deps.work_stage_dir,
        record_bundle_stage_metric=deps.record_bundle_stage_metric,
    )
    return prepare_payload


__all__ = [
    "PreparePipelineDependencies",
    "run_prepare_and_attach",
]