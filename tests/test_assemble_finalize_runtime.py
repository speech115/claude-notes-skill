import argparse
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.assemble_finalize_runtime import (
    AssembleFinalizeDependencies,
    finalize_assemble_success,
)


class AssembleFinalizeRuntimeTests(unittest.TestCase):
    def test_finalize_assemble_success_emits_json_and_records_stage(self) -> None:
        stdout_buffer = io.StringIO()
        sentinel_payloads: list[tuple[Path, dict]] = []
        metric_calls: list[tuple[Path, str, int]] = []
        finish_calls: list[dict] = []
        update_calls: list[tuple[Path, dict]] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "work"
            bundle_dir = Path(tmp_dir) / "bundle"
            output_md = bundle_dir / "note.md"
            output_html = bundle_dir / "note.html"
            exit_code = finalize_assemble_success(
                args=argparse.Namespace(json=True),
                work_dir=work_dir,
                bundle_dir=bundle_dir,
                output_md=output_md,
                output_html=output_html,
                duration_ms=33,
                run_context={"run_id": "run-1"},
                success_context={
                    "prepare_payload": {"fingerprint": "abc", "prepare_state_path": str(work_dir / "prepare_state.json")},
                    "quality_payload": {"final": {"ok": True}},
                    "contract_errors": [],
                    "quality_checks_path": str(work_dir / "quality-checks.json"),
                },
                telegram_delivery={"attempted": True, "success": True},
                deps=AssembleFinalizeDependencies(
                    stage_sentinel_path=lambda work, stage: work / "stages" / f"{stage}.json",
                    write_stage_sentinel=lambda path, payload: sentinel_payloads.append((path, payload)),
                    quality_checks_path=lambda work: work / "quality-checks.json",
                    update_prepare_state_fields=lambda work, updates: update_calls.append((work, updates)),
                    record_bundle_stage_metric=lambda bundle, stage, duration_ms, **kwargs: metric_calls.append((bundle, stage, duration_ms)),
                    finish_bundle_run=lambda bundle, run_context, **kwargs: finish_calls.append(kwargs),
                    iso_now=lambda: "2026-04-18T21:00:00+04:00",
                    stdout=stdout_buffer,
                    stderr=io.StringIO(),
                ),
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_buffer.getvalue())
        self.assertEqual(payload["duration_ms"], 33)
        self.assertEqual(payload["contract_errors"], [])
        self.assertTrue(payload["telegram_delivery"]["success"])
        self.assertEqual(sentinel_payloads[0][1]["stage"], "assemble")
        self.assertTrue(sentinel_payloads[0][1]["completed"])
        self.assertEqual(metric_calls[0][1], "assemble")
        self.assertEqual(update_calls[0][1]["stage_statuses"]["assemble"], "ready")
        self.assertEqual(finish_calls[0]["status"], "assembled")

    def test_finalize_assemble_success_returns_2_on_contract_errors(self) -> None:
        stderr_buffer = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "work"
            bundle_dir = Path(tmp_dir) / "bundle"
            output_md = bundle_dir / "note.md"
            output_html = bundle_dir / "note.html"
            exit_code = finalize_assemble_success(
                args=argparse.Namespace(json=False),
                work_dir=work_dir,
                bundle_dir=bundle_dir,
                output_md=output_md,
                output_html=output_html,
                duration_ms=44,
                run_context={"run_id": "run-2"},
                success_context={
                    "prepare_payload": {"fingerprint": "abc", "prepare_state_path": str(work_dir / "prepare_state.json")},
                    "quality_payload": {"final": {"ok": False}},
                    "contract_errors": ["missing tldr"],
                    "quality_checks_path": str(work_dir / "quality-checks.json"),
                },
                telegram_delivery={"attempted": False, "success": False},
                deps=AssembleFinalizeDependencies(
                    stage_sentinel_path=lambda work, stage: work / "stages" / f"{stage}.json",
                    write_stage_sentinel=lambda path, payload: None,
                    quality_checks_path=lambda work: work / "quality-checks.json",
                    update_prepare_state_fields=lambda work, updates: None,
                    record_bundle_stage_metric=lambda bundle, stage, duration_ms, **kwargs: None,
                    finish_bundle_run=lambda bundle, run_context, **kwargs: None,
                    iso_now=lambda: "2026-04-18T21:00:00+04:00",
                    stdout=io.StringIO(),
                    stderr=stderr_buffer,
                ),
            )

        self.assertEqual(exit_code, 2)
        self.assertIn("ASSEMBLE CONTRACT ERROR: missing tldr", stderr_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
