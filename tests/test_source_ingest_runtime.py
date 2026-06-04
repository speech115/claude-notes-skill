import sys
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.source_ingest_runtime import (
    build_youtube_source_hints,
    extract_youtube_chapters,
    extract_youtube_video_id,
    is_youtube_url,
)


class SourceIngestRuntimeTests(unittest.TestCase):
    def test_extract_youtube_video_id_watch_url(self) -> None:
        url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
        self.assertEqual(extract_youtube_video_id(url), "dQw4w9WgXcQ")

    def test_extract_youtube_video_id_short_url(self) -> None:
        self.assertEqual(extract_youtube_video_id("https://youtu.be/dQw4w9WgXcQ"), "dQw4w9WgXcQ")

    def test_is_youtube_url(self) -> None:
        self.assertTrue(is_youtube_url("https://youtube.com/watch?v=abc"))
        self.assertFalse(is_youtube_url("https://example.com"))

    def test_build_youtube_source_hints_dedupes_speaker_candidates(self) -> None:
        hints = build_youtube_source_hints(
            {
                "id": "abc12345678",
                "uploader": "Channel Name",
                "channel": "Channel Name",
                "uploader_id": "@channel",
            }
        )
        self.assertEqual(hints["source_kind"], "youtube")
        self.assertEqual(hints["author_hint"], "Channel Name")
        self.assertEqual(hints["speaker_candidates"], ["Channel Name"])

    def test_extract_youtube_chapters_from_description(self) -> None:
        chapters = extract_youtube_chapters(
            {
                "description": "0:00 Intro\n5:30 Main topic\n12:00 Wrap-up",
            }
        )
        self.assertEqual(len(chapters), 3)
        self.assertEqual(chapters[0]["timestamp"], "0:00")
        self.assertEqual(chapters[0]["title"], "Intro")


if __name__ == "__main__":
    unittest.main()