# TL;DR Agent Prompt

Launch **ONE** sonnet-model agent that reads ONLY the summary files (not all blocks — saves context).

## Prompt

```
Read all summary_chunk_*.md files in $WORK_DIR (sorted).

Write ONE file: $WORK_DIR/tldr.md
Numbered key takeaways. Just the list, no heading. One sentence each.
Based on the summaries you read.

Determine the number of takeaways based on content volume:
- If there is 1 summary file (short recording): 5 takeaways
- If there are 2 summary files: 7-10 takeaways
- If there are 3-4 summary files: 10-12 takeaways
- If there are 5+ summary files: 12-15 takeaways

Output in Russian. Only use information from the files — do NOT invent.
Do NOT add version numbers, model names, or facts from your own knowledge — only what appears in the source files. If a file says "Claude" without a version, write "Claude", not "Claude Opus 4.5".

NOTE: Speaker labels may appear as "Speaker N" — this is expected. Use them as-is.
Real names will be substituted by a post-processing script.
```
