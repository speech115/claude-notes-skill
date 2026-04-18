from __future__ import annotations

from pathlib import Path
from typing import Callable

from .common import load_json_if_exists, merge_nested_dict, write_json, write_text
from .prepare_bundle_runtime import update_prepare_state_fields
from .prepare_runtime import execution_mode_for_plan, find_prepare_state_path, normalize_chunk_plan, note_contract_path


def enrich_work_dir_with_source_hints(
    work_dir: Path,
    source_hints: dict | None,
    *,
    header_seed_filename: str,
    clean_title: Callable[[str], str],
    is_informative_title: Callable[[str], bool],
    is_informative_person_hint: Callable[[str], bool],
    duration_seconds_override_from_source_hints: Callable[[dict | None], int],
    format_duration_hhmmss: Callable[[object], str],
    build_note_contract: Callable[..., dict],
    inject_source_hints_into_prescan_context: Callable[[str, dict | None], str],
    work_prompt_dir: Callable[[Path], Path],
    render_speaker_prompt: Callable[[Path], str],
    render_header_prompt: Callable[[Path], str],
    render_extraction_prompt: Callable[[Path, dict, str], str],
) -> None:
    if not isinstance(source_hints, dict) or not source_hints:
        return

    header_seed_path = work_dir / header_seed_filename
    header_seed = load_json_if_exists(header_seed_path) if header_seed_path.is_file() else {}
    if not isinstance(header_seed, dict):
        header_seed = {}

    author_hint = str(source_hints.get("author_hint") or "").strip()
    speaker_candidates = [
        str(item).strip()
        for item in source_hints.get("speaker_candidates", [])
        if isinstance(item, str) and str(item).strip()
    ]
    existing_candidates = header_seed.get("title_candidates") if isinstance(header_seed.get("title_candidates"), list) else []
    title_candidates: list[str] = []
    if author_hint and is_informative_person_hint(author_hint):
        title_candidates.append(author_hint)
    title_candidates.extend(str(item) for item in existing_candidates if isinstance(item, str))
    deduped_candidates: list[str] = []
    seen_titles: set[str] = set()
    for candidate in title_candidates:
        cleaned = clean_title(candidate)
        if not is_informative_title(cleaned):
            continue
        key = cleaned.casefold()
        if key in seen_titles:
            continue
        deduped_candidates.append(cleaned)
        seen_titles.add(key)

    participants_hint = header_seed.get("participants_hint")
    if author_hint and str(header_seed.get("speaker_stage") or "").strip() == "skip":
        participants_hint = f"single-speaker (likely {author_hint})"

    duration_override = duration_seconds_override_from_source_hints(source_hints)
    merged_header_seed = merge_nested_dict(
        header_seed,
        {
            "author_hint": author_hint or header_seed.get("author_hint"),
            "speaker_candidates": speaker_candidates or header_seed.get("speaker_candidates") or [],
            "source_identity": source_hints,
            "participants_hint": participants_hint or header_seed.get("participants_hint"),
            "title_candidates": deduped_candidates or header_seed.get("title_candidates") or [],
            "duration_estimate": (
                format_duration_hhmmss(duration_override)
                if duration_override > 0
                else header_seed.get("duration_estimate")
            ),
        },
    )
    write_json(header_seed_path, merged_header_seed)

    prepare_state_path = find_prepare_state_path(work_dir)
    prepare_state = load_json_if_exists(prepare_state_path) if prepare_state_path else {}
    if not isinstance(prepare_state, dict):
        prepare_state = {}
    content_mode = str(prepare_state.get("content_mode") or "conversation")
    execution_mode = str(prepare_state.get("execution_mode") or execution_mode_for_plan(0, content_mode=content_mode))
    total_chunks = int(prepare_state.get("total_chunks") or 0)
    duration_seconds = duration_override
    if duration_seconds <= 0:
        telemetry = prepare_state.get("telemetry") if isinstance(prepare_state.get("telemetry"), dict) else {}
        duration_seconds = int(telemetry.get("duration_seconds") or 0)
    refreshed_contract = build_note_contract(
        work_dir=work_dir,
        content_mode=content_mode,
        execution_mode=execution_mode,
        header_seed=merged_header_seed,
        total_chunks=total_chunks,
        duration_seconds=duration_seconds,
    )
    write_json(note_contract_path(work_dir), refreshed_contract)

    prescan_path = work_dir / "prescan_context.txt"
    if prescan_path.is_file():
        prescan_text = prescan_path.read_text(encoding="utf-8", errors="replace")
        enriched_text = inject_source_hints_into_prescan_context(prescan_text, source_hints)
        if enriched_text != prescan_text:
            write_text(prescan_path, enriched_text)

    prompt_dir = work_prompt_dir(work_dir)
    speaker_prompt_path = prompt_dir / "speaker-identification.md"
    if speaker_prompt_path.is_file():
        write_text(speaker_prompt_path, render_speaker_prompt(work_dir))
    header_prompt_path = prompt_dir / "header.md"
    if header_prompt_path.is_file():
        write_text(header_prompt_path, render_header_prompt(work_dir))
    for chunk in normalize_chunk_plan(prepare_state):
        chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
        if not chunk_id:
            continue
        chunk_prompt_path = prompt_dir / f"extract-{chunk_id}.md"
        if chunk_prompt_path.is_file():
            write_text(chunk_prompt_path, render_extraction_prompt(work_dir, chunk, execution_mode))

    update_prepare_state_fields(
        work_dir,
        {
            "duration_estimate": merged_header_seed.get("duration_estimate") or prepare_state.get("duration_estimate"),
            "header_seed": merged_header_seed,
            "title_candidates": merged_header_seed.get("title_candidates") or [],
            "source_identity": source_hints,
            "note_contract": refreshed_contract,
            "telemetry": {
                "duration_seconds": duration_seconds,
            } if duration_seconds > 0 else prepare_state.get("telemetry", {}),
        },
    )
