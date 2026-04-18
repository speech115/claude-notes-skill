from __future__ import annotations

import re
from pathlib import Path


SPEAKER_MAPPING_RE = re.compile(
    r"^(Speaker\s+\d+|Unmarked\s+(?:lines|speaker)(?:\s*\([^)]*\))?)\s*→\s*(.+)"
)
REPLACE_SPEAKERS_TARGET_PATTERNS = (
    "chunk_*_block_*.md",
    "manifest_chunk_*.tsv",
    "summary_chunk_*.md",
    "tldr.md",
)


def replace_speakers(work_dir: Path) -> dict:
    """Replace Speaker N labels with real names from speakers.txt."""
    speakers_file = work_dir / "speakers.txt"
    if not speakers_file.is_file():
        return {"modified": 0, "mappings": 0, "skipped": True, "reason": "no speakers.txt"}

    mappings: list[tuple[str, str]] = []
    for line in speakers_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("NOTE:"):
            continue
        m = SPEAKER_MAPPING_RE.match(line)
        if m:
            pattern = m.group(1).strip()
            replacement = m.group(2).strip()
            if pattern and replacement:
                mappings.append((pattern, replacement))

    if not mappings:
        return {"modified": 0, "mappings": 0, "skipped": True, "reason": "no valid mappings"}

    # Sort by pattern length DESC (Speaker 10 before Speaker 1)
    mappings.sort(key=lambda x: len(x[0]), reverse=True)

    target_files: list[Path] = []
    for pat in REPLACE_SPEAKERS_TARGET_PATTERNS:
        target_files.extend(sorted(work_dir.glob(pat)))

    modified = 0
    for fpath in target_files:
        text = fpath.read_text(encoding="utf-8")
        original = text
        for pattern, replacement in mappings:
            bold_pattern_re = re.compile(r"\*\*" + re.escape(pattern) + r"\*\*")
            text = bold_pattern_re.sub(f"**{replacement}**", text)
            pattern_re = re.compile(r"\b" + re.escape(pattern) + r"\b")
            text = pattern_re.sub(replacement, text)
        if text != original:
            fpath.write_text(text, encoding="utf-8")
            modified += 1

    return {"modified": modified, "mappings": len(mappings), "skipped": False}


__all__ = [
    "SPEAKER_MAPPING_RE",
    "REPLACE_SPEAKERS_TARGET_PATTERNS",
    "replace_speakers",
]
