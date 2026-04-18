from __future__ import annotations

import hashlib
import json
import math
import re
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


SPEAKER_MARKER_RE = re.compile(r"\*\*Speaker\s+(\d+)\*\*")
DIALOGUE_PREFIX_RE = re.compile(r"^\s*(?:\*\*)?(?:[A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 .,_\-]{0,40})(?:\*\*)?\s*:")
DIALOGUE_SPEAKER_RE = re.compile(r"^\s*(?:\*\*)?([A-Za-zА-Яа-я0-9][A-Za-zА-Яа-я0-9 .,_\-]{0,40})(?:\*\*)?\s*:")
INTRO_RE = re.compile(
    r"(меня зовут|мне зовут|расскажи про себя|расскажите про себя|"
    r"представься|представьтесь|представь себя|представьте себя|"
    r"я .*кодер|я .*предприниматель|я .*разработчик|кто ты такой|кто вы такой)",
    re.IGNORECASE,
)
TIME_RE = re.compile(r"\*([0-9]{1,2}:[0-9]{2}(?::[0-9]{2})?)\*")
SPEAKER_CLUE_RE = re.compile(
    r"(меня зовут|мне зовут|я —|привет,?\s*я\b|расскажи про себя|расскажите про себя|представь(?:ся| себя)?|"
    r"у нас в гостях|сегодня с нами|в гостях у нас|спасибо,?\s+\w|"
    r"Speaker\s+\d+|^\s*[\wА-Яа-я][^:\n]{0,60}:)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class FileMeta:
    path: Path
    lines: int
    bytes: int
    mtime: float
    estimated_tokens: int
    markers: int
    dialogue_cues: int
    dialogue_speakers: int
    intro_cues: int
    clues: list[str]
    duration_estimate: str | None


@dataclass(frozen=True)
class PrepareLogicDependencies:
    cleanup_title_text: Callable[[str], str]
    cleanup_person_hint: Callable[[str], str]
    humanize_path_title_hint: Callable[[str], str]
    is_informative_title: Callable[[str], bool]
    is_informative_person_hint: Callable[[str], bool]
    render_source_hint_lines: Callable[[dict | None], list[str]]
    duration_seconds_override_from_source_hints: Callable[[dict | None], int]
    effective_duration_seconds_for_meta: Callable[[list[FileMeta], dict | None], int]
    effective_duration_estimate_for_meta: Callable[[list[FileMeta], dict | None], str]
    min_blocks_for_chunk: Callable[..., int]
    prepare_effective_speaker_stage: Callable[..., tuple[str, str, str, str]]
    execution_mode_for_plan: Callable[..., str]
    build_note_contract: Callable[..., dict]
    build_prepare_quality_checks: Callable[..., dict]
    note_contract_path: Callable[[Path], Path]
    quality_checks_path: Callable[[Path], Path]
    work_prompt_dir: Callable[[Path], Path]
    work_stage_dir: Callable[[Path], Path]
    stage_sentinel_path: Callable[..., Path]
    write_stage_sentinel: Callable[[Path, dict], None]
    append_trace_event: Callable[..., object]
    iso_now: Callable[[], str]
    ms_since: Callable[[float], int]
    write_json: Callable[[Path, object], None]
    write_text: Callable[[Path, str], None]
    load_json_if_exists: Callable[[Path], dict | None]
    format_label_for_content_mode: Callable[[str], str]
    format_mmss: Callable[[object], str]
    script_path: Path
    header_seed_filename: str
    stage_state_dirname: str


def _prepare_read_lines(path: Path) -> list[str]:
    return path.read_text(encoding="utf-8", errors="replace").splitlines()


def _prepare_short_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:12]


def _prepare_chunk_label(index: int) -> str:
    n = index
    label = ""
    while True:
        n, rem = divmod(n, 26)
        label = chr(ord("A") + rem) + label
        if n == 0:
            return label
        n -= 1


def _prepare_last_timestamp(lines: list[str]) -> str | None:
    timestamps = TIME_RE.findall("\n".join(lines))
    return timestamps[-1] if timestamps else None


def _estimate_tokens_from_lines(lines: list[str]) -> int:
    text = "\n".join(line.strip() for line in lines if line.strip())
    if not text:
        return 0
    chars = len(text)
    words = len(re.findall(r"\S+", text))
    return max(1, int(round(max(chars / 4.1, words * 1.18))))


def _parse_duration_to_seconds(duration_str: str | None) -> int:
    if not duration_str:
        return 0
    parts = duration_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + int(parts[1])
    except ValueError:
        pass
    return 0


def _prepare_detect_file_meta(path: Path) -> FileMeta:
    lines = _prepare_read_lines(path)
    joined = "\n".join(lines)
    marker_matches = SPEAKER_MARKER_RE.findall(joined)
    dialogue_cues = sum(1 for line in lines if DIALOGUE_PREFIX_RE.match(line))
    dialogue_speakers = {
        match.group(1).strip(" *_")
        for line in lines
        for match in [DIALOGUE_SPEAKER_RE.match(line)]
        if match and match.group(1).strip(" *_")
    }
    intro_cues = sum(1 for line in lines if INTRO_RE.search(line))
    clues: list[str] = []
    for idx, line in enumerate(lines, start=1):
        if SPEAKER_CLUE_RE.search(line):
            context_lines = []
            for ctx_idx in range(max(0, idx - 3), min(len(lines), idx + 2)):
                prefix = ">>>" if ctx_idx == idx - 1 else "   "
                context_lines.append(f"{prefix} {ctx_idx + 1}: {lines[ctx_idx].strip()}")
            clues.append("\n".join(context_lines))
            if len(clues) >= 15:
                break
    stat = path.stat()
    return FileMeta(
        path=path,
        lines=len(lines),
        bytes=stat.st_size,
        mtime=stat.st_mtime,
        estimated_tokens=_estimate_tokens_from_lines(lines),
        markers=len(set(marker_matches)),
        dialogue_cues=dialogue_cues,
        dialogue_speakers=len(dialogue_speakers),
        intro_cues=intro_cues,
        clues=clues,
        duration_estimate=_prepare_last_timestamp(lines),
    )


def prepare_fingerprint_for_files(
    input_files: list[Path], *, deps: PrepareLogicDependencies
) -> tuple[list[FileMeta], str]:
    resolved = [path.expanduser().resolve() for path in input_files]
    meta = [_prepare_detect_file_meta(path) for path in resolved]
    fingerprint_source = "\n".join(
        f"{item.path}|{item.lines}|{item.bytes}|{int(item.mtime)}" for item in meta
    )
    return meta, _prepare_short_hash(fingerprint_source)


def _prepare_classify_speaker_stage(files: list[FileMeta]) -> tuple[str, str]:
    total_markers = sum(item.markers for item in files)
    total_dialogue = sum(item.dialogue_cues for item in files)
    total_dialogue_speakers = sum(item.dialogue_speakers for item in files)
    total_intro = sum(item.intro_cues for item in files)
    total_lines = sum(item.lines for item in files)

    if total_markers >= 2 or total_dialogue >= 4 or total_intro >= 2 or total_dialogue_speakers >= 3:
        return "required", "multiple speaker markers or dialog cues detected"
    if total_markers <= 1 and total_dialogue <= 1 and total_dialogue_speakers <= 1 and total_intro <= 1 and total_lines < 1200:
        return "skip", "single-speaker or lecture-style transcript with weak dialog cues and at most one intro cue"
    return "optional", "speaker identification may help, but content can be processed safely without it"


def _prepare_choose_prescan_limit(speaker_stage: str) -> int:
    return 40 if speaker_stage == "skip" else 200


def _prepare_is_quick_mode(total_lines: int) -> bool:
    return total_lines < 250


def _prepare_line_based_chunk_count(lines: int, speaker_stage: str) -> int:
    if lines < 350 and speaker_stage == "skip":
        return 1

    speaker_factor = {
        "required": 0.92,
        "optional": 1.0,
        "skip": 1.16,
    }[speaker_stage]
    target_lines = max(350.0, (500.0 + lines / 12.0) * speaker_factor)
    chunks = max(1, math.ceil(lines / target_lines))

    if lines >= 500:
        chunks = max(2, chunks)
    elif chunks == 0:
        chunks = 1
    return chunks


def _prepare_chunk_count_for(
    lines: int,
    speaker_stage: str,
    *,
    duration_seconds: int = 0,
    estimated_tokens: int = 0,
    content_mode: str = "conversation",
) -> int:
    if _prepare_is_quick_mode(lines):
        return 1

    chunks_by_lines = _prepare_line_based_chunk_count(lines, speaker_stage)
    chunks = chunks_by_lines

    if estimated_tokens > 0 and lines < 2000:
        target_chunk_tokens = {
            "required": 2200,
            "optional": 2600,
            "skip": 3000,
        }[speaker_stage]
        chunks_by_tokens = max(1, math.ceil(estimated_tokens / target_chunk_tokens))
        chunks = max(chunks, min(chunks_by_tokens, chunks_by_lines + 1))

    if duration_seconds > 0:
        target_chunk_minutes = 20
        chunks_by_duration = max(1, math.ceil(duration_seconds / 60 / target_chunk_minutes))
        chunks = max(chunks, min(chunks_by_duration, chunks_by_lines + 2))
        if content_mode == "monologue":
            max_chunks = 2 if duration_seconds <= 30 * 60 else 3 if duration_seconds <= 55 * 60 else 4
        else:
            max_chunks = 12 if lines >= 12000 else 10 if lines >= 8000 else 8
        return min(chunks, max_chunks)

    if content_mode == "monologue":
        max_chunks = 2 if lines < 2000 else 3
    else:
        max_chunks = 12 if lines >= 12000 else 10 if lines >= 8000 else 8
    return min(chunks, max_chunks)


def _prepare_infer_topic_hint(lines: list[str], *, deps: PrepareLogicDependencies) -> str:
    for raw_line in lines[:80]:
        candidate = deps.cleanup_title_text(raw_line)
        if deps.is_informative_title(candidate):
            return candidate
    return ""


def _prepare_build_title_candidates(
    meta: list[FileMeta],
    chapters_loaded: list[dict] | None = None,
    source_hints: dict | None = None,
    *,
    deps: PrepareLogicDependencies,
) -> list[str]:
    candidates: list[str] = []
    if isinstance(source_hints, dict):
        author_hint = deps.cleanup_person_hint(str(source_hints.get("author_hint") or ""))
        if deps.is_informative_person_hint(author_hint):
            candidates.append(author_hint)
    if chapters_loaded:
        for chapter in chapters_loaded[:3]:
            title = deps.cleanup_title_text(str(chapter.get("title") or ""))
            if deps.is_informative_title(title):
                candidates.append(title)
    for item in meta:
        candidates.append(deps.humanize_path_title_hint(item.path.parent.name))
        candidates.append(deps.humanize_path_title_hint(item.path.stem))
        topic_hint = _prepare_infer_topic_hint(_prepare_read_lines(item.path), deps=deps)
        if topic_hint:
            candidates.append(topic_hint)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        cleaned = deps.cleanup_title_text(candidate)
        key = cleaned.casefold()
        if not deps.is_informative_title(cleaned) or key in seen:
            continue
        deduped.append(cleaned)
        seen.add(key)
    return deduped[:6]


def _prepare_build_header_seed(
    meta: list[FileMeta],
    speaker_stage: str,
    *,
    chapters_loaded: list[dict] | None = None,
    source_hints: dict | None = None,
    deps: PrepareLogicDependencies,
) -> dict:
    title_candidates = _prepare_build_title_candidates(
        meta,
        chapters_loaded,
        source_hints=source_hints,
        deps=deps,
    )
    topic_hint = title_candidates[0] if title_candidates else ""
    duration_hint = deps.effective_duration_estimate_for_meta(meta, source_hints)
    source_names = [item.path.name for item in meta]
    source_identity = source_hints if isinstance(source_hints, dict) else {}
    author_hint = str(source_identity.get("author_hint") or "").strip()
    speaker_candidates = [
        str(item).strip()
        for item in source_identity.get("speaker_candidates", [])
        if isinstance(item, str) and str(item).strip()
    ]
    participants_hint = "single-speaker" if speaker_stage == "skip" else "multi-speaker or interview"
    if author_hint and speaker_stage == "skip":
        participants_hint = f"single-speaker (likely {author_hint})"
    return {
        "title_candidates": title_candidates,
        "topic_hint": topic_hint,
        "duration_estimate": duration_hint,
        "speaker_stage": speaker_stage,
        "participants_hint": participants_hint,
        "source_files": source_names,
        "author_hint": author_hint or None,
        "speaker_candidates": speaker_candidates,
        "source_identity": source_identity,
    }


def _prepare_build_chunk_plan(
    meta: list[FileMeta],
    speaker_stage: str,
    *,
    work_dir: Path,
    content_mode: str,
    source_hints: dict | None = None,
    deps: PrepareLogicDependencies,
) -> list[dict]:
    plan: list[dict] = []
    prompt_dir = deps.work_prompt_dir(work_dir)
    global_index = 0
    total_override_seconds = deps.duration_seconds_override_from_source_hints(source_hints)
    total_lines_all = max(1, sum(item.lines for item in meta))
    for file_meta in meta:
        lines = file_meta.lines
        file_lines = _prepare_read_lines(file_meta.path)
        duration_seconds = _parse_duration_to_seconds(file_meta.duration_estimate)
        if total_override_seconds > 0:
            duration_seconds = int(round(total_override_seconds * (lines / total_lines_all)))
        chunks = _prepare_chunk_count_for(
            lines,
            speaker_stage,
            duration_seconds=duration_seconds,
            estimated_tokens=file_meta.estimated_tokens,
            content_mode=content_mode,
        )
        chunk_size = math.ceil(lines / chunks)
        overlap = max(10, min(24, round(chunk_size * 0.08)))

        for chunk_index in range(chunks):
            start = chunk_index * chunk_size + 1
            end = min(lines, (chunk_index + 1) * chunk_size)
            if chunk_index == chunks - 1:
                end = lines

            if chunk_index == 0 and global_index == 0:
                context_start = None
                context_end = None
                read_start = start
            else:
                context_start = max(1, start - overlap)
                context_end = max(1, start - 1)
                read_start = context_start

            chunk_id = _prepare_chunk_label(global_index)
            extraction_lines = file_lines[start - 1:end]
            chunk_token_estimate = _estimate_tokens_from_lines(extraction_lines)
            extraction_line_count = end - start + 1
            approx_chunk_duration_seconds = (
                int(round(duration_seconds * (extraction_line_count / max(lines, 1))))
                if duration_seconds > 0
                else 0
            )
            min_blocks = deps.min_blocks_for_chunk(
                extraction_lines=extraction_line_count,
                estimated_tokens=chunk_token_estimate,
                approx_duration_seconds=approx_chunk_duration_seconds,
                content_mode=content_mode,
            )
            chunk_fingerprint = _prepare_short_hash(
                "\n".join(
                    [
                        str(file_meta.path),
                        speaker_stage,
                        str(start),
                        str(end),
                        str(context_start or ""),
                        str(context_end or ""),
                        "\n".join(extraction_lines),
                    ]
                )
            )
            plan.append(
                {
                    "chunk_id": chunk_id,
                    "file": str(file_meta.path),
                    "context_start": context_start,
                    "context_end": context_end,
                    "extraction_start": start,
                    "extraction_end": end,
                    "read_start": read_start,
                    "read_end": end,
                    "chunk_size": chunk_size,
                    "overlap": overlap,
                    "estimated_tokens": chunk_token_estimate,
                    "approx_duration_seconds": approx_chunk_duration_seconds,
                    "min_blocks": min_blocks,
                    "chunk_fingerprint": chunk_fingerprint,
                    "prompt_path": str(prompt_dir / f"extract-{chunk_id}.md"),
                    "stage_sentinel_path": str(
                        deps.stage_sentinel_path(work_dir, "extraction", chunk_id=chunk_id)
                    ),
                    "expected_outputs": [
                        f"manifest_chunk_{chunk_id}.tsv",
                        f"summary_chunk_{chunk_id}.md",
                        f"{deps.stage_state_dirname}/extraction-{chunk_id}.json",
                    ],
                    "target_lines": max(
                        650,
                        int(
                            round(
                                (1000.0 + lines / 12.0)
                                * {"required": 0.92, "optional": 1.0, "skip": 1.16}[speaker_stage]
                            )
                        ),
                    ),
                    "content_mode": content_mode,
                }
            )
            global_index += 1
    return plan


def _prepare_build_prescan_context(
    meta: list[FileMeta],
    speaker_stage: str,
    prescan_limit: int,
    source_hints: dict | None = None,
    *,
    deps: PrepareLogicDependencies,
) -> str:
    tail_lines_count = 100
    parts: list[str] = []
    source_hint_lines = deps.render_source_hint_lines(source_hints)
    if source_hint_lines:
        parts.extend(source_hint_lines)
        parts.append("")
    for item in meta:
        file_stem = item.path.stem
        parts.append(f"=== FILE NAME HINT: \"{file_stem}\" ===")
        parts.append("(The file is usually named after the main speaker/guest. Use this as primary identification hint.)")
        parts.append("")

        all_lines = _prepare_read_lines(item.path)
        head_lines = all_lines[:prescan_limit]
        parts.append(f"=== FILE: {item.path} (first {prescan_limit} lines) ===")
        parts.extend(head_lines)
        parts.append("")

        if len(all_lines) > prescan_limit + tail_lines_count:
            tail_lines = all_lines[-tail_lines_count:]
            tail_start = len(all_lines) - tail_lines_count + 1
            parts.append(f"=== LAST {tail_lines_count} LINES (from line {tail_start}): {item.path} ===")
            parts.extend(tail_lines)
            parts.append("")

        mid_sample = 50
        if len(all_lines) > prescan_limit + tail_lines_count + mid_sample:
            mid_start = prescan_limit
            mid_end = len(all_lines) - tail_lines_count
            if mid_end - mid_start > mid_sample:
                best_score = -1
                best_offset = mid_start
                window_step = max(1, (mid_end - mid_start - mid_sample) // 20)
                for offset in range(mid_start, mid_end - mid_sample, window_step):
                    window = all_lines[offset:offset + mid_sample]
                    score = sum(1 for line in window if SPEAKER_CLUE_RE.search(line))
                    markers_in_window = set(SPEAKER_MARKER_RE.findall("\n".join(window)))
                    score += len(markers_in_window) * 2
                    if score > best_score:
                        best_score = score
                        best_offset = offset
                mid_lines = all_lines[best_offset:best_offset + mid_sample]
                parts.append(
                    f"=== MIDDLE SAMPLE (lines {best_offset + 1}-{best_offset + mid_sample}, densest speaker activity): {item.path} ==="
                )
                parts.extend(mid_lines)
                parts.append("")

        parts.append(f"=== SPEAKER HINTS FROM FULL FILE: {item.path} ===")
        if speaker_stage == "skip":
            parts.append("Speaker stage can be skipped for this file.")
        else:
            if item.clues:
                parts.extend(item.clues)
            else:
                parts.append("No strong speaker clues found in the sampled text.")
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def _prepare_build_report(
    *,
    work_dir: Path,
    fingerprint: str,
    meta: list[FileMeta],
    speaker_stage: str,
    content_mode: str,
    speaker_reason: str,
    prescan_limit: int,
    plan: list[dict],
    source_hints: dict | None = None,
    deps: PrepareLogicDependencies,
) -> str:
    total_lines = sum(item.lines for item in meta)
    total_chunks = len(plan)
    duration_estimate = deps.effective_duration_estimate_for_meta(meta, source_hints)
    speaker_markers = sorted(
        {
            f"Speaker {marker}"
            for item in meta
            for marker in SPEAKER_MARKER_RE.findall("\n".join(_prepare_read_lines(item.path)))
        }
    )

    lines: list[str] = [
        "=== NOTES PREPARATION REPORT ===",
        f"WORK_DIR: {work_dir}",
        f"Fingerprint: {fingerprint}",
        f"Files: {len(meta)}",
        f"Total lines: {total_lines}",
        f"Duration estimate: {duration_estimate}",
        f"Unique speakers: {len(speaker_markers)}",
        f"Content mode: {content_mode}",
        f"Speaker stage: {speaker_stage} ({speaker_reason})",
        f"Prescan limit: {prescan_limit} lines",
    ]
    if speaker_markers:
        lines.append(f"Speaker markers: {', '.join(speaker_markers)}")
    lines.extend(["", "=== CHUNK ASSIGNMENTS ===", ""])

    current_file = None
    for chunk in plan:
        if chunk["file"] != current_file:
            current_file = chunk["file"]
            file_meta = next(item for item in meta if str(item.path) == current_file)
            lines.append(
                f"FILE: {current_file} ({file_meta.lines} lines, "
                f"{_prepare_chunk_count_for(file_meta.lines, speaker_stage, content_mode=content_mode)} chunks)"
            )
            lines.append("")

        lines.append(f"  CHUNK {chunk['chunk_id']}:")
        lines.append(f"    file: {chunk['file']}")
        if chunk["context_start"] is None:
            lines.append("    context_zone: none (first chunk)")
        else:
            lines.append(f"    context_zone: lines {chunk['context_start']} to {chunk['context_end']}")
        lines.append(f"    extraction_zone: lines {chunk['extraction_start']} to {chunk['extraction_end']}")
        lines.append(f"    read_range: lines {chunk['read_start']} to {chunk['read_end']}")
        lines.append(f"    target_lines: {chunk['target_lines']}")
        lines.append(f"    overlap: {chunk['overlap']}")
        lines.append("")

    lines.extend(
        [
            f"=== TOTAL CHUNKS: {total_chunks} ===",
            "",
            f"prepare_plan.json: {work_dir / 'prepare_plan.json'}",
            f"prepare_state.json: {work_dir / 'prepare_state.json'}",
            f"prescan_context.txt: {work_dir / 'prescan_context.txt'}",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _prepare_dump_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def execution_mode_for_total_chunks(total_chunks: int, *, deps: PrepareLogicDependencies) -> str:
    return deps.execution_mode_for_plan(total_chunks, content_mode="conversation")


def _prepare_render_speaker_prompt(work_dir: Path, *, deps: PrepareLogicDependencies) -> str:
    sentinel_path = deps.stage_sentinel_path(work_dir, "speaker-identification")
    return (
        f"Read {work_dir / 'prescan_context.txt'} and {work_dir / deps.header_seed_filename} and identify speakers.\n\n"
        f"WORK_DIR: {work_dir}\n"
        f"OUTPUT: {work_dir / 'speakers.txt'}\n"
        f"SENTINEL: {sentinel_path}\n\n"
        "Rules:\n"
        "- Use filename hints first, then introductions, then who asks questions vs who answers.\n"
        "- Write plain text mappings only: Speaker N → RealName\n"
        "- If a person is unmarked, use: Unmarked lines → RealName\n"
        "- If unsure, keep Speaker N unchanged.\n\n"
        "- If source metadata names a likely YouTube author/uploader and the transcript is a monologue, prefer that real name over Speaker 1.\n\n"
        "After writing speakers.txt, write the sentinel JSON with fields:\n"
        '{\n'
        '  "stage": "speaker-identification",\n'
        '  "work_dir": "<WORK_DIR>",\n'
        '  "completed": true,\n'
        '  "completed_at": "<ISO8601>",\n'
        '  "output": "speakers.txt"\n'
        '}\n'
    )


def _prepare_render_extraction_prompt(
    work_dir: Path,
    chunk: dict,
    execution_mode: str,
    *,
    deps: PrepareLogicDependencies,
) -> str:
    chunk_id = str(chunk.get("chunk_id") or chunk.get("id") or "").strip()
    if not chunk_id:
        raise KeyError("chunk_id")
    sentinel_path = chunk["stage_sentinel_path"]
    expected_outputs = chunk.get("expected_outputs") or []
    note_contract = deps.load_json_if_exists(deps.note_contract_path(work_dir)) or {}
    block_contract = note_contract.get("blocks") if isinstance(note_contract.get("blocks"), dict) else {}
    theses_min = int(block_contract.get("theses_min") or 5)
    theses_max = int(block_contract.get("theses_max") or 8)
    meaning_section = str(block_contract.get("meaning_section") or "optional").strip()
    case_section = str(block_contract.get("case_section") or "optional").strip()
    detail_profile = str(block_contract.get("detail_profile") or "standard").strip()
    quote_max_per_block = int(block_contract.get("quote_max_per_block") or 1)
    min_blocks = max(1, int(chunk.get("min_blocks") or 1))
    approx_duration_seconds = int(chunk.get("approx_duration_seconds") or 0)
    approx_duration_line = (
        f"APPROX CHUNK DURATION: {deps.format_mmss(approx_duration_seconds)}\n"
        if approx_duration_seconds > 0
        else ""
    )
    dense_block_rule = (
        "- One dense block is valid only if the material is genuinely narrow inside this chunk.\n"
        if min_blocks == 1
        else "- One dense block is not enough for this chunk even if the material feels coherent.\n"
    )
    meaning_rule = (
        "- `### Смысл блока` is expected for every block and should state the practical implication in one short line.\n"
        if meaning_section == "expected"
        else "- `### Смысл блока` is preferred for most blocks and should state the practical implication in one short line when it is clear.\n"
        if meaning_section == "preferred"
        else "- `### Смысл блока` is optional and should be one short line only when the block has a clear practical implication.\n"
    )
    case_rule = (
        "- `### Кейс` is preferred whenever the source gives a concrete participant situation, mini-story, before/after shift, or applied example with its own lesson.\n"
        if case_section == "preferred"
        else "- Add a short case section only when an example carries a distinct lesson beyond the theses.\n"
    )
    profile_rule = (
        "- This is deep-longform material. Prefer coverage over compression, even when the source feels repetitive at first glance.\n"
        "- Preserve intermediate conclusions, local turning points, and shifts in the speaker's logic instead of flattening them into one abstract summary.\n"
        "- If the chunk contains a concrete situation or participant story, surface it as `### Кейс` rather than burying it inside generic theses.\n"
        "- Blocks in this mode should read like a guided walkthrough of the source, not a compressed essay.\n"
        if detail_profile == "deep_longform"
        else ""
    )
    single_mode_extra = ""
    if execution_mode == "single":
        single_mode_extra = (
            f"- $WORK_DIR/tldr.md\n"
            "- Because this is single-mode, also write tldr.md as a numbered list of 5-8 key takeaways in Russian.\n"
        )
    return (
        "You are an extraction agent creating detailed study notes.\n\n"
        f"WORK_DIR: {work_dir}\n"
        f"CHUNK_ID: {chunk_id}\n"
        f"FILE: {chunk['file']}\n"
        f"READ RANGE: lines {chunk.get('read_start') or chunk.get('line_start')} to {chunk.get('read_end') or chunk.get('line_end')}\n"
        f"CONTEXT ZONE: {chunk['context_start']} to {chunk['context_end']}\n"
        f"EXTRACTION ZONE: lines {chunk.get('extraction_start') or chunk.get('line_start')} to {chunk.get('extraction_end') or chunk.get('line_end')}\n"
        f"TARGET TOKENS: {chunk.get('estimated_tokens') or 'unknown'}\n"
        f"{approx_duration_line}"
        f"CHUNK FINGERPRINT: {chunk['chunk_fingerprint']}\n"
        f"MODE: {execution_mode}\n\n"
        f"NOTE CONTRACT: {deps.note_contract_path(work_dir)}\n\n"
        "Required outputs:\n"
        f"- $WORK_DIR/chunk_{chunk_id}_block_01.md ... chunk_{chunk_id}_block_NN.md\n"
        f"- $WORK_DIR/manifest_chunk_{chunk_id}.tsv\n"
        f"- $WORK_DIR/summary_chunk_{chunk_id}.md\n"
        f"{single_mode_extra}"
        f"- {sentinel_path}\n\n"
        "Rules:\n"
        "- Output in Russian.\n"
        "- Keep Speaker N labels exactly as in transcript.\n"
        "- Do not invent facts, versions, or tools not present in the source.\n"
        "- Extract only from EXTRACTION ZONE; use CONTEXT ZONE only for orientation.\n"
        "- Split by semantic or chapter boundaries, not by a fixed number of blocks.\n"
        f"- This chunk must yield at least {min_blocks} semantically distinct block(s).\n"
        f"{dense_block_rule}"
        "- Do not create blocks shorter than 5 minutes unless the source naturally ends there.\n"
        "- Each block must be dense and interpretive, not just a sparse paraphrase.\n"
        f"{profile_rule}"
        "- Give each block a conclusion-style title: what the block proves, changes, or clarifies for the reader.\n"
        f"- Each block should contain {theses_min}-{theses_max} theses with italic timestamps *(MM:SS)*.\n"
        "- Focus on ideas, models, tensions, decisions, warnings, and non-obvious implications.\n"
        "- Skip low-value procedural filler and repetitive phrasing.\n"
        f"{case_rule}"
        "- Add a short dialogue section only when the exchange reveals something non-obvious that is lost in plain theses.\n"
        f"- Include at most {quote_max_per_block} memorable verbatim quote per block, only if it is genuinely sharp or revealing.\n"
        f"{meaning_rule}"
        "- Write exactly one summary_chunk file with 5-7 numbered key ideas from this chunk.\n\n"
        "Each block file should use this structure:\n"
        "---\n"
        f"block_id: {chunk_id}_NN\n"
        'timestamp_start: "MM:SS"\n'
        'timestamp_end: "MM:SS"\n'
        'topic: "Topic title in Russian"\n'
        "---\n\n"
        "## [topic] ([timestamp range])\n\n"
        "### Тезисы:\n"
        "1. ... *(MM:SS)*\n"
        f"[{theses_min}-{theses_max} items]\n\n"
        "### Кейс: [name]\n"
        "**Контекст:** ...\n"
        "**Что произошло:** ...\n"
        "**Вывод:** ...\n"
        "[omit this whole section if no real case]\n\n"
        "### Диалог с участниками:\n"
        "**[Name]:** «...»\n"
        "**[Speaker name]:** «...»\n"
        "[omit this whole section if no meaningful dialogue]\n\n"
        "> *«Verbatim quote preserving exact language»* — [timestamp]\n"
        f"[max {quote_max_per_block} per block]\n\n"
        "### Смысл блока:\n"
        "...\n"
        "[optional: one short line only if the practical implication is genuinely clear]\n\n"
        "Manifest format:\n"
        "First line = header: block_file\\ttimestamp_start\\ttimestamp_end\\ttopic\\tprimary_claim\\tnames\\tresources\\tcase_title\\thas_dialogue\\tquote_text\\taction_now\\taction_check\\taction_avoid\\tquotes_count\\tcases\n"
        "- `primary_claim`: the single strongest idea of the block in one sentence.\n"
        "- `names`: people explicitly mentioned in the block, including Speaker N labels if real names are still unknown.\n"
        "- `resources`: books, tools, platforms, apps, services mentioned.\n"
        "- `case_title`: short case/example label or empty string.\n"
        "- `has_dialogue`: 1 if a dialogue section is present, else 0.\n"
        "- `quote_text`: the memorable quote text without markdown, or empty string.\n"
        "- `action_now`: reader-facing imperative action to try immediately, or empty string.\n"
        "- `action_check`: reader-facing diagnostic/check question for the next week, or empty string.\n"
        "- `action_avoid`: one trap/pitfall to avoid on an ongoing basis, or empty string.\n"
        "- `cases`: 1 if a real case/example section was included, else 0.\n\n"
        "After writing all files, write the sentinel JSON with fields:\n"
        "{\n"
        '  "stage": "extraction",\n'
        f'  "chunk_id": "{chunk_id}",\n'
        f'  "chunk_fingerprint": "{chunk["chunk_fingerprint"]}",\n'
        f'  "expected_outputs": {json.dumps(expected_outputs, ensure_ascii=False)},\n'
        f'  "summary_file": "summary_chunk_{chunk_id}.md",\n'
        '  "completed": true,\n'
        '  "completed_at": "<ISO8601>",\n'
        '  "block_files": ["chunk_' + chunk_id + '_block_01.md"]\n'
        "}\n"
    )


def _prepare_render_tldr_prompt(work_dir: Path, *, deps: PrepareLogicDependencies) -> str:
    sentinel_path = deps.stage_sentinel_path(work_dir, "tldr")
    return (
        "Read all summary_chunk_*.md files in $WORK_DIR (sorted), plus the note contract and block manifests.\n\n"
        f"WORK_DIR: {work_dir}\n"
        f"NOTE CONTRACT: {deps.note_contract_path(work_dir)}\n"
        f"SENTINEL: {sentinel_path}\n\n"
        "Output only a numbered list of key takeaways in Russian.\n"
        "Use the contract bounds for the number of bullets.\n"
        "Deduplicate near-identical points aggressively.\n"
        "Use only information from summary files and manifests. Do not invent.\n\n"
        "After writing tldr.md, write the sentinel JSON with fields:\n"
        '{\n'
        '  "stage": "tldr",\n'
        '  "strategy": "agent",\n'
        '  "output": "tldr.md",\n'
        '  "completed": true,\n'
        '  "completed_at": "<ISO8601>"\n'
        '}\n'
    )


def _prepare_render_header_prompt(work_dir: Path, *, deps: PrepareLogicDependencies) -> str:
    header_seed = deps.load_json_if_exists(work_dir / deps.header_seed_filename) or {}
    note_contract = deps.load_json_if_exists(deps.note_contract_path(work_dir)) or {}
    source_identity = header_seed.get("source_identity") if isinstance(header_seed.get("source_identity"), dict) else {}
    topic_hint = deps.cleanup_title_text(str(header_seed.get("topic_hint") or ""))
    duration_hint = str(header_seed.get("duration_estimate") or "unknown").strip() or "unknown"
    author_hint = deps.cleanup_person_hint(str(header_seed.get("author_hint") or ""))
    format_label = str(
        (note_contract.get("header") or {}).get("format_label")
        or deps.format_label_for_content_mode("conversation")
    )
    youtube_meta = source_identity.get("youtube") if isinstance(source_identity.get("youtube"), dict) else {}
    video_id = str(youtube_meta.get("video_id") or "").strip()
    source_label = (
        f"https://www.youtube.com/watch?v={video_id}"
        if video_id
        else ", ".join(
            [
                str(item).strip()
                for item in header_seed.get("source_files", [])
                if isinstance(item, str) and str(item).strip()
            ]
        )
        or "локальный источник"
    )
    metadata_lines: list[str] = []
    if deps.is_informative_person_hint(author_hint):
        metadata_lines.append(f"**Автор:** {author_hint}")
    metadata_lines.append(f"**Формат:** {format_label}")
    metadata_lines.append(f"**Тема:** {topic_hint or 'Сформулируй по содержанию'}")
    metadata_lines.append(f"**Длительность:** {duration_hint}")
    metadata_lines.append(f"**Источник:** {source_label}")
    metadata_block = "\n".join(metadata_lines)
    return (
        f"Read {work_dir / deps.header_seed_filename}, {deps.note_contract_path(work_dir)} and {work_dir / 'tldr.md'} if it exists.\n"
        f"Use {work_dir / 'prescan_context.txt'} only as a fallback for disambiguation.\n"
        f"Write {work_dir / 'header.md'} using the header seed, note contract and TL;DR.\n"
        "Prefer the best content title candidate, not the raw source title.\n"
        "If header-seed.json contains author_hint and this is a single-speaker YouTube monologue, use that real name in the title instead of generic labels.\n\n"
        "Write deterministic metadata exactly as provided below, and generate only the abstract plus the three author-frame bullets.\n\n"
        "Metadata block to preserve:\n"
        f"{metadata_block}\n\n"
        "Output format:\n"
        "# [Content-based title]\n\n"
        "> [2-3 sentence content summary in Russian]\n\n"
        f"{metadata_block}\n\n"
        "## Главная рамка автора\n"
        "- [core belief]\n"
        "- [what the author pushes against]\n"
        "- [practical frame for the reader]\n"
    )


def _prepare_write_prompt_packs(
    work_dir: Path,
    plan: list[dict],
    *,
    speaker_stage: str,
    execution_mode: str,
    header_seed: dict,
    deps: PrepareLogicDependencies,
) -> dict:
    prompt_dir = deps.work_prompt_dir(work_dir, create=True)
    stage_dir = deps.work_stage_dir(work_dir, create=True)

    deps.write_json(work_dir / deps.header_seed_filename, header_seed)
    prompt_paths: dict[str, object] = {
        "dir": str(prompt_dir),
        "stage_dir": str(stage_dir),
        "header_seed": str(work_dir / deps.header_seed_filename),
        "note_contract": str(deps.note_contract_path(work_dir)),
        "quality_checks": str(deps.quality_checks_path(work_dir)),
        "header": str(prompt_dir / "header.md"),
        "speaker_identification": None,
        "tldr_agent": None,
        "tldr_strategy": "inline-extraction"
        if execution_mode == "single"
        else "deterministic-merge"
        if execution_mode == "micro-multi"
        else "agent",
        "extract": {},
    }

    deps.write_text(prompt_dir / "header.md", _prepare_render_header_prompt(work_dir, deps=deps))

    if speaker_stage != "skip":
        speaker_prompt = prompt_dir / "speaker-identification.md"
        deps.write_text(speaker_prompt, _prepare_render_speaker_prompt(work_dir, deps=deps))
        prompt_paths["speaker_identification"] = str(speaker_prompt)

    for chunk in plan:
        chunk_id = chunk["chunk_id"]
        chunk_prompt_path = prompt_dir / f"extract-{chunk_id}.md"
        deps.write_text(
            chunk_prompt_path,
            _prepare_render_extraction_prompt(work_dir, chunk, execution_mode, deps=deps),
        )
        prompt_paths["extract"][chunk_id] = str(chunk_prompt_path)

    if execution_mode == "multi":
        tldr_prompt = prompt_dir / "tldr-agent.md"
        deps.write_text(tldr_prompt, _prepare_render_tldr_prompt(work_dir, deps=deps))
        prompt_paths["tldr_agent"] = str(tldr_prompt)
    else:
        deps.write_text(
            prompt_dir / "tldr-deterministic.md",
            f"Run: {deps.script_path} build-tldr {work_dir} --json\n",
        )
        prompt_paths["tldr_deterministic"] = str(prompt_dir / "tldr-deterministic.md")

    deps.write_json(prompt_dir / "plan.json", prompt_paths)
    return prompt_paths


def run_prepare_logic(
    input_files: list[Path],
    *,
    source_hints: dict | None = None,
    deps: PrepareLogicDependencies,
) -> dict:
    started_at = time.monotonic()
    resolved = [path.expanduser().resolve() for path in input_files]
    if not resolved:
        raise ValueError("No input files provided")

    meta, fingerprint = prepare_fingerprint_for_files(resolved, deps=deps)
    timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
    work_dir = Path(f"/tmp/notes_{timestamp}_{fingerprint}")
    work_dir.mkdir(parents=True, exist_ok=True)

    speaker_stage, speaker_reason = _prepare_classify_speaker_stage(meta)
    speaker_stage, speaker_reason, content_mode, content_reason = deps.prepare_effective_speaker_stage(
        meta,
        speaker_stage,
        speaker_reason,
        source_hints=source_hints,
    )
    prescan_limit = _prepare_choose_prescan_limit(speaker_stage)

    chapters_loaded: list[dict] = []
    for item in meta:
        chapters_path = item.path.parent / "chapters.json"
        if chapters_path.is_file():
            try:
                chapters_data = json.loads(chapters_path.read_text(encoding="utf-8"))
                chapters_loaded = chapters_data.get("chapters", [])
            except (json.JSONDecodeError, KeyError):
                pass
            break

    total_duration_seconds = deps.effective_duration_seconds_for_meta(meta, source_hints)
    plan = _prepare_build_chunk_plan(
        meta,
        speaker_stage,
        work_dir=work_dir,
        content_mode=content_mode,
        source_hints=source_hints,
        deps=deps,
    )
    execution_mode = deps.execution_mode_for_plan(
        len(plan),
        content_mode=content_mode,
        duration_seconds=total_duration_seconds,
    )
    prescan_context = _prepare_build_prescan_context(
        meta,
        speaker_stage,
        prescan_limit,
        source_hints=source_hints,
        deps=deps,
    )
    header_seed = _prepare_build_header_seed(
        meta,
        speaker_stage,
        chapters_loaded=chapters_loaded,
        source_hints=source_hints,
        deps=deps,
    )
    note_contract = deps.build_note_contract(
        work_dir=work_dir,
        content_mode=content_mode,
        execution_mode=execution_mode,
        header_seed=header_seed,
        total_chunks=len(plan),
        duration_seconds=total_duration_seconds,
    )
    _prepare_dump_json(deps.note_contract_path(work_dir), note_contract)
    prompt_packs = _prepare_write_prompt_packs(
        work_dir,
        plan,
        speaker_stage=speaker_stage,
        execution_mode=execution_mode,
        header_seed=header_seed,
        deps=deps,
    )
    prepare_quality_checks = deps.build_prepare_quality_checks(
        content_mode=content_mode,
        execution_mode=execution_mode,
        speaker_stage=speaker_stage,
        content_reason=content_reason,
        note_contract=note_contract,
        meta=meta,
        plan=plan,
        source_hints=source_hints,
    )
    report = _prepare_build_report(
        work_dir=work_dir,
        fingerprint=fingerprint,
        meta=meta,
        speaker_stage=speaker_stage,
        content_mode=content_mode,
        speaker_reason=speaker_reason,
        prescan_limit=prescan_limit,
        plan=plan,
        source_hints=source_hints,
        deps=deps,
    )

    total_lines = sum(item.lines for item in meta)
    quick_mode = _prepare_is_quick_mode(total_lines)
    prepare_duration_ms = deps.ms_since(started_at)

    state_payload = {
        "schema_version": 1,
        "work_dir": str(work_dir),
        "created_at": timestamp,
        "fingerprint": fingerprint,
        "quick_mode": quick_mode,
        "total_lines": total_lines,
        "total_chunks": len(plan),
        "unique_speakers": sum(item.markers for item in meta),
        "duration_estimate": deps.effective_duration_estimate_for_meta(meta, source_hints),
        "speaker_stage": speaker_stage,
        "speaker_stage_reason": speaker_reason,
        "content_mode": content_mode,
        "content_mode_reason": content_reason,
        "speaker_stage_skippable": speaker_stage == "skip",
        "prescan_limit": prescan_limit,
        "execution_mode": execution_mode,
        "title_candidates": header_seed["title_candidates"],
        "stage_hints": {
            "speaker_identification": speaker_stage,
            "appendix": "deterministic-fallback",
        },
        "stage_statuses": {
            "speaker_identification": "skipped" if speaker_stage == "skip" else "missing",
            "extraction": "missing",
            "tldr": "missing",
            "assemble": "missing",
        },
        "files": [
            {
                "path": str(item.path),
                "lines": item.lines,
                "bytes": item.bytes,
                "mtime": item.mtime,
                "estimated_tokens": item.estimated_tokens,
                "markers": item.markers,
                "dialogue_cues": item.dialogue_cues,
                "dialogue_speakers": item.dialogue_speakers,
                "intro_cues": item.intro_cues,
                "duration_estimate": item.duration_estimate,
            }
            for item in meta
        ],
        "totals": {
            "files": len(meta),
            "lines": sum(item.lines for item in meta),
            "chunks": len(plan),
            "estimated_tokens": sum(item.estimated_tokens for item in meta),
            "speaker_markers": sum(item.markers for item in meta),
            "dialogue_speakers": sum(item.dialogue_speakers for item in meta),
        },
        "artifacts": {
            "report": str(work_dir / "prepare_report.txt"),
            "plan": str(work_dir / "prepare_plan.json"),
            "state": str(work_dir / "prepare_state.json"),
            "prescan_context": str(work_dir / "prescan_context.txt"),
            "prompt_pack_dir": str(deps.work_prompt_dir(work_dir)),
            "stage_dir": str(deps.work_stage_dir(work_dir)),
            "header_seed": str(work_dir / deps.header_seed_filename),
            "note_contract": str(deps.note_contract_path(work_dir)),
            "quality_checks": str(deps.quality_checks_path(work_dir)),
        },
        "chunk_plan": plan,
        "prompt_packs": prompt_packs,
        "header_seed": header_seed,
        "source_identity": source_hints if isinstance(source_hints, dict) else {},
        "note_contract": note_contract,
        "quality_checks": prepare_quality_checks,
        "telemetry": {
            "prepare_duration_ms": prepare_duration_ms,
            "duration_seconds": total_duration_seconds,
        },
    }

    plan_payload: dict = {
        "schema_version": 1,
        "work_dir": str(work_dir),
        "fingerprint": fingerprint,
        "quick_mode": quick_mode,
        "speaker_stage": speaker_stage,
        "speaker_stage_reason": speaker_reason,
        "content_mode": content_mode,
        "content_mode_reason": content_reason,
        "execution_mode": execution_mode,
        "chunking": {
            "strategy": "single-chunk" if quick_mode else "adaptive-line-token-budget",
            "prescan_limit": prescan_limit,
        },
        "chunks": plan,
        "prompt_packs": prompt_packs,
        "header_seed": header_seed,
        "source_identity": source_hints if isinstance(source_hints, dict) else {},
        "note_contract": note_contract,
        "quality_checks": prepare_quality_checks,
        "telemetry": {
            "prepare_duration_ms": prepare_duration_ms,
            "duration_seconds": total_duration_seconds,
        },
    }

    plan_payload["chunking"]["max_chunks"] = max(
        [
            _prepare_chunk_count_for(
                item.lines,
                speaker_stage,
                estimated_tokens=item.estimated_tokens,
                content_mode=content_mode,
            )
            for item in meta
        ]
        or [0]
    )
    plan_payload["chunking"]["total_chunks"] = len(plan)

    if chapters_loaded:
        chapter_lines = ["", "=== CHAPTER MARKERS (from source) ==="]
        for chapter in chapters_loaded:
            chapter_lines.append(f"{chapter.get('timestamp', '?')} {chapter.get('title', '')}")
        chapter_lines.append("")
        prescan_context = prescan_context.rstrip("\n") + "\n" + "\n".join(chapter_lines) + "\n"

    _prepare_dump_json(work_dir / "prepare_state.json", state_payload)
    _prepare_dump_json(work_dir / "prepare_plan.json", plan_payload)
    _prepare_dump_json(deps.quality_checks_path(work_dir), prepare_quality_checks)
    (work_dir / "prescan_context.txt").write_text(prescan_context, encoding="utf-8")
    (work_dir / "prepare_report.txt").write_text(report, encoding="utf-8")
    deps.write_stage_sentinel(
        deps.stage_sentinel_path(work_dir, "prepare"),
        {
            "stage": "prepare",
            "work_dir": str(work_dir),
            "fingerprint": fingerprint,
            "content_mode": content_mode,
            "execution_mode": execution_mode,
            "completed": True,
            "completed_at": deps.iso_now(),
            "duration_ms": prepare_duration_ms,
        },
    )
    deps.append_trace_event(
        work_dir,
        "prepare.completed",
        fingerprint=fingerprint,
        duration_ms=prepare_duration_ms,
        total_chunks=len(plan),
        content_mode=content_mode,
        execution_mode=execution_mode,
    )

    return {
        "work_dir": str(work_dir),
        "fingerprint": fingerprint,
        "speaker_stage": speaker_stage,
        "speaker_stage_reason": speaker_reason,
        "content_mode": content_mode,
        "content_mode_reason": content_reason,
        "files": len(meta),
        "total_lines": sum(item.lines for item in meta),
        "total_chunks": len(plan),
        "execution_mode": execution_mode,
        "report_path": str(work_dir / "prepare_report.txt"),
        "plan_path": str(work_dir / "prepare_plan.json"),
        "state_path": str(work_dir / "prepare_state.json"),
        "prescan_context_path": str(work_dir / "prescan_context.txt"),
        "prompt_pack_dir": str(deps.work_prompt_dir(work_dir)),
        "header_seed_path": str(work_dir / deps.header_seed_filename),
        "note_contract_path": str(deps.note_contract_path(work_dir)),
        "quality_checks_path": str(deps.quality_checks_path(work_dir)),
        "prepare_duration_ms": prepare_duration_ms,
    }


__all__ = [
    "FileMeta",
    "PrepareLogicDependencies",
    "execution_mode_for_total_chunks",
    "prepare_fingerprint_for_files",
    "run_prepare_logic",
]
