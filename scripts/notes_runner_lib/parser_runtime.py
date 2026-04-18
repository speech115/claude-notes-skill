from __future__ import annotations

import argparse


def build_parser(
    default_output_root: str,
    default_telegram_mcp_url: str,
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="notes-runner",
        description="Run deterministic helper steps for the notes transcript pipeline.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare", help="Run prepare.sh and summarize the result.")
    prepare_parser.add_argument("files", nargs="+", help="Transcript files.")
    prepare_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    status_parser = subparsers.add_parser("status", help="Inspect a notes work directory.")
    status_parser.add_argument("work_dir", help="Work directory path.")
    status_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON status.")

    replace_speakers_parser = subparsers.add_parser(
        "replace-speakers",
        help="Replace Speaker N labels with real names from speakers.txt.",
    )
    replace_speakers_parser.add_argument("work_dir", help="Work directory path.")
    replace_speakers_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON result.")

    tldr_parser = subparsers.add_parser(
        "build-tldr",
        help="Build tldr.md deterministically from summary_chunk_*.md files.",
    )
    tldr_parser.add_argument("work_dir", help="Work directory path.")
    tldr_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON result.")

    appendix_parser = subparsers.add_parser(
        "ensure-appendix",
        help="Build appendix.md deterministically from manifests and summaries when needed.",
    )
    appendix_parser.add_argument("work_dir", help="Work directory path.")
    appendix_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON result.")

    assemble_parser = subparsers.add_parser("assemble", help="Run assemble.sh for an existing work dir.")
    assemble_parser.add_argument("work_dir", help="Work directory path.")
    assemble_parser.add_argument("output_md", help="Output markdown path.")
    assemble_parser.add_argument("output_html", help="Output HTML path.")
    assemble_parser.add_argument("title", help="Document title.")
    assemble_parser.add_argument("--send-to", default=None, help="Override Telegram chat target (e.g. @username or chat_id)")
    assemble_parser.add_argument(
        "--skip-telegram",
        action="store_true",
        default=False,
        help="Skip Telegram delivery even if config.json enables it.",
    )
    assemble_parser.add_argument(
        "--force-telegram-resend",
        action="store_true",
        default=False,
        help="Force Telegram delivery even if the current HTML was already delivered successfully.",
    )
    assemble_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON result.")

    youtube_parser = subparsers.add_parser(
        "youtube",
        help="Create a reusable notes bundle from a YouTube URL.",
    )
    youtube_parser.add_argument("url", help="YouTube video URL.")
    youtube_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    youtube_parser.add_argument(
        "--transcribe-backend",
        choices=("auto", "groq"),
        default="auto",
        help="API backend for subtitle fallback transcription.",
    )
    youtube_parser.add_argument(
        "--language",
        choices=("auto", "en", "ru"),
        default="auto",
        help="Optional language hint for API transcription.",
    )
    youtube_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run notes prepare.sh after transcript creation and link work/ into the bundle.",
    )
    youtube_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Refresh transcript artifacts even if the bundle already exists.",
    )
    youtube_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    local_parser = subparsers.add_parser(
        "local",
        help="Create a reusable notes bundle from a local markdown/text file.",
    )
    local_parser.add_argument("path", help="Local markdown or text file.")
    local_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    local_parser.add_argument(
        "--title",
        default=None,
        help="Override title for bundle directory naming (instead of first line of file).",
    )
    local_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run notes prepare.sh after transcript creation and link work/ into the bundle.",
    )
    local_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Refresh transcript artifacts even if the bundle already exists.",
    )
    local_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    audio_parser = subparsers.add_parser(
        "audio",
        help="Create a reusable notes bundle from a local audio file (.m4a, .mp3, .wav, .ogg, .opus).",
    )
    audio_parser.add_argument("path", help="Local audio file path.")
    audio_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    audio_parser.add_argument(
        "--title",
        default=None,
        help="Override title for bundle directory naming (instead of filename stem).",
    )
    audio_parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="Whisper model for transcription.",
    )
    audio_parser.add_argument(
        "--language",
        default="ru",
        help="Language hint for whisper transcription.",
    )
    audio_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run notes prepare.sh after transcript creation and link work/ into the bundle.",
    )
    audio_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Re-transcribe even if transcript already exists.",
    )
    audio_parser.add_argument(
        "--transcribe-backend",
        choices=("auto", "groq"),
        default="auto",
        help="API backend for transcription. When set, uses Groq instead of local whisper.",
    )
    audio_parser.add_argument(
        "--diarize",
        action="store_true",
        default=False,
        help="Run speaker diarization via whisperx (requires whisperx installed).",
    )
    audio_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    telegram_parser = subparsers.add_parser(
        "telegram",
        help="Download a voice/audio message from Telegram and create a notes bundle.",
    )
    telegram_parser.add_argument("chat", help="Chat identifier (@username, phone, or numeric ID).")
    telegram_parser.add_argument("message_id", type=int, help="Message ID to download.")
    telegram_parser.add_argument(
        "--mcp-url",
        default=default_telegram_mcp_url,
        help="Telegram MCP server URL.",
    )
    telegram_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    telegram_parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="Whisper model for transcription.",
    )
    telegram_parser.add_argument(
        "--language",
        default="ru",
        help="Language hint for whisper transcription.",
    )
    telegram_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run notes prepare.sh after transcript creation.",
    )
    telegram_parser.add_argument(
        "--diarize",
        action="store_true",
        default=False,
        help="Run speaker diarization via whisperx (requires whisperx installed).",
    )
    telegram_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    auto_parser = subparsers.add_parser(
        "auto",
        help="Auto-detect input type (YouTube URL, audio/video file, or text file) and route accordingly.",
    )
    auto_parser.add_argument("input", help="File path or YouTube URL.")
    auto_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    auto_parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="Whisper model for audio transcription.",
    )
    auto_parser.add_argument(
        "--language",
        default="auto",
        help="Language hint for transcription.",
    )
    auto_parser.add_argument(
        "--transcribe-backend",
        choices=("auto", "groq"),
        default="auto",
        help="API backend for YouTube subtitle fallback transcription.",
    )
    auto_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run notes prepare.sh after transcript creation.",
    )
    auto_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Refresh/re-transcribe even if artifacts already exist.",
    )
    auto_parser.add_argument(
        "--diarize",
        action="store_true",
        default=False,
        help="Run speaker diarization via whisperx (requires whisperx installed).",
    )
    auto_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    batch_parser = subparsers.add_parser(
        "batch",
        help="Process multiple audio/text files from a directory into notes bundles.",
    )
    batch_parser.add_argument("directory", help="Directory containing audio or text files to process.")
    batch_parser.add_argument(
        "--output-root",
        default=default_output_root,
        help="Root directory for stored notes bundles.",
    )
    batch_parser.add_argument(
        "--model",
        default="mlx-community/whisper-large-v3-turbo",
        help="Whisper model for audio transcription.",
    )
    batch_parser.add_argument(
        "--language",
        default="auto",
        help="Language hint for transcription.",
    )
    batch_parser.add_argument(
        "--transcribe-backend",
        choices=("auto", "groq"),
        default="auto",
        help="API backend for transcription.",
    )
    batch_parser.add_argument(
        "--prepare",
        action="store_true",
        default=False,
        help="Run prepare after each transcription.",
    )
    batch_parser.add_argument(
        "--refresh",
        action="store_true",
        default=False,
        help="Re-transcribe even if transcript already exists.",
    )
    batch_parser.add_argument("--json", action="store_true", default=False, help="Emit JSON summary.")

    doctor_parser = subparsers.add_parser("doctor", help="Check prerequisites and environment.")
    doctor_parser.add_argument("--json", action="store_true", default=False, help="Output as JSON.")

    return parser


__all__ = ["build_parser"]
