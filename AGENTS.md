# notes-skill repo notes

Коротко:

- Этот repo — source of truth.
- Live install — deployment target.
- Не правь `~/.codex/skills/notes` или `~/.agents/skills/notes` руками, если это не аварийная forensic-диагностика.

Сначала читать:

- `CONTEXT.md`
- `REFERENCES.md`
- `README.md`
- `SKILL.md`

Главные команды:

- `bin/status`
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

- Только для дебага harness-а и локальной forensic-проверки.
- Не используй это как финальный шаг для пользовательского `/notes`: штатный результат считается завершённым только после Telegram-доставки.

```bash
NOTES_RUNNER_DISABLE_TELEGRAM=1 python3 scripts/notes-runner assemble "$WORK_DIR" "$OUTPUT_MD" "$OUTPUT_HTML" "$TITLE" --skip-telegram --json
```

Если `release-check` в quick-режиме показывает `SKIP`, это уже не “нормально”, а баг harness-а: deterministic слой должен проходить без пропусков.

Рабочие зоны:

- `scripts/notes_runner_lib/` — runtime-код runner-а.
- `tests/` — regression и contract coverage.
- `drafts/` — черновики решений и временные планы.
- `outputs/` — существенные отчёты, audit notes и синтезы.
- `final/` — готовые пользовательские/релизные артефакты, если они не являются кодом.
- `references/` — внешние или локальные reference-материалы, не входящие в runtime.

Done значит:

- изменение сделано в repo, а не в live install;
- `bin/status` проходит;
- для runtime-изменений запущен `bash scripts/release-check.sh` или явно названо, почему он не запускался;
- если изменение влияет на пользовательский `/notes`, финальный smoke не считается штатным без Telegram-доставки.

## Agent skills

### Issue tracker

Issues live in GitHub (`speech115/notes-skill`). See `docs/agents/issue-tracker.md`.

### Triage labels

Canonical triage roles use default label names (`needs-triage`, `ready-for-agent`, …). See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: `CONTEXT.md` at repo root and `docs/adr/` for ADRs. See `docs/agents/domain.md`.
