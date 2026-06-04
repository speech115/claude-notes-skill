"""Transcription backends: Groq, MacWhisper Parakeet, and diarize helper CLI."""

from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from .common import compute_file_sha256, load_json, write_json, write_text
from .source_ingest_runtime import run_checked
from .transcript_runtime import format_mmss


def _skill_root() -> Path:
    return Path(os.environ.get("NOTES_SKILL_ROOT", Path(__file__).resolve().parents[2])).expanduser()


def _advanced_setup_message(feature: str, hint: str | None, *, advanced_doc_path: Path) -> str:
    parts = [f"{feature} is part of advanced setup."]
    if hint:
        parts.append(hint.rstrip(".") + ".")
    parts.append(f"See {advanced_doc_path}.")
    return " ".join(parts)


def is_macos() -> bool:
    return sys.platform == "darwin"


def ensure_audio_transcription_available(
    feature_name: str,
    *,
    advanced_doc_path: Path | None = None,
) -> None:
    doc = advanced_doc_path or (_skill_root() / "ADVANCED.md")
    if os.environ.get("GROQ_API_KEY"):
        return
    if is_macos() and parakeet_available():
        return
    if is_macos():
        raise FileNotFoundError(
            _advanced_setup_message(
                feature_name,
                "Install MacWhisper CLI (`mw`) with the parakeet-pro:nvidia_parakeet-v3 model, or set GROQ_API_KEY (free at console.groq.com)",
                advanced_doc_path=doc,
            )
        )
    raise FileNotFoundError(
        _advanced_setup_message(
            feature_name,
            "Set GROQ_API_KEY (free at console.groq.com). MacWhisper Parakeet is macOS-only.",
            advanced_doc_path=doc,
        )
    )


def resolve_transcribe_cli(*, skill_root: Path | None = None, advanced_doc_path: Path | None = None) -> Path:
    root = (skill_root or _skill_root()).expanduser()
    doc = advanced_doc_path or (root / "ADVANCED.md")
    override = os.environ.get("NOTES_RUNNER_TRANSCRIBE_CLI")
    if override:
        resolved = Path(override).expanduser()
        if not resolved.is_file():
            raise FileNotFoundError(f"NOTES_RUNNER_TRANSCRIBE_CLI points to a missing file: {resolved}")
        return resolved

    bundled = root / "scripts" / "transcribe_diarize.py"
    if bundled.is_file():
        return bundled

    raise FileNotFoundError(
        _advanced_setup_message(
            "YouTube transcription fallback",
            "Starter mode only supports videos with subtitles/autosubs. To enable fallback transcription, set NOTES_RUNNER_TRANSCRIBE_CLI",
            advanced_doc_path=doc,
        )
    )


def parakeet_available() -> bool:
    """Check if MacWhisper CLI is available for Parakeet transcription."""
    return shutil.which("mw") is not None


MACWHISPER_DIRECT_AUDIO_SUFFIXES = {".m4a", ".mp3", ".wav", ".aif", ".aiff", ".flac"}
PARAKEET_MODEL = "parakeet-pro:nvidia_parakeet-v3"
PARAKEET_CHUNK_SECONDS = 600
PARAKEET_FAILURE_SETTLE_SECONDS = 30


def normalize_audio_for_macwhisper(audio_path: Path, output_dir: Path) -> Path:
    """Return a MacWhisper-friendly audio file, converting risky containers to m4a."""
    if audio_path.suffix.lower() in MACWHISPER_DIRECT_AUDIO_SUFFIXES:
        return audio_path

    cache_root = Path(
        os.environ.get("NOTES_MACWHISPER_NORMALIZED_CACHE")
        or (Path.home() / "Library/Caches/notes-runner/macwhisper-normalized")
    ).expanduser()
    source_hash = compute_file_sha256(audio_path)
    output_path = cache_root / f"{source_hash}-{audio_path.stem}.m4a"
    if output_path.is_file():
        return output_path

    cache_root.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    tmp_output_path = output_dir / f"{audio_path.stem}-{uuid.uuid4().hex}.m4a"
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "error",
        "-i",
        str(audio_path),
        "-vn",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        str(tmp_output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except FileNotFoundError:
        raise ValueError("ffmpeg not found — install ffmpeg to normalize audio for MacWhisper") from None
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise ValueError(f"ffmpeg failed normalizing {audio_path} for MacWhisper: {detail}") from exc
    cache_tmp_path = cache_root / f".{source_hash}-{uuid.uuid4().hex}.m4a"
    shutil.copy2(tmp_output_path, cache_tmp_path)
    cache_tmp_path.replace(output_path)
    return output_path


def _split_audio_for_parakeet(audio_path: Path, output_dir: Path, chunk_seconds: int = PARAKEET_CHUNK_SECONDS) -> list[tuple[Path, float]]:
    """Split audio into MacWhisper-friendly m4a chunks."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        raise ValueError("ffprobe not found — install ffmpeg to enable Parakeet chunk fallback") from None
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ffprobe failed for {audio_path}: {(exc.stderr or '').strip()}") from exc

    total_duration = float(probe.stdout.strip())
    num_chunks = math.ceil(total_duration / chunk_seconds)
    output_dir.mkdir(parents=True, exist_ok=True)
    chunks: list[tuple[Path, float]] = []
    for index in range(num_chunks):
        start = index * chunk_seconds
        chunk_path = output_dir / f"parakeet_chunk_{index:03d}.m4a"
        command = [
            "ffmpeg",
            "-y",
            "-v",
            "error",
            "-ss",
            str(start),
            "-t",
            str(chunk_seconds),
            "-i",
            str(audio_path),
            "-vn",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            str(chunk_path),
        ]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            raise ValueError("ffmpeg not found — install ffmpeg to enable Parakeet chunk fallback") from None
        except subprocess.CalledProcessError as exc:
            detail = (exc.stderr or exc.stdout or "").strip()
            raise ValueError(f"ffmpeg failed splitting chunk {index} of {audio_path}: {detail}") from exc
        chunks.append((chunk_path, float(start)))
    return chunks


def _run_macwhisper_parakeet(mw_bin: str, audio_path: Path, md_out: Path, json_out: Path) -> None:
    command = [
        mw_bin,
        "transcribe",
        str(audio_path),
        "--model",
        PARAKEET_MODEL,
        "--quiet",
        "--md-out",
        str(md_out),
        "--json-out",
        str(json_out),
    ]
    run_checked(command, label="MacWhisper Parakeet transcription")


def _format_parakeet_markdown_from_segments(segments: list[dict[str, object]]) -> str:
    lines: list[str] = []
    for segment in segments:
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        speaker = str(segment.get("speaker") or "Speaker 1").strip() or "Speaker 1"
        start_ms = segment.get("start_ms", 0)
        try:
            start_seconds = float(start_ms) / 1000.0
        except (TypeError, ValueError):
            start_seconds = 0.0
        lines.append(f"**{speaker}**: {text}")
        lines.append(f"*{format_mmss(start_seconds)}*")
        lines.append("")
    return "\n".join(lines).rstrip() + "\n" if lines else ""


def _merge_parakeet_chunk_payloads(chunk_payloads: list[tuple[dict[str, object], float]]) -> dict[str, object]:
    merged_segments: list[dict[str, object]] = []
    text_parts: list[str] = []
    chunk_summaries: list[dict[str, object]] = []
    for chunk_index, (payload, offset_seconds) in enumerate(chunk_payloads):
        chunk_text = str(payload.get("text") or "").strip()
        if chunk_text:
            text_parts.append(chunk_text)
        chunk_summaries.append(
            {
                "index": chunk_index,
                "offset_seconds": offset_seconds,
                "duration_seconds": payload.get("duration_seconds"),
                "transcription_seconds": payload.get("transcription_seconds"),
                "segments": len(payload.get("segments", [])) if isinstance(payload.get("segments"), list) else 0,
            }
        )
        segments = payload.get("segments")
        if not isinstance(segments, list):
            continue
        offset_ms = int(offset_seconds * 1000)
        for segment in segments:
            if not isinstance(segment, dict):
                continue
            adjusted = dict(segment)
            raw_start_ms = int(adjusted.get("start_ms") or 0)
            raw_end_ms = int(adjusted.get("end_ms") or raw_start_ms)
            start_ms = raw_start_ms + offset_ms
            end_ms = raw_end_ms + offset_ms
            adjusted["start_ms"] = start_ms
            adjusted["end_ms"] = end_ms
            adjusted["start"] = format_mmss(start_ms / 1000.0)
            adjusted["end"] = format_mmss(end_ms / 1000.0)
            merged_segments.append(adjusted)

    return {
        "transcription_succeeded": True,
        "chunked": True,
        "model_engine": "parakeetKitPro",
        "model_identifier": "nvidia_parakeet-v3",
        "text": " ".join(text_parts),
        "segments": merged_segments,
        "chunks": chunk_summaries,
    }


def _parakeet_payload_summary(json_out: Path) -> dict[str, object]:
    if not json_out.is_file():
        return {}
    try:
        payload = load_json(json_out)
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    if not isinstance(payload, dict):
        return {}
    segments = payload.get("segments")
    return {
        "duration_seconds": payload.get("duration_seconds"),
        "macwhisper_transcription_seconds": payload.get("transcription_seconds"),
        "segments": len(segments) if isinstance(segments, list) else None,
        "chunked": bool(payload.get("chunked")),
    }


def call_parakeet_transcribe(
    audio_path: Path,
    language: str | None = None,
    json_output_path: Path | None = None,
    telemetry_output_path: Path | None = None,
) -> str:
    """Transcribe using MacWhisper Parakeet, return transcript markdown."""
    mw_bin = shutil.which("mw")
    if not mw_bin:
        raise FileNotFoundError("MacWhisper CLI (`mw`) not found.")

    total_started = time.monotonic()
    with tempfile.TemporaryDirectory(prefix="notes-macwhisper-") as tmp_dir:
        tmp_path = Path(tmp_dir)
        normalize_started = time.monotonic()
        macwhisper_audio_path = normalize_audio_for_macwhisper(audio_path, tmp_path)
        normalize_ms = int((time.monotonic() - normalize_started) * 1000)
        md_out = tmp_path / "transcript.md"
        json_out = json_output_path or (tmp_path / "transcript.json")
        if json_output_path:
            json_output_path.parent.mkdir(parents=True, exist_ok=True)
        mode = "whole_file"
        chunks: list[dict[str, object]] = []
        full_attempt_error: str | None = None
        transcribe_started = time.monotonic()
        try:
            _run_macwhisper_parakeet(mw_bin, macwhisper_audio_path, md_out, json_out)
        except ValueError as exc:
            full_attempt_error = str(exc)
            if "MacWhisper reported a failed transcription" in full_attempt_error:
                if PARAKEET_FAILURE_SETTLE_SECONDS > 0:
                    time.sleep(PARAKEET_FAILURE_SETTLE_SECONDS)
                try:
                    _run_macwhisper_parakeet(mw_bin, macwhisper_audio_path, md_out, json_out)
                    mode = "whole_file_retry"
                except ValueError as retry_exc:
                    full_attempt_error = str(retry_exc)
            if mode != "whole_file_retry":
                mode = "chunked_fallback"
            if mode == "chunked_fallback":
                chunk_payloads: list[tuple[dict[str, object], float]] = []
                chunk_dir = tmp_path / "chunks"
                for chunk_index, (chunk_path, offset_seconds) in enumerate(_split_audio_for_parakeet(macwhisper_audio_path, chunk_dir)):
                    chunk_md_out = tmp_path / f"chunk_{chunk_index:03d}.md"
                    chunk_json_out = tmp_path / f"chunk_{chunk_index:03d}.json"
                    chunk_started = time.monotonic()
                    _run_macwhisper_parakeet(mw_bin, chunk_path, chunk_md_out, chunk_json_out)
                    chunk_ms = int((time.monotonic() - chunk_started) * 1000)
                    chunk_payload = load_json(chunk_json_out)
                    if not isinstance(chunk_payload, dict):
                        raise ValueError(f"MacWhisper chunk {chunk_index} produced invalid JSON")
                    chunk_payloads.append((chunk_payload, offset_seconds))
                    chunks.append(
                        {
                            "index": chunk_index,
                            "path": str(chunk_path),
                            "offset_seconds": offset_seconds,
                            "transcribe_ms": chunk_ms,
                            "json_output_path": str(chunk_json_out),
                        }
                    )
                merged_payload = _merge_parakeet_chunk_payloads(chunk_payloads)
                write_json(json_out, merged_payload)
                write_text(md_out, _format_parakeet_markdown_from_segments(merged_payload["segments"]))
        transcribe_ms = int((time.monotonic() - transcribe_started) * 1000)
        if not md_out.is_file():
            raise FileNotFoundError(f"MacWhisper produced no Markdown output at {md_out}")
        payload_summary = _parakeet_payload_summary(json_out)
        if telemetry_output_path:
            telemetry_output_path.parent.mkdir(parents=True, exist_ok=True)
            write_json(
                telemetry_output_path,
                {
                    "backend": "macwhisper_parakeet",
                    "model": PARAKEET_MODEL,
                    "language": language or "auto",
                    "source_path": str(audio_path),
                    "macwhisper_audio_path": str(macwhisper_audio_path),
                    "normalized_audio": macwhisper_audio_path != audio_path,
                    "md_output_path": str(md_out),
                    "json_output_path": str(json_out),
                    "mode": mode,
                    "full_attempt_error": full_attempt_error,
                    "chunks": chunks,
                    **payload_summary,
                    "normalize_ms": normalize_ms,
                    "transcribe_ms": transcribe_ms,
                    "total_ms": int((time.monotonic() - total_started) * 1000),
                },
            )
        return md_out.read_text(encoding="utf-8")


def choose_transcribe_backend(choice: str) -> str:
    normalized = choice.strip().lower()
    if normalized != "auto":
        return normalized
    if os.environ.get("GROQ_API_KEY"):
        return "groq"
    if is_macos() and parakeet_available():
        return "parakeet"
    hint = "Set GROQ_API_KEY (free at console.groq.com)."
    if is_macos():
        hint += " Or install MacWhisper CLI (`mw`) with parakeet-pro:nvidia_parakeet-v3 for local transcription."
    raise ValueError(hint)


def call_transcribe_helper(
    audio_path: Path,
    raw_output_path: Path,
    *,
    backend: str,
    language: str | None,
    skill_root: Path | None = None,
) -> dict:
    helper = resolve_transcribe_cli(skill_root=skill_root)
    model = "nova-3" if backend == "deepgram" else "gpt-4o-transcribe-diarize"
    command = [
        sys.executable,
        str(helper),
        str(audio_path),
        "--backend",
        backend,
        "--model",
        model,
        "--response-format",
        "diarized_json",
        "--out",
        str(raw_output_path),
    ]
    if language:
        command.extend(["--language", language])
    result = run_checked(command, label="transcribe helper")
    try:
        payload = json.loads(raw_output_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Transcription output was not valid JSON: {exc}") from exc
    if result.stdout.strip():
        payload["_stdout"] = result.stdout.strip()
    return payload


GROQ_STT_URL = "https://api.groq.com/openai/v1/audio/transcriptions"
GROQ_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB
GROQ_MAX_WAIT_SEC = 120  # Fall back to MLX if rate limit wait exceeds this
GROQ_CHUNK_DURATION_SEC = 1800  # 30-minute chunks for splitting large files
GROQ_AUDIO_SECONDS_PER_HOUR = 7200
GROQ_AUDIO_SECONDS_PER_DAY = 28800


class RateLimitError(ValueError):
    """Raised when Groq rate limits make cloud transcription a bad bet."""

    def __init__(self, message: str, *, details: dict[str, object] | None = None):
        super().__init__(message)
        self.details = details or {}


def _parse_groq_headers(raw_headers: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for line in raw_headers.splitlines():
        if ":" not in line:
            continue
        name, value = line.split(":", 1)
        normalized = name.strip().lower()
        if normalized:
            headers[normalized] = value.strip()
    return headers


def _parse_retry_after_seconds(headers: dict[str, str], message: str) -> int | None:
    retry_after = headers.get("retry-after")
    if retry_after and retry_after.isdigit():
        return int(retry_after)
    match = re.search(r"in\s+(\d+)m(\d+)s", message)
    if match:
        return int(match.group(1)) * 60 + int(match.group(2)) + 5
    match = re.search(r"in\s+(\d+)s", message)
    if match:
        return int(match.group(1))
    return None


def _classify_groq_rate_limit_scope(message: str, headers: dict[str, str]) -> str:
    lowered = message.lower()
    header_text = " ".join(headers)
    if any(token in lowered for token in (" per day", "daily", "asd")) or "day" in header_text:
        return "daily"
    if any(token in lowered for token in (" per hour", "hourly", "ash")) or "hour" in header_text:
        return "hourly"
    if "audio" in lowered or "audio" in header_text:
        return "audio"
    return "unknown"


def _groq_rate_limit_details(
    *,
    message: str,
    headers: dict[str, str] | None = None,
    preflight: dict[str, object] | None = None,
) -> dict[str, object]:
    header_map = headers or {}
    retry_after = _parse_retry_after_seconds(header_map, message)
    rate_headers = {
        key: value
        for key, value in header_map.items()
        if key == "retry-after" or key.startswith("x-ratelimit-")
    }
    details: dict[str, object] = {
        "scope": _classify_groq_rate_limit_scope(message, header_map),
        "retry_after_seconds": retry_after,
        "headers": rate_headers,
    }
    details["daily_limit_status"] = "exhausted" if details["scope"] == "daily" else "not_checked" if preflight else "unknown"
    details["hourly_limit_status"] = "exhausted" if details["scope"] == "hourly" else "unknown"
    if preflight:
        details["preflight"] = preflight
    return details


def _groq_transcribe_single(audio_path: Path, *, api_key: str, language: str | None) -> dict:
    """Transcribe a single audio file (must be under 25 MB) via Groq API."""
    with tempfile.TemporaryDirectory(prefix="notes-groq-response-") as tmp_dir:
        headers_path = Path(tmp_dir) / "headers.txt"
        command = [
            "curl", "-s", "--max-time", "600",
            "-D", str(headers_path),
            GROQ_STT_URL,
            "-H", f"Authorization: Bearer {api_key}",
            "-F", f"file=@{audio_path}",
            "-F", "model=whisper-large-v3-turbo",
            "-F", "response_format=verbose_json",
        ]
        if language:
            command.extend(["-F", f"language={language}"])

        result = subprocess.run(command, capture_output=True, text=True, check=False, timeout=660)
        headers = _parse_groq_headers(headers_path.read_text(encoding="utf-8")) if headers_path.is_file() else {}
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or f"exit code {result.returncode}"
        raise ValueError(f"Groq API error: {detail}")

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Groq response was not valid JSON: {exc}") from exc

    if "error" in payload:
        err = payload["error"]
        msg = err.get("message", str(err))
        # Extract retry-after hint from rate limit messages
        if err.get("code") == "rate_limit_exceeded":
            raise RateLimitError(msg, details=_groq_rate_limit_details(message=msg, headers=headers))
        raise ValueError(f"Groq API error: {msg}")

    if headers:
        payload["_groq_rate_limit"] = _groq_rate_limit_details(message="", headers=headers)
    return payload


def probe_media_duration_seconds(path: Path) -> int:
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        return 0
    except subprocess.CalledProcessError:
        return 0
    try:
        return max(0, int(float(probe.stdout.strip())))
    except ValueError:
        return 0


def _split_audio_ffmpeg(audio_path: Path, output_dir: Path, chunk_seconds: int) -> list[tuple[Path, float]]:
    """Split audio into chunks with ffmpeg. Returns list of (chunk_path, start_offset_seconds)."""
    try:
        probe = subprocess.run(
            ["ffprobe", "-v", "quiet", "-show_entries", "format=duration", "-of", "csv=p=0", str(audio_path)],
            capture_output=True, text=True, check=True,
        )
    except FileNotFoundError:
        raise ValueError("ffprobe not found — install ffmpeg to enable audio splitting") from None
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ffprobe failed for {audio_path}: {(exc.stderr or '').strip()}") from exc
    total_duration = float(probe.stdout.strip())
    num_chunks = math.ceil(total_duration / chunk_seconds)

    chunks: list[tuple[Path, float]] = []
    for i in range(num_chunks):
        start = i * chunk_seconds
        chunk_path = output_dir / f"chunk_{i:03d}.mp3"
        cmd = [
            "ffmpeg", "-y", "-v", "quiet",
            "-ss", str(start),
            "-t", str(chunk_seconds),
            "-i", str(audio_path),
            "-ac", "1", "-ar", "16000", "-b:a", "48k",
            str(chunk_path),
        ]
        try:
            subprocess.run(cmd, check=True, capture_output=True)
        except FileNotFoundError:
            raise ValueError("ffmpeg not found — install ffmpeg to enable audio splitting") from None
        except subprocess.CalledProcessError as exc:
            raise ValueError(f"ffmpeg failed splitting chunk {i} of {audio_path}: {(exc.stderr or '').strip()}") from exc
        chunks.append((chunk_path, float(start)))
    return chunks


def _merge_groq_payloads(chunk_results: list[tuple[dict, float]]) -> dict:
    """Merge multiple Groq payloads, adjusting segment timestamps by chunk offsets."""
    all_segments: list[dict] = []
    all_text_parts: list[str] = []
    rate_limits: list[dict[str, object]] = []

    for payload, offset in chunk_results:
        text = payload.get("text", "")
        if text:
            all_text_parts.append(text.strip())
        rate_limit = payload.get("_groq_rate_limit")
        if isinstance(rate_limit, dict):
            rate_limits.append(rate_limit)
        for seg in payload.get("segments", []):
            adjusted = dict(seg)
            adjusted["start"] = seg.get("start", 0) + offset
            adjusted["end"] = seg.get("end", 0) + offset
            all_segments.append(adjusted)

    merged = {
        "text": " ".join(all_text_parts),
        "segments": all_segments,
        "language": chunk_results[0][0].get("language") if chunk_results else None,
    }
    if rate_limits:
        merged["_groq_rate_limit"] = {
            "chunks": rate_limits,
            "latest": rate_limits[-1],
        }
    return merged


def call_groq_transcribe(
    audio_path: Path,
    raw_output_path: Path,
    *,
    language: str | None,
) -> dict:
    """Transcribe audio via Groq Whisper API. Auto-splits files larger than 25 MB."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError("GROQ_API_KEY not set.")

    duration_seconds = probe_media_duration_seconds(audio_path)
    if duration_seconds >= GROQ_AUDIO_SECONDS_PER_HOUR:
        preflight = {
            "duration_seconds": duration_seconds,
            "hourly_limit_seconds": GROQ_AUDIO_SECONDS_PER_HOUR,
            "daily_limit_seconds": GROQ_AUDIO_SECONDS_PER_DAY,
            "reason": "audio duration is at or above Groq hourly audio-seconds limit",
        }
        raise RateLimitError(
            f"Groq preflight skipped: audio is {duration_seconds}s, hourly limit is {GROQ_AUDIO_SECONDS_PER_HOUR}s",
            details=_groq_rate_limit_details(
                message="preflight hourly ASH limit",
                preflight=preflight,
            ),
        )

    file_size = audio_path.stat().st_size
    if file_size <= GROQ_MAX_FILE_SIZE:
        payload = _groq_transcribe_single(audio_path, api_key=api_key, language=language)
        write_json(raw_output_path, payload)
        return payload

    # Large file — split, transcribe chunks, merge
    print(f"File is {file_size / 1024 / 1024:.0f} MB — splitting into chunks for Groq API...", file=sys.stderr)
    with tempfile.TemporaryDirectory(prefix="notes-groq-chunks-") as tmp_dir:
        chunks = _split_audio_ffmpeg(audio_path, Path(tmp_dir), GROQ_CHUNK_DURATION_SEC)
        print(f"Split into {len(chunks)} chunks, transcribing...", file=sys.stderr)
        chunk_results: list[tuple[dict, float]] = []
        for i, (chunk_path, offset) in enumerate(chunks):
            print(f"  Chunk {i + 1}/{len(chunks)} ({chunk_path.stat().st_size / 1024 / 1024:.1f} MB)...", file=sys.stderr)
            payload = None
            for attempt in range(5):
                try:
                    payload = _groq_transcribe_single(chunk_path, api_key=api_key, language=language)
                    break
                except RateLimitError as exc:
                    wait = int(exc.details.get("retry_after_seconds") or 180)
                    if wait > GROQ_MAX_WAIT_SEC:
                        raise RateLimitError(
                            f"Rate limit wait {wait}s exceeds threshold {GROQ_MAX_WAIT_SEC}s",
                            details={
                                **exc.details,
                                "retry_after_seconds": wait,
                                "wait_threshold_seconds": GROQ_MAX_WAIT_SEC,
                            },
                        ) from exc
                    print(f"    Rate limit, waiting {wait}s...", file=sys.stderr)
                    time.sleep(wait)
                except ValueError as exc:
                    if attempt < 4:
                        wait = 10 * (attempt + 1)
                        print(f"    Retry {attempt + 1}/4 in {wait}s ({exc})...", file=sys.stderr)
                        time.sleep(wait)
                    else:
                        raise
            if payload is None:
                raise ValueError("All 5 transcription attempts failed due to rate limiting")
            chunk_results.append((payload, offset))
            if i < len(chunks) - 1:
                time.sleep(2)

    merged = _merge_groq_payloads(chunk_results)
    write_json(raw_output_path, merged)
    return merged
