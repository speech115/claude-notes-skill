# Troubleshooting

## `batch` свалился на одном файле

Проверь:

- `batch-index.json`
- `trace.jsonl`

Обычно причина лежит прямо в `results[].error`.

## Локальная транскрипция не стартует на macOS

Проверь:

- `python3 scripts/notes-runner doctor --json`
- есть ли `macwhisper_parakeet` или `GROQ_API_KEY`

Если используешь autodetect языка, runner больше не должен пихать `auto` в локальный transcriber. Если это снова всплывёт, смотри `trace.jsonl` и командный stderr.

## `assemble` упал и непонятно почему

Проверь:

- `work/stages/assemble.json`
- `timeline.jsonl`
- `trace.jsonl`
- `work/quality-checks.json`

При падении shell-скрипта теперь всё равно пишутся sentinel и trace. Так и должно быть.

## Хочу понять, что менялось между прогонами одного конспекта

Проверь:

- `run.json`
- `timeline.jsonl`
- `runs/<run_id>.json`

`run.json` покажет latest summary. `timeline.jsonl` покажет историю запусков. `runs/<run_id>.json` покажет полный snapshot конкретной ревизии, включая `external_refs`, hashes и `change_flags`.

## Telegram не нужен в локальной проверке

Используй:

```bash
NOTES_RUNNER_DISABLE_TELEGRAM=1 python3 scripts/notes-runner assemble "$WORK_DIR" "$OUTPUT_MD" "$OUTPUT_HTML" "$TITLE" --skip-telegram --json
```

Это debug-only ветка. Для нормального пользовательского `/notes` финал считается закрытым только после успешной Telegram-доставки.

## `telegram_delivery.success == false` с `Unknown tool: send_file`

Сборка конспекта прошла, но `assemble` вернул ошибку доставки. Обычно это не баг `notes-runner`, а профиль локального Telegram MCP.

Проверь:

- `mcporter list telegram` содержит `send_file`
- `config.json` указывает на рабочий `mcp_url` (часто `http://127.0.0.1:8799/mcp`)
- `NOTES_RUNNER_DIGEST_RUNNER` резолвится в рабочий `digest-runner`

Если `send_file` нет в списке tools, перезапусти HTTP daemon `telegram-mcp` после обновления (facade-профиль должен экспортировать `send_file` для `digest-runner send-file`). После рестарта повтори `assemble` без `--skip-telegram`.

Локальные черновики и benchmark-отчёты в `drafts/` и `outputs/` git не отслеживает — это нормально и не мешает `promote-live`.

## `promote-live` отказался работать

Чаще всего это не баг, а dirty tree.

Проверь:

- `git status --short`
- правильный ли target выбрался

Скрипты теперь по умолчанию резолвят live dir так же, как `install.sh`: сначала `~/.codex/skills/notes`, потом существующие legacy install paths.

## Skill не виден в Codex App

Сначала проверь live install, а не repo:

- `~/.codex/skills/notes/SKILL.md`
- `~/.codex/skills/notes/agents/openai.yaml`

Оба файла должны существовать как обычные файлы, не как symlink. Для `notes` это важно для discoverability внутри Codex App.

Нормальный способ починки:

```bash
bash scripts/dev-link-live.sh
```

После этого можно быстро проверить индексатор без ручного тыканья в UI:

```bash
/Applications/Codex.app/Contents/Resources/codex debug prompt-input '' | rg '\- notes:'
```

## `release-check` зелёный, но доверия нет

Сначала проверь, нет ли там `SKIP`. В quick-режиме их больше быть не должно.

Если `scripts/release-check.sh` зелёный, значит deterministic слой реально прошёл целиком.

Если нужен более жёсткий прогон с внешними сценариями:

```bash
bash scripts/test-pipeline.sh --full
```

Там `SKIP` ещё возможен, потому что full-слой может зависеть от локальных длинных bundle’ов и внешних сервисов.
