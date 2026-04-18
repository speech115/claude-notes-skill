from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class AssembleShellContext:
    work_dir: Path
    output_md: Path
    output_html: Path
    bundle_dir: Path
    started_at: float
    run_context: dict


@dataclass(frozen=True)
class AssembleShellDependencies:
    assemble_script: Path
    ensure_dir: Callable[[Path, str], Path]
    merge_manifest_parts: Callable[[Path], Path | None]
    build_deterministic_appendix: Callable[[Path], Path]
    start_bundle_run: Callable[..., dict]
    subprocess_run: Callable[..., subprocess.CompletedProcess[str]]
    handle_assemble_shell_failure: Callable[..., object]
    update_prepare_state_fields: Callable[[Path, dict], None]
    write_stage_sentinel: Callable[[Path, dict], None]
    append_trace_event: Callable[..., object]
    record_bundle_stage_metric: Callable[..., object]
    finish_bundle_run: Callable[..., object]
    ms_since: Callable[[float], int]
    stderr_sink: TextIO | None = None


def prepare_assemble_shell_context(
    args: argparse.Namespace,
    *,
    deps: AssembleShellDependencies,
) -> AssembleShellContext:
    if not deps.assemble_script.is_file():
        raise FileNotFoundError(f"Assemble script not found: {deps.assemble_script}")
    work_dir = deps.ensure_dir(Path(args.work_dir), "Work directory")
    deps.merge_manifest_parts(work_dir)
    deps.build_deterministic_appendix(work_dir)
    output_md = Path(args.output_md).expanduser().resolve()
    output_html = Path(args.output_html).expanduser().resolve()
    output_md.parent.mkdir(parents=True, exist_ok=True)
    output_html.parent.mkdir(parents=True, exist_ok=True)
    started_at = time.monotonic()
    bundle_dir = output_html.parent
    run_context = deps.start_bundle_run(
        bundle_dir,
        command="assemble",
        state_seed={
            "title": args.title,
            "outputs": {
                "markdown": str(output_md),
                "html": str(output_html),
            },
        },
    )
    return AssembleShellContext(
        work_dir=work_dir,
        output_md=output_md,
        output_html=output_html,
        bundle_dir=bundle_dir,
        started_at=started_at,
        run_context=run_context,
    )


def run_assemble_shell(
    args: argparse.Namespace,
    *,
    context: AssembleShellContext,
    deps: AssembleShellDependencies,
) -> subprocess.CompletedProcess[str] | int:
    result = deps.subprocess_run(
        ["bash", str(deps.assemble_script), str(context.work_dir), str(context.output_md), str(context.output_html), args.title],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode == 0:
        return result

    deps.handle_assemble_shell_failure(
        work_dir=context.work_dir,
        bundle_dir=context.bundle_dir,
        output_md=context.output_md,
        output_html=context.output_html,
        started_at=context.started_at,
        result=result,
        run_context=context.run_context,
        update_prepare_state_fields=deps.update_prepare_state_fields,
        write_stage_sentinel=deps.write_stage_sentinel,
        append_trace_event=deps.append_trace_event,
        record_bundle_stage_metric=deps.record_bundle_stage_metric,
        finish_bundle_run=deps.finish_bundle_run,
        ms_since=deps.ms_since,
        stderr_sink=deps.stderr_sink if deps.stderr_sink is not None else sys.stderr,
    )
    return result.returncode


__all__ = [
    "AssembleShellContext",
    "AssembleShellDependencies",
    "prepare_assemble_shell_context",
    "run_assemble_shell",
]
