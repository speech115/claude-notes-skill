# Advanced Setup

Starter mode supports YouTube (with subs) and local `.md`/`.txt`. Everything below is optional.

## Audio transcription

**Option A — Local MLX Whisper (Apple Silicon, no API key):**

```bash
python3 -m pip install mlx-whisper
```

**Option B — Groq Cloud API (any Mac, faster for large files):**

```bash
export GROQ_API_KEY=your-key-here
```

Get a free key at [console.groq.com](https://console.groq.com). If Groq hits rate limits (>2 min wait), the runner automatically falls back to local MLX Whisper.

After setup, these commands work:

```bash
notes-runner audio /path/to/file.mp3 --language en --prepare --json
notes-runner audio /path/to/file.mp3 --title "Lecture 1" --prepare --json
notes-runner audio /path/to/file.mp3 --transcribe-backend groq --prepare --json
```

## Batch processing

Process an entire course folder:

```bash
notes-runner batch /path/to/course/ --language en --prepare --json
```

This will:
- find all `.mp3`, `.m4a`, `.wav`, `.md`, `.txt` files in the directory
- transcribe/prepare each one with progress reporting (`[1/8] file.mp3...`)
- write `batch-index.json` and `batch-index.html` with links to all notes
- reuse existing transcripts (skip already-processed files)

The runner also checks for adjacent `.json` files (Whisper output) next to audio files and reuses them automatically.

## Speaker diarization

Install `whisperx` separately and use:

```bash
~/.claude/skills/notes/scripts/notes-runner audio /absolute/path/to/file.m4a --prepare --diarize --json
```

If `whisperx` is missing, the runner falls back to plain transcription.

## YouTube fallback transcription without subtitles

Starter mode expects subtitles/autosubs.

If a video has no usable subtitles, you can wire your own transcription helper by setting:

```bash
export NOTES_RUNNER_TRANSCRIBE_CLI=/absolute/path/to/transcribe_diarize.py
```

You also need one of:

```bash
export OPENAI_API_KEY=...
```

or:

```bash
export DEEPGRAM_API_KEY=...
```

Then the runner can use API transcription fallback for subtitle-poor videos.

## Telegram auto-delivery

Telegram delivery is disabled by default.

To enable it:

1. Install or provide a compatible `digest-runner`
2. Point the runner at it:

```bash
export NOTES_RUNNER_DIGEST_RUNNER=/absolute/path/to/digest-runner
```

3. Edit `~/.claude/skills/notes/config.json`

Example:

```json
{
  "telegram_delivery": {
    "enabled": true,
    "chat": "-1001234567890",
    "mcp_url": "http://127.0.0.1:8799/mcp",
    "parse_mode": "md"
  }
}
```

## Telegram voice messages

This needs both:

- audio transcription prerequisites
- Telegram media access via MCP

Example runner command:

```bash
~/.claude/skills/notes/scripts/notes-runner telegram "@username_or_chat_id" MESSAGE_ID --prepare --json
```

## Optional environment variables

- `NOTES_RUNNER_TRANSCRIBE_CLI`
- `NOTES_RUNNER_DIGEST_RUNNER`
- `NOTES_RUNNER_YTDLP_BIN`
- `NOTES_SKILL_ROOT`
