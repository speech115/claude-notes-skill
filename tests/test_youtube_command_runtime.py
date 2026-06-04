import argparse
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.bundle_runtime import bundle_paths
from notes_runner_lib.youtube_command_runtime import run_youtube_command


class YoutubeCommandRuntimeTests(unittest.TestCase):
    def test_prepare_path_uses_run_prepare_and_attach(self) -> None:
        captured: dict[str, object] = {}

        def fake_prepare_and_attach(payload, transcript_path, bundle_dir, *, refresh=False, source_hints=None):
            captured["payload"] = payload
            captured["transcript"] = transcript_path
            captured["bundle_dir"] = bundle_dir
            captured["source_hints"] = source_hints
            payload["prepare"] = {"work_dir": str(bundle_dir / "work"), "reused": False}

        with tempfile.TemporaryDirectory() as tmp_dir:
            bundle_dir = Path(tmp_dir) / "bundle"
            bundle_dir.mkdir()
            subs_dir = bundle_dir / "subs"
            subs_dir.mkdir()
            transcript_path = bundle_dir / "transcript.md"
            transcript_path.write_text("*00:01* cue\n", encoding="utf-8")

            metadata = {
                "id": "abc12345678",
                "title": "Test Video",
                "duration": 120,
                "webpage_url": "https://www.youtube.com/watch?v=abc12345678",
            }
            paths = bundle_paths(bundle_dir)
            paths["subs_dir"].mkdir(parents=True, exist_ok=True)

            args = argparse.Namespace(
                url="https://www.youtube.com/watch?v=abc12345678",
                output_root=tmp_dir,
                refresh=False,
                prepare=True,
                transcribe_backend="auto",
                json=False,
            )

            exit_code = run_youtube_command(
                args,
                ensure_parent_dir=lambda p: p.mkdir(parents=True, exist_ok=True) or p,
                find_existing_youtube_bundle=lambda *_a, **_k: None,
                load_bundle_metadata=lambda *_a, **_k: None,
                extract_youtube_metadata=lambda _url: metadata,
                bundle_dir_for=lambda _meta, root: bundle_dir,
                bundle_paths=lambda _bundle: paths,
                start_bundle_run=lambda *_a, **_k: {"run_id": "test"},
                write_json=lambda path, payload: path.write_text("{}", encoding="utf-8"),
                write_text=lambda path, text: path.write_text(text, encoding="utf-8"),
                extract_youtube_chapters=lambda _meta: [],
                build_youtube_source_hints=lambda _meta: {"source_kind": "youtube"},
                try_youtube_transcript_api=lambda *_a, **_k: ([], None, "skip"),
                transcript_markdown_from_cues=lambda cues: "\n".join(cues),
                select_best_subtitle=lambda *_a, **_k: (None, [], "no subs"),
                download_subtitles=lambda *_a, **_k: None,
                choose_transcribe_backend=lambda _c: "groq",
                normalize_language_hint=lambda _v: None,
                download_audio=lambda *_a, **_k: bundle_dir / "audio.m4a",
                call_groq_transcribe=lambda *_a, **_k: {"text": "x"},
                advanced_setup_message=lambda *_a, **_k: "advanced",
                groq_payload_to_transcript_markdown=lambda _p: "*00:01* x\n",
                run_prepare_and_attach=fake_prepare_and_attach,
                extract_prepare_duration_ms=lambda _p: 0,
                write_bundle_state_snapshot=lambda *_a, **_k: {"note_id": "test-note"},
                append_trace_event=lambda *_a, **_k: bundle_dir / "trace.jsonl",
                finish_bundle_run=lambda *_a, **_k: None,
                ms_since=lambda _s: 1,
            )

        self.assertEqual(exit_code, 0)
        self.assertEqual(captured["transcript"], transcript_path)
        self.assertIn("prepare", captured["payload"])


if __name__ == "__main__":
    unittest.main()