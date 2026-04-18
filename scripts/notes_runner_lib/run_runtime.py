from __future__ import annotations

import os
import sys
import uuid
from datetime import datetime
from pathlib import Path

from .bundle_runtime import bundle_paths, infer_bundle_note_id
from .common import (
    append_jsonl,
    collect_external_refs,
    file_sha256_if_exists,
    iso_now,
    load_json,
    load_json_if_exists,
    merge_nested_dict,
    write_json,
    write_text,
)
from .prepare_runtime import (
    active_run_context_for_dir,
    find_prepare_state_path,
    load_prepare_payload,
    quality_checks_path,
)

BUNDLE_STATE_PERSISTENT_KEYS = (
    "note_id",
    "timeline_path",
    "runs_dir",
    "latest_run_id",
    "latest_run_snapshot",
    "latest_status",
    "last_external_refs",
    "active_run_id",
)


def load_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return load_json(path)


def trace_path_for_dir(base_dir: Path) -> Path:
    return base_dir / "trace.jsonl"


def timeline_path_for_dir(base_dir: Path) -> Path:
    return base_dir / "timeline.jsonl"


def runs_dir_for_dir(base_dir: Path) -> Path:
    return base_dir / "runs"


def generate_run_id() -> str:
    stamp = datetime.now().astimezone().strftime("%Y%m%dT%H%M%S")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def append_trace_event(base_dir: Path, event: str, **fields: object) -> Path:
    record = {
        "ts": iso_now(),
        "event": event,
    }
    for key, value in fields.items():
        if value is not None:
            record[key] = value
    active_run = active_run_context_for_dir(base_dir)
    if "run_id" not in record and active_run.get("run_id"):
        record["run_id"] = active_run["run_id"]
    if "note_id" not in record and active_run.get("note_id"):
        record["note_id"] = active_run["note_id"]
    trace_path = trace_path_for_dir(base_dir)
    append_jsonl(trace_path, record)
    if str(os.environ.get("NOTES_RUNNER_TRACE_STDERR") or "").strip().lower() in {"1", "true", "yes", "on"}:
        summary_fields = [
            f"{key}={value}"
            for key, value in record.items()
            if key not in {"ts", "event", "error", "stderr", "stdout"}
        ]
        summary = " ".join(summary_fields).strip()
        if record.get("error"):
            summary = f"{summary} error={record['error']}".strip()
        print(f"[notes-trace] {event}{(' ' + summary) if summary else ''}", file=sys.stderr)
    return trace_path


def resolve_bundle_work_dir(bundle_dir: Path) -> Path | None:
    work_link = bundle_dir / "work"
    if work_link.exists() or work_link.is_symlink():
        try:
            resolved = work_link.resolve(strict=True)
        except FileNotFoundError:
            resolved = None
        if resolved and resolved.is_dir():
            return resolved

    work_dir_file = bundle_dir / "work-dir.txt"
    if work_dir_file.is_file():
        raw = work_dir_file.read_text(encoding="utf-8").strip()
        if raw:
            candidate = Path(raw).expanduser()
            if candidate.is_dir():
                return candidate.resolve()
    return None


def link_bundle_work_dir(bundle_dir: Path, work_dir: Path) -> Path:
    work_link = bundle_dir / "work"
    if work_link.exists() or work_link.is_symlink():
        work_link.unlink()
    work_link.symlink_to(work_dir)
    write_text(bundle_dir / "work-dir.txt", str(work_dir) + "\n")
    return work_link


def merge_bundle_state(bundle_dir: Path, patch: dict) -> dict:
    paths = bundle_paths(bundle_dir)
    state_path = paths["state"]
    existing = load_json_file(state_path) if state_path.is_file() else {}
    if not isinstance(existing, dict):
        existing = {}
    merged = merge_nested_dict(existing, patch)
    merged["updated_at"] = iso_now()
    merged.setdefault("timeline_path", str(paths["timeline"]))
    merged.setdefault("runs_dir", str(paths["runs_dir"]))
    if not str(merged.get("note_id") or "").strip():
        merged["note_id"] = infer_bundle_note_id(bundle_dir, state=merged)
    write_json(state_path, merged)
    return merged


def load_bundle_state(bundle_dir: Path) -> dict:
    state_path = bundle_paths(bundle_dir)["state"]
    payload = load_json_file(state_path) if state_path.is_file() else {}
    return payload if isinstance(payload, dict) else {}


def write_bundle_state_snapshot(bundle_dir: Path, payload: dict) -> dict:
    paths = bundle_paths(bundle_dir)
    existing = load_bundle_state(bundle_dir)
    snapshot = {
        key: existing[key]
        for key in BUNDLE_STATE_PERSISTENT_KEYS
        if key in existing and existing.get(key) is not None and key not in payload
    }
    snapshot.update(payload)
    snapshot["updated_at"] = iso_now()
    snapshot.setdefault("timeline_path", str(paths["timeline"]))
    snapshot.setdefault("runs_dir", str(paths["runs_dir"]))
    if not str(snapshot.get("note_id") or "").strip():
        snapshot["note_id"] = infer_bundle_note_id(bundle_dir, state=snapshot)
    write_json(paths["state"], snapshot)
    return snapshot


def summarize_quality_payload(quality_payload: dict | None, contract_errors: list[str] | None = None) -> dict:
    final_quality = quality_payload.get("final") if isinstance(quality_payload, dict) and isinstance(quality_payload.get("final"), dict) else {}
    placeholder_payload = final_quality.get("placeholder_leakage") if isinstance(final_quality.get("placeholder_leakage"), dict) else {}
    duplicate_payload = final_quality.get("duplicate_case_titles") if isinstance(final_quality.get("duplicate_case_titles"), dict) else {}
    actionability_payload = final_quality.get("actionability_score") if isinstance(final_quality.get("actionability_score"), dict) else {}
    deep_longform_payload = final_quality.get("deep_longform_coverage") if isinstance(final_quality.get("deep_longform_coverage"), dict) else {}
    density_payload = final_quality.get("detail_density") if isinstance(final_quality.get("detail_density"), dict) else {}
    return {
        "contract_errors": list(contract_errors or []),
        "header_complete": final_quality.get("header_complete"),
        "tldr_count": final_quality.get("tldr_count"),
        "tldr_length_ok": final_quality.get("tldr_length_ok"),
        "placeholder_ok": placeholder_payload.get("ok"),
        "duplicate_case_titles_ok": duplicate_payload.get("ok"),
        "actionability_ok": actionability_payload.get("ok"),
        "detail_density_ok": density_payload.get("ok"),
        "deep_longform_ok": deep_longform_payload.get("ok"),
    }


def summarize_telegram_delivery(telegram_delivery: dict | None) -> dict:
    if not isinstance(telegram_delivery, dict):
        return {}
    summary = {
        "enabled": telegram_delivery.get("enabled"),
        "attempted": telegram_delivery.get("attempted"),
        "success": telegram_delivery.get("success"),
        "reason": telegram_delivery.get("reason"),
        "chat": telegram_delivery.get("chat"),
        "file_sha256": telegram_delivery.get("file_sha256"),
        "error": telegram_delivery.get("error"),
    }
    return {key: value for key, value in summary.items() if value is not None}


def load_run_snapshot(path: str | Path | None) -> dict | None:
    if not path:
        return None
    snapshot_path = Path(path).expanduser()
    payload = load_json_file(snapshot_path)
    return payload if isinstance(payload, dict) else None


def build_change_flags(previous_snapshot: dict | None, current_hashes: dict, quality_summary: dict, delivery_summary: dict) -> dict:
    if not isinstance(previous_snapshot, dict):
        output_changed = any(current_hashes.get(key) for key in ("markdown", "html"))
        return {
            "first_run": True,
            "input_changed": bool(current_hashes.get("transcript")),
            "output_changed": output_changed,
            "quality_changed": bool(quality_summary),
            "delivery_changed": bool(delivery_summary),
            "only_resume": False,
        }
    previous_hashes = previous_snapshot.get("hashes") if isinstance(previous_snapshot.get("hashes"), dict) else {}
    previous_quality = previous_snapshot.get("quality") if isinstance(previous_snapshot.get("quality"), dict) else {}
    previous_delivery = previous_snapshot.get("telegram_delivery") if isinstance(previous_snapshot.get("telegram_delivery"), dict) else {}
    input_changed = previous_hashes.get("transcript") != current_hashes.get("transcript")
    output_changed = (
        previous_hashes.get("markdown") != current_hashes.get("markdown")
        or previous_hashes.get("html") != current_hashes.get("html")
    )
    quality_changed = previous_quality != quality_summary
    delivery_changed = previous_delivery != delivery_summary
    return {
        "first_run": False,
        "input_changed": input_changed,
        "output_changed": output_changed,
        "quality_changed": quality_changed,
        "delivery_changed": delivery_changed,
        "only_resume": not any((input_changed, output_changed, quality_changed, delivery_changed)),
    }


def build_run_snapshot(
    bundle_dir: Path,
    run_context: dict,
    *,
    status: str,
    error: str | None = None,
    contract_errors: list[str] | None = None,
    quality_payload: dict | None = None,
    telegram_delivery: dict | None = None,
) -> dict:
    state = load_bundle_state(bundle_dir)
    paths = bundle_paths(bundle_dir)
    work_dir = resolve_bundle_work_dir(bundle_dir)
    try:
        prepare_payload = load_prepare_payload(work_dir) if work_dir else {}
    except FileNotFoundError:
        prepare_payload = {}
    quality_source = quality_payload if isinstance(quality_payload, dict) else (load_json_if_exists(quality_checks_path(work_dir)) if work_dir else None)
    quality_summary = summarize_quality_payload(quality_source, contract_errors=contract_errors)
    delivery_summary = summarize_telegram_delivery(telegram_delivery if isinstance(telegram_delivery, dict) else state.get("telegram_delivery"))
    outputs = state.get("outputs") if isinstance(state.get("outputs"), dict) else {}
    markdown_path = Path(str(outputs.get("markdown") or paths["notes_md"])).expanduser()
    html_path = Path(str(outputs.get("html") or paths["notes_html"])).expanduser()
    transcript_path = Path(str(state.get("transcript_path") or paths["transcript"])).expanduser()
    hashes = {
        "transcript": file_sha256_if_exists(transcript_path),
        "markdown": file_sha256_if_exists(markdown_path),
        "html": file_sha256_if_exists(html_path),
    }
    previous_snapshot = load_run_snapshot(run_context.get("previous_snapshot_path") or state.get("latest_run_snapshot"))
    change_flags = build_change_flags(previous_snapshot, hashes, quality_summary, delivery_summary)
    stage_statuses = prepare_payload.get("stage_statuses") if isinstance(prepare_payload, dict) and isinstance(prepare_payload.get("stage_statuses"), dict) else {}
    telemetry = state.get("telemetry") if isinstance(state.get("telemetry"), dict) else {}
    source_identity = {
        "source_kind": state.get("source_kind"),
        "source_path": state.get("source_path"),
        "source_url": state.get("source_url"),
        "video_id": state.get("video_id"),
        "telegram_chat": state.get("telegram_chat"),
        "telegram_message_id": state.get("telegram_message_id"),
    }
    source_identity = {key: value for key, value in source_identity.items() if value not in (None, "", [])}
    snapshot = {
        "run_id": run_context["run_id"],
        "note_id": run_context["note_id"],
        "command": run_context["command"],
        "status": status,
        "started_at": run_context["started_at"],
        "finished_at": iso_now(),
        "bundle_dir": str(bundle_dir),
        "title": state.get("title"),
        "external_refs": list(run_context.get("external_refs") or []),
        "source_identity": source_identity,
        "input_fingerprint": prepare_payload.get("fingerprint") if isinstance(prepare_payload, dict) else None,
        "work_dir": str(work_dir) if work_dir else None,
        "prepare_reused": bool(((state.get("prepare") or {}).get("reused"))) if isinstance(state.get("prepare"), dict) else False,
        "hashes": hashes,
        "quality": quality_summary,
        "telegram_delivery": delivery_summary,
        "telemetry": telemetry,
        "stage_statuses": stage_statuses,
        "change_flags": change_flags,
    }
    if error:
        snapshot["error"] = error
    return snapshot


def start_bundle_run(bundle_dir: Path, *, command: str, state_seed: dict | None = None) -> dict:
    existing = load_bundle_state(bundle_dir)
    seeded_state = merge_nested_dict(existing, state_seed or {})
    note_id = infer_bundle_note_id(bundle_dir, state=seeded_state)
    run_context = {
        "run_id": generate_run_id(),
        "note_id": note_id,
        "command": command,
        "started_at": iso_now(),
        "external_refs": collect_external_refs(),
        "previous_snapshot_path": str(existing.get("latest_run_snapshot") or "").strip() or None,
    }
    merge_bundle_state(
        bundle_dir,
        {
            "note_id": note_id,
            "active_run_id": run_context["run_id"],
            "timeline_path": str(timeline_path_for_dir(bundle_dir)),
            "runs_dir": str(runs_dir_for_dir(bundle_dir)),
            "last_external_refs": run_context["external_refs"],
        },
    )
    append_trace_event(
        bundle_dir,
        "run.started",
        run_id=run_context["run_id"],
        note_id=note_id,
        command=command,
        external_refs=run_context["external_refs"] or None,
    )
    return run_context


def finish_bundle_run(
    bundle_dir: Path,
    run_context: dict,
    *,
    status: str,
    error: str | None = None,
    contract_errors: list[str] | None = None,
    quality_payload: dict | None = None,
    telegram_delivery: dict | None = None,
) -> dict:
    paths = bundle_paths(bundle_dir)
    snapshot = build_run_snapshot(
        bundle_dir,
        run_context,
        status=status,
        error=error,
        contract_errors=contract_errors,
        quality_payload=quality_payload,
        telegram_delivery=telegram_delivery,
    )
    paths["runs_dir"].mkdir(parents=True, exist_ok=True)
    snapshot_path = paths["runs_dir"] / f"{run_context['run_id']}.json"
    write_json(snapshot_path, snapshot)
    timeline_entry = {
        "ts": snapshot["finished_at"],
        "run_id": snapshot["run_id"],
        "note_id": snapshot["note_id"],
        "command": snapshot["command"],
        "status": snapshot["status"],
        "title": snapshot.get("title"),
        "external_refs": snapshot.get("external_refs", []),
        "hashes": snapshot.get("hashes", {}),
        "quality": snapshot.get("quality", {}),
        "telegram_delivery": snapshot.get("telegram_delivery", {}),
        "change_flags": snapshot.get("change_flags", {}),
        "snapshot_path": str(snapshot_path),
    }
    if error:
        timeline_entry["error"] = error
    append_jsonl(paths["timeline"], timeline_entry)
    merge_bundle_state(
        bundle_dir,
        {
            "note_id": snapshot["note_id"],
            "active_run_id": None,
            "latest_run_id": snapshot["run_id"],
            "latest_run_snapshot": str(snapshot_path),
            "latest_status": snapshot["status"],
            "last_external_refs": snapshot.get("external_refs", []),
            "timeline_path": str(paths["timeline"]),
            "runs_dir": str(paths["runs_dir"]),
        },
    )
    append_trace_event(
        bundle_dir,
        "run.finished",
        run_id=snapshot["run_id"],
        note_id=snapshot["note_id"],
        command=snapshot["command"],
        status=snapshot["status"],
        external_refs=snapshot.get("external_refs") or None,
        input_changed=snapshot["change_flags"].get("input_changed"),
        output_changed=snapshot["change_flags"].get("output_changed"),
        quality_changed=snapshot["change_flags"].get("quality_changed"),
        delivery_changed=snapshot["change_flags"].get("delivery_changed"),
        error=error,
    )
    return snapshot


def bundle_dir_from_work_dir(work_dir: Path) -> Path | None:
    state_path = find_prepare_state_path(work_dir)
    state = load_json_file(state_path) if state_path else None
    if not isinstance(state, dict):
        return None
    raw = state.get("bundle_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None
    bundle_dir = Path(raw).expanduser()
    return bundle_dir if bundle_dir.is_dir() else None
