from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from .common import load_json
from .transcript_runtime import format_mmss


AUDIO_EXTENSIONS = {".m4a", ".mp3", ".wav", ".ogg", ".opus"}
VIDEO_EXTENSIONS = {".webm", ".mp4", ".mkv", ".mov", ".avi"}


def normalize_transcript_text(text: str) -> str:
    """Clean up whisper-generated transcript text.

    Steps:
    1. Remove <unk> tokens
    2. Clean up excessive whitespace within lines
    3. Remove duplicate consecutive lines
    4. Parse into (speaker, text, timestamp) entries
    5. Merge fragmented sentences from the same speaker
    6. Remove empty speaker turns
    7. Reconstruct markdown format
    """
    if not text or not text.strip():
        return ""

    text = text.replace("<unk>", "")

    lines = text.split("\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in lines]

    deduped: list[str] = []
    for line in lines:
        if not deduped or line != deduped[-1]:
            deduped.append(line)
    lines = deduped

    speaker_re = re.compile(
        r"^(?:\*\*(.+?)\*\*|([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 .,_\-]{0,40}))\s*:\s*(.*)"
    )
    timestamp_re = re.compile(r"^\*([^*]+)\*$")

    entries: list[dict[str, str]] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        speaker_match = speaker_re.match(line)
        if speaker_match:
            speaker = (speaker_match.group(1) or speaker_match.group(2) or "").strip()
            spoken_text = speaker_match.group(3).strip()
            timestamp = ""
            if index + 1 < len(lines) and not lines[index + 1]:
                if index + 2 < len(lines):
                    timestamp_match = timestamp_re.match(lines[index + 2])
                    if timestamp_match:
                        timestamp = timestamp_match.group(1)
                        index += 3
                        entries.append({"speaker": speaker, "text": spoken_text, "timestamp": timestamp})
                        continue
            if index + 1 < len(lines):
                timestamp_match = timestamp_re.match(lines[index + 1])
                if timestamp_match:
                    timestamp = timestamp_match.group(1)
                    index += 2
                    entries.append({"speaker": speaker, "text": spoken_text, "timestamp": timestamp})
                    continue
            entries.append({"speaker": speaker, "text": spoken_text, "timestamp": timestamp})
            index += 1
            continue
        index += 1

    if not entries:
        cleaned = "\n".join(lines).strip()
        return cleaned + "\n" if cleaned else ""

    terminal_punct_re = re.compile(r"[.!?\u2026]$")
    merged: list[dict[str, str]] = []
    for entry in entries:
        if (
            merged
            and merged[-1]["speaker"] == entry["speaker"]
            and merged[-1]["text"]
            and not terminal_punct_re.search(merged[-1]["text"])
        ):
            merged[-1]["text"] = merged[-1]["text"] + " " + entry["text"]
        else:
            merged.append(dict(entry))
    entries = merged

    noise_re = re.compile(r"^[.\s,;:]*$")
    entries = [entry for entry in entries if entry["text"] and not noise_re.match(entry["text"])]

    result_lines: list[str] = []
    for entry in entries:
        result_lines.append(f"**{entry['speaker']}**: {entry['text']}")
        if entry["timestamp"]:
            result_lines.append(f"*{entry['timestamp']}*")
        result_lines.append("")

    result = "\n".join(result_lines).strip()
    return result + "\n" if result else ""


def copy_local_source(source_path: Path, bundle_dir: Path) -> Path:
    source_dir = bundle_dir / "source"
    source_dir.mkdir(parents=True, exist_ok=True)
    destination = source_dir / source_path.name
    shutil.copy2(source_path, destination)
    return destination


def _fallback_run_checked(
    command: list[str],
    *,
    cwd: Path | None = None,
    label: str,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        stdout = result.stdout.strip()
        stderr = result.stderr.strip()
        detail = stderr or stdout or f"exit code {result.returncode}"
        raise ValueError(f"{label} failed: {detail}")
    return result


def _resolve_run_checked() -> Callable[..., subprocess.CompletedProcess[str]]:
    main_module = sys.modules.get("__main__")
    candidate = getattr(main_module, "run_checked", None)
    if callable(candidate):
        return candidate
    return _fallback_run_checked


def run_mlx_whisper(audio_path: Path, output_dir: Path, *, model: str, language: str | None) -> Path:
    """Run mlx_whisper CLI and return path to the JSON output file."""
    mlx_bin = shutil.which("mlx_whisper")
    if mlx_bin:
        command = [mlx_bin]
    else:
        command = [sys.executable, "-m", "mlx_whisper"]
    command += ["--model", model]
    if language:
        command.extend(["--language", language])
    command += [
        "--output-format",
        "json",
        "--output-dir",
        str(output_dir),
        str(audio_path),
    ]
    _resolve_run_checked()(command, label="mlx_whisper transcription")
    json_output = output_dir / (audio_path.stem + ".json")
    if not json_output.is_file():
        candidates = sorted(output_dir.glob("*.json"))
        if not candidates:
            raise FileNotFoundError(f"mlx_whisper produced no JSON output in {output_dir}")
        json_output = candidates[0]
    return json_output


def whisper_json_to_transcript_markdown(whisper_json_path: Path) -> str:
    """Convert whisper JSON output (with segments) to timestamped transcript markdown.

    Produces clean ``*MM:SS* text`` lines (one per segment) that are directly
    compatible with the prepare/extraction pipeline. No speaker labels are
    emitted because vanilla MLX Whisper has no diarization.
    """
    payload = load_json(whisper_json_path)
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return f"*00:00* {text.strip()}\n"
        raise ValueError("Whisper JSON contains no segments or text.")

    lines: list[str] = []
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = segment.get("start", 0)
        lines.append(f"*{format_mmss(start)}* {text}")

    return "\n".join(lines) + "\n" if lines else ""


def run_whisperx_diarize(audio_path: Path, output_dir: Path, *, model: str, language: str | None) -> Path:
    """Run whisperx with --diarize and return path to the JSON output file."""
    output_dir.mkdir(parents=True, exist_ok=True)
    command = [
        "whisperx",
        str(audio_path),
        "--model",
        model,
        "--diarize",
        "--output_format",
        "json",
        "--output_dir",
        str(output_dir),
    ]
    if language:
        command.extend(["--language", language])
    hf_token = os.environ.get("HF_TOKEN") or os.environ.get("HUGGING_FACE_HUB_TOKEN")
    if hf_token:
        command.extend(["--hf_token", hf_token])
    _resolve_run_checked()(command, label="whisperx diarization")
    json_output = output_dir / (audio_path.stem + ".json")
    if not json_output.is_file():
        candidates = sorted(output_dir.glob("*.json"))
        if not candidates:
            raise FileNotFoundError(f"whisperx produced no JSON output in {output_dir}")
        json_output = candidates[0]
    return json_output


def whisperx_json_to_transcript_markdown(whisperx_json_path: Path) -> str:
    """Convert whisperx JSON output (with speaker-labeled segments) to transcript markdown."""
    payload = load_json(whisperx_json_path)
    segments = payload.get("segments")
    if not isinstance(segments, list) or not segments:
        text = payload.get("text")
        if isinstance(text, str) and text.strip():
            return f"**Speaker 1**: {text.strip()}\n"
        raise ValueError("WhisperX JSON contains no segments or text.")

    raw_speakers: set[str] = set()
    for segment in segments:
        if isinstance(segment, dict):
            speaker = segment.get("speaker")
            if isinstance(speaker, str) and speaker:
                raw_speakers.add(speaker)
    sorted_speakers = sorted(raw_speakers)
    speaker_map = {raw: f"Speaker {index + 1}" for index, raw in enumerate(sorted_speakers)}

    lines: list[str] = []
    prev_speaker: str | None = None
    for segment in segments:
        if not isinstance(segment, dict):
            continue
        text = str(segment.get("text") or "").strip()
        if not text:
            continue
        start = segment.get("start", 0)
        raw_speaker = segment.get("speaker")
        speaker_label = speaker_map.get(str(raw_speaker), "Speaker 1") if raw_speaker else "Speaker 1"

        if speaker_label == prev_speaker and lines and not lines[-1]:
            lines.pop()
            if lines:
                lines.pop()
            lines.append(text)
            lines.append(f"*{format_mmss(start)}*")
            lines.append("")
        else:
            lines.append(f"**{speaker_label}**: {text}")
            lines.append(f"*{format_mmss(start)}*")
            lines.append("")
        prev_speaker = speaker_label

    return "\n".join(lines).rstrip() + "\n" if lines else ""


def extract_audio_from_video(video_path: Path, output_dir: Path) -> Path:
    """Extract audio from video file as compressed mono mp3."""
    output_path = output_dir / (video_path.stem + ".mp3")
    command = [
        "ffmpeg",
        "-y",
        "-v",
        "quiet",
        "-i",
        str(video_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        "48k",
        str(output_path),
    ]
    try:
        subprocess.run(command, check=True, capture_output=True)
    except FileNotFoundError:
        raise ValueError("ffmpeg not found — install ffmpeg to enable video audio extraction") from None
    except subprocess.CalledProcessError as exc:
        raise ValueError(f"ffmpeg failed extracting audio from {video_path}: {(exc.stderr or '').strip()}") from exc
    print(f"Extracted audio: {output_path} ({output_path.stat().st_size / 1024 / 1024:.1f} MB)", file=sys.stderr)
    return output_path
