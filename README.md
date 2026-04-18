# Notes Skill

`/notes` skill for local coding agents. Turns YouTube videos, audio/video files, and text transcripts into detailed study packages with timestamped blocks, TL;DR, and appendix.

Works on **macOS**, **Linux**, and **WSL**.

## Install

Fastest install:

```bash
curl -fsSL https://raw.githubusercontent.com/speech115/notes-skill/main/install.sh | bash
```

That is the intended Codex flow. It installs the skill, runs a smoke check, and tells you whether `notes-runner` is globally available.

Local checkout works too:

```bash
cd /path/to/notes-skill
bash ./install.sh
```

Install target order:
- keep an existing install where it already lives
- otherwise prefer `$CODEX_HOME/skills/notes` (usually `~/.codex/skills/notes`)
- fall back to `~/.agents/skills/notes` or `~/.claude/skills/notes` only when those already exist

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

Restart your agent client, then:

```text
/notes https://www.youtube.com/watch?v=...
/notes /absolute/path/to/file.md
/notes /path/to/lecture.mp3
/notes /path/to/recording.mp4
```

Or just say "сделай конспект" with a URL or file path.

The installer already runs a doctor smoke check for you. If you want to rerun it manually:

```bash
notes-runner doctor
```

If `notes-runner` is not on PATH yet, use the full path the installer prints at the end.

## Stable workflow

Treat this repo as the single source of truth. Do not patch the live skill directory by hand.

- Work in a feature branch.
- For active local development, link the live skill once:
  - `scripts/dev-link-live.sh`
- Before `promote-live`, make sure `git status --short` is clean.
- `scripts/promote-live.sh --allow-dirty` is an escape hatch for forensics, not the happy path.
- Run `scripts/release-check.sh`.
- Promote the checked-out repo to the live skill with `scripts/promote-live.sh`.
- Tag the stable commit after the live smoke check passes.

See [RELEASE.md](RELEASE.md).

## What works

| Input | Requirements |
|-------|-------------|
| YouTube URL (with subs) | starter deps only |
| Local `.md` / `.txt` | starter deps only |
| Audio/video files (`.mp3`, `.m4a`, `.wav`, `.ogg`, `.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`) | + audio transcription setup |
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
notes-runner status "$WORK_DIR" --json
```

Safe local smoke-check without Telegram side effects:

```bash
NOTES_RUNNER_DISABLE_TELEGRAM=1 notes-runner assemble "$WORK_DIR" "$OUTPUT_MD" "$OUTPUT_HTML" "$TITLE" --skip-telegram --json
```

Debug artifacts worth opening first:

- `run.json` — short bundle summary
- `timeline.jsonl` — one line per run of this note
- `runs/<run_id>.json` — full snapshot for a specific note revision
- `trace.jsonl` — append-only stage trace
- `work/prepare_state.json` and `work/stages/*.json` — orchestration state

When `notes-runner` is launched from Codex, it auto-attaches the current `CODEX_THREAD_ID` as an external ref in the note history.
You can add extra refs manually with `NOTES_RUNNER_EXTERNAL_REF` or `NOTES_RUNNER_EXTERNAL_REFS`.

More detail lives in [OBSERVABILITY.md](OBSERVABILITY.md) and [TROUBLESHOOTING.md](TROUBLESHOOTING.md).

## Advanced features

See [ADVANCED.md](ADVANCED.md) for:
- speaker diarization
- YouTube fallback transcription
- Telegram voice messages
- Telegram auto-delivery

By default, generated notes are auto-delivered to the Telegram channel `Конспекты` (`-1003850136767`) when a compatible `digest-runner` is available.
Use `config.json` only if you want to override that target or disable delivery for this machine.

## Safety note

Do not copy someone else's `config.json`. Use `config.example.json` as template.
Keep `config.json` local-only: it may contain Telegram delivery settings and should not be committed or shared.
