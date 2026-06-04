from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path

from .prepare_runtime import (
    build_chunk_statuses,
    build_execution_plan,
    build_stage_statuses,
    find_prepare_state_path,
    load_prepare_payload,
    note_contract_path,
    quality_checks_path,
)
from .run_runtime import bundle_dir_from_work_dir, load_bundle_state, timeline_path_for_dir, trace_path_for_dir

PROMPT_PACK_DIRNAME = "prompts"
STAGE_STATE_DIRNAME = "stages"
HEADER_SEED_FILENAME = "header-seed.json"


def _parse_iso_datetime(value: object) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_iso_z(value: datetime) -> str:
    return value.astimezone(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z"


def _load_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _external_extraction_timing(work_dir: Path, chunk_statuses: dict) -> dict | None:
    chunks: dict[str, dict] = {}
    starts: list[datetime] = []
    completions: list[datetime] = []
    for chunk_id, status in sorted(chunk_statuses.items()):
        if not isinstance(status, dict):
            continue
        sentinel_value = str(status.get("sentinel") or "").strip()
        sentinel_path = Path(sentinel_value) if sentinel_value else work_dir / STAGE_STATE_DIRNAME / f"extraction-{chunk_id}.json"
        sentinel = _load_json_file(sentinel_path)
        if not sentinel:
            continue
        started_at = _parse_iso_datetime(sentinel.get("started_at"))
        completed_at = _parse_iso_datetime(sentinel.get("completed_at"))
        chunk_payload: dict[str, object] = {}
        if started_at is not None:
            starts.append(started_at)
            chunk_payload["started_at"] = _format_iso_z(started_at)
        if completed_at is not None:
            completions.append(completed_at)
            chunk_payload["completed_at"] = _format_iso_z(completed_at)
        if started_at is not None and completed_at is not None:
            chunk_payload["duration_ms"] = max(0, int((completed_at - started_at).total_seconds() * 1000))
        if chunk_payload:
            chunks[str(chunk_id)] = chunk_payload
    if not chunks:
        return None
    payload: dict[str, object] = {"chunks": chunks}
    if starts:
        payload["started_at"] = _format_iso_z(min(starts))
    if completions:
        payload["completed_at"] = _format_iso_z(max(completions))
    if starts and completions:
        payload["duration_ms"] = max(0, int((max(completions) - min(starts)).total_seconds() * 1000))
    return payload


def build_status_payload(work_dir: Path) -> dict:
    prepare_payload = load_prepare_payload(work_dir)
    bundle_dir = bundle_dir_from_work_dir(work_dir)
    bundle_state = load_bundle_state(bundle_dir) if bundle_dir else {}
    block_files = sorted(work_dir.glob("chunk_*_block_*.md"))
    manifest_parts = sorted(work_dir.glob("manifest_chunk_*.tsv"))
    outputs = sorted(work_dir.glob("*.html"))
    markdown_outputs = sorted(work_dir.glob("*.md"))
    chunk_plan = prepare_payload.get("chunk_plan", [])
    if not isinstance(chunk_plan, list):
        chunk_plan = []
    chunk_statuses = build_chunk_statuses(work_dir, chunk_plan)
    stages = build_stage_statuses(work_dir, prepare_payload, chunk_statuses)
    stage_statuses = {
        "speaker_identification": stages["speaker_identification"]["status"],
        "extraction": stages["extraction"]["status"],
        "tldr": stages["tldr"]["status"],
        "assemble": stages["assemble"]["status"],
    }
    telemetry = dict(prepare_payload.get("telemetry", {}) if isinstance(prepare_payload.get("telemetry"), dict) else {})
    extraction_timing = _external_extraction_timing(work_dir, chunk_statuses)
    if extraction_timing:
        telemetry.setdefault("external_stages", {})["extraction"] = extraction_timing

    payload = {
        "work_dir": str(work_dir),
        "fingerprint": prepare_payload.get("fingerprint"),
        "execution_mode": prepare_payload.get("execution_mode"),
        "content_mode": prepare_payload.get("content_mode"),
        "chunk_plan": chunk_plan,
        "chunk_statuses": chunk_statuses,
        "stage_hints": prepare_payload.get("stage_hints", {}),
        "stage_statuses": stage_statuses,
        "stages": stages,
        "prompt_packs": prepare_payload.get("prompt_packs", {}),
        "header_seed": prepare_payload.get("header_seed", {}),
        "note_contract": prepare_payload.get("note_contract", {}),
        "quality_checks": prepare_payload.get("quality_checks", {}),
        "title_candidates": prepare_payload.get("title_candidates", []),
        "telemetry": telemetry,
        "trace_path": str(trace_path_for_dir(work_dir)),
        "bundle_trace_path": str(trace_path_for_dir(bundle_dir)) if bundle_dir else None,
        "note_id": bundle_state.get("note_id"),
        "bundle_timeline_path": str(timeline_path_for_dir(bundle_dir)) if bundle_dir else None,
        "bundle_latest_run_id": bundle_state.get("latest_run_id"),
        "bundle_latest_status": bundle_state.get("latest_status"),
        "bundle_latest_run_snapshot": bundle_state.get("latest_run_snapshot"),
        "next_action": None,
        "counts": {
            "block_files": len(block_files),
            "manifest_parts": len(manifest_parts),
            "html_outputs": len(outputs),
            "markdown_outputs": len(markdown_outputs),
        },
        "exists": {
            "prepare_report": (work_dir / "prepare_report.txt").exists(),
            "prepare_state": find_prepare_state_path(work_dir) is not None,
            "prescan_context": (work_dir / "prescan_context.txt").exists(),
            "header": (work_dir / "header.md").exists(),
            "header_seed": (work_dir / HEADER_SEED_FILENAME).exists(),
            "tldr": (work_dir / "tldr.md").exists(),
            "appendix": (work_dir / "appendix.md").exists(),
            "merged_manifest": (work_dir / "manifest.tsv").exists(),
            "prompt_pack_dir": (work_dir / PROMPT_PACK_DIRNAME).is_dir(),
            "stage_dir": (work_dir / STAGE_STATE_DIRNAME).is_dir(),
            "note_contract": note_contract_path(work_dir).is_file(),
            "quality_checks": quality_checks_path(work_dir).is_file(),
        },
    }
    payload["execution_plan"] = build_execution_plan(prepare_payload, chunk_statuses, stages)
    payload["next_action"] = payload["execution_plan"]["next_action"]
    return payload
