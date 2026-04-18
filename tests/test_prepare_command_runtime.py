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

from notes_runner_lib.prepare_command_runtime import PrepareCommandDependencies, run_prepare_command


class PrepareCommandRuntimeTests(unittest.TestCase):
    def test_run_prepare_command_emits_json_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            transcript_path = Path(tmp_dir) / "transcript.md"
            transcript_path.write_text("hello\n", encoding="utf-8")
            work_dir = Path(tmp_dir) / "work"
            stdout_buffer = io.StringIO()
            prepare_calls: list[list[Path]] = []

            exit_code = run_prepare_command(
                argparse.Namespace(files=[str(transcript_path)], json=True),
                deps=PrepareCommandDependencies(
                    ensure_file=lambda path, label: path,
                    run_prepare_logic=lambda files: prepare_calls.append(files) or {"work_dir": str(work_dir)},
                    load_prepare_payload=lambda work: {"work_dir": str(work), "files": 1, "total_lines": 10},
                    stdout=stdout_buffer,
                ),
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(prepare_calls, [[transcript_path]])
            payload = json.loads(stdout_buffer.getvalue())
            self.assertEqual(payload["work_dir"], str(work_dir))
            self.assertEqual(payload["files"], 1)

    def test_run_prepare_command_emits_human_output(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            transcript_path = Path(tmp_dir) / "transcript.md"
            transcript_path.write_text("hello\n", encoding="utf-8")
            stdout_buffer = io.StringIO()

            exit_code = run_prepare_command(
                argparse.Namespace(files=[str(transcript_path)], json=False),
                deps=PrepareCommandDependencies(
                    ensure_file=lambda path, label: path,
                    run_prepare_logic=lambda files: {"work_dir": str(Path(tmp_dir) / "work")},
                    load_prepare_payload=lambda work: {
                        "work_dir": str(work),
                        "files": 1,
                        "total_lines": 10,
                        "total_chunks": 2,
                        "unique_speakers": 1,
                        "duration_estimate": "00:10:00",
                    },
                    stdout=stdout_buffer,
                ),
            )

            self.assertEqual(exit_code, 0)
            self.assertIn("Work dir:", stdout_buffer.getvalue())
            self.assertIn("Chunks: 2", stdout_buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
