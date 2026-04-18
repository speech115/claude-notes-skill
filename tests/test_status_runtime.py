import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
import sys

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.status_runtime import build_status_payload


class StatusRuntimeTests(unittest.TestCase):
    def test_build_status_payload_prefers_observed_stage_statuses_over_stale_prepare_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            (work_dir / "chunk_A_block_01.md").write_text("## Block\n", encoding="utf-8")
            (work_dir / "manifest_chunk_A.tsv").write_text(
                "block_file\ttimestamp_start\ttimestamp_end\ttopic\tprimary_claim\tnames\tresources\tcase_title\thas_dialogue\tquote_text\taction_now\taction_check\taction_avoid\tquotes_count\tcases\n",
                encoding="utf-8",
            )
            (work_dir / "tldr.md").write_text("1. Test\n", encoding="utf-8")

            prepare_payload = {
                "fingerprint": "abc123",
                "execution_mode": "single",
                "content_mode": "monologue",
                "chunk_plan": [{"id": "A"}],
                "stage_hints": {"speaker_identification": "skip"},
                "stage_statuses": {
                    "speaker_identification": "skipped",
                    "extraction": "missing",
                    "tldr": "missing",
                    "assemble": "failed",
                },
            }

            with (
                mock.patch("notes_runner_lib.status_runtime.load_prepare_payload", return_value=prepare_payload),
                mock.patch("notes_runner_lib.status_runtime.bundle_dir_from_work_dir", return_value=None),
                mock.patch("notes_runner_lib.status_runtime.load_bundle_state", return_value={}),
            ):
                payload = build_status_payload(work_dir)

            self.assertEqual(payload["stages"]["extraction"]["status"], "ready")
            self.assertEqual(payload["stages"]["tldr"]["status"], "ready")
            self.assertEqual(
                payload["stage_statuses"],
                {
                    "speaker_identification": "skipped",
                    "extraction": "ready",
                    "tldr": "ready",
                    "assemble": "failed",
                },
            )


if __name__ == "__main__":
    unittest.main()
