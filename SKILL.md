---
name: notes
description: Create detailed study notes from YouTube videos or local transcripts. Use when the user says 'сделай конспект', 'конспект', 'законспектируй', 'notes', 'заметки по видео', or provides a YouTube URL and asks for a summary/notes. Also triggers on /notes.
argument-hint: <youtube-url-or-absolute-path>
metadata:
  short-description: Detailed notes from YouTube or local transcripts
---

# /notes — detailed study notes

Triggers automatically when the user asks to create notes/конспект, or explicitly runs `/notes ...`.

This skill is a Claude skill, not an app project.

Never ask about:

- preview servers
- `runtimeExecutable`
- `package.json`
- `manage.py`
- "setting up this repo"

Use the bundled helper:

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner
```

Do not assume a global `notes-runner` exists in `PATH`.

## Supported inputs

**Starter mode** (no extra setup):
- a YouTube URL with usable subtitles/autosubs
- a local absolute path to `.md` or `.txt`

**With audio transcription setup** (mlx-whisper or Groq API):
- audio files (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.opus`)
- a directory of audio/text files (batch mode)

**Advanced setup**:
- Telegram voice/audio
- YouTube videos without usable subtitles
- speaker diarization

If the user provides an audio file but transcription is not available, explain the setup and point to:

```text
${CLAUDE_SKILL_DIR}/ADVANCED.md
```

## First run

If the user looks confused or asks how to start, tell them to try:

```text
What skills are available?
/notes https://www.youtube.com/watch?v=...
/notes /absolute/path/to/file.md
/notes /path/to/audio.mp3
```

## Input routing

If no argument was provided:

1. Ask for exactly one input:
   - one YouTube URL, or
   - one absolute path to `.md` / `.txt`
2. Do not start processing until the user gives it.

If the argument is a YouTube URL:

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner youtube "$ARGUMENTS" --prepare --json
```

If the argument is an absolute path to `.md` or `.txt`:

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner local "$ARGUMENTS" --prepare --json
```

If the argument is an absolute path to an audio file (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.opus`):

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner audio "$ARGUMENTS" --prepare --json
```

Use `--title "Custom Title"` when the filename is not a good title.
Use `--language` to set the audio language (default: `ru`). Only add `--language en` for English content.

If the argument is a directory containing multiple files:

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner batch "$ARGUMENTS" --prepare --json
```

If the argument is not recognized, ask the user to provide one of:
- a YouTube URL
- an absolute path to `.md` / `.txt`
- an absolute path to an audio file
- a directory for batch processing

## Error handling

If notes-runner exits with non-zero or produces no JSON output, report the error to the user and STOP. Do not proceed to extraction with missing/empty data.

## After the helper runs

Read the JSON output and extract these variables:

| Variable | JSON path | Description |
|----------|-----------|-------------|
| `$BUNDLE_DIR` | `bundle_dir` | Output folder with final files |
| `$RAW_TITLE` | `title` | Original title from source (filename, video title) |
| `$TRANSCRIPT_PATH` | `transcript_path` | Path to transcript file |
| `$WORK_DIR` | `prepare.work_dir` | Temp working directory for intermediate agent files |
| `$SUGGESTED_MD` | `suggested_output_md` | Default markdown output path |
| `$SUGGESTED_HTML` | `suggested_output_html` | Default HTML output path |
| `$TOTAL_CHUNKS` | `prepare.total_chunks` | Number of chunks (determines single vs multi-agent) |
| `$SPEAKER_STAGE` | `prepare.stage_hints.speaker_identification` | `"skip"` or `"identify"` — whether to run speaker ID |
| `$WARNINGS` | `warnings` | Array of warning strings (may be empty) |

**Key distinction:** `$BUNDLE_DIR` is the permanent output folder. `$WORK_DIR` is a temp directory inside it where agents write intermediate files (blocks, manifests, summaries).

**IMPORTANT: Do NOT read the transcript into main context.** The extraction agents read it themselves. Reading it here wastes ~2K+ tokens. Only read `prescan_context.txt` in main context.

## Processing flow

Speed-optimized: overlap I/O with reads, pre-bake agent prompts, parallelize aggressively.

### Pre-read: templates + Telegram tool in parallel with prepare

While the `notes-runner ... --prepare` command is running, in the SAME `<function_calls>` block:

1. Read ALL templates:
   ```
   - ${CLAUDE_SKILL_DIR}/block-templates/extraction-agent.md
   - ${CLAUDE_SKILL_DIR}/block-templates/tldr-agent.md
   - ${CLAUDE_SKILL_DIR}/block-templates/header.md
   - ${CLAUDE_SKILL_DIR}/block-templates/speaker-identification.md
   ```
2. Pre-load Telegram tool schema: `ToolSearch("select:mcp__telegram__send_file")`

This saves two full round-trips later in the pipeline.

### After prepare: check for chapters

If `$BUNDLE_DIR/chapters.json` exists, read it. Include chapter markers in extraction agent prompts as `CHAPTER HINTS` — agents use them as preferred block boundaries (better quality + faster processing).

### Routing: single-agent vs multi-agent

**If `$TOTAL_CHUNKS == 1` (quick mode):** use **single-agent mode** — skip multi-agent orchestration overhead.

Launch ONE sonnet agent with the FULL extraction-agent template pre-baked into its prompt (copy the template content from what you read earlier — the agent MUST follow the exact file format with YAML frontmatter, `chunk_A_block_NN.md` naming, manifest TSV columns). The agent:
- Reads the transcript
- Writes block files, manifest, summary (MUST match extraction-agent.md format exactly)
- ALSO writes `$WORK_DIR/tldr.md` inline (5 takeaways from its own extraction)
- This eliminates Wave 2 TL;DR agent entirely — saves ~20s round-trip

Then skip to "Post-processing" but WITHOUT the TL;DR agent (already done).

**If `$TOTAL_CHUNKS >= 2`:** use **multi-agent mode** (standard flow below).

### Wave 1: Speaker identification + Extraction (PARALLEL) — multi-agent mode only

Launch ALL of the following agents in a **single message** (one `<function_calls>` block):

**Agent A — Speaker identification** (ONLY if `$SPEAKER_STAGE != "skip"`):
- Model: sonnet
- Use the speaker-identification template you already read above
- Agent reads `$WORK_DIR/prescan_context.txt` and writes `$WORK_DIR/speakers.txt`

**Agents B1..BN — Extraction** (one per chunk from the `prepare.chunk_plan` array):
- **Pre-bake the full extraction prompt**: embed the template content directly into each agent's prompt (do NOT tell agents to read the template file — saves a round-trip per agent)
- Fill in chunk boundaries from `prepare.chunk_plan`
- **Include chapter hints** in the prompt if `chapters.json` was found (format: `CHAPTER HINTS:\n- MM:SS Title\n- MM:SS Title`)
- Extraction agents use "Speaker N" labels as-is (NOT real names)
- Each writes: `chunk_[id]_block_*.md`, `manifest_chunk_[id].tsv`, `summary_chunk_[id].md`
- Skip chunks where `status == "ready"`

Wait for ALL agents to complete.

**Validation:** After Wave 1, verify that each chunk produced at least one `chunk_[id]_block_*.md` and a `manifest_chunk_[id].tsv`. If any chunk is missing output, report the failure and stop.

### Wave 2: Post-processing (PARALLEL)

Launch ALL of the following in a **single message**:

**Bash — Name substitution:**

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner replace-speakers "$WORK_DIR"
```

**Agent — TL;DR** (sonnet — NOT haiku) — SKIP if single-agent mode already wrote tldr.md:
- Embed the TL;DR template directly in the agent prompt (pre-baked, no file read needed)
- Agent reads `summary_chunk_*.md` files and writes `$WORK_DIR/tldr.md`
- Appendix is NOT generated by LLM — assemble creates it deterministically from manifests

**Main context — Content-based title + header:**

1. Read `speakers.txt` (if exists) + `prescan_context.txt` (NOT the transcript file)
2. Generate title (`$FINAL_TITLE`): `[Speaker] — [Core Topic]`
   - Examples: `Роман — Тело, энергия и продуктивность`
   - No clear speaker name: `[Topic] (групповая сессия)`
   - Single unnamed speaker (e.g. YouTube blogger): `[N] кейсов/идей/уроков [Topic]` or `[Core Topic]` — use the video's content to craft a descriptive title, not the speaker's unknown name
3. Set output paths using `$FINAL_TITLE`:
   - `$OUTPUT_MD` → `$BUNDLE_DIR/$FINAL_TITLE.md`
   - `$OUTPUT_HTML` → `$BUNDLE_DIR/$FINAL_TITLE.html`
4. Write `$WORK_DIR/header.md` using the header template you already read

Wait for TL;DR agent + replace-speakers to complete.

**Post-wave 2:** Always run replace-speakers once more (idempotent, ensures tldr.md is also cleaned):

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner replace-speakers "$WORK_DIR"
```

### Assemble

Run:

```bash
${CLAUDE_SKILL_DIR}/scripts/notes-runner assemble \
  "$WORK_DIR" \
  "$OUTPUT_MD" \
  "$OUTPUT_HTML" \
  "$FINAL_TITLE" \
  --json
```

The assemble step automatically generates `appendix.md` from manifest data (deterministic, no LLM needed).

If assemble exits non-zero, report the error to the user and stop.

## Telegram delivery

The assemble step attempts Telegram delivery automatically via its built-in config. If it succeeds (check `telegram_delivery.success` in the JSON output), you're done.

If `telegram_delivery.success == false`, try sending manually via MCP as a fallback:

- Tool: `mcp__telegram__send_file`
- Chat: `Конспекты`
- File: the generated HTML (`$OUTPUT_HTML`)
- Caption format:
  ```
  📝 Конспект видео:
  [Title]
  [source URL if available]
  ```

If the MCP send also fails, report it as a warning — the notes files are already written and the task is not failed. Do NOT retry more than once.

## Output to the user

At the end, report only the practical result:

- markdown path
- HTML path
- whether Telegram delivery succeeded
- whether there were warnings

Be concise.

Do not paste the generated notes into chat when files were already written successfully.
