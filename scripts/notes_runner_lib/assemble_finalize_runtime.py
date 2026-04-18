from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class AssembleFinalizeDependencies:
    stage_sentinel_path: Callable[[Path, str], Path]
    write_stage_sentinel: Callable[[Path, dict], None]
    quality_checks_path: Callable[[Path], Path]
    update_prepare_state_fields: Callable[[Path, dict], None]
    record_bundle_stage_metric: Callable[..., object]
    finish_bundle_run: Callable[..., object]
    iso_now: Callable[[], str]
    stdout: TextIO | None = None
    stderr: TextIO | None = None


def finalize_assemble_success(
    *,
    args: argparse.Namespace,
    work_dir: Path,
    bundle_dir: Path,
    output_md: Path,
    output_html: Path,
    duration_ms: int,
    run_context: dict,
    success_context: dict,
    telegram_delivery: dict,
    deps: AssembleFinalizeDependencies,
) -> int:
    prepare_payload = success_context["prepare_payload"] if isinstance(success_context.get("prepare_payload"), dict) else {}
    quality_payload = success_context["quality_payload"] if isinstance(success_context.get("quality_payload"), dict) else {}
    contract_errors = list(success_context.get("contract_errors") or [])
    sentinel_path = deps.stage_sentinel_path(work_dir, "assemble")
    assemble_completed = not contract_errors
    deps.write_stage_sentinel(
        sentinel_path,
        {
            "stage": "assemble",
            "fingerprint": prepare_payload.get("fingerprint") if isinstance(prepare_payload, dict) else None,
            "completed": assemble_completed,
            "completed_at": deps.iso_now(),
            "duration_ms": duration_ms,
            "output_md": str(output_md),
            "output_html": str(output_html),
            "quality_checks": str(success_context.get("quality_checks_path") or deps.quality_checks_path(work_dir)),
            "contract_errors": contract_errors,
        },
    )
    if isinstance(prepare_payload, dict) and prepare_payload.get("prepare_state_path"):
        deps.update_prepare_state_fields(
            work_dir,
            {"stage_statuses": {"assemble": "ready" if assemble_completed else "failed"}},
        )
    deps.record_bundle_stage_metric(
        bundle_dir,
        "assemble",
        duration_ms,
        output_md=str(output_md),
        output_html=str(output_html),
        telegram_success=telegram_delivery.get("success"),
        contract_ok=assemble_completed,
    )
    deps.finish_bundle_run(
        bundle_dir,
        run_context,
        status="assembled" if assemble_completed else "contract-failed",
        contract_errors=contract_errors,
        quality_payload=quality_payload,
        telegram_delivery=telegram_delivery,
    )

    payload = {
        "work_dir": str(work_dir),
        "output_md": str(output_md),
        "output_html": str(output_html),
        "telegram_delivery": telegram_delivery,
        "quality_checks": quality_payload,
        "contract_errors": contract_errors,
        "duration_ms": duration_ms,
        "sentinel": str(sentinel_path),
    }
    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    stderr = deps.stderr if deps.stderr is not None else sys.stderr
    if contract_errors:
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
            return 2
        for error in contract_errors:
            print(f"ASSEMBLE CONTRACT ERROR: {error}", file=stderr)
        return 2
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=stdout)
        return 0
    print(f"Markdown: {output_md}", file=stdout)
    print(f"HTML: {output_html}", file=stdout)
    if telegram_delivery["attempted"]:
        status = "ok" if telegram_delivery["success"] else "failed"
        print(f"Telegram delivery: {status}", file=stdout)
    return 0


__all__ = ["AssembleFinalizeDependencies", "finalize_assemble_success"]
