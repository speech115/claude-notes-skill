from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime
from pathlib import Path


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8")


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_json_if_exists(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        payload = load_json(path)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def iso_now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def append_jsonl(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")


def sha1_text(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()


def normalize_external_refs(values: list[object]) -> list[str]:
    refs: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        refs.append(text)
        seen.add(text)
    return refs


def collect_external_refs() -> list[str]:
    refs: list[object] = []
    codex_thread_id = str(os.environ.get("CODEX_THREAD_ID") or "").strip()
    if codex_thread_id:
        refs.append(f"codex:thread:{codex_thread_id}")
    for env_name in ("NOTES_RUNNER_EXTERNAL_REF", "NOTES_RUNNER_EXTERNAL_REFS"):
        raw = str(os.environ.get(env_name) or "")
        if not raw.strip():
            continue
        refs.extend(part.strip() for part in re.split(r"[\n,]+", raw) if part.strip())
    return normalize_external_refs(refs)


def resolved_path_string(raw_path: str) -> str:
    return str(Path(raw_path).expanduser().resolve(strict=False))


def read_first_line(path: Path) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace").strip()
    return text or None


def merge_nested_dict(base: dict, patch: dict) -> dict:
    result = dict(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge_nested_dict(result[key], value)
        else:
            result[key] = value
    return result


def collapse_blank_lines(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def sanitize_delivery_name(value: str, *, suffix: str) -> str:
    normalized = re.sub(r"[\r\n]+", " ", value).strip()
    normalized = re.sub(r'[<>:"/\\|?*]+', " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip(" .")
    if not normalized:
        normalized = "Конспект"
    return f"{normalized[:120].rstrip(' .')}{suffix}"


def compute_file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def file_sha256_if_exists(path: Path | None) -> str | None:
    if path is None or not path.is_file():
        return None
    return compute_file_sha256(path)
