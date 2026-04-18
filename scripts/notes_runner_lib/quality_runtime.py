from __future__ import annotations

import math
import re
from pathlib import Path
from typing import Callable

from .common import load_json_if_exists, write_json
from .prepare_runtime import load_prepare_payload, note_contract_path, quality_checks_path

HEADER_METADATA_LABELS = ("Автор", "Формат", "Тема", "Длительность", "Источник")
ACTION_VERB_RE = re.compile(
    r"^(?:сделай|проверь|зафиксируй|запиши|определи|выбери|сравни|найди|ответь|сформулируй|вернись|ограничь|убери|избегай|попробуй|скажи|спроси|не\b)",
    re.IGNORECASE,
)
SUMMARY_LINE_RE = re.compile(r"^\s*(?:\d+[.)]|[-*])\s+(.+?)\s*$")


def write_quality_checks(work_dir: Path, payload: dict) -> None:
    write_json(quality_checks_path(work_dir), payload)


def _read_text_file(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _read_summary_points(summary_path: Path) -> list[str]:
    points: list[str] = []
    for raw_line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        match = SUMMARY_LINE_RE.match(raw_line)
        if match:
            point = re.sub(r"\s+", " ", match.group(1)).strip()
            if point:
                points.append(point)
    if points:
        return points
    fallback = [
        re.sub(r"\s+", " ", line.strip())
        for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    return fallback[:7]


def _extract_checklist_actions(text: str) -> list[str]:
    actions: list[str] = []
    for line in text.splitlines():
        match = re.match(r"^\s*-\s+\[[ xX]\]\s+(.+?)\s*$", line)
        if match:
            action = re.sub(r"\s+", " ", match.group(1)).strip()
            if action:
                actions.append(action)
    return actions


def _count_populated_sections(text: str, heading_pattern: str) -> int:
    heading_re = re.compile(heading_pattern)
    next_heading_re = re.compile(r"^###\s+")
    lines = text.splitlines()
    count = 0
    for index, line in enumerate(lines):
        if not heading_re.match(line.strip()):
            continue
        has_content = False
        for follow in lines[index + 1:]:
            stripped = follow.strip()
            if next_heading_re.match(stripped):
                break
            if stripped:
                has_content = True
                break
        if has_content:
            count += 1
    return count


def detail_density_targets_for(duration_seconds: int, content_mode: str) -> dict:
    del content_mode
    minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    if minutes >= 150:
        return {"min_blocks_per_10min": 0.85, "min_words_per_min": 24}
    if minutes >= 90:
        return {"min_blocks_per_10min": 0.75, "min_words_per_min": 20}
    if minutes >= 45:
        return {"min_blocks_per_10min": 0.6, "min_words_per_min": 15}
    if minutes >= 20:
        return {"min_blocks_per_10min": 0.5, "min_words_per_min": 11}
    return {"min_blocks_per_10min": 0.0, "min_words_per_min": 0}


def deep_longform_targets_for(block_count: int, block_contract: dict) -> dict:
    payload = block_contract.get("deep_longform") if isinstance(block_contract.get("deep_longform"), dict) else {}
    enabled = bool(payload.get("enabled"))
    if not enabled:
        return {
            "enabled": False,
            "min_meaning_blocks": 0,
            "min_case_blocks": 0,
        }

    meaning_floor = int(payload.get("min_meaning_blocks_floor") or 0)
    meaning_ratio = float(payload.get("min_meaning_blocks_ratio") or 0.0)
    case_floor = int(payload.get("min_case_blocks_floor") or 0)
    case_ratio = float(payload.get("min_case_blocks_ratio") or 0.0)
    return {
        "enabled": True,
        "min_meaning_blocks": max(meaning_floor, math.ceil(block_count * meaning_ratio)),
        "min_case_blocks": max(case_floor, math.ceil(block_count * case_ratio)),
    }


def compute_final_quality_checks(
    work_dir: Path,
    output_md: Path,
    *,
    update_prepare_state_fields: Callable[[Path, dict], None],
    load_prepare_payload_fn: Callable[[Path], dict] = load_prepare_payload,
) -> dict:
    note_contract = load_json_if_exists(note_contract_path(work_dir)) or {}
    try:
        prepare_payload = load_prepare_payload_fn(work_dir)
    except FileNotFoundError:
        prepare_payload = {}
    quality = load_json_if_exists(quality_checks_path(work_dir)) or {
        "schema_version": 1,
        "content_mode": note_contract.get("content_mode") or "conversation",
        "prepare": {},
        "final": {},
    }

    text = _read_text_file(output_md)
    required_metadata = [
        str(item).strip()
        for item in (note_contract.get("header") or {}).get("required_metadata", [])
        if isinstance(item, str) and str(item).strip()
    ]
    if not required_metadata:
        required_metadata = list(HEADER_METADATA_LABELS)

    header_complete = bool(re.search(r"^\s*#\s+\S", text, flags=re.MULTILINE)) and bool(
        re.search(r"^\s*>\s+\S", text, flags=re.MULTILINE)
    )
    missing_header_fields: list[str] = []
    for field in required_metadata:
        if not re.search(rf"^\*\*{re.escape(field)}:\*\*\s+\S", text, flags=re.MULTILINE):
            header_complete = False
            missing_header_fields.append(field)
    if not re.search(r"^##\s+Главная рамка автора\s*$", text, flags=re.MULTILINE):
        header_complete = False
        missing_header_fields.append("Главная рамка автора")

    tldr_path = work_dir / "tldr.md"
    tldr_lines = _read_summary_points(tldr_path) if tldr_path.is_file() else []
    tldr_contract = note_contract.get("tldr") if isinstance(note_contract.get("tldr"), dict) else {}
    tldr_min = int(tldr_contract.get("min_items") or 0)
    tldr_max = int(tldr_contract.get("max_items") or 0)
    tldr_count = len(tldr_lines)
    tldr_min_ok = tldr_count >= tldr_min if tldr_min > 0 else True
    tldr_max_ok = tldr_count <= tldr_max if tldr_max > 0 else True
    tldr_length_ok = tldr_min_ok and tldr_max_ok

    placeholder_hits: list[str] = []
    if re.search(r"\bSpeaker\s+\d+\b", text):
        placeholder_hits.append("Speaker N")
    if re.search(r"^\s*-\s+\*\*[—-]\*\*", text, flags=re.MULTILINE):
        placeholder_hits.append("—")
    if re.search(r"\bunknown\b", text, flags=re.IGNORECASE):
        placeholder_hits.append("unknown")

    case_titles = [
        re.sub(r"\s+", " ", match.group(1)).strip().casefold()
        for match in re.finditer(r"^###\s+Кейс:\s*(.+?)\s*$", text, flags=re.MULTILINE)
        if re.sub(r"\s+", " ", match.group(1)).strip()
    ]
    seen_case_titles: set[str] = set()
    duplicate_case_titles: list[str] = []
    for title in case_titles:
        if title in seen_case_titles and title not in duplicate_case_titles:
            duplicate_case_titles.append(title)
        seen_case_titles.add(title)

    actions = _extract_checklist_actions(text)
    verbish_actions = sum(1 for item in actions if ACTION_VERB_RE.match(item))
    actionability_ratio = round(verbish_actions / len(actions), 2) if actions else 1.0
    duration_seconds = int(((prepare_payload.get("telemetry") or {}).get("duration_seconds") or 0))
    block_contract = note_contract.get("blocks") if isinstance(note_contract.get("blocks"), dict) else {}
    detail_targets = detail_density_targets_for(duration_seconds, str(note_contract.get("content_mode") or "conversation"))
    block_files = sorted(work_dir.glob("chunk_*_block_*.md"))
    block_count = len(block_files)
    minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    block_density = round((block_count / minutes) * 10, 2) if minutes > 0 else None
    word_count = len(re.findall(r"[\wА-Яа-яЁё'-]+", text, flags=re.UNICODE))
    words_per_minute = round(word_count / minutes, 2) if minutes > 0 else None
    meaning_blocks = _count_populated_sections(text, r"^###\s+Смысл блока:\s*$")
    case_blocks = _count_populated_sections(text, r"^###\s+Кейс:\s*(.+?)\s*$")
    deep_longform_targets = deep_longform_targets_for(block_count, block_contract)
    deep_longform_ok = (
        not deep_longform_targets["enabled"]
        or (
            meaning_blocks >= deep_longform_targets["min_meaning_blocks"]
            and case_blocks >= deep_longform_targets["min_case_blocks"]
        )
    )
    detail_density_ok = (
        duration_seconds <= 0
        or (
            (block_density is None or block_density >= detail_targets["min_blocks_per_10min"])
            and (words_per_minute is None or words_per_minute >= detail_targets["min_words_per_min"])
        )
    )

    quality["final"] = {
        "header_complete": header_complete,
        "missing_header_fields": missing_header_fields,
        "tldr_length_ok": tldr_length_ok,
        "tldr_count": tldr_count,
        "tldr_min_items": tldr_min,
        "tldr_max_items": tldr_max,
        "placeholder_leakage": {
            "ok": not placeholder_hits,
            "hits": placeholder_hits,
        },
        "duplicate_case_titles": {
            "ok": not duplicate_case_titles,
            "titles": duplicate_case_titles,
        },
        "actionability_score": {
            "items": len(actions),
            "verbish_items": verbish_actions,
            "ratio": actionability_ratio,
            "ok": actionability_ratio >= 0.6,
        },
        "deep_longform_coverage": {
            "enabled": deep_longform_targets["enabled"],
            "detail_profile": str(block_contract.get("detail_profile") or "standard"),
            "meaning_blocks": meaning_blocks,
            "min_meaning_blocks": deep_longform_targets["min_meaning_blocks"],
            "case_blocks": case_blocks,
            "min_case_blocks": deep_longform_targets["min_case_blocks"],
            "ok": deep_longform_ok,
        },
        "detail_density": {
            "duration_seconds": duration_seconds,
            "block_count": block_count,
            "blocks_per_10min": block_density,
            "min_blocks_per_10min": detail_targets["min_blocks_per_10min"],
            "word_count": word_count,
            "words_per_min": words_per_minute,
            "min_words_per_min": detail_targets["min_words_per_min"],
            "ok": detail_density_ok,
        },
    }
    write_quality_checks(work_dir, quality)
    update_prepare_state_fields(work_dir, {"quality_checks": quality})
    return quality


def contract_errors_for_quality(prepare_payload: dict, quality_payload: dict) -> list[str]:
    note_contract = prepare_payload.get("note_contract") if isinstance(prepare_payload.get("note_contract"), dict) else {}
    if not isinstance(note_contract, dict) or not note_contract:
        return []
    if not note_contract.get("enforce_on_assemble"):
        return []

    final_quality = quality_payload.get("final") if isinstance(quality_payload.get("final"), dict) else {}
    errors: list[str] = []
    if not final_quality.get("header_complete", True):
        missing = ", ".join(final_quality.get("missing_header_fields", []))
        errors.append(f"header contract failed: missing {missing or 'required fields'}")
    if not final_quality.get("tldr_length_ok", True):
        errors.append("tldr contract failed: takeaway count outside note contract bounds")
    placeholder_payload = (
        final_quality.get("placeholder_leakage")
        if isinstance(final_quality.get("placeholder_leakage"), dict)
        else {}
    )
    if placeholder_payload and not placeholder_payload.get("ok", True):
        hits = ", ".join(placeholder_payload.get("hits", []))
        errors.append(f"placeholder leakage detected: {hits}")
    duplicate_payload = (
        final_quality.get("duplicate_case_titles")
        if isinstance(final_quality.get("duplicate_case_titles"), dict)
        else {}
    )
    if duplicate_payload and not duplicate_payload.get("ok", True):
        errors.append("duplicate case titles detected across chunk boundaries")
    actionability_payload = (
        final_quality.get("actionability_score")
        if isinstance(final_quality.get("actionability_score"), dict)
        else {}
    )
    if actionability_payload and not actionability_payload.get("ok", True):
        errors.append("action plan failed actionability threshold")
    deep_longform_payload = (
        final_quality.get("deep_longform_coverage")
        if isinstance(final_quality.get("deep_longform_coverage"), dict)
        else {}
    )
    if deep_longform_payload and deep_longform_payload.get("enabled") and not deep_longform_payload.get("ok", True):
        errors.append("deep longform coverage is too thin: add more cases and intermediate conclusions")
    detail_payload = final_quality.get("detail_density") if isinstance(final_quality.get("detail_density"), dict) else {}
    if detail_payload and not detail_payload.get("ok", True):
        errors.append("note is too compressed for source duration")
    return errors
