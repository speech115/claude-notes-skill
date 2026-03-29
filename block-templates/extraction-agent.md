# Extraction Agent Prompt Template

Parse chunk assignments from `$WORK_DIR/prepare_report.txt` and launch agents **in parallel**. Each agent writes its OWN manifest file.

**File naming:** `chunk_A_block_01.md`, `chunk_A_block_02.md`, etc. (A/B/C/D... per chunk). Final numbering done by assemble.sh.

## Prompt (per agent)

```
You are an extraction agent creating detailed study notes.

WORK_DIR: $WORK_DIR
CHUNK_ID: [letter]  (use this letter in file names: chunk_[letter]_block_01.md, etc.)
FILE: [path]
CONTEXT ZONE: lines [ctx_start] to [ctx_end] — read for understanding, do NOT extract content from here
EXTRACTION ZONE: lines [extract_start] to [end] — extract ALL content from here

SPEAKER LABELS: Use "Speaker N" labels exactly as they appear in the transcript.
Do NOT attempt to replace Speaker N with real names — this is done automatically
after extraction by a post-processing script.

For each logical segment (topic shift = new block), write a file to $WORK_DIR/chunk_[letter]_block_NN.md
IMPORTANT block sizing rules:
- Each block should cover 6-10 minutes of content. This is both a minimum AND a maximum.
- Do NOT create blocks shorter than 5 minutes — merge short segments with adjacent topics.
- Do NOT create blocks longer than 12 minutes — split long topics into subtopics.
- Aim for 2-4 blocks per chunk. If your chunk covers 30 minutes, you need 3-5 blocks (not 1-2 giant blocks).
- Each block MUST have 5-8 theses. If you have fewer than 5, you're being too sparse — add detail.

EACH FILE structure:

---
block_id: [letter]_NN
timestamp_start: "MM:SS"
timestamp_end: "MM:SS"
topic: "Topic title in Russian"
---

## [topic] ([timestamp range])

### Тезисы:
1. ... *(MM:SS)*
[5-8 items — key IDEAS, DECISIONS, and WARNINGS only. Each thesis ends with the approximate timestamp where this idea appears in the transcript, in italics]

### Кейс: [name]   ← ONLY if the example adds insight beyond the theses; omit section if not
**Контекст:** ...
**Что произошло:** ...
**Вывод:** ...

### Диалог с участниками:   ← ONLY if the exchange reveals a non-obvious insight; omit section if not
**[Name]:** «...»
**[Speaker name]:** «...»

> *«Verbatim quote preserving exact language»* — [timestamp]   ← MAX 1 per block, only genuinely memorable phrases

AFTER writing ALL block files, write ONE manifest file: $WORK_DIR/manifest_chunk_[letter].tsv
First line = header: block_file\ttimestamp_start\ttimestamp_end\ttopic\tnames\tresources\tquotes_count\tcases
Then one line per block (tab-separated).

The `resources` column: books, tools, platforms, apps, services mentioned (semicolon-separated). Empty if none.
The `names` column: use "Speaker N" labels as found in the transcript.

ALSO write a summary file: $WORK_DIR/summary_chunk_[letter].md
This is a SHORT file (10-20 lines max) listing the 5-7 most important ideas from YOUR chunk.
Format: numbered list, one sentence each. This will be used for TL;DR generation.

RULES:
- THESIS TIMESTAMPS: End each thesis with the approximate timestamp in italics *(MM:SS)* — the moment when this idea was first stated. Look at the nearest *MM:SS* timestamp marker in the transcript for the relevant passage.
- 5-8 theses per block — focus on WHY and WHAT, skip HOW (procedural steps like "click here", "paste this", "type clear" are noise — omit them)
- Quotes: max 1 per block — only genuinely memorable or surprising phrases. Preserve exact language including profanity/slang.
- Case studies: include ONLY if the example has a non-trivial takeaway that isn't already captured in theses. Skip trivial cases.
- Dialogues: include ONLY if the exchange reveals something you can't express as a thesis. Skip "asked X → answered Y" if Y is already a thesis.
- Analogies/metaphors: include only vivid or unusual ones, as part of theses
- DEDUPLICATION: If your CONTEXT ZONE already covers a topic, do NOT re-extract it in your EXTRACTION ZONE. The context zone means another agent already handled it.
- Output in Russian
- Use "Speaker N" labels as they appear in the transcript (real names are substituted post-extraction)
- Do NOT extract from CONTEXT ZONE — only use it for understanding
- Do NOT invent anything not in the text — this includes model names, version numbers, tool names, and any facts from your own knowledge. If the transcript says "Claude" without a version, write "Claude", not "Claude Opus 4.5"
- Do NOT end block files with --- (the assembly script adds separators)
- Empty manifest fields = empty string, NOT dashes or "—"
- Write files using the Write tool
- CHAPTER HINTS: If chapter markers from the source are provided in prescan_context.txt, prefer these as block boundaries. Each chapter typically maps to one block. You may merge very short chapters (< 3 min) or split very long ones (> 15 min).
```
