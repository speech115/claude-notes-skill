from __future__ import annotations

from pathlib import Path
from typing import Callable

from .common import load_json_if_exists, merge_nested_dict, write_json
from .prepare_runtime import find_prepare_plan_path, find_prepare_state_path


def update_prepare_state_fields(work_dir: Path, updates: dict) -> None:
    state_path = find_prepare_state_path(work_dir)
    if state_path is not None:
        payload = load_json_if_exists(state_path) or {}
        if isinstance(payload, dict):
            write_json(state_path, merge_nested_dict(payload, updates))
    plan_path = find_prepare_plan_path(work_dir)
    if plan_path is not None:
        payload = load_json_if_exists(plan_path) or {}
        if isinstance(payload, dict):
            write_json(plan_path, merge_nested_dict(payload, updates))


def extract_prepare_duration_ms(prepare_payload: dict | None) -> int:
    if not isinstance(prepare_payload, dict):
        return 0
    raw_value = prepare_payload.get("prepare_duration_ms")
    if isinstance(raw_value, (int, float)):
        return int(raw_value)
    telemetry = prepare_payload.get("telemetry") if isinstance(prepare_payload.get("telemetry"), dict) else {}
    raw_value = telemetry.get("prepare_duration_ms")
    return int(raw_value) if isinstance(raw_value, (int, float)) else 0


def record_bundle_stage_metric(
    bundle_dir: Path,
    stage_name: str,
    duration_ms: int,
    *,
    merge_bundle_state: Callable[[Path, dict], dict],
    append_trace_event: Callable[..., Path],
    **extra: object,
) -> None:
    metric_payload = {
        "telemetry": {
            "stages": {
                stage_name: {
                    "duration_ms": duration_ms,
                    **extra,
                }
            }
        }
    }
    merge_bundle_state(bundle_dir, metric_payload)
    append_trace_event(bundle_dir, f"stage.{stage_name}", duration_ms=duration_ms, **extra)


def attach_prepare_outputs(
    payload: dict[str, object],
    prepare_payload: dict,
    bundle_dir: Path,
    *,
    header_seed_filename: str,
    ensure_dir: Callable[[Path, str], Path],
    build_status: Callable[[Path], dict],
    link_bundle_work_dir: Callable[[Path, Path], Path],
    clean_title: Callable[[str], str],
    is_informative_title: Callable[[str], bool],
    work_prompt_dir: Callable[[Path], Path],
    work_stage_dir: Callable[[Path], Path],
    record_bundle_stage_metric: Callable[..., None],
) -> None:
    work_dir = ensure_dir(Path(prepare_payload["work_dir"]), "Work directory")
    work_link = link_bundle_work_dir(bundle_dir, work_dir)
    status_payload = build_status(work_dir)
    execution_plan = status_payload.get("execution_plan")

    if isinstance(execution_plan, dict) and prepare_payload.get("reused"):
        execution_plan = dict(execution_plan)
        execution_plan["resume"] = True
        status_payload = dict(status_payload)
        status_payload["execution_plan"] = execution_plan

    payload["prepare"] = prepare_payload
    payload["status"] = status_payload
    payload["execution_plan"] = execution_plan
    payload["work_link"] = str(work_link)

    header_seed_path = work_dir / header_seed_filename
    header_seed = load_json_if_exists(header_seed_path) if header_seed_path.is_file() else {}
    if not isinstance(header_seed, dict):
        header_seed = {}
    payload_title = str(payload.get("title") or "").strip()
    existing_candidates = header_seed.get("title_candidates") if isinstance(header_seed.get("title_candidates"), list) else []
    title_candidates: list[str] = []
    if payload_title:
        title_candidates.append(payload_title)
    title_candidates.extend(str(item) for item in existing_candidates if isinstance(item, str))
    deduped_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in title_candidates:
        cleaned = clean_title(candidate)
        key = cleaned.casefold()
        if not is_informative_title(cleaned) or key in seen:
            continue
        deduped_candidates.append(cleaned)
        seen.add(key)

    header_seed = merge_nested_dict(
        header_seed,
        {
            "bundle_dir": str(bundle_dir),
            "raw_title": payload_title,
            "source_kind": payload.get("source_kind"),
            "title_candidates": deduped_candidates or header_seed.get("title_candidates") or [],
            "suggested_output_md": payload.get("suggested_output_md"),
            "suggested_output_html": payload.get("suggested_output_html"),
        },
    )
    write_json(header_seed_path, header_seed)
    update_prepare_state_fields(
        work_dir,
        {
            "bundle_dir": str(bundle_dir),
            "title_candidates": header_seed.get("title_candidates") or [],
            "header_seed": header_seed,
            "artifacts": {
                "prompt_pack_dir": str(work_prompt_dir(work_dir)),
                "stage_dir": str(work_stage_dir(work_dir)),
                "header_seed": str(header_seed_path),
            },
        },
    )
    if isinstance(payload.get("prepare"), dict):
        payload["prepare"]["bundle_dir"] = str(bundle_dir)
        payload["prepare"]["title_candidates"] = header_seed.get("title_candidates") or []
        payload["prepare"]["header_seed"] = header_seed
    if isinstance(payload.get("status"), dict):
        payload["status"]["header_seed"] = header_seed
        payload["status"]["title_candidates"] = header_seed.get("title_candidates") or []

    prepare_ms = extract_prepare_duration_ms(prepare_payload)
    if prepare_ms > 0:
        record_bundle_stage_metric(
            bundle_dir,
            "prepare",
            prepare_ms,
            work_dir=str(work_dir),
            reused=bool(prepare_payload.get("reused")),
            total_chunks=prepare_payload.get("total_chunks"),
        )

    if isinstance(payload.get("execution_plan"), dict):
        title_header = payload["execution_plan"].get("title_header")
        if isinstance(title_header, dict):
            title_header["title_candidates"] = header_seed.get("title_candidates") or []
            title_header["header_seed_path"] = str(header_seed_path)
            title_header["speaker_candidates"] = header_seed.get("speaker_candidates") or []
            title_header["author_hint"] = header_seed.get("author_hint")
