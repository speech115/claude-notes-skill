# Speaker Identification Agent Prompt

Launch a **sonnet-model** agent that reads `$WORK_DIR/prescan_context.txt` and writes `$WORK_DIR/speakers.txt`.

## Prompt

```
Read $WORK_DIR/prescan_context.txt.
This file contains:
- The FILE NAME of each transcript (critical hint — files are usually named after the main speaker/guest)
- The first 200 lines of each transcript file
- The LAST 100 lines of each transcript file (speakers often introduce/thank each other at the end)
- 50 lines from the MIDDLE of the transcript where names/speaker changes are most dense
- Grep results for speaker clues from the full file WITH ±2 lines of context around each match

## Identification Strategy

### Step 1: Use the FILE NAME as the primary hint
The file name almost always contains the main speaker/guest name.
- If file is named "X в гостях" or "X интервью" → X is the main speaker/guest
- The main speaker/guest is the person giving long, monologue-style answers
- The OTHER person (host/interviewer) is the one asking short questions

### Step 2: Analyze speech patterns
- Who ASKS questions? → Usually the host/interviewer (NOT the main speaker)
- Who gives LONG answers and monologues? → Usually the main speaker/guest named in the file
- Who is addressed by name in questions? → That name belongs to the person being addressed

### Step 3: Look for self-references and cross-references
- When someone says "меня зовут X", "я — X", "привет, я X" → they ARE X
- When someone says "X, расскажи..." or "мне говорили, что X, ты..." → the person being addressed IS X
- When someone says "у нас в гостях X" or "сегодня с нами X" → X is the guest speaker

### Step 4: Check the ending of the transcript
- Speakers often say goodbye with names: "спасибо, X" or "это был X"
- Hosts often sign off: "с вами был Y, а в гостях у нас был X"

### Step 5: Verify consistency
- If file is named "X в гостях", then X MUST be matched to the speaker with the most monologue-style content
- If your identification puts X as the question-asker, you likely have them swapped — re-check

## Output

Identify ALL speakers:
1. Speakers with **Speaker N** markers — match them to real names via self-introductions and context
2. UNMARKED speakers — lines of dialogue WITHOUT any **Speaker N** prefix. These are a different person. Identify them from introductions, names used in conversation, or context.

Write $WORK_DIR/speakers.txt with STRICT format (one mapping per line, no markdown, no headers, no NOTE lines):
Speaker 1 → RealName
Speaker 2 → RealName
Unmarked lines → RealName

Rules for speakers.txt:
- One mapping per line, nothing else
- No parentheses, no (evidence: ...), no (role: ...) — just the arrow and the name
- No markdown headers (##), no blank lines, no NOTE: lines
- If a speaker cannot be identified, keep "Speaker N" as the name
- "Unmarked lines" = lines without any **Speaker N** prefix — map them to the most likely speaker
```
