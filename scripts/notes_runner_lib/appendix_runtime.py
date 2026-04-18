from __future__ import annotations

import csv
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Callable


def merge_manifest_parts(
    work_dir: Path,
    *,
    write_text: Callable[[Path, str], None],
) -> Path | None:
    manifest_parts = sorted(work_dir.glob("manifest_chunk_*.tsv"))
    merged_path = work_dir / "manifest.tsv"
    if not manifest_parts:
        return merged_path if merged_path.is_file() else None
    lines = manifest_parts[0].read_text(encoding="utf-8", errors="replace").splitlines()[:1]
    for part in manifest_parts:
        part_lines = part.read_text(encoding="utf-8", errors="replace").splitlines()
        if part_lines:
            lines.extend(part_lines[1:])
    write_text(merged_path, "\n".join(lines).rstrip() + "\n")
    return merged_path


def _split_manifest_values(value: str) -> list[str]:
    items = re.split(r"[;|,]\s*", value or "")
    return [item.strip() for item in items if item.strip() and item.strip() not in {"—", "-", "–"}]


def _normalize_statement(value: str) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    text = re.sub(r"^\*\*[^*]+\*\*\s*:?\s*", "", text)
    text = re.sub(r"^[—–-]\s*", "", text)
    text = re.sub(r"\s*\*\([^)]+\)\*\s*$", "", text)
    return text.rstrip(".").strip()


def _limit_text(value: str, limit: int = 140) -> str:
    text = re.sub(r"\s+", " ", (value or "").strip())
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def _topic_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", value.lower())
        if len(token) >= 4 and token not in {"этого", "этими", "почему", "через", "когда", "после", "теория", "вопрос", "совет", "автора"}
    ]


def _extract_people_from_text(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}|[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})\b", text or ""):
        name = re.sub(r"\s+", " ", match.strip())
        if len(name) >= 4:
            candidates.append(name)
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        key = candidate.casefold()
        if key in seen:
            continue
        deduped.append(candidate)
        seen.add(key)
    return deduped


def _is_placeholder_entity(value: str) -> bool:
    text = re.sub(r"\s+", " ", (value or "").strip())
    if not text or text in {"—", "-", "–"}:
        return True
    if text.casefold() in {"unknown", "speaker", "author", "creator", "uploader"}:
        return True
    if re.fullmatch(r"speaker\s+\d+", text, flags=re.IGNORECASE):
        return True
    return False


def _prepare_action_candidate_text(value: str) -> str:
    text = _normalize_statement(value)
    if not text:
        return ""
    if ":" in text:
        prefix, suffix = text.split(":", 1)
        prefix_lower = prefix.lower()
        if any(marker in prefix_lower for marker in ("вопрос", "метод", "совет", "критерий", "практик", "диагност", "вывод", "предупреждение")):
            suffix = re.sub(r"\s+", " ", suffix.strip().strip("«»\""))
            if suffix:
                text = suffix
    return text.strip().strip("«»\"").rstrip(".")


def _imperative_action_text(value: str) -> str:
    text = _prepare_action_candidate_text(value)
    if not text:
        return ""
    first = text.split(" ", 1)[0].strip("«»\".,:;!?").casefold()
    if re.match(r"^(сделай|проверь|зафиксируй|запиши|определи|выбери|сравни|найди|ответь|сформулируй|вернись|ограничь|убери|избегай|попробуй|скажи|спроси|не)$", first):
        return text
    lowered = text.casefold()
    for token, prefix in (
        ("перв", "Зафиксируй "),
        ("вопрос", "Ответь себе на вопрос: "),
        ("мысл", "Запиши мысль: "),
        ("страх", "Проверь страх: "),
        ("роль", "Определи роль: "),
        ("блокир", "Найди блокирующую мысль: "),
    ):
        if token in lowered:
            return prefix + text[0].lower() + text[1:] if text else ""
    return text


def _score_action_candidate(text: str) -> int:
    lowered = text.lower()
    score = 0
    strong_positive = (
        "сегодня", "завтра", "прямо сейчас", "немедлен", "сделай", "проверь", "зафиксируй", "запиши",
        "определи", "выбери", "ответь", "найди", "сформулируй", "вернись", "ограничь", "убери",
        "избегай", "попробуй", "зафиксир", "представь", "скажи себе", "сделать", "делать только это",
        "не сопротивля", "не бойся", "чернов", "первую мысль",
    )
    positive = ("вопрос", "упражнен", "метод", "практик", "начать", "действовать", "действуй", "вспомни", "живого контакта", "не пуг", "возвращ")
    negative = ("соответствует понятию", "нейробиологический факт", "не метафора", "моделирование", "механическая система", "теория", "опровергнута исследованиями", "диагностический инструмент")
    score += sum(2 for token in strong_positive if token in lowered)
    score += sum(1 for token in positive if token in lowered)
    score -= sum(2 for token in negative if token in lowered)
    if "?" in text or "«" in text:
        score += 1
    if len(text) > 220:
        score -= 1
    return score


def _classify_action_bucket(text: str) -> str | None:
    lowered = text.lower()
    if _score_action_candidate(text) < 2:
        return None
    if any(token in lowered for token in ("сегодня", "завтра", "прямо сейчас", "немедлен", "чернов", "зафиксир", "скажи себе", "представь", "сделать", "делать только это")):
        return "immediate"
    if lowered.startswith(("сделай", "проверь", "зафиксируй", "запиши", "определи", "выбери", "ответь", "найди", "сформулируй")):
        return "immediate"
    if any(token in lowered for token in ("не сопротивля", "не бойся", "не пуг", "живого контакта", "возвращ", "не смиря")):
        return "ongoing"
    if lowered.startswith(("не ", "избегай", "вернись")):
        return "ongoing"
    return "month"


def build_deterministic_appendix(
    work_dir: Path,
    *,
    header_seed_filename: str,
    load_json_if_exists: Callable[[Path], dict | None],
    read_summary_points: Callable[[Path], list[str]],
    read_text_file: Callable[[Path], str],
    write_text: Callable[[Path, str], None],
) -> Path:
    appendix_path = work_dir / "appendix.md"
    manifest_paths = sorted(work_dir.glob("manifest_chunk_*.tsv"))
    summary_paths = sorted(work_dir.glob("summary_chunk_*.md"))
    block_paths = sorted(work_dir.glob("chunk_*_block_*.md"))
    source_paths = manifest_paths + summary_paths + block_paths + [work_dir / header_seed_filename]
    if appendix_path.is_file():
        appendix_mtime = appendix_path.stat().st_mtime
        newest_source = max((path.stat().st_mtime for path in source_paths if path.is_file()), default=0)
        if newest_source <= appendix_mtime:
            return appendix_path
    header_seed = load_json_if_exists(work_dir / header_seed_filename) or {}

    name_contexts: dict[str, set[str]] = defaultdict(set)
    resource_contexts: dict[str, set[str]] = defaultdict(set)
    topic_counter: Counter[str] = Counter()
    topic_descriptions: dict[str, list[str]] = defaultdict(list)
    block_candidate_actions: list[str] = []
    manifest_action_now: list[str] = []
    manifest_action_check: list[str] = []
    manifest_action_avoid: list[str] = []

    author_hint = re.sub(r"\s+", " ", str(header_seed.get("author_hint") or "").strip())
    speaker_candidates = [
        re.sub(r"\s+", " ", str(item).strip())
        for item in header_seed.get("speaker_candidates", [])
        if isinstance(item, str) and str(item).strip()
    ]
    if author_hint and not _is_placeholder_entity(author_hint):
        name_contexts[author_hint].add("YouTube-автор / вероятный основной спикер")
    for candidate in speaker_candidates:
        if candidate != author_hint and not _is_placeholder_entity(candidate):
            name_contexts[candidate].add("Имя из metadata источника")

    for manifest_path in manifest_paths:
        with manifest_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
            reader = csv.DictReader(fh, delimiter="\t")
            for row in reader:
                topic = re.sub(r"\s+", " ", (row.get("topic", "") or row.get("title", "")).strip())
                block_file = re.sub(r"\s+", " ", (row.get("block_file", manifest_path.stem)).strip())
                if topic:
                    topic_counter[topic] += 1
                primary_claim = _normalize_statement(row.get("primary_claim", ""))
                if topic and primary_claim and len(topic_descriptions[topic]) < 4:
                    topic_descriptions[topic].append(primary_claim)
                for name in _split_manifest_values(row.get("names", "")):
                    if not _is_placeholder_entity(name):
                        name_contexts[name].add(topic or block_file)
                for resource in _split_manifest_values(row.get("resources", "")):
                    if not _is_placeholder_entity(resource):
                        resource_contexts[resource].add(topic or block_file)
                case_title = re.sub(r"\s+", " ", (row.get("case_title", "") or "").strip())
                if topic and case_title and len(topic_descriptions[topic]) < 4:
                    topic_descriptions[topic].append(f"Кейс: {case_title}")
                for candidate, bucket in (
                    (row.get("action_now", ""), manifest_action_now),
                    (row.get("action_check", ""), manifest_action_check),
                    (row.get("action_avoid", ""), manifest_action_avoid),
                ):
                    prepared = _imperative_action_text(candidate or "")
                    if prepared:
                        bucket.append(prepared)

    summary_lines: list[str] = []
    for summary_path in summary_paths:
        summary_lines.extend([_normalize_statement(line) for line in read_summary_points(summary_path)])

    for block_path in block_paths:
        block_topic = ""
        block_topic_recorded = False
        in_theses = False
        for raw_line in read_text_file(block_path).splitlines():
            line = raw_line.rstrip()
            heading_match = re.match(r"^\s*#\s*Блок\s+\d+\s*:\s*(.+)$", line)
            if heading_match and not block_topic:
                block_topic = re.sub(r"\s+", " ", heading_match.group(1).strip())
            subheading_match = re.match(r"^\s*##\s+(.+?)(?:\s+\([0-9:–-]+\))?\s*$", line)
            if subheading_match and not block_topic:
                block_topic = re.sub(r"\s+", " ", subheading_match.group(1).strip())
            if block_topic and not block_topic_recorded:
                topic_counter[block_topic] += 1
                block_topic_recorded = True
            if re.match(r"^\s*###\s+Тезисы", line):
                in_theses = True
                continue
            if re.match(r"^\s*###\s+", line):
                in_theses = False
            thesis_match = re.match(r"^\s*\d+\.\s+(.+)$", line)
            bullet_match = re.match(r"^\s*[-*]\s*(?:\*\([^)]+\)\*\s*)?(.+)$", line)
            verdict_match = re.match(r"^\s*\*\*Вывод:\*\*\s*(.+)$", line)
            candidate = ""
            if in_theses and thesis_match:
                candidate = thesis_match.group(1)
            elif bullet_match and re.search(r"\*\([^)]+\)\*", line):
                candidate = bullet_match.group(1)
            elif verdict_match:
                candidate = verdict_match.group(1)
            if candidate:
                statement = _normalize_statement(candidate)
                if statement:
                    block_candidate_actions.append(statement)
                    if block_topic and len(topic_descriptions[block_topic]) < 4:
                        topic_descriptions[block_topic].append(statement)
                    for person in _extract_people_from_text(statement):
                        if not _is_placeholder_entity(person):
                            name_contexts[person].add(block_topic or block_path.name)

    actions = {"immediate": [], "month": [], "ongoing": []}
    seen_actions: set[str] = set()

    def append_direct(bucket_name: str, lines: list[str]) -> None:
        for line in lines:
            prepared = _imperative_action_text(line)
            if not prepared:
                continue
            key = prepared.casefold()
            if key in seen_actions:
                continue
            actions[bucket_name].append(prepared)
            seen_actions.add(key)

    def append_scored(lines: list[str], min_score: int) -> None:
        for line in lines:
            prepared = _prepare_action_candidate_text(line)
            if not prepared:
                continue
            if _score_action_candidate(prepared) < min_score:
                continue
            bucket = _classify_action_bucket(prepared)
            if not bucket:
                continue
            key = prepared.casefold()
            if key in seen_actions:
                continue
            actions[bucket].append(prepared)
            seen_actions.add(key)

    append_direct("immediate", manifest_action_now)
    append_direct("month", manifest_action_check)
    append_direct("ongoing", manifest_action_avoid)
    append_scored(block_candidate_actions, 2)
    if sum(len(items) for items in actions.values()) < 5:
        append_scored(summary_lines, 3)

    def best_topic_description(topic: str) -> str:
        candidates = topic_descriptions.get(topic) or []
        if candidates:
            return _limit_text(candidates[0], limit=180)
        topic_words = set(_topic_tokens(topic))
        best_line = ""
        best_score = 0
        for line in summary_lines:
            line_words = set(_topic_tokens(line))
            score = len(topic_words & line_words)
            if score > best_score:
                best_line = line
                best_score = score
        return _limit_text(best_line, limit=180) if best_line else "Ключевая идея проходит через несколько частей конспекта."

    appendix_lines: list[str] = ["# Упомянутые люди и ресурсы"]
    if name_contexts or resource_contexts:
        appendix_lines.extend(["", "## Люди"])
        if name_contexts:
            for name in sorted(name_contexts):
                contexts = sorted(name_contexts[name])
                appendix_lines.append(f"- **{name}:** {_limit_text('; '.join(contexts[:2]))}.")
        else:
            appendix_lines.append("- Явно названные люди не были извлечены из материалов.")
        appendix_lines.extend(["", "## Ресурсы"])
        if resource_contexts:
            for resource in sorted(resource_contexts):
                contexts = sorted(resource_contexts[resource])
                appendix_lines.append(f"- **{resource}:** {_limit_text('; '.join(contexts[:2]))}.")
        else:
            appendix_lines.append("- Явно названные книги, инструменты или сервисы не были извлечены из материалов.")
    else:
        appendix_lines.extend(["", "- Имена и ресурсы не были явно извлечены из материалов."])

    if any(actions.values()):
        appendix_lines.extend(["", "---", "", "# План действий", "", "### Прямо сейчас"])
        for item in actions["immediate"][:5]:
            appendix_lines.append(f"- [ ] {item}")
        if actions["month"]:
            appendix_lines.extend(["", "### На этой неделе"])
            for item in actions["month"][:5]:
                appendix_lines.append(f"- [ ] {item}")
        if actions["ongoing"]:
            appendix_lines.extend(["", "### На постоянной основе"])
            for item in actions["ongoing"][:6]:
                appendix_lines.append(f"- [ ] {item}")

    appendix_lines.extend(["", "---", "", "# Ключевые идеи и модели"])
    if topic_counter:
        for topic, _count in topic_counter.most_common(8):
            appendix_lines.append(f"- **{_limit_text(topic)}:** {best_topic_description(topic)}")
    else:
        appendix_lines.append("- Явные модели и повторяющиеся идеи не были извлечены из материалов.")

    write_text(appendix_path, "\n".join(appendix_lines).rstrip() + "\n")
    return appendix_path
