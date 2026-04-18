import argparse
import io
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.assemble_shell_runtime import (
    AssembleShellDependencies,
    prepare_assemble_shell_context,
    run_assemble_shell,
)


class AssembleShellRuntimeTests(unittest.TestCase):
    def test_prepare_assemble_shell_context_sets_outputs_and_run_context(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            script_path = tmp_path / "assemble.sh"
            script_path.write_text("#!/bin/bash\n", encoding="utf-8")
            args = argparse.Namespace(
                work_dir=str(tmp_path / "work"),
                output_md=str(tmp_path / "out" / "note.md"),
                output_html=str(tmp_path / "out" / "note.html"),
                title="Test note",
            )

            context = prepare_assemble_shell_context(
                args,
                deps=AssembleShellDependencies(
                    assemble_script=script_path,
                    ensure_dir=lambda path, label: path,
                    merge_manifest_parts=lambda work_dir: None,
                    build_deterministic_appendix=lambda work_dir: work_dir / "appendix.md",
                    start_bundle_run=lambda bundle_dir, command, state_seed: {"run_id": "run-1", "command": command, "state_seed": state_seed},
                    subprocess_run=lambda **kwargs: None,  # unused
                    handle_assemble_shell_failure=lambda **kwargs: None,
                    update_prepare_state_fields=lambda work_dir, updates: None,
                    write_stage_sentinel=lambda path, payload: None,
                    append_trace_event=lambda *args, **kwargs: None,
                    record_bundle_stage_metric=lambda *args, **kwargs: None,
                    finish_bundle_run=lambda *args, **kwargs: None,
                    ms_since=lambda started_at: 0,
                    stderr_sink=io.StringIO(),
                ),
            )

            self.assertEqual(context.output_md.name, "note.md")
            self.assertEqual(context.output_html.name, "note.html")
            self.assertEqual(context.bundle_dir, context.output_html.parent)
            self.assertEqual(context.run_context["command"], "assemble")

    def test_run_assemble_shell_routes_failures_into_handler(self) -> None:
        failure_calls: list[dict] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            script_path = tmp_path / "assemble.sh"
            script_path.write_text("#!/bin/bash\n", encoding="utf-8")
            args = argparse.Namespace(
                work_dir=str(tmp_path / "work"),
                output_md=str(tmp_path / "out" / "note.md"),
                output_html=str(tmp_path / "out" / "note.html"),
                title="Test note",
            )
            deps = AssembleShellDependencies(
                assemble_script=script_path,
                ensure_dir=lambda path, label: path,
                merge_manifest_parts=lambda work_dir: None,
                build_deterministic_appendix=lambda work_dir: work_dir / "appendix.md",
                start_bundle_run=lambda bundle_dir, command, state_seed: {"run_id": "run-1", "command": command, "state_seed": state_seed},
                subprocess_run=lambda *args, **kwargs: subprocess.CompletedProcess(args[0], 9, stdout="", stderr="boom"),
                handle_assemble_shell_failure=lambda **kwargs: failure_calls.append(kwargs),
                update_prepare_state_fields=lambda work_dir, updates: None,
                write_stage_sentinel=lambda path, payload: None,
                append_trace_event=lambda *args, **kwargs: None,
                record_bundle_stage_metric=lambda *args, **kwargs: None,
                finish_bundle_run=lambda *args, **kwargs: None,
                ms_since=lambda started_at: 13,
                stderr_sink=io.StringIO(),
            )
            context = prepare_assemble_shell_context(args, deps=deps)

            exit_code = run_assemble_shell(args, context=context, deps=deps)

        self.assertEqual(exit_code, 9)
        self.assertEqual(failure_calls[0]["work_dir"], context.work_dir)
        self.assertEqual(failure_calls[0]["result"].returncode, 9)


if __name__ == "__main__":
    unittest.main()
