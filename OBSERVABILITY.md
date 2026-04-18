# Observability

`notes-runner` не нуждается в тяжёлой телеметрии. Ему нужен честный файловый след.

## Артефакты

- `run.json` — короткий bundle summary: источник, выходные файлы, latest run, Telegram delivery, stage metrics.
- `timeline.jsonl` — note-level ledger: одна строка на один запуск/ревизию конспекта.
- `runs/<run_id>.json` — полный snapshot конкретного запуска: refs, hashes, quality summary, change flags.
- `trace.jsonl` — append-only trace по bundle. Сюда падают high-signal события вроде `local.ready`, `youtube.ready`, `stage.prepare`, `stage.assemble`, `batch.file.failed`.
- `work/prepare_state.json` — материализованное состояние после `prepare`.
- `work/prepare_plan.json` — план chunk/stage orchestration.
- `work/stages/*.json` — sentinel-файлы по стадиям.
- `work/quality-checks.json` — prepare/final quality contract.

## Полезные команды

```bash
python3 scripts/notes-runner doctor --json
python3 scripts/notes-runner status "$WORK_DIR" --json
tail -n 50 "$BUNDLE_DIR/trace.jsonl"
tail -n 20 "$BUNDLE_DIR/timeline.jsonl"
```

## Живой trace в stderr

Для локального дебага можно зеркалить trace-события в stderr:

```bash
NOTES_RUNNER_TRACE_STDERR=1 python3 scripts/notes-runner local /abs/path/to/file.md --prepare --json
```

## Что смотреть первым

- Команда упала до `assemble`: смотри `work/stages/*.json` и `work/prepare_state.json`.
- Bundle собрался странно: смотри `run.json`, `timeline.jsonl`, `trace.jsonl`, `quality-checks.json`.
- Batch повёл себя мутно: смотри `output-root/trace.jsonl` и `batch-index.json`.

## Ограничение

`run.json` — это summary, а не идеальный source of truth. Для real history смотри `timeline.jsonl` и `runs/<run_id>.json`. Для low-level forensics смотри `trace.jsonl` и stage sentinel’ы.
