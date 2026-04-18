import json
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.prepare_logic_runtime import (
    PrepareLogicDependencies,
    execution_mode_for_total_chunks,
    prepare_fingerprint_for_files,
    run_prepare_logic,
)


def _cleanup_text(value: str) -> str:
    return " ".join((value or "").strip().split())


def _work_prompt_dir(work_dir: Path, *, create: bool = False) -> Path:
    path = work_dir / "prompts"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _work_stage_dir(work_dir: Path, *, create: bool = False) -> Path:
    path = work_dir / "stages"
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def _stage_sentinel_path(work_dir: Path, stage_name: str, *, chunk_id: str | None = None) -> Path:
    suffix = f"{stage_name}-{chunk_id}.json" if chunk_id else f"{stage_name}.json"
    return _work_stage_dir(work_dir, create=True) / suffix


def _load_json_if_exists(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def _format_mmss(seconds_value: object) -> str:
    total_seconds = int(float(seconds_value))
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


class PrepareLogicRuntimeTests(unittest.TestCase):
    def _deps(self, *, trace_events: list[tuple[str, dict]]) -> PrepareLogicDependencies:
        return PrepareLogicDependencies(
            cleanup_title_text=_cleanup_text,
            cleanup_person_hint=_cleanup_text,
            humanize_path_title_hint=_cleanup_text,
            is_informative_title=lambda value: bool(_cleanup_text(value)),
            is_informative_person_hint=lambda value: bool(_cleanup_text(value)),
            render_source_hint_lines=lambda hints: [f"hint: {hints['author_hint']}"] if isinstance(hints, dict) and hints.get("author_hint") else [],
            duration_seconds_override_from_source_hints=lambda hints: int(hints.get("duration_seconds") or 0) if isinstance(hints, dict) else 0,
            effective_duration_seconds_for_meta=lambda meta, hints=None: int(hints.get("duration_seconds") or 0) if isinstance(hints, dict) and hints.get("duration_seconds") else 0,
            effective_duration_estimate_for_meta=lambda meta, hints=None: "12:34" if isinstance(hints, dict) and hints.get("duration_seconds") else "unknown",
            min_blocks_for_chunk=lambda **kwargs: 1,
            prepare_effective_speaker_stage=lambda files, speaker_stage, speaker_reason, source_hints=None: (
                "skip",
                "stub speaker stage",
                "monologue",
                "stub content mode",
            ),
            execution_mode_for_plan=lambda total_chunks, *, content_mode, duration_seconds=0: "single" if total_chunks <= 1 else "multi",
            build_note_contract=lambda **kwargs: {
                "header": {"format_label": "лекция"},
                "blocks": {
                    "theses_min": 5,
                    "theses_max": 8,
                    "meaning_section": "optional",
                    "case_section": "optional",
                    "detail_profile": "standard",
                    "quote_max_per_block": 1,
                },
                "tldr": {"min_items": 5, "max_items": 8},
                "enforce_on_assemble": True,
            },
            build_prepare_quality_checks=lambda **kwargs: {"prepare": {"ok": True}, "final": {}},
            note_contract_path=lambda work_dir: work_dir / "note-contract.json",
            quality_checks_path=lambda work_dir: work_dir / "quality-checks.json",
            work_prompt_dir=_work_prompt_dir,
            work_stage_dir=_work_stage_dir,
            stage_sentinel_path=_stage_sentinel_path,
            write_stage_sentinel=_write_json,
            append_trace_event=lambda work_dir, event, **payload: trace_events.append((event, payload)),
            iso_now=lambda: "2026-04-18T00:00:00+04:00",
            ms_since=lambda started_at: 321,
            write_json=_write_json,
            write_text=_write_text,
            load_json_if_exists=_load_json_if_exists,
            format_label_for_content_mode=lambda mode: "лекция",
            format_mmss=_format_mmss,
            script_path=REPO_ROOT / "scripts" / "notes-runner",
            header_seed_filename="header-seed.json",
            stage_state_dirname="stages",
        )

    def test_prepare_fingerprint_for_files_returns_meta_and_short_hash(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            transcript = Path(tmp_dir) / "transcript.md"
            transcript.write_text("*00:01* hello\n*00:02* world\n", encoding="utf-8")

            meta, fingerprint = prepare_fingerprint_for_files([transcript], deps=self._deps(trace_events=[]))

            self.assertEqual(len(meta), 1)
            self.assertEqual(meta[0].path, transcript.resolve())
            self.assertEqual(meta[0].lines, 2)
            self.assertEqual(len(fingerprint), 12)

    def test_run_prepare_logic_writes_core_artifacts_and_trace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            transcript = Path(tmp_dir) / "lecture.md"
            transcript.write_text(
                "\n".join(
                    f"*00:{index:02d}* ясная мысль номер {index}"
                    for index in range(1, 11)
                )
                + "\n",
                encoding="utf-8",
            )
            trace_events: list[tuple[str, dict]] = []

            result = run_prepare_logic(
                [transcript],
                source_hints={"author_hint": "Alice", "duration_seconds": 754},
                deps=self._deps(trace_events=trace_events),
            )

            work_dir = Path(result["work_dir"])
            self.assertTrue(work_dir.is_dir())
            self.assertEqual(result["execution_mode"], "single")
            self.assertEqual(result["content_mode"], "monologue")
            self.assertEqual(result["prepare_duration_ms"], 321)

            state_payload = json.loads((work_dir / "prepare_state.json").read_text(encoding="utf-8"))
            plan_payload = json.loads((work_dir / "prepare_plan.json").read_text(encoding="utf-8"))
            self.assertEqual(state_payload["fingerprint"], result["fingerprint"])
            self.assertEqual(state_payload["telemetry"]["prepare_duration_ms"], 321)
            self.assertEqual(state_payload["source_identity"]["author_hint"], "Alice")
            self.assertEqual(plan_payload["execution_mode"], "single")
            self.assertTrue((work_dir / "prepare_report.txt").is_file())
            self.assertTrue((work_dir / "prescan_context.txt").is_file())
            self.assertTrue((work_dir / "note-contract.json").is_file())
            self.assertTrue((work_dir / "quality-checks.json").is_file())
            self.assertTrue((work_dir / "prompts" / "extract-A.md").is_file())
            self.assertTrue((work_dir / "prompts" / "header.md").is_file())
            self.assertTrue((work_dir / "stages" / "prepare.json").is_file())
            self.assertEqual(trace_events[0][0], "prepare.completed")
            self.assertEqual(trace_events[0][1]["execution_mode"], "single")

    def test_execution_mode_for_total_chunks_delegates_to_dependency(self) -> None:
        deps = self._deps(trace_events=[])
        self.assertEqual(execution_mode_for_total_chunks(1, deps=deps), "single")
        self.assertEqual(execution_mode_for_total_chunks(4, deps=deps), "multi")


if __name__ == "__main__":
    unittest.main()
