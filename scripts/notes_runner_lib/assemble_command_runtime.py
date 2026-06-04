from __future__ import annotations

import argparse
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO

from .assemble_finalize_runtime import AssembleFinalizeDependencies, finalize_assemble_success
from .assemble_runtime import build_assemble_success_context
from .assemble_shell_runtime import (
    AssembleShellDependencies,
    prepare_assemble_shell_context,
    run_assemble_shell,
)
from .telegram_assemble_runtime import resolve_assemble_telegram_delivery


@dataclass(frozen=True)
class AssembleCommandDependencies:
    assemble_script: Path
    notes_config_path: Path
    ensure_dir: Callable[[Path, str], Path]
    merge_manifest_parts: Callable[..., object]
    build_deterministic_appendix: Callable[..., object]
    start_bundle_run: Callable[..., dict]
    handle_assemble_shell_failure: Callable[..., int]
    update_prepare_state_fields: Callable[[Path, dict], None]
    write_stage_sentinel: Callable[[Path, dict], None]
    append_trace_event: Callable[..., Path]
    record_bundle_stage_metric: Callable[..., None]
    finish_bundle_run: Callable[..., object]
    ms_since: Callable[[float], int]
    build_assemble_success_context: Callable[..., dict]
    compute_final_quality_checks: Callable[..., dict]
    contract_errors_for_quality: Callable[..., list[str]]
    resolve_digest_runner: Callable[[], Path]
    run_command: Callable[..., subprocess.CompletedProcess[str]]
    env_flag_enabled: Callable[[str], bool]
    stage_sentinel_path: Callable[..., Path]
    quality_checks_path: Callable[[Path], Path]
    iso_now: Callable[[], str]
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]]
    stdout: TextIO
    stderr: TextIO


def cmd_assemble(args: argparse.Namespace, *, deps: AssembleCommandDependencies) -> int:
    shell_deps = AssembleShellDependencies(
        assemble_script=deps.assemble_script,
        ensure_dir=deps.ensure_dir,
        merge_manifest_parts=deps.merge_manifest_parts,
        build_deterministic_appendix=deps.build_deterministic_appendix,
        start_bundle_run=deps.start_bundle_run,
        subprocess_run=deps.subprocess_run,
        handle_assemble_shell_failure=deps.handle_assemble_shell_failure,
        update_prepare_state_fields=deps.update_prepare_state_fields,
        write_stage_sentinel=deps.write_stage_sentinel,
        append_trace_event=deps.append_trace_event,
        record_bundle_stage_metric=deps.record_bundle_stage_metric,
        finish_bundle_run=deps.finish_bundle_run,
        ms_since=deps.ms_since,
        stderr_sink=deps.stderr,
    )
    shell_context = prepare_assemble_shell_context(args, deps=shell_deps)
    shell_result = run_assemble_shell(args, context=shell_context, deps=shell_deps)
    if isinstance(shell_result, int):
        return shell_result

    work_dir = shell_context.work_dir
    output_md = shell_context.output_md
    output_html = shell_context.output_html
    bundle_dir = shell_context.bundle_dir
    run_context = shell_context.run_context

    success_context = deps.build_assemble_success_context(
        work_dir,
        output_md,
        update_prepare_state_fields=deps.update_prepare_state_fields,
        compute_final_quality_checks_fn=deps.compute_final_quality_checks,
        contract_errors_for_quality_fn=deps.contract_errors_for_quality,
    )
    contract_errors = list(success_context.get("contract_errors") or [])
    telegram_delivery = resolve_assemble_telegram_delivery(
        output_md=output_md,
        output_html=output_html,
        title=args.title,
        contract_errors=contract_errors,
        config_path=deps.notes_config_path,
        chat_override=getattr(args, "send_to", None),
        skip_telegram=bool(getattr(args, "skip_telegram", False)),
        force_telegram_resend=bool(getattr(args, "force_telegram_resend", False)),
        resolve_digest_runner=deps.resolve_digest_runner,
        run_command=deps.run_command,
        env_flag_enabled=deps.env_flag_enabled,
    )
    duration_ms = deps.ms_since(shell_context.started_at)
    return finalize_assemble_success(
        args=args,
        work_dir=work_dir,
        bundle_dir=bundle_dir,
        output_md=output_md,
        output_html=output_html,
        duration_ms=duration_ms,
        run_context=run_context,
        success_context=success_context,
        telegram_delivery=telegram_delivery,
        deps=AssembleFinalizeDependencies(
            stage_sentinel_path=deps.stage_sentinel_path,
            write_stage_sentinel=deps.write_stage_sentinel,
            quality_checks_path=deps.quality_checks_path,
            update_prepare_state_fields=deps.update_prepare_state_fields,
            record_bundle_stage_metric=deps.record_bundle_stage_metric,
            finish_bundle_run=deps.finish_bundle_run,
            iso_now=deps.iso_now,
            stdout=deps.stdout,
            stderr=deps.stderr,
        ),
    )


__all__ = ["AssembleCommandDependencies", "cmd_assemble"]