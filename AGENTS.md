# notes-skill repo notes

Коротко:

- Этот repo — source of truth.
- Live install — deployment target.
- Не правь `~/.codex/skills/notes` или `~/.agents/skills/notes` руками, если это не аварийная forensic-диагностика.

Главные команды:

- `bash scripts/release-check.sh`
- `python3 scripts/notes-runner doctor --json`
- `python3 scripts/notes-runner status "$WORK_DIR" --json`
- `bash scripts/dev-link-live.sh`
- `bash scripts/promote-live.sh`

Перед `promote-live`:

- Проверь `git status --short`.
- `--allow-dirty` используй только если осознанно разбираешь аварийное состояние.

Где смотреть при дебаге:

- `bundle/run.json`
- `bundle/trace.jsonl`
- `bundle/work/prepare_state.json`
- `bundle/work/stages/*.json`
- `bundle/work/quality-checks.json`

Безопасный локальный smoke без Telegram:

```bash
NOTES_RUNNER_DISABLE_TELEGRAM=1 python3 scripts/notes-runner assemble "$WORK_DIR" "$OUTPUT_MD" "$OUTPUT_HTML" "$TITLE" --skip-telegram --json
```

Если `release-check` в quick-режиме показывает `SKIP`, это уже не “нормально”, а баг harness-а: deterministic слой должен проходить без пропусков.
