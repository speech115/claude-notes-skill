import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.prepare_runtime import build_execution_plan, infer_chunk_status
from notes_runner_lib.prepare_runtime import execution_mode_for_plan


class PrepareRuntimeTests(unittest.TestCase):
    def _write_ready_chunk_files(self, work_dir: Path, chunk_id: str = "A") -> None:
        (work_dir / f"chunk_{chunk_id}_block_01.md").write_text("## Block\n", encoding="utf-8")
        (work_dir / f"manifest_chunk_{chunk_id}.tsv").write_text(
            "block_file\ttimestamp_start\ttimestamp_end\ttopic\tprimary_claim\tnames\tresources\tcase_title\thas_dialogue\tquote_text\taction_now\taction_check\taction_avoid\tquotes_count\tcases\n",
            encoding="utf-8",
        )
        (work_dir / f"summary_chunk_{chunk_id}.md").write_text("1. Summary\n", encoding="utf-8")

    def _planned_chunk(self, work_dir: Path, *, fingerprint: str = "chunk-fp") -> dict:
        return {
            "id": "A",
            "chunk_fingerprint": fingerprint,
            "stage_sentinel_path": str(work_dir / "stages" / "extraction-A.json"),
            "expected_outputs": [
                "manifest_chunk_A.tsv",
                "summary_chunk_A.md",
                "stages/extraction-A.json",
            ],
        }

    def test_execution_mode_routes_five_chunk_conversation_to_micro_multi(self) -> None:
        self.assertEqual(
            execution_mode_for_plan(5, content_mode="conversation", duration_seconds=7080),
            "micro-multi",
        )

    def test_execution_mode_single_means_exactly_one_chunk(self) -> None:
        self.assertEqual(
            execution_mode_for_plan(1, content_mode="monologue", duration_seconds=600),
            "single",
        )

    def test_execution_mode_monologue_fast_path_collapses_two_short_chunks_to_single(self) -> None:
        self.assertEqual(
            execution_mode_for_plan(2, content_mode="monologue", duration_seconds=600),
            "single",
        )

    def test_execution_mode_monologue_two_chunks_without_duration_stays_micro_multi(self) -> None:
        self.assertEqual(
            execution_mode_for_plan(2, content_mode="monologue", duration_seconds=0),
            "micro-multi",
        )

    def test_infer_chunk_status_requires_completed_sentinel(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            stage_dir = work_dir / "stages"
            stage_dir.mkdir()
            self._write_ready_chunk_files(work_dir)
            (stage_dir / "extraction-A.json").write_text(
                '{"stage":"extraction","chunk_id":"A","chunk_fingerprint":"chunk-fp","completed":false}\n',
                encoding="utf-8",
            )

            self.assertEqual(infer_chunk_status(work_dir, "A", self._planned_chunk(work_dir)), "partial")

    def test_infer_chunk_status_requires_summary_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            stage_dir = work_dir / "stages"
            stage_dir.mkdir()
            self._write_ready_chunk_files(work_dir)
            (work_dir / "summary_chunk_A.md").unlink()
            (stage_dir / "extraction-A.json").write_text(
                '{"stage":"extraction","chunk_id":"A","chunk_fingerprint":"chunk-fp","completed":true,"expected_outputs":["manifest_chunk_A.tsv","summary_chunk_A.md","stages/extraction-A.json"]}\n',
                encoding="utf-8",
            )

            self.assertEqual(infer_chunk_status(work_dir, "A", self._planned_chunk(work_dir)), "partial")

    def test_infer_chunk_status_requires_matching_fingerprint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            stage_dir = work_dir / "stages"
            stage_dir.mkdir()
            self._write_ready_chunk_files(work_dir)
            (stage_dir / "extraction-A.json").write_text(
                '{"stage":"extraction","chunk_id":"A","chunk_fingerprint":"old-fp","completed":true,"expected_outputs":["manifest_chunk_A.tsv","summary_chunk_A.md","stages/extraction-A.json"]}\n',
                encoding="utf-8",
            )

            self.assertEqual(infer_chunk_status(work_dir, "A", self._planned_chunk(work_dir)), "stale")

    def test_infer_chunk_status_without_sentinel_is_partial_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir)
            self._write_ready_chunk_files(work_dir)

            self.assertEqual(infer_chunk_status(work_dir, "A", self._planned_chunk(work_dir)), "partial")

    def test_build_execution_plan_skips_optional_speaker_when_no_placeholders_exist(self) -> None:
        chunk_ids = ["A", "B", "C", "D", "E"]
        payload = {
            "execution_mode": "multi",
            "content_mode": "conversation",
            "total_chunks": len(chunk_ids),
            "chunk_plan": [{"id": chunk_id} for chunk_id in chunk_ids],
            "files": [{"markers": 0, "dialogue_cues": 0, "dialogue_speakers": 0, "intro_cues": 0}],
            "totals": {"speaker_markers": 0},
            "prompt_packs": {"tldr_strategy": "agent", "tldr_agent": "/tmp/tldr-agent.md"},
            "header_seed": {},
            "note_contract": {"tldr": {"strategy": "agent", "min_items": 10, "max_items": 14}},
            "quality_checks": {},
        }
        chunk_statuses = {chunk_id: {"status": "ready"} for chunk_id in chunk_ids}
        stages = {
            "speaker_identification": {"hint": "optional", "status": "missing"},
            "extraction": {"status": "ready"},
            "tldr": {"status": "missing"},
            "assemble": {"status": "missing"},
        }

        plan = build_execution_plan(payload, chunk_statuses, stages)

        self.assertEqual(plan["mode"], "micro-multi")
        self.assertFalse(plan["speaker_identification"]["should_run"])
        self.assertFalse(plan["replace_speakers"]["before_tldr"])
        self.assertFalse(plan["replace_speakers"]["after_tldr"])
        self.assertEqual(plan["tldr"]["strategy"], "deterministic-merge")
        self.assertEqual(plan["prompt_packs"]["tldr_strategy"], "deterministic-merge")
        self.assertIsNone(plan["prompt_packs"]["tldr_agent"])
        self.assertEqual(plan["contract"]["tldr_bounds"]["strategy"], "deterministic-merge")
        self.assertEqual(plan["assemble"]["blocked_by"], ["tldr"])

    def test_build_execution_plan_skips_required_speaker_stage_without_labels(self) -> None:
        payload = {
            "execution_mode": "micro-multi",
            "content_mode": "conversation",
            "total_chunks": 4,
            "chunk_plan": [{"id": "A"}],
            "files": [{"markers": 0, "speaker_label_cues": 0}],
            "totals": {"speaker_markers": 0},
            "prompt_packs": {},
            "header_seed": {},
            "note_contract": {},
            "quality_checks": {},
        }
        chunk_statuses = {"A": {"status": "ready"}}
        stages = {
            "speaker_identification": {"hint": "required", "status": "missing"},
            "extraction": {"status": "ready"},
            "tldr": {"status": "missing"},
            "assemble": {"status": "missing"},
        }

        plan = build_execution_plan(payload, chunk_statuses, stages)

        self.assertFalse(plan["speaker_identification"]["should_run"])
        self.assertNotIn("speaker_identification", plan["assemble"]["blocked_by"])
        self.assertEqual(plan["next_action"], "generate-tldr")

    def test_build_execution_plan_keeps_required_speaker_stage_with_speaker_labels(self) -> None:
        payload = {
            "execution_mode": "micro-multi",
            "content_mode": "conversation",
            "total_chunks": 4,
            "chunk_plan": [{"id": "A"}],
            "files": [{"markers": 0, "speaker_label_cues": 2}],
            "totals": {"speaker_markers": 0},
            "prompt_packs": {},
            "header_seed": {},
            "note_contract": {},
            "quality_checks": {},
        }
        chunk_statuses = {"A": {"status": "ready"}}
        stages = {
            "speaker_identification": {"hint": "required", "status": "missing"},
            "extraction": {"status": "ready"},
            "tldr": {"status": "missing"},
            "assemble": {"status": "missing"},
        }

        plan = build_execution_plan(payload, chunk_statuses, stages)

        self.assertTrue(plan["speaker_identification"]["should_run"])
        self.assertIn("speaker_identification", plan["assemble"]["blocked_by"])
        self.assertEqual(plan["next_action"], "speaker-identification")


if __name__ == "__main__":
    unittest.main()
