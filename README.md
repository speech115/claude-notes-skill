# Claude Notes Skill

`/notes` skill for Claude Code. Turns YouTube videos, audio files, and text transcripts into detailed study packages with timestamped blocks, TL;DR, and appendix.

Works on **macOS**, **Linux**, and **WSL**.

## One-command install

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/speech115/claude-notes-skill/main/install.sh)
```

## Requirements

**macOS:**
```bash
brew install python pandoc yt-dlp ffmpeg
```

**Linux / WSL:**
```bash
sudo apt install python3 pandoc ffmpeg
pip install yt-dlp
```

**Windows:** Install [WSL](https://learn.microsoft.com/en-us/windows/wsl/install) first, then follow Linux instructions.

## First run

Restart Claude Code, then:

```text
/notes https://www.youtube.com/watch?v=...
/notes /absolute/path/to/file.md
/notes /path/to/lecture.mp3
```

Or just say "сделай конспект" with a URL or file path.

Run `notes-runner doctor` to check your setup.

## What works

| Input | Requirements |
|-------|-------------|
| YouTube URL (with subs) | starter deps only |
| Local `.md` / `.txt` | starter deps only |
| Audio files (`.mp3`, `.m4a`, `.wav`, `.ogg`) | + audio transcription setup |
| Batch (directory of files) | same as individual files |
| Telegram voice messages | + MCP setup |

## Audio transcription

Required for audio/video files. Pick one:

**Option A — Groq API (all platforms, recommended):**
```bash
export GROQ_API_KEY=your-key-here
```
Free key at [console.groq.com](https://console.groq.com). Fast, no local dependencies.

**Option B — MLX Whisper (macOS Apple Silicon only):**
```bash
pip install mlx-whisper
```
Runs locally, no API key needed. If Groq hits rate limits, the runner falls back to MLX Whisper automatically (macOS only).

## Batch mode

Process an entire course/folder at once:

```bash
notes-runner batch /path/to/course/audio/ --language en --prepare --json
```

Produces individual notes for each file + a `batch-index.html` with links.

## CLI flags

| Flag | Commands | Description |
|------|----------|-------------|
| `--title "Name"` | `audio`, `local` | Override bundle directory name |
| `--language en` | `audio`, `batch`, `youtube` | Audio language hint (default: `ru`) |
| `--transcribe-backend groq` | `audio`, `batch` | Force Groq API |
| `--prepare` | all | Run chunking/prepare after transcription |
| `--refresh` | all | Re-transcribe even if cached |

## Troubleshooting

```bash
notes-runner doctor        # check all prerequisites
notes-runner doctor --json # machine-readable output
```

## Advanced features

See [ADVANCED.md](ADVANCED.md) for:
- speaker diarization
- YouTube fallback transcription
- Telegram voice messages
- Telegram auto-delivery

## Safety note

Do not copy someone else's `config.json`. Use `config.example.json` as template.
