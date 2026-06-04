# Advanced Setup

Starter mode supports YouTube (with subs) and local `.md`/`.txt`. Everything below is optional.

## Audio transcription

**Option A — Local MacWhisper Parakeet (macOS, no API key):**

```bash
mw models select parakeet-pro:nvidia_parakeet-v3
```

**Option B — Groq Cloud API (any Mac, faster for large files):**

```bash
export GROQ_API_KEY=your-key-here
```

Get a free key at [console.groq.com](https://console.groq.com). If Groq hits rate limits (>2 min wait), the runner automatically falls back to local MacWhisper Parakeet.

After setup, these commands work:

```bash
notes-runner audio /path/to/file.mp3 --language en --prepare --json
notes-runner audio /path/to/file.mp3 --title "Lecture 1" --prepare --json
notes-runner audio /path/to/file.mp3 --transcribe-backend groq --prepare --json
notes-runner audio /path/to/file.mp3 --transcribe-backend parakeet --prepare --json
```

## Batch processing

Process an entire course folder:

```bash
notes-runner batch /path/to/course/ --language en --prepare --json
```

This will:
- find all `.mp3`, `.m4a`, `.wav`, `.md`, `.txt` files in the directory
- transcribe/prepare one bundle per supported file with progress reporting (`[1/8] file.mp3...`)
- write `batch-index.json` and `batch-index.html`
- leave final extraction/assemble/Telegram completion as a per-item step unless the runner result explicitly includes final artifacts
- reuse existing transcripts (skip already-processed files)

The runner also checks for adjacent `.json` files (Whisper output) next to audio files and reuses them automatically.

## Speaker diarization

Install `whisperx` separately and use:

```bash
notes-runner audio /absolute/path/to/file.m4a --prepare --diarize --json
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

Telegram delivery is opt-in and local to your machine. Configure it only after you have a compatible `digest-runner` and a chat target you control.

To enable it:

1. Install or provide a compatible `digest-runner`
2. Point the runner at it:

```bash
export NOTES_RUNNER_DIGEST_RUNNER=/absolute/path/to/digest-runner
```

3. Copy `config.example.json` to your installed skill's `config.json`, then set `"enabled": true` and your own chat target.
   If you are on Codex-first install layout, this is usually `~/.codex/skills/notes/config.json`.
4. Confirm the Telegram MCP HTTP daemon exposes `send_file` (`mcporter list telegram`). `digest-runner send-file` depends on it.

Example:

```json
{
  "telegram_delivery": {
    "enabled": true,
    "chat": "@your_channel_or_chat_id",
    "mcp_url": "http://127.0.0.1:8799/mcp",
    "parse_mode": "md"
  }
}
```

Set `"enabled": false` if you want to disable auto-delivery on this machine.

## Telegram voice messages

This needs both:

- audio transcription prerequisites
- Telegram media access via MCP

Example runner command:

```bash
notes-runner telegram "@username_or_chat_id" MESSAGE_ID --prepare --json
```

## Optional environment variables

- `NOTES_RUNNER_TRANSCRIBE_CLI`
- `NOTES_RUNNER_DIGEST_RUNNER`
- `NOTES_RUNNER_YTDLP_BIN`
- `NOTES_SKILL_ROOT`
