from __future__ import annotations

import html
import re
from pathlib import Path


VTT_TIMING_RE = re.compile(
    r"(?P<start>\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2}\.\d{3}|\d{2}:\d{2}\.\d{3})"
)
LANGUAGE_CODE_RE = re.compile(r"\.([a-z]{2}(?:-[A-Za-z0-9]+)?)(?:-orig)?\.vtt$", re.IGNORECASE)
HTML_TAG_RE = re.compile(r"<[^>]+>")


def normalize_vtt_timestamp(value: str) -> float:
    try:
        parts = value.split(":")
        if len(parts) == 1:
            return float(parts[0])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
    except (ValueError, IndexError):
        return 0.0


def format_mmss(seconds_value: object) -> str:
    try:
        total_seconds = max(0, int(float(seconds_value)))
    except (TypeError, ValueError):
        return "00:00"
    minutes, seconds = divmod(total_seconds, 60)
    return f"{minutes:02d}:{seconds:02d}"


def clean_caption_text(lines: list[str]) -> str:
    text = " ".join(line.strip() for line in lines if line.strip())
    text = HTML_TAG_RE.sub("", text)
    text = html.unescape(text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def parse_vtt(path: Path) -> list[dict]:
    cues: list[dict] = []
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    index = 0
    last_text = None
    while index < len(lines):
        line = lines[index].strip()
        if not line or line in {"WEBVTT"} or line.startswith(("Kind:", "Language:", "NOTE", "STYLE")):
            index += 1
            continue
        timing_match = VTT_TIMING_RE.search(line)
        if not timing_match and index + 1 < len(lines):
            timing_match = VTT_TIMING_RE.search(lines[index + 1].strip())
            if timing_match:
                index += 1
        if not timing_match:
            index += 1
            continue
        start_seconds = normalize_vtt_timestamp(timing_match.group("start"))
        index += 1
        text_lines: list[str] = []
        while index < len(lines) and lines[index].strip():
            text_lines.append(lines[index].rstrip())
            index += 1
        text = clean_caption_text(text_lines)
        if text and text != last_text:
            cues.append({"start": start_seconds, "text": text})
            last_text = text
    return cues


def subtitle_language_from_path(path: Path) -> str | None:
    match = LANGUAGE_CODE_RE.search(path.name)
    if not match:
        return None
    return match.group(1).split("-")[0].lower()


def subtitle_quality_ok(cues: list[dict], duration_seconds: int | None) -> bool:
    if not cues:
        return False
    cue_count = len(cues)
    total_chars = sum(len(str(item.get("text") or "")) for item in cues)
    if duration_seconds is not None and duration_seconds <= 300:
        return cue_count >= 2 and total_chars >= 20
    return cue_count >= 20 and total_chars >= 400


def select_best_subtitle(subs_dir: Path, duration_seconds: int | None) -> tuple[Path | None, list[dict], str | None]:
    candidates: list[tuple[tuple[int, int], Path, list[dict], str | None]] = []
    for path in sorted(subs_dir.glob("*.vtt")):
        cues = parse_vtt(path)
        if not subtitle_quality_ok(cues, duration_seconds):
            continue
        language = subtitle_language_from_path(path)
        language_rank = {"ru": 0, "en": 1}.get(language or "", 2)
        candidates.append(((language_rank, -sum(len(item["text"]) for item in cues)), path, cues, language))
    if not candidates:
        return None, [], None
    candidates.sort(key=lambda item: item[0])
    _, path, cues, language = candidates[0]
    return path, cues, language


def try_youtube_transcript_api(video_id: str, duration_seconds: int | None) -> tuple[list[dict], str | None, str | None]:
    """Try to fetch transcript via youtube-transcript-api (fast, no audio download).

    Returns (cues, language, error). On success error is None.
    """
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
    except ImportError:
        return [], None, "youtube-transcript-api not installed"
    try:
        api = YouTubeTranscriptApi()
        languages = ["ru", "en"]
        transcript = api.fetch(video_id, languages=languages)
        snippets = list(transcript)
        cues = [{"start": snippet.start, "text": snippet.text} for snippet in snippets if snippet.text.strip()]
        language = transcript.language if hasattr(transcript, "language") else None
        if language:
            language = (
                "ru" if "russian" in language.lower() or language.lower().startswith("ru")
                else "en" if "english" in language.lower() or language.lower().startswith("en")
                else language[:2].lower()
            )
        if not subtitle_quality_ok(cues, duration_seconds):
            return [], None, "transcript too short or empty"
        return cues, language, None
    except Exception as exc:
        return [], None, str(exc)


def transcript_markdown_from_cues(cues: list[dict]) -> str:
    lines = [f"*{format_mmss(item['start'])}* {item['text']}" for item in cues if item.get("text")]
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def groq_payload_to_transcript_markdown(payload: dict) -> str:
    """Convert Groq Whisper verbose_json response to transcript markdown."""
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return f"*00:00* {text.strip()}\n"
        raise ValueError("Groq response contains no segments or text.")

    lines = [
        f"*{format_mmss(seg.get('start', 0))}* {seg.get('text', '').strip()}"
        for seg in segments
        if isinstance(seg, dict) and seg.get("text", "").strip()
    ]
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def extract_transcript_segments(payload: dict) -> list[dict]:
    candidates: list = []
    for key in ("utterances", "segments"):
        value = payload.get(key)
        if isinstance(value, list):
            candidates.extend(item for item in value if isinstance(item, dict))

    results = payload.get("results")
    if isinstance(results, dict):
        for key in ("utterances", "segments"):
            value = results.get(key)
            if isinstance(value, list):
                candidates.extend(item for item in value if isinstance(item, dict))

    segments: list[dict] = []
    for item in candidates:
        text = item.get("transcript") or item.get("text") or item.get("content")
        if not isinstance(text, str) or not text.strip():
            continue
        start = item.get("start")
        if start is None:
            start = item.get("start_time")
        if start is None:
            timestamp = item.get("timestamp")
            if isinstance(timestamp, (int, float, str)):
                start = timestamp
        segments.append(
            {
                "start": start if start is not None else 0,
                "speaker": item.get("speaker"),
                "text": text.strip(),
            }
        )
    return segments


def transcript_markdown_from_api_payload(payload: dict) -> str:
    segments = extract_transcript_segments(payload)
    speaker_values = {str(item["speaker"]) for item in segments if item.get("speaker") is not None}
    multi_speaker = len(speaker_values) > 1

    if segments:
        lines: list[str] = []
        for item in segments:
            prefix = f"*{format_mmss(item['start'])}* "
            if multi_speaker and item.get("speaker") is not None:
                lines.append(f"**Speaker {item['speaker']}** {prefix}{item['text']}")
            else:
                lines.append(f"{prefix}{item['text']}")
        return "\n".join(lines).rstrip() + "\n"

    text_candidates = [
        payload.get("text"),
        payload.get("transcript"),
    ]
    results = payload.get("results")
    if isinstance(results, dict):
        channels = results.get("channels")
        if isinstance(channels, list) and channels:
            alternatives = channels[0].get("alternatives") if isinstance(channels[0], dict) else None
            if isinstance(alternatives, list) and alternatives:
                text_candidates.append(alternatives[0].get("transcript"))
    for candidate in text_candidates:
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip() + "\n"
    raise ValueError("Transcription payload did not contain usable transcript text.")


__all__ = [
    "normalize_vtt_timestamp",
    "format_mmss",
    "clean_caption_text",
    "parse_vtt",
    "subtitle_language_from_path",
    "subtitle_quality_ok",
    "select_best_subtitle",
    "try_youtube_transcript_api",
    "transcript_markdown_from_cues",
    "groq_payload_to_transcript_markdown",
    "extract_transcript_segments",
    "transcript_markdown_from_api_payload",
]
