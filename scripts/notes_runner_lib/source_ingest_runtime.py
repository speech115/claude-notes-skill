from __future__ import annotations

import json
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .common import load_json


def find_existing_youtube_bundle(
    output_root: Path,
    url: str,
    *,
    extract_youtube_video_id: Callable[[str], str | None],
    bundle_paths: Callable[[Path], dict[str, Path]],
) -> Path | None:
    video_id = extract_youtube_video_id(url)
    if not video_id:
        return None
    candidates = sorted(
        [path for path in output_root.glob(f"{video_id}-*") if path.is_dir()],
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        return None
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
