import argparse
import io
import json
import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.doctor_command_runtime import DoctorCommandDependencies, run_doctor_command


class DoctorCommandRuntimeTests(unittest.TestCase):
    def test_run_doctor_command_emits_json_payload(self) -> None:
        stdout_buffer = io.StringIO()
        captured_kwargs: dict[str, object] = {}

        def fake_build_doctor_checks(**kwargs: object) -> dict[str, object]:
            captured_kwargs.update(kwargs)
            return {"pandoc": True, "skill_root": str(kwargs["skill_root"])}

        exit_code = run_doctor_command(
            argparse.Namespace(json=True),
            deps=DoctorCommandDependencies(
                build_doctor_checks=fake_build_doctor_checks,
                render_doctor_report=lambda checks: "unused\n",
                platform="darwin",
                python_version="3.14.0",
                which=lambda name: f"/usr/bin/{name}",
                groq_api_key_present=True,
                skill_root=Path("/tmp/skill"),
                config_path=Path("/tmp/config.json"),
                load_notes_config=lambda path: {},
                env_flag_enabled=lambda name: False,
                is_macos=lambda: True,
                parakeet_available=lambda: True,
                mlx_whisper_available=lambda: False,
                python_module_available=lambda name: True,
                stdout=stdout_buffer,
            ),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured_kwargs["platform"], "darwin")
        payload = json.loads(stdout_buffer.getvalue())
        self.assertTrue(payload["pandoc"])
        self.assertEqual(payload["skill_root"], "/tmp/skill")

    def test_run_doctor_command_emits_rendered_report(self) -> None:
        stdout_buffer = io.StringIO()

        exit_code = run_doctor_command(
            argparse.Namespace(json=False),
            deps=DoctorCommandDependencies(
                build_doctor_checks=lambda **kwargs: {"audio_transcription_ready": True},
                render_doctor_report=lambda checks: "doctor ok\n",
                platform="linux",
                python_version="3.14.0",
                which=lambda name: None,
                groq_api_key_present=False,
                skill_root=Path("/tmp/skill"),
                config_path=Path("/tmp/config.json"),
                load_notes_config=lambda path: {},
                env_flag_enabled=lambda name: False,
                is_macos=lambda: False,
                parakeet_available=lambda: False,
                mlx_whisper_available=lambda: False,
                python_module_available=lambda name: False,
                stdout=stdout_buffer,
            ),
        )

        self.assertEqual(exit_code, 0)
        self.assertEqual(stdout_buffer.getvalue(), "doctor ok\n")


if __name__ == "__main__":
    unittest.main()
