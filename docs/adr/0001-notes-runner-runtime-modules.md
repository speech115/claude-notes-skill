# ADR-0001: Split notes-runner into `notes_runner_lib` runtime modules

**Status:** accepted  
**Date:** 2026-06-04

## Context

`scripts/notes-runner` had grown into a single file responsible for CLI parsing, YouTube ingest, transcription backends, prepare orchestration, assemble/finalize, Telegram delivery, batch flows, and doctor/status surfaces. That made regressions harder to isolate and increased merge conflict risk.

The repo already used a thin-runner pattern in places (`*_command_runtime.py`), but large blocks of behavior still lived inline in the runner.

## Decision

Keep `scripts/notes-runner` as the **compatibility entrypoint** (CLI surface, dependency wiring, re-exports for tests) and move cohesive behavior into `scripts/notes_runner_lib/`:

| Module | Responsibility |
|--------|----------------|
| `prepare_runtime.py` | Execution-mode routing (`single` vs adaptive), prepare state helpers |
| `prepare_pipeline_runtime.py` | Shared `run_prepare_and_attach()` for youtube/local/audio/telegram |
| `source_ingest_runtime.py` | YouTube metadata, subtitles, chapters, hints |
| `transcribe_backends_runtime.py` | Groq / Parakeet / MLX transcription backends |
| `assemble_command_runtime.py` | Assemble command orchestration |
| `telegram_assemble_runtime.py` | Telegram delivery resolution for assemble |
| `digest_runner_runtime.py` | Resolve `digest-runner` from env, config, `bin/`, or PATH |

Existing small `*_command_runtime.py` files (youtube, local, audio, telegram, workdir, doctor, batch, auto) stay separate; we did **not** merge them into one mega-module to avoid parser/handler regression churn.

## Consequences

**Positive**

- Regression tests target stable import paths (`notes_runner_lib.*`) instead of patching a 2k-line file.
- Prepare/assemble/ingest boundaries are explicit; future changes have a obvious home.
- `test_repo_contracts.py` guards the runtime module inventory.

**Negative / follow-ups**

- Runner file is still large (wiring + legacy helpers); further extraction (VTT helpers, bundle path utilities) is optional, not required for this ADR.
- Live skill installs must sync from this repo (`promote-live` or dev-link); hand-editing `~/.codex/skills/notes` bypasses the split.

## Verification

- `python3 -m unittest discover -s tests`
- `bash scripts/release-check.sh` (quick deterministic layer, no `SKIP`)
- Telegram delivery smoke: `assemble` with `telegram_delivery` enabled resolves `digest-runner` via `config.json` / `bin/digest-runner` without manual `NOTES_RUNNER_DIGEST_RUNNER` in the agent shell.

## Related

- ADR does not change the user-facing `/notes` contract in `SKILL.md`.
- Telegram MCP (`send_file`) and `digest-runner` remain external dependencies documented in `ADVANCED.md` and `docs/agents/issue-tracker.md` is unrelated to runtime layout.