import json
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.prepare_transcript_runtime import (
    PrepareTranscriptDependencies,
    load_reusable_prepare_payload,
    run_prepare_for_transcript,
)


class PrepareTranscriptRuntimeTests(unittest.TestCase):
    def test_load_reusable_prepare_payload_marks_payload_reused_and_keeps_work_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "bundle"
            work_dir = bundle_dir / "work"
            work_dir.mkdir(parents=True)
            transcript_path = bundle_dir / "transcript.md"
            transcript_path.write_text("hello\n", encoding="utf-8")

            deps = PrepareTranscriptDependencies(
                resolve_bundle_work_dir=lambda path: work_dir if path == bundle_dir else None,
                load_prepare_payload=lambda path: {"fingerprint": "abc123", "stage_statuses": {"extraction": "missing"}},
                prepare_fingerprint_for_files=lambda files: ([], "abc123"),
                run_prepare_logic=lambda *args, **kwargs: {"work_dir": str(work_dir)},
                enrich_work_dir_with_source_hints=lambda *_args, **_kwargs: None,
            )

            payload = load_reusable_prepare_payload(bundle_dir, transcript_path, deps=deps)

            self.assertIsNotNone(payload)
            self.assertEqual(payload["work_dir"], str(work_dir))
            self.assertTrue(payload["reused"])
            self.assertEqual(payload["stage_statuses"]["extraction"], "missing")

    def test_run_prepare_for_transcript_reuses_payload_and_refreshes_after_source_hints(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "bundle"
            work_dir = bundle_dir / "work"
            work_dir.mkdir(parents=True)
            transcript_path = bundle_dir / "transcript.md"
            transcript_path.write_text("hello\n", encoding="utf-8")

            enrich_calls: list[tuple[Path, dict | None]] = []
            payload_versions = iter(
                [
                    {"fingerprint": "same", "source_identity": {}},
                    {"fingerprint": "same", "source_identity": {"kind": "youtube"}},
                ]
            )

            deps = PrepareTranscriptDependencies(
                resolve_bundle_work_dir=lambda path: work_dir if path == bundle_dir else None,
                load_prepare_payload=lambda path: next(payload_versions),
                prepare_fingerprint_for_files=lambda files: ([], "same"),
                run_prepare_logic=lambda *args, **kwargs: self.fail("run_prepare_logic should not run for reusable payload"),
                enrich_work_dir_with_source_hints=lambda path, source_hints: enrich_calls.append((path, source_hints)),
            )

            payload = run_prepare_for_transcript(
                transcript_path,
                bundle_dir=bundle_dir,
                source_hints={"kind": "youtube"},
                deps=deps,
            )

            self.assertEqual(enrich_calls, [(work_dir.resolve(), {"kind": "youtube"})])
            self.assertEqual(payload["work_dir"], str(work_dir.resolve()))
            self.assertTrue(payload["reused"])
            self.assertEqual(payload["source_identity"], {"kind": "youtube"})

    def test_run_prepare_for_transcript_runs_prepare_logic_when_refresh_requested(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "bundle"
            work_dir = bundle_dir / "fresh-work"
            work_dir.mkdir(parents=True)
            transcript_path = bundle_dir / "transcript.md"
            transcript_path.parent.mkdir(parents=True, exist_ok=True)
            transcript_path.write_text("hello\n", encoding="utf-8")

            run_calls: list[tuple[list[Path], dict | None]] = []
            enrich_calls: list[tuple[Path, dict | None]] = []

            deps = PrepareTranscriptDependencies(
                resolve_bundle_work_dir=lambda path: bundle_dir / "stale-work",
                load_prepare_payload=lambda path: {"fingerprint": "fresh", "payload": "ok"},
                prepare_fingerprint_for_files=lambda files: ([], "stale"),
                run_prepare_logic=lambda files, *, source_hints=None: (
                    run_calls.append((files, source_hints)) or {"work_dir": str(work_dir)}
                ),
                enrich_work_dir_with_source_hints=lambda path, source_hints: enrich_calls.append((path, source_hints)),
            )

            payload = run_prepare_for_transcript(
                transcript_path,
                bundle_dir=bundle_dir,
                refresh=True,
                source_hints={"kind": "telegram"},
                deps=deps,
            )

            self.assertEqual(run_calls, [([transcript_path], {"kind": "telegram"})])
            self.assertEqual(enrich_calls, [(work_dir.resolve(), {"kind": "telegram"})])
            self.assertEqual(payload["work_dir"], str(work_dir.resolve()))
            self.assertFalse(payload["reused"])
            self.assertEqual(payload["payload"], "ok")


if __name__ == "__main__":
    unittest.main()
