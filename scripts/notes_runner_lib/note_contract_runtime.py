from __future__ import annotations

import math
from pathlib import Path
from typing import Callable


def format_label_for_content_mode(content_mode: str) -> str:
    return {
        "monologue": "лекция",
        "conversation": "интервью",
        "workshop": "воркшоп",
    }.get(content_mode, "разбор")


def tldr_bounds_for(content_mode: str, duration_seconds: int, total_chunks: int) -> tuple[int, int]:
    minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    if content_mode == "monologue":
        if minutes and minutes <= 18:
            return (5, 6)
        if minutes and minutes <= 35:
            return (6, 8)
        if minutes and minutes >= 150:
            return (12, 16)
        if minutes and minutes >= 90:
            return (10, 14)
        return (7, 9) if total_chunks <= 3 else (8, 10)
    if content_mode == "conversation":
        if minutes and minutes <= 30:
            return (6, 8)
        if minutes and minutes >= 150:
            return (12, 16)
        if minutes and minutes >= 90:
            return (10, 14)
        return (7, 10)
    if minutes and minutes >= 150:
        return (13, 18)
    if minutes and minutes >= 90:
        return (11, 15)
    if minutes and minutes <= 35:
        return (7, 9)
    return (8, 12)


def block_contract_for(duration_seconds: int, content_mode: str) -> dict:
    contract = {
        "theses_min": 5,
        "theses_max": 8,
        "meaning_section": "optional",
        "detail_profile": "standard",
        "case_section": "optional",
        "quote_max_per_block": 1,
        "deep_longform": {
            "enabled": False,
            "min_meaning_blocks_floor": 0,
            "min_meaning_blocks_ratio": 0.0,
            "min_case_blocks_floor": 0,
            "min_case_blocks_ratio": 0.0,
        },
    }
    minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    if minutes >= 60:
        contract["theses_min"] = 6
        contract["theses_max"] = 9
        contract["meaning_section"] = "preferred"
    if minutes >= 90:
        contract["theses_min"] = 7
        contract["theses_max"] = 10 if content_mode == "workshop" else 9
        contract["meaning_section"] = "expected"
    if minutes >= 120:
        contract["theses_min"] = 7
        contract["theses_max"] = 11 if content_mode == "workshop" else 10
        contract["meaning_section"] = "expected"
        contract["detail_profile"] = "deep_longform"
        contract["case_section"] = "preferred"
        contract["deep_longform"] = {
            "enabled": True,
            "min_meaning_blocks_floor": 4,
            "min_meaning_blocks_ratio": 0.75,
            "min_case_blocks_floor": 2 if content_mode == "monologue" else 4 if content_mode == "workshop" else 3,
            "min_case_blocks_ratio": 0.2 if content_mode == "monologue" else 0.3 if content_mode == "workshop" else 0.25,
        }
    if minutes >= 150:
        contract["deep_longform"] = {
            "enabled": True,
            "min_meaning_blocks_floor": 5,
            "min_meaning_blocks_ratio": 0.8,
            "min_case_blocks_floor": 3 if content_mode == "monologue" else 5 if content_mode == "workshop" else 4,
            "min_case_blocks_ratio": 0.25 if content_mode == "monologue" else 0.35 if content_mode == "workshop" else 0.3,
        }
    return contract


def detail_density_targets_for(duration_seconds: int, content_mode: str) -> dict:
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


def build_note_contract(
    *,
    work_dir: Path,
    content_mode: str,
    execution_mode: str,
    header_seed: dict,
    total_chunks: int,
    duration_seconds: int,
    cleanup_person_hint: Callable[[str], str],
    is_informative_person_hint: Callable[[str], bool],
    header_seed_filename: str,
) -> dict:
    tldr_min, tldr_max = tldr_bounds_for(content_mode, duration_seconds, total_chunks)
    block_contract = block_contract_for(duration_seconds, content_mode)
    author_hint = cleanup_person_hint(str(header_seed.get("author_hint") or ""))
    required_metadata = ["Формат", "Тема", "Длительность", "Источник"]
    if is_informative_person_hint(author_hint):
        required_metadata.insert(0, "Автор")
    optional_metadata = ["Участники"] if content_mode != "monologue" else []
    required_sections = [
        "title",
        "abstract",
        "metadata",
        "главная_рамка_автора",
        "коротко_о_главном",
        "основные_блоки",
        "упомянутые_люди_и_ресурсы",
    ]
    optional_sections = ["план_действий", "ключевые_идеи_и_модели"]
    return {
        "schema_version": 1,
        "work_dir": str(work_dir),
        "content_mode": content_mode,
        "execution_mode": execution_mode,
        "enforce_on_assemble": True,
        "header": {
            "required_metadata": required_metadata,
            "optional_metadata": optional_metadata,
            "format_label": format_label_for_content_mode(content_mode),
            "author_hint": author_hint or None,
            "author_frame_style": "three-bullets",
        },
        "blocks": {
            "theses_min": block_contract["theses_min"],
            "theses_max": block_contract["theses_max"],
            "meaning_section": block_contract["meaning_section"],
            "meaning_label": "Смысл блока",
            "case_optional": True,
            "case_section": block_contract["case_section"],
            "dialogue_optional": content_mode != "monologue",
            "quote_max_per_block": block_contract["quote_max_per_block"],
            "detail_profile": block_contract["detail_profile"],
            "deep_longform": block_contract["deep_longform"],
        },
        "tldr": {
            "required": True,
            "strategy": "inline-extraction" if execution_mode == "single" else "deterministic-merge" if execution_mode == "micro-multi" else "agent",
            "min_items": tldr_min,
            "max_items": tldr_max,
        },
        "section_order": [
            "header",
            "коротко_о_главном",
            "основные_блоки",
            "упомянутые_люди_и_ресурсы",
            "план_действий",
            "ключевые_идеи_и_модели",
        ],
        "required_sections": required_sections,
        "optional_sections": optional_sections,
        "forbidden_placeholders": ["Speaker N", "—", "unknown"],
        "paths": {
            "header_seed": str(work_dir / header_seed_filename),
        },
    }


def build_prepare_quality_checks(
    *,
    content_mode: str,
    execution_mode: str,
    speaker_stage: str,
    content_reason: str,
    note_contract: dict,
    meta: list,
    plan: list[dict],
    source_hints: dict | None = None,
    effective_duration_seconds_for_meta: Callable[[list, dict | None], int],
    cleanup_person_hint: Callable[[str], str],
    is_informative_person_hint: Callable[[str], bool],
) -> dict:
    total_lines = sum(item.lines for item in meta)
    duration_seconds = effective_duration_seconds_for_meta(meta, source_hints)
    minutes = duration_seconds / 60 if duration_seconds > 0 else 0
    blocks_per_10m = round((len(plan) / minutes) * 10, 2) if minutes > 0 else None
    density_targets = detail_density_targets_for(duration_seconds, content_mode)
    monologue_fast_path_expected = (
        content_mode == "monologue"
        and str((source_hints or {}).get("source_kind") or "").strip() == "youtube"
        and is_informative_person_hint(cleanup_person_hint(str((source_hints or {}).get("author_hint") or "")))
    )
    monologue_fast_path_ok = not monologue_fast_path_expected or (
        speaker_stage == "skip" and execution_mode in {"single", "micro-multi"}
    )
    return {
        "schema_version": 1,
        "content_mode": content_mode,
        "prepare": {
            "header_contract_defined": True,
            "speaker_routing": {
                "ok": speaker_stage in {"skip", "optional", "required"},
                "speaker_stage": speaker_stage,
                "content_reason": content_reason,
            },
            "monologue_fast_path": {
                "expected": monologue_fast_path_expected,
                "ok": monologue_fast_path_ok,
            },
            "fragmentation": {
                "total_lines": total_lines,
                "duration_seconds": duration_seconds,
                "planned_chunks": len(plan),
                "content_blocks_per_10min": blocks_per_10m,
                "min_blocks_per_10min": density_targets["min_blocks_per_10min"],
                "ok": blocks_per_10m is None or (
                    density_targets["min_blocks_per_10min"] <= blocks_per_10m <= 1.8
                ),
            },
            "tldr_bounds": note_contract.get("tldr", {}),
        },
        "final": {},
    }


__all__ = [
    "format_label_for_content_mode",
    "tldr_bounds_for",
    "block_contract_for",
    "detail_density_targets_for",
    "deep_longform_targets_for",
    "build_note_contract",
    "build_prepare_quality_checks",
]
