import os
import ast
import importlib
import importlib.machinery
import importlib.util
import json
import subprocess
import shutil
import sys
import tempfile
import types
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))
RUNNER_PATH = REPO_ROOT / "scripts" / "notes-runner"
EXPECTED_RUNNER_COMMANDS = [
    "prepare",
    "status",
    "replace-speakers",
    "build-tldr",
    "build-header",
    "ensure-appendix",
    "assemble",
    "youtube",
    "local",
    "audio",
    "telegram",
    "auto",
    "batch",
    "doctor",
]
EXPECTED_COMMAND_HANDLERS = {
    "prepare": "cmd_prepare",
    "status": "cmd_status",
    "replace-speakers": "cmd_replace_speakers",
    "build-tldr": "cmd_build_tldr",
    "build-header": "cmd_build_header",
    "ensure-appendix": "cmd_ensure_appendix",
    "assemble": "cmd_assemble",
    "youtube": "cmd_youtube",
    "local": "cmd_local",
    "audio": "cmd_audio",
    "telegram": "cmd_telegram",
    "auto": "cmd_auto",
    "batch": "cmd_batch",
    "doctor": "cmd_doctor",
}
RUNNER_COMPAT_ATTRS = [
    "HEADER_METADATA_LABELS",
    "RateLimitError",
    "_groq_transcribe_single",
    "build_youtube_source_hints",
    "build_parser",
    "build_run_snapshot",
    "call_groq_transcribe",
    "call_parakeet_transcribe",
    "choose_transcribe_backend",
    "cmd_assemble",
    "cmd_audio",
    "cmd_auto",
    "cmd_batch",
    "cmd_local",
    "compute_file_sha256",
    "compute_final_quality_checks",
    "enrich_work_dir_with_source_hints",
    "enrich_work_dir_with_source_hints_impl",
    "execution_mode_for_plan",
    "extract_youtube_metadata",
    "local_backend_language",
    "note_contract_path",
    "parakeet_available",
    "probe_media_duration_seconds",
    "run_checked",
    "run_mlx_whisper",
    "run_mlx_whisper_impl",
    "run_prepare_logic",
    "run_whisperx_diarize",
    "run_whisperx_diarize_impl",
    "update_bundle_run_state",
    "whisper_json_to_transcript_markdown",
    "whisper_json_to_transcript_markdown_impl",
    "whisperx_json_to_transcript_markdown",
    "whisperx_json_to_transcript_markdown_impl",
    "write_json",
]
EXPECTED_RUNNER_RUNTIME_MODULES = [
    "appendix_runtime",
    "assemble_command_runtime",
    "assemble_runtime",
    "audio_command_runtime",
    "auto_command_runtime",
    "batch_command_runtime",
    "batch_runtime",
    "bundle_runtime",
    "cli_runtime",
    "common",
    "digest_runner_runtime",
    "doctor_command_runtime",
    "doctor_runtime",
    "header_runtime",
    "local_command_runtime",
    "media_transcribe_runtime",
    "note_contract_runtime",
    "parser_runtime",
    "prepare_bundle_runtime",
    "prepare_command_runtime",
    "prepare_logic_runtime",
    "prepare_pipeline_runtime",
    "prepare_runtime",
    "prepare_transcript_runtime",
    "quality_runtime",
    "run_runtime",
    "source_hint_runtime",
    "source_ingest_runtime",
    "speaker_runtime",
    "status_runtime",
    "telegram_command_runtime",
    "tldr_runtime",
    "transcribe_backends_runtime",
    "transcript_runtime",
    "workdir_command_runtime",
    "youtube_command_runtime",
]


def load_runner_module() -> types.ModuleType:
    loader = importlib.machinery.SourceFileLoader("notes_runner_contract_test", str(RUNNER_PATH))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    if spec is None:
        raise RuntimeError("Failed to build import spec for notes-runner")
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


class RepoContractTests(unittest.TestCase):
    def seed_local_only_live_state(self, target: Path) -> None:
        target.mkdir(parents=True, exist_ok=True)
        (target / "config.json").write_text('{"local": "preserve"}\n', encoding="utf-8")
        (target / "backups").mkdir(parents=True, exist_ok=True)
        (target / "backups" / "marker.txt").write_text("preserve backups\n", encoding="utf-8")
        (target / ".ai" / "runtime").mkdir(parents=True, exist_ok=True)
        (target / ".ai" / "runtime" / "marker.txt").write_text("preserve runtime\n", encoding="utf-8")

    def assert_local_only_live_state_preserved(self, target: Path) -> None:
        self.assertEqual((target / "config.json").read_text(encoding="utf-8"), '{"local": "preserve"}\n')
        self.assertEqual((target / "backups" / "marker.txt").read_text(encoding="utf-8"), "preserve backups\n")
        self.assertEqual((target / ".ai" / "runtime" / "marker.txt").read_text(encoding="utf-8"), "preserve runtime\n")

    def assert_codex_discovery_files_are_materialized(self, target: Path) -> None:
        skill_file = target / "SKILL.md"
        self.assertTrue(skill_file.is_file())
        self.assertFalse(skill_file.is_symlink())

        agents_dir = target / "agents"
        self.assertTrue(agents_dir.is_dir())
        self.assertFalse(agents_dir.is_symlink())

        openai_interface = agents_dir / "openai.yaml"
        self.assertTrue(openai_interface.is_file())
        self.assertFalse(openai_interface.is_symlink())

    def test_refactor_parity_doc_exists(self) -> None:
        text = (REPO_ROOT / "docs" / "refactor-parity.md").read_text(encoding="utf-8")
        self.assertIn("Runner module facade", text)
        self.assertIn("Live install layout", text)

    def test_cli_command_surface_stays_stable(self) -> None:
        from notes_runner_lib.parser_runtime import build_parser

        parser = build_parser(
            default_output_root="/tmp/notes-output",
            default_telegram_mcp_url="http://127.0.0.1:8765",
        )
        subparser_action = next(
            action
            for action in parser._actions
            if getattr(action, "dest", None) == "command"
        )
        self.assertEqual(list(subparser_action.choices), EXPECTED_RUNNER_COMMANDS)

        assemble = subparser_action.choices["assemble"]
        assemble_options = {
            option
            for action in assemble._actions
            for option in getattr(action, "option_strings", [])
        }
        for option in ("--html-theme", "--send-to", "--skip-telegram", "--force-telegram-resend", "--json"):
            self.assertIn(option, assemble_options)
        parsed = parser.parse_args(["assemble", "/tmp/work", "/tmp/out.md", "/tmp/out.html", "Title", "--html-theme", "classic"])
        self.assertEqual(parsed.html_theme, "classic")

        audio = subparser_action.choices["audio"]
        audio_options = {
            option
            for action in audio._actions
            for option in getattr(action, "option_strings", [])
        }
        for option in ("--output-root", "--title", "--model", "--language", "--prepare", "--refresh", "--transcribe-backend", "--diarize", "--parakeet-benchmark", "--json"):
            self.assertIn(option, audio_options)

    def test_runner_help_surface_lists_public_commands(self) -> None:
        result = subprocess.run(
            ["python3", str(RUNNER_PATH), "--help"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        for command in EXPECTED_RUNNER_COMMANDS:
            self.assertIn(command, result.stdout)

    def test_runner_doctor_json_surface_has_expected_keys(self) -> None:
        result = subprocess.run(
            ["python3", str(RUNNER_PATH), "doctor", "--json"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        for key in (
            "platform",
            "python_version",
            "pandoc",
            "yt-dlp",
            "ffmpeg",
            "skill_root",
            "telegram_delivery_enabled",
            "digest_runner",
            "audio_transcription_ready",
        ):
            self.assertIn(key, payload)

    def test_runner_status_json_surface_has_expected_keys(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            work_dir = Path(tmp_dir) / "single-chunk"
            shutil.copytree(REPO_ROOT / "test-fixtures" / "single-chunk", work_dir)
            result = subprocess.run(
                ["python3", str(RUNNER_PATH), "status", str(work_dir), "--json"],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            for key in ("work_dir", "fingerprint", "execution_mode", "chunk_plan", "chunk_statuses", "stages", "execution_plan"):
                self.assertIn(key, payload)
            self.assertEqual(payload["execution_plan"]["mode"], "single")

    def test_cli_runtime_dispatches_by_command_name(self) -> None:
        from notes_runner_lib.cli_runtime import dispatch_command

        called: list[str] = []
        args = types.SimpleNamespace(command="doctor")
        result = dispatch_command(
            args,
            handlers={"doctor": lambda _: called.append("doctor") or 17},
            parser_error=lambda message: self.fail(message),
        )
        self.assertEqual(result, 17)
        self.assertEqual(called, ["doctor"])

    def test_cli_runtime_reports_unsupported_command(self) -> None:
        from notes_runner_lib.cli_runtime import dispatch_command

        errors: list[str] = []
        args = types.SimpleNamespace(command="missing")
        result = dispatch_command(
            args,
            handlers={},
            parser_error=errors.append,
        )
        self.assertEqual(result, 2)
        self.assertEqual(errors, ["Unsupported command: missing"])

    def test_runner_import_compat_surface_stays_available(self) -> None:
        runner = load_runner_module()
        missing = [name for name in RUNNER_COMPAT_ATTRS if not hasattr(runner, name)]
        self.assertEqual(missing, [])

    def test_runner_command_handlers_match_parser_commands(self) -> None:
        runner = load_runner_module()
        parser = runner.build_parser()
        subparser_action = next(
            action
            for action in parser._actions
            if getattr(action, "dest", None) == "command"
        )
        self.assertEqual(
            list(runner.command_handlers()),
            list(subparser_action.choices),
        )
        for command_name, handler_name in EXPECTED_COMMAND_HANDLERS.items():
            with self.subTest(command_name=command_name):
                self.assertIs(
                    runner.command_handlers()[command_name],
                    getattr(runner, handler_name),
                )

    def test_dev_link_live_temp_target_preserves_codex_discovery_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "skills" / "notes"
            self.seed_local_only_live_state(target)
            result = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "scripts" / "dev-link-live.sh"),
                    "--target",
                    str(target),
                    "--skip-backup",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assert_codex_discovery_files_are_materialized(target)
            scripts_dir = target / "scripts"
            self.assertTrue(scripts_dir.is_symlink())
            self.assertTrue((scripts_dir / "notes-runner").is_file())
            self.assertTrue(os.access(scripts_dir / "notes-runner", os.X_OK))

            self.assertTrue((target / ".live-link.json").is_file())
            self.assert_local_only_live_state_preserved(target)

    def test_promote_live_temp_target_preserves_codex_discovery_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            target = Path(tmp_dir) / "skills" / "notes"
            self.seed_local_only_live_state(target)
            result = subprocess.run(
                [
                    "bash",
                    str(REPO_ROOT / "scripts" / "promote-live.sh"),
                    "--target",
                    str(target),
                    "--allow-dirty",
                    "--skip-checks",
                ],
                cwd=REPO_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assert_codex_discovery_files_are_materialized(target)
            self.assertFalse((target / ".live-link.json").exists())
            self.assertTrue((target / "scripts" / "notes-runner").is_file())
            self.assertTrue(os.access(target / "scripts" / "notes-runner", os.X_OK))
            self.assertFalse((target / "scripts").is_symlink())
            self.assert_local_only_live_state_preserved(target)

    def test_install_temp_target_preserves_codex_discovery_layout(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_root = Path(tmp_dir)
            target = tmp_root / "skills" / "notes"
            self.seed_local_only_live_state(target)
            fake_bin = tmp_root / "fake-bin"
            fake_bin.mkdir()
            for command_name in ("pandoc", "yt-dlp", "ffmpeg"):
                command_path = fake_bin / command_name
                command_path.write_text("#!/usr/bin/env sh\nexit 0\n", encoding="utf-8")
                command_path.chmod(0o755)
            env = os.environ.copy()
            env.update(
                {
                    "HOME": str(tmp_root / "home"),
                    "CODEX_HOME": str(tmp_root / "codex-home"),
                    "NOTES_SKILL_TARGET_DIR": str(target),
                    "PATH": f"{fake_bin}{os.pathsep}{env.get('PATH', '')}",
                }
            )
            result = subprocess.run(
                ["bash", str(REPO_ROOT / "install.sh")],
                cwd=REPO_ROOT,
                env=env,
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)

            self.assert_codex_discovery_files_are_materialized(target)
            self.assertTrue((target / "scripts" / "notes-runner").is_file())
            self.assertTrue(os.access(target / "scripts" / "notes-runner", os.X_OK))
            self.assertFalse((target / "scripts").is_symlink())
            runner_link = tmp_root / "home" / ".local" / "bin" / "notes-runner"
            self.assertTrue(runner_link.is_symlink())
            self.assertTrue(os.access(runner_link, os.X_OK))
            self.assert_local_only_live_state_preserved(target)

    def test_runner_runtime_module_wiring_is_importable(self) -> None:
        package_dir = REPO_ROOT / "scripts" / "notes_runner_lib"
        self.assertTrue(package_dir.is_dir())
        imported_modules = {
            node.module.removeprefix("notes_runner_lib.")
            for node in ast.walk(ast.parse(RUNNER_PATH.read_text(encoding="utf-8")))
            if isinstance(node, ast.ImportFrom)
            and node.module is not None
            and node.module.startswith("notes_runner_lib.")
        }
        self.assertEqual(sorted(imported_modules), EXPECTED_RUNNER_RUNTIME_MODULES)
        for module_name in EXPECTED_RUNNER_RUNTIME_MODULES:
            with self.subTest(module_name=module_name):
                module_path = package_dir / f"{module_name}.py"
                self.assertTrue(module_path.is_file())
                self.assertIsNotNone(importlib.import_module(f"notes_runner_lib.{module_name}"))

    def test_regression_loader_avoids_hardcoded_user_path(self) -> None:
        text = (REPO_ROOT / "tests" / "test_notes_runner_regressions.py").read_text(encoding="utf-8")
        self.assertNotIn("/Users/sereja/Projects/products/notes-skill", text)

    def test_public_repo_text_files_do_not_contain_private_machine_defaults(self) -> None:
        result = subprocess.run(
            ["git", "ls-files"],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=True,
        )
        forbidden = [
            "-100" + "3850136767",
            "/Users/" + "sereja/Downloads",
            "/Users/" + "sereja/Projects/families",
        ]
        offenders: list[str] = []
        for relative_path in result.stdout.splitlines():
            path = REPO_ROOT / relative_path
            if path.suffix in {".zip", ".png", ".jpg", ".jpeg", ".gif", ".pdf"}:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            for marker in forbidden:
                if marker in text:
                    offenders.append(f"{relative_path}: {marker}")
        self.assertEqual(offenders, [])

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

    def test_skill_contract_promises_end_to_end_delivery(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "This one-shot contract applies to one source item at a time. It does not turn the current batch summary payload into a single note.",
            "Do not stop after `--prepare` succeeds.",
            "Continue autonomously through extraction, header, and assemble until the final note files exist or a real error stops the run.",
            "Do not ask the user to manually run extraction, `replace-speakers`, `build-tldr`, or `assemble`.",
            "Only report the final note paths or a real blocking error.",
        ]
        for marker in required:
            self.assertIn(marker, text)

    def test_batch_contract_is_not_single_note_one_shot(self) -> None:
        skill_text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "Batch JSON is not a single-note payload.",
            "Do not apply the single-note continuation flow below to the whole batch result.",
            "Report the batch `results`, `index`, `ok`, and `failed` values.",
            "For `batch`, stop at the batch summary unless the runner exposes per-item final artifacts or the user chooses a specific item to finish.",
        ]
        for marker in required:
            self.assertIn(marker, skill_text)
        readme_text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Produces individual notes for each file + a `batch-index.html` with links.", readme_text)

    def test_skill_contract_requires_telegram_for_normal_notes_completion(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "Telegram delivery is part of the normal `/notes` completion contract.",
            "If the user did not explicitly ask to skip Telegram, do not treat `telegram_delivery.success == false` as a minor warning.",
            "Use `--skip-telegram` only for explicit debug/smoke work, never as the final completion path for a user-facing `/notes` request.",
        ]
        for marker in required:
            self.assertIn(marker, text)
        self.assertNotIn(
            "If `telegram_delivery.success == false`, treat it as a warning only.",
            text,
        )

    def test_skill_contract_retries_fixable_assemble_contract_failures(self) -> None:
        text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        required = [
            "If `assemble` exits non-zero or returns `contract_errors`, inspect the failure before giving up.",
            "For fixable note-quality failures, repair the upstream files you control and rerun `assemble`.",
            "Do this repair loop up to 2 times.",
        ]
        for marker in required:
            self.assertIn(marker, text)

    def test_skill_is_user_invocable_and_has_openai_interface_metadata(self) -> None:
        skill_text = (REPO_ROOT / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("user-invocable: true", skill_text)

        interface_path = REPO_ROOT / "agents" / "openai.yaml"
        self.assertTrue(interface_path.is_file())

        interface_text = interface_path.read_text(encoding="utf-8")
        required = [
            'display_name: "Notes"',
            'short_description: "Create detailed notes from YouTube, local media, or transcripts"',
            'default_prompt: "Create detailed notes from this YouTube URL, local media file, or transcript."',
        ]
        for marker in required:
            self.assertIn(marker, interface_text)

    def test_dev_link_live_materializes_skill_metadata_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            target_dir = Path(tmpdir) / "notes"
            env = dict(os.environ, NOTES_LIVE_DIR=str(target_dir))
            subprocess.run(
                ["bash", "scripts/dev-link-live.sh", "--skip-backup"],
                cwd=REPO_ROOT,
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            skill_md = target_dir / "SKILL.md"
            agents_dir = target_dir / "agents"
            openai_yaml = agents_dir / "openai.yaml"
            self.assertTrue(skill_md.is_file())
            self.assertFalse(skill_md.is_symlink())
            self.assertTrue(agents_dir.is_dir())
            self.assertFalse(agents_dir.is_symlink())
            self.assertTrue(openai_yaml.exists())
            self.assertFalse(openai_yaml.is_symlink())

    def test_quick_suite_no_longer_depends_on_download_bundles(self) -> None:
        text = (REPO_ROOT / "scripts" / "test-pipeline.sh").read_text(encoding="utf-8")
        self.assertNotIn("$HOME/Downloads/конспекты", text)
        self.assertNotIn("BUNDLE_SHORT=", text)
        self.assertNotIn("BUNDLE_MEDIUM=", text)
        self.assertNotIn("BUNDLE_LONG=", text)

    def test_release_check_explicitly_rejects_skip_in_quick_output(self) -> None:
        text = (REPO_ROOT / "scripts" / "release-check.sh").read_text(encoding="utf-8")
        self.assertIn("quick suite emitted SKIP", text)
        self.assertIn("grep -Eq '\\bSKIP\\b'", text)


if __name__ == "__main__":
    unittest.main()
