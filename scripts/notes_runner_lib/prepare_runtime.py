from __future__ import annotations

import re
from pathlib import Path

from .common import load_json_if_exists

PREPARE_STATE_FILENAMES = ("prepare_state.json",)
PREPARE_PLAN_FILENAMES = ("prepare_plan.json",)
CHUNK_BLOCK_PATTERN = re.compile(r"^chunk_([A-Za-z0-9]+)_block_\d+\.md$")
MANIFEST_PATTERN = re.compile(r"^manifest_chunk_([A-Za-z0-9]+)\.tsv$")
STAGE_STATE_DIRNAME = "stages"
NOTE_CONTRACT_FILENAME = "note-contract.json"
QUALITY_CHECKS_FILENAME = "quality-checks.json"


def note_contract_path(work_dir: Path) -> Path:
    return work_dir / NOTE_CONTRACT_FILENAME


def quality_checks_path(work_dir: Path) -> Path:
    return work_dir / QUALITY_CHECKS_FILENAME


def work_stage_dir(work_dir: Path, *, create: bool = False) -> Path:
    path = work_dir / STAGE_STATE_DIRNAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def stage_sentinel_path(work_dir: Path, stage_name: str, *, chunk_id: str | None = None) -> Path:
    suffix = f"{stage_name}-{chunk_id}.json" if chunk_id else f"{stage_name}.json"
    return work_stage_dir(work_dir, create=True) / suffix


def load_stage_sentinel(path: Path) -> dict | None:
    payload = load_json_if_exists(path)
    return payload if isinstance(payload, dict) else None


def execution_mode_for_plan(total_chunks: int, *, content_mode: str, duration_seconds: int = 0) -> str:
    if total_chunks <= 1:
        return "single"
    if content_mode == "monologue":
        if duration_seconds and duration_seconds <= 18 * 60 and total_chunks <= 2:
            return "single"
        if total_chunks <= 4 and (duration_seconds == 0 or duration_seconds <= 35 * 60):
            return "micro-multi"
    if total_chunks <= 3:
        return "micro-multi"
    return "multi"


def parse_prepare_report(report_path: Path) -> dict:
    text = report_path.read_text(encoding="utf-8")

    def extract(pattern: str) -> str | None:
        match = re.search(pattern, text, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    return {
        "work_dir": extract(r"^WORK_DIR:\s*(.+)$") or str(report_path.parent),
        "files": int(extract(r"^Files:\s*(\d+)$") or 0),
        "total_lines": int(extract(r"^Total lines:\s*(\d+)$") or 0),
        "duration_estimate": extract(r"^Duration estimate:\s*(.+)$") or "unknown",
        "unique_speakers": int(extract(r"^Unique speakers:\s*(\d+)$") or 0),
        "total_chunks": int(extract(r"^=== TOTAL CHUNKS:\s*(\d+)\s*===$") or 0),
        "report_path": str(report_path),
    }


def active_run_context_for_dir(base_dir: Path) -> dict[str, str]:
    state: dict | None = None
    state_path = base_dir / "run.json"
    payload = load_json_if_exists(state_path)
    if isinstance(payload, dict):
        state = payload
    if state is None:
        prepare_state_path = find_prepare_state_path(base_dir)
        prepare_state = load_json_if_exists(prepare_state_path) if prepare_state_path else None
        if isinstance(prepare_state, dict):
            bundle_raw = str(prepare_state.get("bundle_dir") or "").strip()
            if bundle_raw:
                payload = load_json_if_exists(Path(bundle_raw).expanduser() / "run.json")
                if isinstance(payload, dict):
                    state = payload
    if not isinstance(state, dict):
        return {}
    run_id = str(state.get("active_run_id") or "").strip()
    note_id = str(state.get("note_id") or "").strip()
    result: dict[str, str] = {}
    if run_id:
        result["run_id"] = run_id
    if note_id:
        result["note_id"] = note_id
    return result


def find_prepare_state_path(work_dir: Path) -> Path | None:
    for filename in PREPARE_STATE_FILENAMES:
        candidate = work_dir / filename
        if candidate.is_file():
            return candidate
    return None


def find_prepare_plan_path(work_dir: Path) -> Path | None:
    for filename in PREPARE_PLAN_FILENAMES:
        candidate = work_dir / filename
        if candidate.is_file():
            return candidate
    return None


def normalize_chunk_id(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def normalize_chunk_plan(state: dict | None) -> list[dict]:
    if not isinstance(state, dict):
        return []

    raw_plan = state.get("chunk_plan") or []
    if not isinstance(raw_plan, list):
        return []

    plan: list[dict] = []
    for item in raw_plan:
        if not isinstance(item, dict):
            continue
        chunk_id = normalize_chunk_id(item.get("chunk_id") or item.get("id"))
        if not chunk_id:
            continue
        plan.append(
            {
                "id": chunk_id,
                "file": item.get("file"),
                "line_start": item.get("extraction_start"),
                "line_end": item.get("extraction_end"),
                "context_start": item.get("context_start"),
                "context_end": item.get("context_end"),
                "estimated_tokens": item.get("estimated_tokens"),
                "chunk_fingerprint": item.get("chunk_fingerprint"),
                "prompt_path": item.get("prompt_path"),
                "stage_sentinel_path": item.get("stage_sentinel_path"),
                "status": item.get("status"),
                "expected_outputs": item.get("expected_outputs") or [],
            }
        )
    return plan


def prepare_state_payload(work_dir: Path, state: dict | None, plan_state: dict | None, report_path: Path | None) -> dict:
    state = state or {}
    plan_state = plan_state or {}
    totals = state.get("totals") if isinstance(state.get("totals"), dict) else {}
    stage_hints = state.get("stage_hints") if isinstance(state.get("stage_hints"), dict) else {}
    if not stage_hints and state.get("speaker_stage"):
        stage_hints = {
            "speaker_identification": state.get("speaker_stage"),
            "appendix": "deterministic-fallback",
        }

    stage_statuses = state.get("stage_statuses") if isinstance(state.get("stage_statuses"), dict) else {}
    if not stage_statuses:
        speaker_stage = str(state.get("speaker_stage") or "").strip()
        speaker_status = "skipped" if speaker_stage == "skip" else "missing"
        stage_statuses = {
            "speaker_identification": speaker_status,
            "extraction": "missing",
            "tldr": "missing",
            "assemble": "missing",
        }

    prepare_state_path = find_prepare_state_path(work_dir)
    prepare_plan_path = find_prepare_plan_path(work_dir)
    unique_speakers = state.get("unique_speakers") or totals.get("speaker_markers") or 0
    file_entries = state.get("files")
    files_count = state.get("files") if isinstance(state.get("files"), int) else totals.get("files")
    if files_count is None and isinstance(file_entries, list):
        files_count = len(file_entries)

    payload = {
        "work_dir": str(state.get("work_dir") or work_dir),
        "fingerprint": state.get("fingerprint") or state.get("run_fingerprint"),
        "execution_mode": state.get("execution_mode") or plan_state.get("execution_mode"),
        "content_mode": state.get("content_mode") or plan_state.get("content_mode") or "conversation",
        "stage_hints": stage_hints,
        "stage_statuses": stage_statuses,
        "chunk_plan": normalize_chunk_plan(state) or normalize_chunk_plan(plan_state),
        "prepare_state_path": str(prepare_state_path) if prepare_state_path else None,
        "prepare_plan_path": str(prepare_plan_path) if prepare_plan_path else None,
        "report_path": str(report_path) if report_path else None,
        "files": int(files_count or 0),
        "total_lines": int(state.get("total_lines") or totals.get("lines") or 0),
        "duration_estimate": state.get("duration_estimate") or totals.get("duration_estimate") or "unknown",
        "unique_speakers": int(unique_speakers or 0),
        "total_chunks": int(state.get("total_chunks") or totals.get("chunks") or 0),
        "title_candidates": state.get("title_candidates") if isinstance(state.get("title_candidates"), list) else [],
        "prompt_packs": state.get("prompt_packs") if isinstance(state.get("prompt_packs"), dict) else {},
        "header_seed": state.get("header_seed") if isinstance(state.get("header_seed"), dict) else {},
        "source_identity": state.get("source_identity") if isinstance(state.get("source_identity"), dict) else {},
        "telemetry": state.get("telemetry") if isinstance(state.get("telemetry"), dict) else {},
        "bundle_dir": state.get("bundle_dir"),
        "note_contract": state.get("note_contract") if isinstance(state.get("note_contract"), dict) else {},
        "quality_checks": state.get("quality_checks") if isinstance(state.get("quality_checks"), dict) else {},
        "note_contract_path": str(note_contract_path(work_dir)) if note_contract_path(work_dir).is_file() else None,
        "quality_checks_path": str(quality_checks_path(work_dir)) if quality_checks_path(work_dir).is_file() else None,
    }
    if payload["chunk_plan"]:
        payload["total_chunks"] = len(payload["chunk_plan"])
    elif report_path:
        report_payload = parse_prepare_report(report_path)
        payload.update(
            {
                "files": report_payload["files"],
                "total_lines": report_payload["total_lines"],
                "duration_estimate": report_payload["duration_estimate"],
                "unique_speakers": report_payload["unique_speakers"],
                "total_chunks": report_payload["total_chunks"],
            }
        )
    if not payload.get("execution_mode"):
        payload["execution_mode"] = execution_mode_for_plan(
            int(payload.get("total_chunks") or 0),
            content_mode=str(payload.get("content_mode") or "conversation"),
        )
    if not payload.get("note_contract") and payload.get("note_contract_path"):
        contract_payload = load_json_if_exists(Path(str(payload["note_contract_path"])))
        if isinstance(contract_payload, dict):
            payload["note_contract"] = contract_payload
    if not payload.get("quality_checks") and payload.get("quality_checks_path"):
        quality_payload = load_json_if_exists(Path(str(payload["quality_checks_path"])))
        if isinstance(quality_payload, dict):
            payload["quality_checks"] = quality_payload
    return payload


def load_prepare_payload(work_dir: Path) -> dict:
    state_path = find_prepare_state_path(work_dir)
    state = load_json_if_exists(state_path) if state_path else None
    plan_path = find_prepare_plan_path(work_dir)
    plan_state = load_json_if_exists(plan_path) if plan_path else None
    report_path = work_dir / "prepare_report.txt"
    report = parse_prepare_report(report_path) if report_path.is_file() else None

    if state is not None or plan_state is not None:
        payload = prepare_state_payload(work_dir, state, plan_state, report_path if report_path.is_file() else None)
        if report is not None:
            if not payload.get("files"):
                payload["files"] = report["files"]
            if not payload.get("total_lines"):
                payload["total_lines"] = report["total_lines"]
            if payload.get("duration_estimate") == "unknown":
                payload["duration_estimate"] = report["duration_estimate"]
            if not payload.get("unique_speakers"):
                payload["unique_speakers"] = report["unique_speakers"]
            if not payload.get("total_chunks"):
                payload["total_chunks"] = report["total_chunks"]
        return payload

    if report is None:
        raise FileNotFoundError(f"prepare_report.txt not found: {report_path}")
    return report


def collect_chunk_ids_from_files(work_dir: Path) -> set[str]:
    chunk_ids: set[str] = set()
    for path in work_dir.glob("chunk_*_block_*.md"):
        match = CHUNK_BLOCK_PATTERN.match(path.name)
        if match:
            chunk_ids.add(match.group(1))
    for path in work_dir.glob("manifest_chunk_*.tsv"):
        match = MANIFEST_PATTERN.match(path.name)
        if match:
            chunk_ids.add(match.group(1))
    return chunk_ids


def infer_chunk_status(work_dir: Path, chunk_id: str, planned_chunk: dict | None) -> str:
    block_files = sorted(work_dir.glob(f"chunk_{chunk_id}_block_*.md"))
    manifest_exists = (work_dir / f"manifest_chunk_{chunk_id}.tsv").is_file()

    if planned_chunk is None:
        if block_files or manifest_exists:
            return "stale"
        return "missing"

    sentinel_value = planned_chunk.get("stage_sentinel_path")
    if isinstance(sentinel_value, str) and sentinel_value:
        sentinel_path = Path(sentinel_value)
    else:
        sentinel_path = stage_sentinel_path(work_dir, "extraction", chunk_id=chunk_id)
    sentinel = load_stage_sentinel(sentinel_path)
    planned_fingerprint = str(planned_chunk.get("chunk_fingerprint") or "").strip()

    if sentinel:
        sentinel_fingerprint = str(sentinel.get("chunk_fingerprint") or "").strip()
        if planned_fingerprint and sentinel_fingerprint and sentinel_fingerprint != planned_fingerprint:
            return "stale"

        expected_outputs = sentinel.get("expected_outputs")
        if not isinstance(expected_outputs, list) or not expected_outputs:
            expected_outputs = planned_chunk.get("expected_outputs") or []
        block_output_names = sentinel.get("block_files")
        if isinstance(block_output_names, list):
            expected_outputs = list(expected_outputs) + [str(item) for item in block_output_names if isinstance(item, str)]

        existing: list[bool] = []
        for item in expected_outputs:
            candidate = Path(str(item))
            if not candidate.is_absolute():
                candidate = work_dir / candidate
            existing.append(candidate.exists())

        if existing and all(existing) and (block_files or manifest_exists):
            return "ready"
        if any(existing) or block_files or manifest_exists:
            return "partial"
        return "missing"

    if block_files and manifest_exists:
        return "ready"
    if block_files or manifest_exists:
        return "partial"
    return "missing"


def build_chunk_statuses(work_dir: Path, chunk_plan: list[dict]) -> dict[str, dict]:
    planned_chunks: dict[str, dict] = {}
    for item in chunk_plan:
        if not isinstance(item, dict):
            continue
        chunk_id = normalize_chunk_id(item.get("id"))
        if chunk_id:
            planned_chunks[chunk_id] = item
    planned_ids = set(planned_chunks)

    chunk_ids = planned_ids | collect_chunk_ids_from_files(work_dir)
    statuses: dict[str, dict] = {}
    for chunk_id in sorted(chunk_ids):
        planned_chunk = planned_chunks.get(chunk_id)
        statuses[chunk_id] = {
            "status": infer_chunk_status(work_dir, chunk_id, planned_chunk),
            "block_files": [str(path) for path in sorted(work_dir.glob(f"chunk_{chunk_id}_block_*.md"))],
            "manifest": str(work_dir / f"manifest_chunk_{chunk_id}.tsv") if (work_dir / f"manifest_chunk_{chunk_id}.tsv").exists() else None,
            "planned": chunk_id in planned_ids,
            "sentinel": str(Path(str(planned_chunk.get("stage_sentinel_path")))) if isinstance(planned_chunk, dict) and planned_chunk.get("stage_sentinel_path") else None,
            "chunk_fingerprint": planned_chunk.get("chunk_fingerprint") if isinstance(planned_chunk, dict) else None,
        }
    return statuses


def stage_status_from_prepare_state(stage_statuses: dict, key: str, default: str) -> str:
    value = stage_statuses.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return default


def build_stage_statuses(work_dir: Path, payload: dict, chunk_statuses: dict[str, dict]) -> dict[str, dict]:
    stage_hints = payload.get("stage_hints") if isinstance(payload.get("stage_hints"), dict) else {}
    explicit = payload.get("stage_statuses") if isinstance(payload.get("stage_statuses"), dict) else {}
    planned_chunks = [item for item in payload.get("chunk_plan", []) if isinstance(item, dict)]
    planned_ids = {chunk_id for item in planned_chunks if (chunk_id := normalize_chunk_id(item.get("id")))}

    speakers_file = work_dir / "speakers.txt"
    tldr_file = work_dir / "tldr.md"
    html_outputs = list(work_dir.glob("*.html"))
    md_outputs = list(work_dir.glob("*.md"))
    overall_fingerprint = str(payload.get("fingerprint") or "")
    speaker_sentinel = load_stage_sentinel(stage_sentinel_path(work_dir, "speaker-identification"))
    tldr_sentinel = load_stage_sentinel(stage_sentinel_path(work_dir, "tldr"))
    assemble_sentinel = load_stage_sentinel(stage_sentinel_path(work_dir, "assemble"))

    planned_chunk_statuses = [chunk_statuses[chunk_id]["status"] for chunk_id in sorted(planned_ids) if chunk_id in chunk_statuses]
    if planned_chunk_statuses and all(status == "ready" for status in planned_chunk_statuses):
        extraction_status = "ready"
    elif any(status == "stale" for status in planned_chunk_statuses):
        extraction_status = "stale"
    elif any(status == "ready" for status in planned_chunk_statuses) or any(status == "partial" for status in planned_chunk_statuses):
        extraction_status = "partial"
    else:
        extraction_status = "missing"

    speaker_hint = stage_hints.get("speaker_identification") if isinstance(stage_hints, dict) else None
    if speaker_hint == "skip":
        speaker_status = "skipped"
    elif speaker_sentinel and speakers_file.is_file():
        speaker_status = "ready"
    elif speakers_file.is_file():
        speaker_status = "ready"
    else:
        speaker_status = stage_status_from_prepare_state(explicit, "speaker_identification", "missing")

    if tldr_file.is_file():
        tldr_status = "ready"
        if extraction_status in {"missing", "partial", "stale"}:
            tldr_status = "stale"
        elif tldr_sentinel:
            sentinel_fingerprint = str(tldr_sentinel.get("fingerprint") or "")
            if sentinel_fingerprint and overall_fingerprint and sentinel_fingerprint != overall_fingerprint:
                tldr_status = "stale"
    else:
        tldr_status = stage_status_from_prepare_state(explicit, "tldr", "missing")

    if html_outputs:
        assemble_status = "ready"
        if extraction_status != "ready":
            assemble_status = "stale"
        elif tldr_file.is_file() and tldr_status != "ready":
            assemble_status = "stale"
        elif assemble_sentinel:
            sentinel_fingerprint = str(assemble_sentinel.get("fingerprint") or "")
            if sentinel_fingerprint and overall_fingerprint and sentinel_fingerprint != overall_fingerprint:
                assemble_status = "stale"
    else:
        assemble_status = stage_status_from_prepare_state(explicit, "assemble", "missing")

    if extraction_status == "ready" and any(status != "ready" for status in planned_chunk_statuses):
        extraction_status = "partial"

    return {
        "speaker_identification": {
            "status": speaker_status,
            "hint": speaker_hint,
            "sentinel": str(stage_sentinel_path(work_dir, "speaker-identification")) if speaker_hint != "skip" else None,
        },
        "extraction": {
            "status": extraction_status,
            "planned_chunks": len(planned_ids),
            "ready_chunks": sum(1 for status in planned_chunk_statuses if status == "ready"),
            "partial_chunks": sum(1 for status in planned_chunk_statuses if status == "partial"),
            "missing_chunks": sum(1 for status in planned_chunk_statuses if status == "missing"),
            "stale_chunks": sum(1 for status in planned_chunk_statuses if status == "stale"),
        },
        "tldr": {
            "status": tldr_status,
            "exists": tldr_file.is_file(),
            "sentinel": str(stage_sentinel_path(work_dir, "tldr")),
        },
        "assemble": {
            "status": assemble_status,
            "html_outputs": [str(path) for path in html_outputs],
            "markdown_outputs": [str(path) for path in md_outputs],
            "sentinel": str(stage_sentinel_path(work_dir, "assemble")),
        },
    }


def determine_next_action(stages: dict[str, dict]) -> str:
    speaker_status = stages["speaker_identification"]["status"]
    speaker_hint = stages["speaker_identification"].get("hint")
    extraction_status = stages["extraction"]["status"]
    tldr_status = stages["tldr"]["status"]
    assemble_status = stages["assemble"]["status"]

    if speaker_hint == "required" and speaker_status not in {"ready", "skipped"}:
        return "speaker-identification"
    if extraction_status != "ready":
        return "extract-chunks"
    if tldr_status != "ready":
        return "generate-tldr"
    if assemble_status != "ready":
        return "assemble"
    return "done"


def build_execution_plan(payload: dict, chunk_statuses: dict[str, dict], stages: dict[str, dict]) -> dict:
    chunk_plan = payload.get("chunk_plan", [])
    if not isinstance(chunk_plan, list):
        chunk_plan = []

    total_chunks = int(payload.get("total_chunks") or len(chunk_plan) or 0)
    mode = str(payload.get("execution_mode") or "").strip() or execution_mode_for_plan(
        total_chunks,
        content_mode=str(payload.get("content_mode") or "conversation"),
    )
    content_mode = str(payload.get("content_mode") or "conversation")
    next_action = determine_next_action(stages)
    prompt_packs = payload.get("prompt_packs") if isinstance(payload.get("prompt_packs"), dict) else {}
    header_seed = payload.get("header_seed") if isinstance(payload.get("header_seed"), dict) else {}
    note_contract = payload.get("note_contract") if isinstance(payload.get("note_contract"), dict) else {}
    quality_checks = payload.get("quality_checks") if isinstance(payload.get("quality_checks"), dict) else {}
    if isinstance(payload.get("title_candidates"), list):
        title_candidates = payload.get("title_candidates")
    elif isinstance(header_seed.get("title_candidates"), list):
        title_candidates = header_seed.get("title_candidates")
    else:
        title_candidates = []

    ready_chunk_ids: list[str] = []
    pending_chunks: list[dict] = []
    partial_chunk_ids: list[str] = []
    for item in chunk_plan:
        if not isinstance(item, dict):
            continue
        chunk_id = normalize_chunk_id(item.get("id"))
        if not chunk_id:
            continue
        status = str(chunk_statuses.get(chunk_id, {}).get("status") or "missing")
        enriched = dict(item)
        enriched["status"] = status
        if status == "ready":
            ready_chunk_ids.append(chunk_id)
        else:
            pending_chunks.append(enriched)
            if status == "partial":
                partial_chunk_ids.append(chunk_id)

    speaker_hint = str(stages["speaker_identification"].get("hint") or "")
    speaker_status = str(stages["speaker_identification"].get("status") or "missing")
    extraction_status = str(stages["extraction"].get("status") or "missing")
    tldr_status = str(stages["tldr"].get("status") or "missing")
    assemble_status = str(stages["assemble"].get("status") or "missing")

    should_run_speaker = (
        mode in {"micro-multi", "multi"}
        and speaker_hint != "skip"
        and speaker_status not in {"ready", "skipped"}
    )
    should_run_extraction = extraction_status != "ready"
    tldr_strategy = (
        "inline-extraction" if mode == "single"
        else "deterministic-merge" if mode == "micro-multi"
        else "agent"
    )
    should_run_tldr = mode in {"micro-multi", "multi"} and extraction_status == "ready" and tldr_status != "ready"

    assemble_blocked_by: list[str] = []
    if mode in {"micro-multi", "multi"} and should_run_speaker:
        assemble_blocked_by.append("speaker_identification")
    if extraction_status != "ready":
        assemble_blocked_by.append("extraction")
    if mode in {"micro-multi", "multi"} and tldr_status != "ready":
        assemble_blocked_by.append("tldr")

    resume = bool(payload.get("reused")) or any(
        status["status"] in {"ready", "partial"}
        for status in chunk_statuses.values()
        if isinstance(status, dict) and isinstance(status.get("status"), str)
    )

    return {
        "mode": mode,
        "content_mode": content_mode,
        "resume": resume,
        "next_action": next_action,
        "speaker_identification": {
            "should_run": should_run_speaker,
            "hint": speaker_hint,
            "status": speaker_status,
        },
        "extraction": {
            "should_run": should_run_extraction,
            "status": extraction_status,
            "inline_tldr": mode == "single",
            "chunks_to_extract": pending_chunks,
            "pending_chunk_ids": [item["id"] for item in pending_chunks if isinstance(item.get("id"), str)],
            "ready_chunk_ids": ready_chunk_ids,
            "partial_chunk_ids": partial_chunk_ids,
        },
        "tldr": {
            "should_run": should_run_tldr,
            "status": tldr_status,
            "inline_with_extraction": mode == "single",
            "strategy": tldr_strategy,
        },
        "replace_speakers": {
            "before_tldr": mode in {"micro-multi", "multi"} and extraction_status == "ready" and tldr_status != "ready" and speaker_hint != "skip",
            "after_tldr": mode in {"micro-multi", "multi"} and extraction_status == "ready" and tldr_status != "ready" and speaker_hint != "skip",
        },
        "title_header": {
            "should_run": assemble_status != "ready",
            "title_candidates": title_candidates,
            "header_seed_path": prompt_packs.get("header_seed"),
            "prompt_path": prompt_packs.get("header"),
            "speaker_candidates": header_seed.get("speaker_candidates") if isinstance(header_seed.get("speaker_candidates"), list) else [],
            "author_hint": header_seed.get("author_hint"),
        },
        "contract": {
            "note_contract_path": payload.get("note_contract_path"),
            "quality_checks_path": payload.get("quality_checks_path"),
            "tldr_bounds": note_contract.get("tldr") if isinstance(note_contract.get("tldr"), dict) else {},
            "prepare_quality": quality_checks.get("prepare") if isinstance(quality_checks.get("prepare"), dict) else {},
        },
        "assemble": {
            "should_run": assemble_status != "ready" and not assemble_blocked_by,
            "status": assemble_status,
            "blocked_by": assemble_blocked_by,
        },
        "prompt_packs": prompt_packs,
    }
