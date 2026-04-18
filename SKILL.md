---
name: notes
description: Create detailed study notes from YouTube videos, local media, or local transcripts. Use when the user says 'сделай конспект', 'конспект', 'законспектируй', 'notes', 'заметки по видео', or provides a YouTube URL and asks for a summary/notes. Also triggers on /notes.
argument-hint: <youtube-url-or-absolute-path>
metadata:
  short-description: Detailed notes from YouTube, local media, or transcripts
---

# /notes — detailed study notes

Triggers automatically when the user asks to create notes/конспект, or explicitly runs `/notes ...`.

This is a local agent skill, not an app project.

Treat `notes-runner` as the source of truth for:
- input routing
- stage routing
- note contract
- final quality / contract validation

Use the bundled helper:

```bash
<skill-root>/scripts/notes-runner
```

Do not assume a global `notes-runner` exists in `PATH`.

## Supported inputs

**Starter mode** (no extra setup):
- a YouTube URL with usable subtitles/autosubs
- a local absolute path to `.md` or `.txt`

**With audio transcription setup** (mlx-whisper or Groq API):
- audio/video files (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`)
- a directory of audio/text files (batch mode)

**Advanced setup**:
- Telegram voice/audio
- YouTube videos without usable subtitles
- speaker diarization

If the user provides an audio/video file but transcription is not available, explain the setup and point to:

```text
<skill-root>/ADVANCED.md
```

## First run

If the user looks confused or asks how to start, tell them to try:

```text
What skills are available?
/notes https://www.youtube.com/watch?v=...
/notes /absolute/path/to/file.md
/notes /path/to/audio.mp3
/notes /path/to/video.mp4
```

## Input routing

If no argument was provided:

1. Ask for exactly one input:
   - one YouTube URL, or
   - one absolute path to `.md` / `.txt`
2. Do not start processing until the user gives it.

If the argument is a YouTube URL:

```bash
<skill-root>/scripts/notes-runner youtube "$ARGUMENTS" --prepare --json
```

If the argument is an absolute path to `.md` or `.txt`:

```bash
<skill-root>/scripts/notes-runner local "$ARGUMENTS" --prepare --json
```

If the argument is an absolute path to an audio or video file (`.m4a`, `.mp3`, `.wav`, `.ogg`, `.opus`, `.mp4`, `.mov`, `.mkv`, `.webm`, `.avi`):

```bash
<skill-root>/scripts/notes-runner audio "$ARGUMENTS" --prepare --json
```

Use `--title "Custom Title"` when the filename is not a good title.
Use `--language` to set the transcription language (default: `ru`). Only add `--language en` for English content.

If the argument is a directory containing multiple files:

```bash
<skill-root>/scripts/notes-runner batch "$ARGUMENTS" --prepare --json
```

If the argument is not recognized, ask the user to provide one of:
- a YouTube URL
- an absolute path to `.md` / `.txt`
- an absolute path to an audio/video file
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
| `$STATUS` | `status` | Current work-dir stage/chunk status from notes-runner |
| `$EXECUTION_PLAN` | `execution_plan` | Runner-provided orchestration plan for resume/single/micro-multi/multi-stage execution |
| `$PREPARE_REUSED` | `prepare.reused` | `true` when notes-runner reused an existing work dir |
| `$WARNINGS` | `warnings` | Array of warning strings (may be empty) |

**Key distinction:** `$BUNDLE_DIR` is the permanent output folder. `$WORK_DIR` is a temp directory inside it where agents write intermediate files (blocks, manifests, summaries).

**IMPORTANT: Do NOT read the transcript into main context.** The extraction agents read it themselves. Reading it here wastes ~2K+ tokens. Only read `prescan_context.txt` in main context.

## Processing flow

Goal: keep `/notes` deterministic. Prefer the runner state over ad-hoc decisions.

### Core rules

- Do not rerun `youtube/local/audio ... --prepare` after it already succeeded unless the user explicitly asked for refresh.
- Do not read the full transcript into main context.
- If the helper succeeded and `transcript_path` exists, `warnings` are informational. Continue unless the helper itself exited non-zero.
- Prefer `$EXECUTION_PLAN`, `$STATUS`, `note-contract.json`, and `quality-checks.json` over any hand-written heuristics in the skill.
- If `$PREPARE_REUSED == true`, assume this is a resume/continue path and skip any stage already marked ready in `$STATUS`.
- Valid YouTube transcript sources are: `existing`, `youtube-transcript-api`, `subtitles`, `api`. `api` means the slower audio fallback ran; it is not an error by itself.
- Do not use `ToolSearch` or `mcp__telegram__send_file` here. Telegram is best-effort inside `assemble` only.
- Prefer richer coverage over aggressive compression for long-form material. A 90-180 minute source should usually produce many local blocks, not a handful of mega-blocks.
- Treat runner-provided density requirements as hard constraints. If the extraction prompt says the chunk must yield at least `N` blocks, do not collapse it further.
- If assemble reports that the note is too compressed for source duration, treat that as a real contract failure and expand the coverage instead of polishing wording.
- For `120+` minute sources, default to a deep-longform reading mode: preserve intermediate conclusions, participant situations, and concrete examples instead of flattening them into generic theses.

### Read only required files

After prepare:

1. Prefer runner-generated prompt packs from `$EXECUTION_PLAN.prompt_packs`.
2. Read `$WORK_DIR/prescan_context.txt`.
3. Read `$WORK_DIR/header-seed.json` and `$WORK_DIR/note-contract.json` before writing `header.md`.
4. Read block templates from `<skill-root>/block-templates/` only if the prompt pack files are missing.

### Extraction routing

Use `$EXECUTION_PLAN.mode` and `*.should_run` flags as the source of truth for routing. Do not invent extra stages.

**If `$EXECUTION_PLAN.mode == "single"` and `$EXECUTION_PLAN.extraction.should_run == true`:** use **single-agent mode**.

Launch one worker agent using the runner-generated extraction prompt from `$EXECUTION_PLAN.prompt_packs.extract.A` (or the only chunk entry in `chunks_to_extract`). The agent must:
- read the transcript file itself
- write `chunk_A_block_*.md`, `manifest_chunk_A.tsv`, `summary_chunk_A.md`
- also write `$WORK_DIR/tldr.md`
- write the extraction sentinel JSON requested by the prompt pack

Then skip the TL;DR wave and continue to title/header + assemble.

If `$EXECUTION_PLAN.extraction.should_run == false`, do not relaunch extraction. Reuse the existing block files and continue from the first missing stage.

**If `$EXECUTION_PLAN.mode == "micro-multi"` or `$EXECUTION_PLAN.mode == "multi"`:** use **parallel chunk mode**.

1. If `$EXECUTION_PLAN.speaker_identification.should_run == true`, launch one speaker-ID agent using `$EXECUTION_PLAN.prompt_packs.speaker_identification`.
2. Launch one extraction agent per chunk from `$EXECUTION_PLAN.extraction.chunks_to_extract`.
   - Use the runner-generated prompt file from `$EXECUTION_PLAN.prompt_packs.extract[chunk_id]`.
   - Keep `Speaker N` labels until `replace-speakers`.
   - Each chunk must write `chunk_[id]_block_*.md`, `manifest_chunk_[id].tsv`, `summary_chunk_[id].md`.
   - Each chunk must also write the extraction sentinel JSON described in its prompt pack.
   - Do not relaunch chunks outside `chunks_to_extract`.
3. Wait for all extraction work to finish.
4. Validate every chunk: at least one `chunk_[id]_block_*.md` and one `manifest_chunk_[id].tsv` must exist. If any chunk is missing output, stop and report the failure.
5. Run:

```bash
<skill-root>/scripts/notes-runner replace-speakers "$WORK_DIR"
```

6. If `$EXECUTION_PLAN.tldr.should_run == true` and `$EXECUTION_PLAN.tldr.strategy == "deterministic-merge"`, run:

```bash
<skill-root>/scripts/notes-runner build-tldr "$WORK_DIR" --json
```

7. If `$EXECUTION_PLAN.tldr.should_run == true` and `$EXECUTION_PLAN.tldr.strategy == "agent"`, launch one TL;DR agent using `$EXECUTION_PLAN.prompt_packs.tldr_agent`.
8. If `$EXECUTION_PLAN.replace_speakers.after_tldr == true`, run `replace-speakers` once more after TL;DR completes so `tldr.md` is also cleaned.

### Title + header

1. Read `speakers.txt` if it exists, plus `prescan_context.txt`, plus `$EXECUTION_PLAN.title_header.header_seed_path`.
2. Respect `$EXECUTION_PLAN.content_mode` and `$EXECUTION_PLAN.contract`; do not improvise a different note schema.
3. Generate title (`$FINAL_TITLE`) as `[Speaker] — [Core Topic]`.
   - Example: `Роман — Тело, энергия и продуктивность`
   - If `$EXECUTION_PLAN.title_header.author_hint` or `speaker_candidates` names a likely YouTube author/uploader and the material is single-speaker, use that real name as `[Speaker]`.
   - No clear speaker name: `[Topic] (групповая сессия)`
   - Single unnamed YouTube speaker with no usable author hint: use a descriptive topic title, not `Speaker 1`
   - Prefer `$EXECUTION_PLAN.title_header.title_candidates` before inventing a fresh title from scratch.
4. Set:
   - `$OUTPUT_MD` → `$BUNDLE_DIR/$FINAL_TITLE.md`
   - `$OUTPUT_HTML` → `$BUNDLE_DIR/$FINAL_TITLE.html`
5. Write `$WORK_DIR/header.md` using the runner-generated header prompt or the header template as fallback.
   - Preserve deterministic metadata lines from `header-seed.json` / `note-contract.json`.
   - Generate only the abstract and `Главная рамка автора`.

### Assemble

Run exactly once when `$EXECUTION_PLAN.assemble.should_run == true`:

```bash
<skill-root>/scripts/notes-runner assemble \
  "$WORK_DIR" \
  "$OUTPUT_MD" \
  "$OUTPUT_HTML" \
  "$FINAL_TITLE" \
  --json
```

The assemble step generates the appendix deterministically from manifests.

If assemble exits non-zero, report the error and stop.
If assemble returns `contract_errors`, surface them to the user as the reason the note was not accepted.

If `telegram_delivery.success == false`, treat it as a warning only. The notes files are already the primary result. Do not attempt manual Telegram fallback from the agent.

## Output to the user

At the end, report only the practical result:

- markdown path
- HTML path
- whether Telegram delivery succeeded
- whether there were warnings

Be concise.

Do not paste the generated notes into chat when files were already written successfully.
