You are reviewing a local agent skill called `/notes`.

This skill creates detailed Russian notes from YouTube videos, transcripts, and audio. The packet you received contains:

- the skill instructions
- the runner / assembly scripts
- prompt templates
- tests
- one preferred older example note
- one newer weaker note
- one real runtime JSON file

Review this as:

- a prompt engineer
- a systems designer
- a product-minded editor for educational notes
- a reliability engineer

Your job is not to praise the system. Your job is to find the best ways to improve it.

Important constraints:

- It must remain a local agent skill with a runner-based workflow.
- The main hot path is `/notes <youtube-url>`.
- Quality, detail, and consistency matter a lot.
- Speed and stability matter too.
- User-facing notes must never expose internal pipeline details.
- YouTube author / channel metadata should be used intelligently.

Please study the files and then answer with this structure:

## 1. Main diagnosis
What is the core problem with the current system?

## 2. Top 5 improvements by impact
Rank them from highest to lowest impact.

## 3. What should be simplified or deleted
Be specific about which layers, prompts, or sections are unnecessary.

## 4. What should become deterministic
List the parts that should move out of the model and into code.

## 5. Output schema critique
Does the current target note format make sense?
If not, propose a better one.

## 6. Prompt-layer critique
How would you redesign:
- extraction prompts
- header prompts
- TL;DR prompts
- action-plan generation

## 7. Architecture critique
How would you rebalance responsibilities between:
- `SKILL.md`
- `notes-runner`
- `assemble.sh`
- prompt templates
- deterministic tests

## 8. Missing tests / metrics
What do you think is still unmeasured or weakly tested?

## 9. First patch set
Give a concrete, staged patch plan with file-level recommendations.

Be direct. Prefer specific recommendations over general advice.
