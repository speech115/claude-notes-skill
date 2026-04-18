# Troubleshooting

## `batch` свалился на одном файле

Проверь:

- `batch-index.json`
- `trace.jsonl`

Обычно причина лежит прямо в `results[].error`.

## Локальная транскрипция не стартует на macOS

Проверь:

- `python3 scripts/notes-runner doctor --json`
- есть ли `mlx_whisper`, `parakeet_mlx` или `GROQ_API_KEY`

Если используешь autodetect языка, runner больше не должен пихать `auto` в локальный MLX CLI. Если это снова всплывёт, смотри `trace.jsonl` и командный stderr.

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

## `promote-live` отказался работать

Чаще всего это не баг, а dirty tree.

Проверь:

- `git status --short`
- правильный ли target выбрался

Скрипты теперь по умолчанию резолвят live dir так же, как `install.sh`: сначала `~/.codex/skills/notes`, потом существующие legacy install paths.

## `release-check` зелёный, но доверия нет

Сначала проверь, нет ли там `SKIP`. В quick-режиме их больше быть не должно.

Если `scripts/release-check.sh` зелёный, значит deterministic слой реально прошёл целиком.

Если нужен более жёсткий прогон с внешними сценариями:

```bash
bash scripts/test-pipeline.sh --full
```

Там `SKIP` ещё возможен, потому что full-слой может зависеть от локальных длинных bundle’ов и внешних сервисов.
