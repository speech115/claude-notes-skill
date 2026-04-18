import argparse
import json
import io
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.local_command_runtime import LocalCommandDependencies, run_local_command


class LocalCommandRuntimeTests(unittest.TestCase):
    def test_run_local_command_emits_expected_payload_and_marks_source_ready(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            tmp_path = Path(tmp_dir)
            source_path = tmp_path / "source.md"
            source_path.write_text("# Title\n\nBody\n", encoding="utf-8")
            bundle_dir = tmp_path / "bundle"
            transcript_path = bundle_dir / "transcript.md"
            metadata_path = bundle_dir / "metadata.json"
            source_file_path = bundle_dir / "source.txt"
            notes_md_path = bundle_dir / "note.md"
            notes_html_path = bundle_dir / "note.html"
            trace_path = bundle_dir / "trace.jsonl"

            written_json: dict[Path, object] = {}
            written_text: dict[Path, str] = {}
            state_snapshots: list[dict[str, object]] = []
            finish_calls: list[dict[str, object]] = []
            trace_events: list[dict[str, object]] = []
            stdout_buffer = io.StringIO()

            def fake_write_json(path: Path, payload: object) -> None:
                written_json[path] = payload

            def fake_write_text(path: Path, text: str) -> None:
                written_text[path] = text

            def fake_write_bundle_state_snapshot(bundle: Path, payload: dict[str, object]) -> dict[str, object]:
                snapshot = {
                    **payload,
                    "note_id": "file:test-note",
                }
                state_snapshots.append(snapshot)
                return snapshot

            def fake_append_trace_event(bundle: Path, event: str, **payload: object) -> None:
                trace_events.append({"bundle": str(bundle), "event": event, **payload})

            args = argparse.Namespace(
                path=str(source_path),
                output_root=str(tmp_path),
                title=None,
                prepare=False,
                refresh=False,
                json=True,
            )

            exit_code = run_local_command(
                args,
                deps=LocalCommandDependencies(
                    ensure_file=lambda path, label: path,
                    file_looks_binary=lambda path: False,
                    ensure_parent_dir=lambda path: path,
                    infer_local_title=lambda path: "Source",
                    local_bundle_dir_for=lambda source, title, output_root: bundle_dir,
                    bundle_paths=lambda bundle: {
                        "source_file": source_file_path,
                        "metadata": metadata_path,
                        "transcript": transcript_path,
                        "notes_md": notes_md_path,
                        "notes_html": notes_html_path,
                        "trace": trace_path,
                    },
                    start_bundle_run=lambda bundle, command, state_seed: {"run_id": "run-1", "command": command, "state_seed": state_seed},
                    copy_local_source=lambda source, bundle: bundle / source.name,
                    write_text=fake_write_text,
                    write_json=fake_write_json,
                    normalize_transcript_text=lambda text: text.strip(),
                    read_text_file=lambda path: path.read_text(encoding="utf-8"),
                    run_prepare_for_transcript=lambda transcript, *, bundle_dir, refresh: {"work_dir": str(bundle_dir / "work")},
                    attach_prepare_outputs=lambda payload, prepare_payload, bundle: payload.update({"prepare": prepare_payload}),
                    ms_since=lambda started: 12,
                    extract_prepare_duration_ms=lambda payload: 0,
                    write_bundle_state_snapshot=fake_write_bundle_state_snapshot,
                    append_trace_event=fake_append_trace_event,
                    finish_bundle_run=lambda bundle, run_context, *, status, error=None: finish_calls.append(
                        {
                            "bundle": str(bundle),
                            "run_id": run_context["run_id"],
                            "status": status,
                            "error": error,
                        }
                    ),
                    audio_extensions=set(),
                    video_extensions=set(),
                    stdout=stdout_buffer,
                ),
            )

            self.assertEqual(exit_code, 0)
            self.assertEqual(len(finish_calls), 1)
            self.assertEqual(finish_calls[0]["status"], "source-ready")
            self.assertEqual(trace_events[0]["event"], "local.ready")

            metadata_payload = written_json[metadata_path]
            self.assertEqual(metadata_payload["source_name"], "source.md")
            self.assertEqual(state_snapshots[0]["trace_path"], str(trace_path))

            transcript_text = written_text[transcript_path]
            self.assertEqual(transcript_text, "# Title\n\nBody")

            payload = json.loads(stdout_buffer.getvalue())
            self.assertEqual(payload["bundle_dir"], str(bundle_dir))
            self.assertEqual(payload["trace_path"], str(trace_path))
            self.assertEqual(payload["note_id"], "file:test-note")


if __name__ == "__main__":
    unittest.main()
