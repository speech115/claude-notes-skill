# Notes Skill Review Packet

This packet is meant to be uploaded into ChatGPT Pro for an external review.

## What This System Is

`/notes` is a local agent skill that generates detailed Russian study notes from:

- YouTube videos
- local `.md` / `.txt` transcripts
- audio files when transcription is available

The system is not a web app. It is a local skill + runner pipeline.

## Main Goal

Improve the system so that notes are:

- more detailed and complete
- more consistent in structure and naming
- faster on repeat runs and YouTube-heavy workflows
- more stable and deterministic
- more useful as a reader-facing artifact, not just a transcript log

## Current Architecture

High-level flow:

1. `SKILL.md` routes Claude into a runner-first workflow.
2. `scripts/notes-runner` handles:
   - input routing
   - YouTube/local/audio prepare
   - chunking
   - source metadata / author hints
   - execution plan generation
   - prompt pack generation
   - deterministic TL;DR merge in some modes
   - status / resume logic
3. Claude agents perform:
   - chunk extraction
   - optional speaker identification
   - optional TL;DR generation
   - header generation
4. `replace-speakers.sh` cleans `Speaker N` labels after extraction.
5. `assemble.sh` builds final Markdown + HTML and can synthesize appendix content deterministically if `appendix.md` is missing.

## Important Constraints

- This must remain a local agent skill with a local runner.
- It should work well for `/notes <youtube-url>` with minimal user friction.
- It should avoid loading the full transcript into main model context when possible.
- YouTube author/channel metadata should be used intelligently for single-speaker notes.
- Internal pipeline details must not leak into user-facing notes.
- The final artifact should feel like a high-quality editorial note set, not a raw transcript dump.

## What Was Recently Improved

Recent improvements already landed:

- YouTube author/channel hints now propagate into title/header logic.
- Reuse/resume behavior was improved so repeat runs do less work.
- `micro-multi` mode was introduced to reduce unnecessary TL;DR agent work for smaller multi-chunk jobs.
- The deterministic appendix generator was fixed to understand the current manifest schema.
- Internal footer leakage like `manifest_chunk_*.tsv` / `chunk_*_block_*.md` was removed from user-facing notes.
- Extraction prompts were upgraded to ask for:
  - denser theses
  - optional case sections
  - optional dialogue sections
  - quotes
  - `Практический смысл`
- Header prompts were upgraded to ask for:
  - `Автор`
  - `Формат`
  - `Тема`
  - `Длительность`
  - `Источник`
  - `Главная рамка автора`
- Appendix format was shifted away from internal analytics and toward:
  - `Упомянутые люди и ресурсы`
  - `План действий`
  - `Ключевые идеи и модели`

Current local deterministic suite status:

- `23 PASS / 0 FAIL`

## Current Output Direction

The target note format is now roughly:

- strong content-based title
- short editorial summary
- metadata lines (`Автор`, `Формат`, `Тема`, `Длительность`, `Источник`)
- `Главная рамка автора`
- `Коротко о главном`
- multiple content blocks with:
  - `Тезисы`
  - optional `Кейс`
  - optional `Диалог с участниками`
  - optional quote
  - `Практический смысл`
- `План действий`
- `Ключевые идеи и модели`
- `Упомянутые люди и ресурсы`

## Known Tensions / Open Questions

These are the questions we want you to think hard about:

1. Is the current division of labor between `SKILL.md`, `notes-runner`, shell scripts, and agent prompts optimal, or still too complex?
2. What should be moved out of prompts and made deterministic?
3. Is the current note schema the right one for usefulness and reading experience?
4. How would you improve the `План действий` generation so it is concrete, reader-facing, and not just rephrased theses?
5. How would you decide when to include or omit:
   - `Кейс`
   - `Диалог с участниками`
   - quotes
   - `Практический смысл`
6. Would you simplify the appendix further?
7. How would you improve speed without losing depth?
8. What would you redesign if you were allowed to clean up this system aggressively but still keep it as a local agent skill?

## Review Priorities

Please prioritize:

1. Output quality and completeness
2. Structural clarity for the reader
3. Stability and determinism
4. Simplicity of orchestration
5. Speed / latency improvements
6. Testability and observability

## Files Included In This Packet

Core system:

- `SKILL.md`
- `scripts/notes-runner`
- `assemble.sh`
- `prepare.sh`
- `scripts/replace-speakers.sh`
- `scripts/test-pipeline.sh`

Prompt / template layer:

- `block-templates/extraction-agent.md`
- `block-templates/header.md`
- `block-templates/tldr-agent.md`
- `block-templates/speaker-identification.md`

Examples:

- `examples/reference-good-note.html`
- `examples/current-note.md`
- `examples/current-run.json`

## How To Use The Example Files

- `reference-good-note.html` is an older reference note whose content style is preferred by the user.
- `current-note.md` is a newer note that exposed recent weaknesses:
  - weaker content density
  - poorer action plan quality
  - earlier appendix leakage / technical tail problems
- `current-run.json` gives real runtime context and telemetry for that note.

## What We Want Back From You

Please respond with:

1. Top 5 architectural improvements ranked by impact.
2. Top 5 output-format or prompt-layer improvements ranked by impact.
3. What you would delete or simplify.
4. What you would make deterministic instead of model-driven.
5. What tests or metrics are still missing.
6. A concrete “first patch set” plan with file-level recommendations.
7. If you think the current target schema is still wrong, propose a better one.
