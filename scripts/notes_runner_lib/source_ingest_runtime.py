from __future__ import annotations

import html
import json
import os
import re
import shutil
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .common import load_json

HTML_TAG_RE = re.compile(r"<[^>]+>")
MARKDOWN_H1_RE = re.compile(r"^\s*#\s+(.+?)\s*$")
TITLE_TIMESTAMP_PREFIX_RE = re.compile(r"^(?:\*?\d{1,2}:\d{2}(?::\d{2})?\*?\s+)+", re.IGNORECASE)
TITLE_SPEAKER_PREFIX_RE = re.compile(r"^(?:\*\*)?speaker\s+\d+(?:\*\*)?\s*:?\s*", re.IGNORECASE)


def resolve_yt_dlp_bin() -> str:
    override = os.environ.get("NOTES_RUNNER_YTDLP_BIN")
    if override:
        return str(Path(override).expanduser())
    found = shutil.which("yt-dlp")
    if found:
        return found
    raise FileNotFoundError("yt-dlp not found. Install it or set NOTES_RUNNER_YTDLP_BIN.")


def run_command(command: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def run_checked(command: list[str], *, cwd: Path | None = None, label: str) -> subprocess.CompletedProcess[str]:
    result = run_command(command, cwd=cwd)
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise ValueError(f"{label} failed: {detail}")
    return result


def extract_youtube_video_id(url: str) -> str | None:
    patterns = (
        r"(?:youtube\.com/watch\?(?:.*?&)?v=)([A-Za-z0-9_-]{11})",
        r"(?:youtu\.be/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/shorts/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/live/)([A-Za-z0-9_-]{11})",
        r"(?:youtube\.com/embed/)([A-Za-z0-9_-]{11})",
    )
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def extract_youtube_metadata(url: str) -> dict:
    try:
        result = run_checked(
            [resolve_yt_dlp_bin(), "--dump-single-json", "--skip-download", url],
            label="yt-dlp metadata fetch",
        )
        payload = json.loads(result.stdout)
        if not isinstance(payload, dict):
            raise ValueError("yt-dlp metadata JSON was not an object")
        return payload
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        video_id = extract_youtube_video_id(url)
        if not video_id:
            raise
        return {
            "id": video_id,
            "title": video_id,
            "webpage_url": url,
            "_metadata_warning": f"yt-dlp metadata fetch failed; using URL-derived metadata: {exc}",
        }


def extract_youtube_chapters(metadata: dict) -> list[dict]:
    """Extract chapter markers from YouTube metadata."""

    def _ts_to_seconds(ts: str) -> int:
        parts = ts.split(":")
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        return int(parts[0]) * 60 + int(parts[1])

    def _seconds_to_ts(seconds: int) -> str:
        minutes, sec = divmod(seconds, 60)
        return f"{minutes}:{sec:02d}"

    raw_chapters = metadata.get("chapters")
    if raw_chapters and isinstance(raw_chapters, list):
        result: list[dict] = []
        for chapter in raw_chapters:
            start = chapter.get("start_time")
            title = chapter.get("title", "").strip()
            if start is not None and title:
                seconds = int(start)
                result.append({
                    "timestamp": _seconds_to_ts(seconds),
                    "title": title,
                    "seconds": seconds,
                })
        if result:
            return result

    description = metadata.get("description") or ""
    chapter_re = re.compile(r"^(\d{1,2}:\d{2}(?::\d{2})?)\s+(.+)$", re.MULTILINE)
    matches = chapter_re.findall(description)
    if len(matches) >= 2:
        return [
            {
                "timestamp": ts.strip(),
                "title": title.strip(),
                "seconds": _ts_to_seconds(ts.strip()),
            }
            for ts, title in matches
        ]

    return []


def _cleanup_title_text(value: str) -> str:
    text = html.unescape(HTML_TAG_RE.sub("", value or "")).strip()
    if not text:
        return ""
    heading_match = MARKDOWN_H1_RE.match(text)
    if heading_match:
        text = heading_match.group(1).strip()
    text = TITLE_TIMESTAMP_PREFIX_RE.sub("", text)
    text = TITLE_SPEAKER_PREFIX_RE.sub("", text)
    text = text.replace("**", "").replace("__", "").replace("`", "").replace("*", "")
    text = re.sub(r"^[>\-–—•\s:;,.]+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:140].strip()


def _cleanup_person_hint(value: str) -> str:
    text = _cleanup_title_text(value)
    if text.startswith("@"):
        text = text[1:].strip()
    text = re.sub(r"\s+", " ", text).strip(" -|")
    return text[:80].strip()


def _is_informative_person_hint(value: str) -> bool:
    text = (value or "").strip()
    if len(text) < 2:
        return False
    if re.fullmatch(r"speaker\s+\d+", text, flags=re.IGNORECASE):
        return False
    if re.fullmatch(r"[\d\s:._/\-]+", text):
        return False
    if text.casefold() in {"author", "creator", "uploader", "channel"}:
        return False
    return True


def build_youtube_source_hints(metadata: dict) -> dict:
    candidates: list[str] = []
    for raw in (
        metadata.get("creator"),
        metadata.get("uploader"),
        metadata.get("channel"),
        metadata.get("artist"),
    ):
        cleaned = _cleanup_person_hint(str(raw or ""))
        if cleaned and _is_informative_person_hint(cleaned):
            candidates.append(cleaned)

    deduped_candidates: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if key in seen:
            continue
        deduped_candidates.append(candidate)
        seen.add(key)

    uploader_handle = str(metadata.get("uploader_id") or "").strip()
    author_hint = deduped_candidates[0] if deduped_candidates else _cleanup_person_hint(uploader_handle)
    if author_hint and not _is_informative_person_hint(author_hint):
        author_hint = ""

    youtube_meta = {
        "video_id": str(metadata.get("id") or "").strip() or None,
        "channel": _cleanup_person_hint(str(metadata.get("channel") or "")) or None,
        "channel_id": str(metadata.get("channel_id") or "").strip() or None,
        "uploader": _cleanup_person_hint(str(metadata.get("uploader") or "")) or None,
        "uploader_id": uploader_handle or None,
        "creator": _cleanup_person_hint(str(metadata.get("creator") or "")) or None,
    }

    return {
        "source_kind": "youtube",
        "author_hint": author_hint or None,
        "speaker_candidates": deduped_candidates,
        "youtube": youtube_meta,
    }


def find_existing_youtube_bundle(
    output_root: Path,
    url: str,
    *,
    bundle_paths: Callable[[Path], dict[str, Path]],
) -> Path | None:
    video_id = extract_youtube_video_id(url)
    candidates: list[Path] = []
    if video_id:
        candidates.extend(path for path in output_root.glob(f"{video_id}-*") if path.is_dir())
    for path in (output_root.iterdir() if output_root.is_dir() else []):
        if not path.is_dir() or path in candidates:
            continue
        try:
            metadata = load_json(path / "metadata.json") if (path / "metadata.json").is_file() else None
        except (OSError, json.JSONDecodeError, ValueError):
            metadata = None
        if not isinstance(metadata, dict):
            continue
        metadata_video_id = str(metadata.get("id") or metadata.get("video_id") or "").strip()
        metadata_url = str(metadata.get("webpage_url") or metadata.get("source_url") or "").strip()
        source_url_path = bundle_paths(path)["source_url"]
        source_url = source_url_path.read_text(encoding="utf-8").strip() if source_url_path.is_file() else ""
        if (video_id and metadata_video_id == video_id) or metadata_url == url or source_url == url:
            candidates.append(path)
    if not candidates:
        return None
    candidates = sorted(candidates, key=lambda path: path.stat().st_mtime, reverse=True)
    for candidate in candidates:
        if bundle_paths(candidate)["transcript"].is_file():
            return candidate
    return candidates[0]


def download_subtitles(
    url: str,
    subs_dir: Path,
    *,
    run_command: Callable[..., subprocess.CompletedProcess[str]],
    resolve_yt_dlp_bin: Callable[[], str],
) -> str | None:
    subs_dir.mkdir(parents=True, exist_ok=True)
    try:
        result = run_command(
            [
                resolve_yt_dlp_bin(),
                "--skip-download",
                "--write-subs",
                "--write-auto-subs",
                "--sub-format",
                "vtt",
                "--sub-langs",
                "ru.*,en.*,ru,en",
                "-P",
                str(subs_dir),
                "-o",
                "%(title)s [%(id)s].%(ext)s",
                url,
            ],
        )
    except FileNotFoundError as exc:
        return str(exc)
    if result.returncode == 0:
        return None
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    return stderr or stdout or f"yt-dlp subtitle download failed with exit code {result.returncode}"


def download_audio(
    url: str,
    audio_dir: Path,
    *,
    run_checked: Callable[..., subprocess.CompletedProcess[str]],
    resolve_yt_dlp_bin: Callable[[], str],
) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    output_template = audio_dir / "source.%(ext)s"
    run_checked(
        [
            resolve_yt_dlp_bin(),
            "-f",
            "bestaudio[ext=m4a]/bestaudio/best",
            "-o",
            str(output_template),
            url,
        ],
        label="yt-dlp audio download",
    )
    matches = sorted(audio_dir.glob("source.*"))
    if not matches:
        raise ValueError(f"yt-dlp audio download produced no files in {audio_dir}")
    return matches[0]


def load_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    return load_json(path)


def normalize_language_hint(value: str) -> str | None:
    normalized = value.strip().lower()
    if normalized in {"", "auto"}:
        return None
    return normalized


def local_backend_language(value: str) -> str | None:
    return normalize_language_hint(value)


def download_telegram_media(chat: str, message_id: int, mcp_url: str) -> Path:
    request_body = json.dumps(
        {
            "jsonrpc": "2.0",
            "method": "tools/call",
            "params": {
                "name": "download_media",
                "arguments": {"chat": chat, "message_id": message_id},
            },
            "id": 1,
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        mcp_url,
        data=request_body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise ValueError(f"Failed to connect to Telegram MCP at {mcp_url}: {exc}") from exc

    if "error" in response_data:
        error = response_data["error"]
        msg = error.get("message", str(error)) if isinstance(error, dict) else str(error)
        raise ValueError(f"Telegram MCP error: {msg}")

    result = response_data.get("result")
    if not result:
        raise ValueError(f"Telegram MCP returned no result: {response_data}")

    content = result.get("content") if isinstance(result, dict) else None
    if isinstance(content, list):
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                text = item["text"]
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict):
                        file_path = parsed.get("path") or parsed.get("file_path") or parsed.get("file")
                        if file_path:
                            path = Path(str(file_path))
                            if path.is_file():
                                return path
                except json.JSONDecodeError:
                    pass
                candidate = Path(text.strip())
                if candidate.is_file():
                    return candidate

    if isinstance(result, dict):
        for key in ("path", "file_path", "file"):
            value = result.get(key)
            if isinstance(value, str) and Path(value).is_file():
                return Path(value)

    raise ValueError(f"Could not extract file path from MCP response: {response_data}")


def is_youtube_url(value: str) -> bool:
    return "youtube.com/" in value or "youtu.be/" in value
