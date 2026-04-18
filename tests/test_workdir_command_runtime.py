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

from notes_runner_lib.workdir_command_runtime import (
    AppendixCommandDependencies,
    ReplaceSpeakersCommandDependencies,
    StatusCommandDependencies,
    TldrCommandDependencies,
    run_build_tldr_command,
    run_ensure_appendix_command,
    run_replace_speakers_command,
    run_status_command,
)


class WorkdirCommandRuntimeTests(unittest.TestCase):
    def test_run_status_command_emits_json_payload(self) -> None:
        stdout_buffer = io.StringIO()

        exit_code = run_status_command(
            argparse.Namespace(work_dir="/tmp/work", json=True),
            deps=StatusCommandDependencies(
                ensure_dir=lambda path, label: path,
                build_status=lambda work_dir: {
                    "work_dir": str(work_dir),
                    "next_action": "assemble",
                    "exists": {"plan": True},
                    "counts": {"chunks": 2},
                },
                stdout=stdout_buffer,
            ),
        )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_buffer.getvalue())
        self.assertEqual(payload["next_action"], "assemble")

    def test_run_build_tldr_command_records_metric(self) -> None:
        stdout_buffer = io.StringIO()
        metric_calls: list[tuple[Path, str, int, str]] = []

        exit_code = run_build_tldr_command(
            argparse.Namespace(work_dir="/tmp/work", json=False),
            deps=TldrCommandDependencies(
                ensure_dir=lambda path, label: path,
                build_tldr_deterministically=lambda work_dir: {"tldr_path": str(work_dir / "tldr.md")},
                bundle_dir_from_work_dir=lambda work_dir: work_dir / "bundle",
                record_bundle_stage_metric=lambda bundle, stage, duration_ms, strategy=None: metric_calls.append(
                    (bundle, stage, duration_ms, strategy)
                ),
                ms_since=lambda started_at: 17,
                stdout=stdout_buffer,
            ),
        )

        self.assertEqual(exit_code, 0)
        self.assertIn("TL;DR:", stdout_buffer.getvalue())
        self.assertEqual(metric_calls[0][1], "tldr")
        self.assertEqual(metric_calls[0][3], "deterministic-merge")

    def test_run_replace_speakers_command_writes_sentinel_and_duration(self) -> None:
        stdout_buffer = io.StringIO()
        sentinel_payloads: list[tuple[Path, dict]] = []
        metric_calls: list[tuple[Path, str, int]] = []

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            exit_code = run_replace_speakers_command(
                argparse.Namespace(work_dir=str(work_dir), json=True),
                deps=ReplaceSpeakersCommandDependencies(
                    ensure_dir=lambda path, label: path,
                    replace_speakers=lambda work: {"modified": 3, "mappings": 2},
                    stage_sentinel_path=lambda work, stage: work / "stages" / f"{stage}.json",
                    write_stage_sentinel=lambda path, payload: sentinel_payloads.append((path, payload)),
                    bundle_dir_from_work_dir=lambda work: work / "bundle",
                    record_bundle_stage_metric=lambda bundle, stage, duration_ms, **kwargs: metric_calls.append(
                        (bundle, stage, duration_ms)
                    ),
                    ms_since=lambda started_at: 21,
                    iso_now=lambda: "2026-04-18T20:00:00+04:00",
                    stdout=stdout_buffer,
                ),
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_buffer.getvalue())
        self.assertEqual(payload["duration_ms"], 21)
        self.assertTrue(payload["sentinel"].endswith("replace-speakers.json"))
        self.assertEqual(sentinel_payloads[0][1]["stage"], "replace-speakers")
        self.assertEqual(metric_calls[0][1], "replace-speakers")

    def test_run_ensure_appendix_command_emits_json_payload(self) -> None:
        stdout_buffer = io.StringIO()

        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            appendix_path = work_dir / "appendix.md"
            manifest_path = work_dir / "manifest.tsv"
            exit_code = run_ensure_appendix_command(
                argparse.Namespace(work_dir=str(work_dir), json=True),
                deps=AppendixCommandDependencies(
                    ensure_dir=lambda path, label: path,
                    merge_manifest_parts=lambda work: manifest_path,
                    build_deterministic_appendix=lambda work: appendix_path,
                    stdout=stdout_buffer,
                ),
            )

        self.assertEqual(exit_code, 0)
        payload = json.loads(stdout_buffer.getvalue())
        self.assertEqual(payload["appendix_path"], str(appendix_path))
        self.assertEqual(payload["manifest_path"], str(manifest_path))
        self.assertTrue(payload["generated"])


if __name__ == "__main__":
    unittest.main()
