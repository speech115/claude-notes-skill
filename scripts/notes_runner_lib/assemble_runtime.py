from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Callable, TextIO

from .common import iso_now
from .prepare_runtime import load_prepare_payload, quality_checks_path, stage_sentinel_path
from .quality_runtime import compute_final_quality_checks, contract_errors_for_quality


def assemble_shell_error_detail(result: subprocess.CompletedProcess[str]) -> str:
    return (result.stderr or result.stdout or f"exit code {result.returncode}").strip()


def relay_assemble_shell_streams(
    result: subprocess.CompletedProcess[str],
    *,
    sink: TextIO,
) -> None:
    if result.stdout:
        print(result.stdout, file=sink, end="")
    if result.stderr:
        print(result.stderr, file=sink, end="")


def build_assemble_shell_failure_sentinel(
    *,
    output_md: Path,
    output_html: Path,
    returncode: int,
    error_detail: str,
    duration_ms: int,
    completed_at: str | None = None,
) -> dict:
    return {
        "stage": "assemble",
        "completed": False,
        "completed_at": completed_at or iso_now(),
        "duration_ms": duration_ms,
        "output_md": str(output_md),
        "output_html": str(output_html),
        "returncode": returncode,
        "error": error_detail,
    }


def handle_assemble_shell_failure(
    *,
    work_dir: Path,
    bundle_dir: Path,
    output_md: Path,
    output_html: Path,
    started_at: float,
    result: subprocess.CompletedProcess[str],
    run_context: dict,
    update_prepare_state_fields: Callable[[Path, dict], None],
    write_stage_sentinel: Callable[[Path, dict], None],
    append_trace_event: Callable[..., Path],
    record_bundle_stage_metric: Callable[..., None],
    finish_bundle_run: Callable[..., dict | None],
    ms_since: Callable[[float], int],
    stage_sentinel_path_fn: Callable[..., Path] = stage_sentinel_path,
    relay_shell_streams: Callable[..., None] = relay_assemble_shell_streams,
    stderr_sink: TextIO | None = None,
) -> dict:
    duration_ms = ms_since(started_at)
    error_detail = assemble_shell_error_detail(result)
    sentinel_path = stage_sentinel_path_fn(work_dir, "assemble")
    sentinel_payload = build_assemble_shell_failure_sentinel(
        output_md=output_md,
        output_html=output_html,
        returncode=result.returncode,
        error_detail=error_detail,
        duration_ms=duration_ms,
    )

    write_stage_sentinel(sentinel_path, sentinel_payload)
    update_prepare_state_fields(work_dir, {"stage_statuses": {"assemble": "failed"}})
    append_trace_event(
        bundle_dir,
        "assemble.shell_failed",
        work_dir=str(work_dir),
        output_md=str(output_md),
        output_html=str(output_html),
        returncode=result.returncode,
        error=error_detail,
    )
    record_bundle_stage_metric(
        bundle_dir,
        "assemble",
        duration_ms,
        output_md=str(output_md),
        output_html=str(output_html),
        returncode=result.returncode,
        shell_ok=False,
        contract_ok=False,
    )
    finish_bundle_run(bundle_dir, run_context, status="failed", error=error_detail)
    if stderr_sink is not None:
        relay_shell_streams(result, sink=stderr_sink)

    return {
        "returncode": result.returncode,
        "duration_ms": duration_ms,
        "error_detail": error_detail,
        "sentinel_path": str(sentinel_path),
        "sentinel_payload": sentinel_payload,
    }


def build_assemble_success_context(
    work_dir: Path,
    output_md: Path,
    *,
    update_prepare_state_fields: Callable[[Path, dict], None],
    load_prepare_payload_fn: Callable[[Path], dict] = load_prepare_payload,
    compute_final_quality_checks_fn: Callable[..., dict] = compute_final_quality_checks,
    contract_errors_for_quality_fn: Callable[[dict, dict], list[str]] = contract_errors_for_quality,
) -> dict:
    try:
        prepare_payload = load_prepare_payload_fn(work_dir)
    except FileNotFoundError:
        prepare_payload = {}
    if not isinstance(prepare_payload, dict):
        prepare_payload = {}

    quality_payload = compute_final_quality_checks_fn(
        work_dir,
        output_md,
        update_prepare_state_fields=update_prepare_state_fields,
    )
    contract_errors = contract_errors_for_quality_fn(prepare_payload, quality_payload)
    return {
        "prepare_payload": prepare_payload,
        "quality_payload": quality_payload,
        "contract_errors": contract_errors,
        "assemble_completed": not contract_errors,
        "quality_checks_path": str(quality_checks_path(work_dir)),
    }
