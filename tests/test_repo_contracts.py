import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]


class RepoContractTests(unittest.TestCase):
    def test_runner_uses_split_local_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "local_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.local_command_runtime import", text)

    def test_runner_uses_split_audio_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "audio_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.audio_command_runtime import", text)

    def test_runner_uses_split_auto_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "auto_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.auto_command_runtime import", text)

    def test_runner_uses_split_youtube_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "youtube_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.youtube_command_runtime import", text)

    def test_runner_uses_split_telegram_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "telegram_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.telegram_command_runtime import", text)

    def test_runner_uses_split_source_ingest_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "source_ingest_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.source_ingest_runtime import", text)

    def test_runner_uses_split_media_transcribe_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "media_transcribe_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.media_transcribe_runtime import", text)

    def test_runner_uses_split_parser_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "parser_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.parser_runtime import", text)

    def test_runner_uses_split_transcript_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "transcript_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.transcript_runtime import", text)

    def test_runner_uses_split_doctor_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "doctor_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.doctor_runtime import", text)

    def test_runner_uses_split_doctor_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "doctor_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.doctor_command_runtime import", text)

    def test_runner_uses_split_note_contract_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "note_contract_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.note_contract_runtime import", text)

    def test_runner_uses_split_batch_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "batch_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.batch_command_runtime import", text)

    def test_runner_uses_split_batch_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "batch_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.batch_runtime import", text)

    def test_runner_uses_split_speaker_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "speaker_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.speaker_runtime import", text)

    def test_runner_uses_split_tldr_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "tldr_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.tldr_runtime import", text)

    def test_runner_uses_split_appendix_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "appendix_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.appendix_runtime import", text)

    def test_runner_uses_split_telegram_assemble_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "telegram_assemble_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.telegram_assemble_runtime import", text)

    def test_runner_uses_split_assemble_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "assemble_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.assemble_runtime import", text)

    def test_runner_uses_split_assemble_shell_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "assemble_shell_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.assemble_shell_runtime import", text)

    def test_runner_uses_split_assemble_finalize_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "assemble_finalize_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.assemble_finalize_runtime import", text)

    def test_runner_uses_split_quality_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "quality_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.quality_runtime import", text)

    def test_runner_uses_split_status_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "status_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.status_runtime import", text)

    def test_runner_uses_split_source_hint_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "source_hint_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.source_hint_runtime import", text)

    def test_runner_uses_split_prepare_bundle_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "prepare_bundle_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.prepare_bundle_runtime import", text)

    def test_runner_uses_split_run_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "run_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.run_runtime import", text)

    def test_runner_uses_split_prepare_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "prepare_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.prepare_runtime import", text)

    def test_runner_uses_split_prepare_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "prepare_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.prepare_command_runtime import", text)

    def test_runner_uses_split_workdir_command_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "workdir_command_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.workdir_command_runtime import", text)

    def test_runner_uses_split_prepare_transcript_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "prepare_transcript_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.prepare_transcript_runtime import", text)

    def test_runner_uses_split_prepare_logic_runtime_module(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue((package_dir / "prepare_logic_runtime.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.prepare_logic_runtime import", text)

    def test_runner_uses_split_runtime_modules(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue(package_dir.is_dir())
        self.assertTrue((package_dir / "__init__.py").is_file())
        text = (REPO_ROOT / "scripts" / "notes-runner").read_text(encoding="utf-8")
        self.assertIn("from notes_runner_lib.common import", text)
        self.assertIn("from notes_runner_lib.bundle_runtime import", text)

    def test_regression_loader_avoids_hardcoded_user_path(self) -> None:
        text = (REPO_ROOT / "tests" / "test_notes_runner_regressions.py").read_text(encoding="utf-8")
        self.assertNotIn("/Users/sereja/Projects/products/notes-skill", text)

    def test_skill_contract_is_vendor_neutral(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        forbidden = [
            "CLAUDE_SKILL_DIR",
            "sonnet agent",
            "from Claude",
            "from this skill. Telegram is best-effort inside `assemble` only.",
        ]
        for marker in forbidden:
            self.assertNotIn(marker, text)

    def test_quick_suite_no_longer_depends_on_download_bundles(self) -> None:
        text = (REPO_ROOT / "scripts" / "test-pipeline.sh").read_text(encoding="utf-8")
        self.assertNotIn("$HOME/Downloads/конспекты", text)
        self.assertNotIn("BUNDLE_SHORT=", text)
        self.assertNotIn("BUNDLE_MEDIUM=", text)
        self.assertNotIn("BUNDLE_LONG=", text)


if __name__ == "__main__":
    unittest.main()
