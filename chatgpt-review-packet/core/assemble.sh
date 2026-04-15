#!/usr/bin/env bash
# Notes assembly pipeline v3
# Usage: assemble.sh <work_dir> <output_md> <output_html> <title>
#
# Expects in <work_dir>:
#   chunk_*_block_*.md    — extracted blocks with YAML frontmatter
#   manifest_chunk_*.tsv  — per-agent metadata (merged here into manifest.tsv)
#   header.md             — title block
#   tldr.md               — TL;DR section
#   appendix.md           — names, resources, action plan, summary tables
# If appendix.md is missing, assemble.sh synthesizes it deterministically from
# manifest_chunk_*.tsv and summary_chunk_*.md.

set -euo pipefail

WORK_DIR="${1:?Usage: assemble.sh <work_dir> <output_md> <output_html> <title>}"
OUTPUT_MD="${2:?Missing output markdown path}"
OUTPUT_HTML="${3:?Missing output HTML path}"
TITLE="${4:?Missing title}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CSS_FILE="$SCRIPT_DIR/dark-theme.css"
TEMPLATE="$SCRIPT_DIR/template.html"
PYTHON_BIN="$(command -v python3 || command -v python || true)"

build_deterministic_appendix() {
  if [[ -f "$WORK_DIR/appendix.md" ]]; then
    return 0
  fi

  if [[ -z "${PYTHON_BIN:-}" ]]; then
    echo "WARNING: python not found — skipping deterministic appendix generation"
    return 0
  fi

  echo "No appendix.md found — generating deterministic appendix from manifests and summaries"
  "$PYTHON_BIN" - "$WORK_DIR" <<'PY'
from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


work_dir = Path(sys.argv[1]).expanduser().resolve()
manifest_paths = sorted(work_dir.glob("manifest_chunk_*.tsv"))
summary_paths = sorted(work_dir.glob("summary_chunk_*.md"))
block_paths = sorted(work_dir.glob("chunk_*_block_*.md"))
header_seed_path = work_dir / "header-seed.json"


def split_values(value: str) -> list[str]:
    items = re.split(r"[;|,]\s*", value or "")
    return [item.strip() for item in items if item.strip() and item.strip() not in {"—", "-", "–"}]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def normalize_statement(value: str) -> str:
    text = clean_text(value)
    text = re.sub(r"^\*\*[^*]+\*\*\s*:?\s*", "", text)
    text = re.sub(r"^[—–-]\s*", "", text)
    text = re.sub(r"\s*\*\([^)]+\)\*\s*$", "", text)
    return text.rstrip(".")


def limit_text(value: str, limit: int = 140) -> str:
    text = clean_text(value)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def top_items(counter: Counter[str], limit: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(limit)


def topic_tokens(value: str) -> list[str]:
    return [
        token
        for token in re.findall(r"[A-Za-zА-Яа-яЁё0-9]+", value.lower())
        if len(token) >= 4 and token not in {"этого", "этими", "почему", "через", "когда", "после", "теория", "вопрос", "совет", "автора"}
    ]


def extract_people(text: str) -> list[str]:
    candidates: list[str] = []
    for match in re.findall(r"\b(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,2}|[А-ЯЁ][а-яё]+(?:\s+[А-ЯЁ][а-яё]+){1,2})\b", text or ""):
        name = clean_text(match)
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


def prepare_action_candidate(value: str) -> str:
    text = normalize_statement(value)
    if not text:
        return ""
    if ":" in text:
        prefix, suffix = text.split(":", 1)
        prefix_lower = prefix.lower()
        if any(
            marker in prefix_lower
            for marker in (
                "вопрос",
                "метод",
                "совет",
                "критерий",
                "практик",
                "диагност",
                "вывод",
                "предупреждение",
            )
        ):
            suffix = clean_text(suffix.strip().strip("«»\""))
            if suffix:
                text = suffix
    return text.strip().strip("«»\"").rstrip(".")


def score_action_candidate(text: str) -> int:
    lowered = text.lower()
    score = 0
    strong_positive = (
        "сегодня",
        "завтра",
        "прямо сейчас",
        "немедлен",
        "зафиксир",
        "представь",
        "скажи себе",
        "сделать",
        "делать только это",
        "не сопротивля",
        "не бойся",
        "чернов",
        "первую мысль",
    )
    positive = (
        "вопрос",
        "упражнен",
        "метод",
        "практик",
        "начать",
        "действовать",
        "действуй",
        "выбери",
        "вспомни",
        "ответь",
        "живого контакта",
        "не пуг",
        "возвращ",
    )
    negative = (
        "соответствует понятию",
        "нейробиологический факт",
        "не метафора",
        "моделирование",
        "механическая система",
        "теория",
        "опровергнута исследованиями",
        "диагностический инструмент",
    )
    score += sum(2 for token in strong_positive if token in lowered)
    score += sum(1 for token in positive if token in lowered)
    score -= sum(2 for token in negative if token in lowered)
    if "?" in text or "«" in text:
        score += 1
    if len(text) > 220:
        score -= 1
    return score


def classify_action(text: str) -> str | None:
    lowered = text.lower()
    if score_action_candidate(text) < 2:
        return None
    if any(token in lowered for token in ("сегодня", "завтра", "прямо сейчас", "немедлен", "чернов", "зафиксир", "скажи себе", "представь", "сделать", "делать только это")):
        return "immediate"
    if any(token in lowered for token in ("не сопротивля", "не бойся", "не пуг", "живого контакта", "возвращ", "не смиря")):
        return "ongoing"
    return "month"


header_seed = {}
if header_seed_path.is_file():
    try:
        header_seed = json.loads(header_seed_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        header_seed = {}

name_contexts: dict[str, set[str]] = defaultdict(set)
resource_contexts: dict[str, set[str]] = defaultdict(set)
topic_counter: Counter[str] = Counter()
topic_sources: dict[str, set[str]] = defaultdict(set)
topic_descriptions: dict[str, list[str]] = defaultdict(list)
block_candidate_actions: list[str] = []

author_hint = clean_text(str(header_seed.get("author_hint") or ""))
speaker_candidates = [
    clean_text(str(item))
    for item in header_seed.get("speaker_candidates", [])
    if isinstance(item, str) and clean_text(str(item))
]
if author_hint:
    name_contexts[author_hint].add("YouTube-автор / вероятный основной спикер")
for candidate in speaker_candidates:
    if candidate != author_hint:
        name_contexts[candidate].add("Имя из metadata источника")

for manifest_path in manifest_paths:
    with manifest_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            topic = clean_text(row.get("topic", "") or row.get("title", ""))
            block_file = clean_text(row.get("block_file", manifest_path.stem))
            if topic:
                topic_counter[topic] += 1
                topic_sources[topic].add(block_file)
            for name in split_values(row.get("names", "")):
                name_contexts[name].add(topic or block_file)
            for resource in split_values(row.get("resources", "")):
                resource_contexts[resource].add(topic or block_file)

summary_lines: list[str] = []
for summary_path in summary_paths:
    for line in summary_path.read_text(encoding="utf-8", errors="replace").splitlines():
        if re.match(r"^\s*\d+\.\s+", line):
            summary_lines.append(normalize_statement(re.sub(r"^\s*\d+\.\s+", "", line)))

for block_path in block_paths:
    block_topic = ""
    in_theses = False
    for raw_line in block_path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw_line.rstrip()
        heading_match = re.match(r"^\s*#\s*Блок\s+\d+\s*:\s*(.+)$", line)
        if heading_match and not block_topic:
            block_topic = clean_text(heading_match.group(1))
            if block_topic:
                topic_counter[block_topic] += 1
                topic_sources[block_topic].add(block_path.name)
        subheading_match = re.match(r"^\s*##\s+(.+?)(?:\s+\([0-9:–-]+\))?\s*$", line)
        if subheading_match and not block_topic:
            block_topic = clean_text(subheading_match.group(1))
            if block_topic:
                topic_counter[block_topic] += 1
                topic_sources[block_topic].add(block_path.name)
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
            statement = normalize_statement(candidate)
            if statement:
                block_candidate_actions.append(statement)
                if block_topic and len(topic_descriptions[block_topic]) < 4:
                    topic_descriptions[block_topic].append(statement)
                for person in extract_people(statement):
                    name_contexts[person].add(block_topic or block_path.name)

actions = {"immediate": [], "month": [], "ongoing": []}
seen_actions: set[str] = set()


def append_actions(lines: list[str], min_score: int) -> None:
    for line in lines:
        prepared = prepare_action_candidate(line)
        if not prepared:
            continue
        if score_action_candidate(prepared) < min_score:
            continue
        bucket = classify_action(prepared)
        if not bucket:
            continue
        key = prepared.casefold()
        if key in seen_actions:
            continue
        actions[bucket].append(prepared)
        seen_actions.add(key)


append_actions(block_candidate_actions, min_score=2)
if sum(len(items) for items in actions.values()) < 5:
    append_actions(summary_lines, min_score=3)


def best_topic_description(topic: str) -> str:
    candidates = topic_descriptions.get(topic) or []
    if candidates:
        return limit_text(candidates[0], limit=180)
    topic_words = set(topic_tokens(topic))
    best_line = ""
    best_score = 0
    for line in summary_lines:
        line_words = set(topic_tokens(line))
        score = len(topic_words & line_words)
        if score > best_score:
            best_line = line
            best_score = score
    return limit_text(best_line, limit=180) if best_line else "Ключевая идея проходит через несколько частей конспекта."

immediate = actions["immediate"][:5]
month = actions["month"][:5]
ongoing = actions["ongoing"][:6]
has_actions = bool(immediate or month or ongoing)

appendix_lines: list[str] = []
appendix_lines.append("# Упомянутые люди и ресурсы")
if name_contexts or resource_contexts:
    appendix_lines.extend(["", "## Люди"])
    if name_contexts:
        for name in sorted(name_contexts):
            contexts = sorted(name_contexts[name])
            appendix_lines.append(f"- **{name}:** {limit_text('; '.join(contexts[:2]))}.")
    else:
        appendix_lines.append("- Явно названные люди не были извлечены из материалов.")

    appendix_lines.extend(["", "## Ресурсы"])
    if resource_contexts:
        for resource in sorted(resource_contexts):
            contexts = sorted(resource_contexts[resource])
            appendix_lines.append(f"- **{resource}:** {limit_text('; '.join(contexts[:2]))}.")
    else:
        appendix_lines.append("- Явно названные книги, инструменты или сервисы не были извлечены из материалов.")
else:
    appendix_lines.extend(["", "- Имена и ресурсы не были явно извлечены из материалов."])

if has_actions:
    appendix_lines.extend([
        "",
        "---",
        "",
        "# План действий",
        "",
        "### Прямо сейчас",
    ])
    for item in immediate:
        appendix_lines.append(f"- [ ] {item}")

    if month:
        appendix_lines.extend(["", "### На этой неделе"])
        for item in month:
            appendix_lines.append(f"- [ ] {item}")

    if ongoing:
        appendix_lines.extend(["", "### На постоянной основе"])
        for item in ongoing:
            appendix_lines.append(f"- [ ] {item}")

appendix_lines.extend([
    "",
    "---",
    "",
    "# Ключевые идеи и модели",
])
if topic_counter:
    for topic, _count in top_items(topic_counter, 8):
        appendix_lines.append(f"- **{limit_text(topic)}:** {best_topic_description(topic)}")
else:
    appendix_lines.append("- Явные модели и повторяющиеся идеи не были извлечены из материалов.")

(work_dir / "appendix.md").write_text("\n".join(appendix_lines).rstrip() + "\n", encoding="utf-8")
print(str(work_dir / "appendix.md"))
PY
}

# ─── Step 1: Validate inputs ───

BLOCK_FILES=("$WORK_DIR"/chunk_*_block_*.md)
if [[ ! -e "${BLOCK_FILES[0]}" ]]; then
  echo "ERROR: No block files found in $WORK_DIR (expected chunk_*_block_*.md)"
  exit 1
fi

BLOCK_COUNT="${#BLOCK_FILES[@]}"
echo "=== Notes Assembly v3 ==="
echo "Blocks found: $BLOCK_COUNT"

# ─── Step 2: Merge per-agent manifests ───

echo ""
echo "--- Merging manifests ---"
MANIFEST_FILES=("$WORK_DIR"/manifest_chunk_*.tsv)
if [[ -e "${MANIFEST_FILES[0]}" ]]; then
  head -1 "${MANIFEST_FILES[0]}" > "$WORK_DIR/manifest.tsv"
  mapfile -t SORTED_MANIFESTS < <(printf '%s\n' "${MANIFEST_FILES[@]}" | sort -V)
  for f in "${SORTED_MANIFESTS[@]}"; do
    tail -n +2 "$f" >> "$WORK_DIR/manifest.tsv"
  done
  echo "Merged ${#MANIFEST_FILES[@]} manifest files"
elif [[ -f "$WORK_DIR/manifest.tsv" ]]; then
  echo "Using existing manifest.tsv"
else
  echo "WARNING: No manifest files found — skipping manifest-based validation"
fi

build_deterministic_appendix

# ─── Step 3: Quality check — shallow blocks ───

echo ""
echo "--- Quality check ---"
SHALLOW_COUNT=0
for f in "${BLOCK_FILES[@]}"; do
  theses=$(grep -cE '^\s*[0-9]+\.' "$f" 2>/dev/null || true)
  if (( theses < 6 )); then
    echo "WARNING: $(basename "$f") has only $theses theses (min 6 expected)"
    SHALLOW_COUNT=$((SHALLOW_COUNT + 1))
  fi
done
if (( SHALLOW_COUNT == 0 )); then
  echo "All blocks pass minimum thesis count"
else
  echo "SHALLOW BLOCKS: $SHALLOW_COUNT (consider re-extracting)"
fi

# ─── Step 4: Coverage validation ───

echo ""
echo "--- Coverage validation ---"
if [[ -f "$WORK_DIR/manifest.tsv" ]]; then
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    "$PYTHON_BIN" - "$WORK_DIR/manifest.tsv" <<'PY'
from __future__ import annotations

import csv
import sys
from pathlib import Path


manifest_path = Path(sys.argv[1])


def to_seconds(value: str) -> int:
    value = (value or "").strip()
    if not value:
        return 0
    parts = value.split(":")
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    return 0


rows = list(csv.DictReader(manifest_path.open("r", encoding="utf-8", newline=""), delimiter="\t"))
prev_end = ""
prev_block = ""
for row in rows:
    block_file = (row.get("block_file") or "").strip()
    ts_start = (row.get("timestamp_start") or row.get("start_time") or row.get("ts_start") or "").strip()
    ts_end = (row.get("timestamp_end") or row.get("end_time") or row.get("ts_end") or "").strip()
    if prev_end and ts_start:
        gap = to_seconds(ts_start) - to_seconds(prev_end)
        if gap > 300:
            print(f"WARNING: {gap // 60}min gap after {prev_block} ({prev_end} -> {ts_start})")
    prev_end = ts_end or prev_end
    prev_block = block_file or prev_block

print(f"Manifest entries: {len(rows)}")
PY
  else
    MANIFEST_ENTRIES=$(( $(wc -l < "$WORK_DIR/manifest.tsv") - 1 ))
    (( MANIFEST_ENTRIES < 0 )) && MANIFEST_ENTRIES=0
    echo "Manifest entries: $MANIFEST_ENTRIES"
  fi
fi

# ─── Step 5: Duplicate detection at chunk boundaries ───

echo ""
echo "--- Boundary duplicate check ---"
mapfile -t SORTED_BLOCKS < <(printf '%s\n' "${BLOCK_FILES[@]}" | sort -V)
DUP_COUNT=0
for (( i=1; i<${#SORTED_BLOCKS[@]}; i++ )); do
  curr="${SORTED_BLOCKS[$i]}"
  prev="${SORTED_BLOCKS[$((i-1))]}"
  # Check if chunks differ (boundary)
  curr_chunk=$(basename "$curr" | sed 's/_block_.*//')
  prev_chunk=$(basename "$prev" | sed 's/_block_.*//')
  if [[ "$curr_chunk" != "$prev_chunk" ]]; then
    # Compare timestamps — extract from frontmatter
    prev_end=$(sed -n "s/^timestamp_end: *['\"]\\?\\([^'\"]*\\)['\"]\\?.*/\\1/p" "$prev" | head -1 | tr -d '[:space:]')
    curr_start=$(sed -n "s/^timestamp_start: *['\"]\\?\\([^'\"]*\\)['\"]\\?.*/\\1/p" "$curr" | head -1 | tr -d '[:space:]')
    prev_topic=$(sed -n "s/^topic: *['\"]\\?\\([^'\"]*\\)['\"]\\?.*/\\1/p" "$prev" | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    curr_topic=$(sed -n "s/^topic: *['\"]\\?\\([^'\"]*\\)['\"]\\?.*/\\1/p" "$curr" | head -1 | sed 's/^[[:space:]]*//;s/[[:space:]]*$//')
    if [[ -n "$prev_topic" && -n "$curr_topic" && "$prev_topic" == "$curr_topic" ]]; then
      echo "DUPLICATE: $(basename "$prev") and $(basename "$curr") have same topic: '$curr_topic'"
      DUP_COUNT=$((DUP_COUNT + 1))
    fi
  fi
done
if (( DUP_COUNT == 0 )); then
  echo "No boundary duplicates detected"
else
  echo "DUPLICATES: $DUP_COUNT (review manually)"
fi

# Stats from block files
TOTAL_QUOTES=$({ grep -c '> \*[«"]' "${BLOCK_FILES[@]}" 2>/dev/null || true; } | awk -F: '{s+=$NF} END {print s+0}')
TOTAL_CASES=$({ grep -cE '^###\s*(Case|Кейс)' "${BLOCK_FILES[@]}" 2>/dev/null || true; } | awk -F: '{s+=$NF} END {print s+0}')
echo ""
echo "Total quotes: $TOTAL_QUOTES"
echo "Total cases: $TOTAL_CASES"

# ─── Step 6: Assemble Markdown with block renumbering ───

echo ""
echo "--- Assembling Markdown ---"
{
  # Header
  if [[ -f "$WORK_DIR/header.md" ]]; then
    cat "$WORK_DIR/header.md"
  else
    echo "# $TITLE"
  fi
  echo ""
  echo "---"
  echo ""

  # TL;DR
  if [[ -f "$WORK_DIR/tldr.md" ]]; then
    echo "## Коротко о главном"
    echo ""
    cat "$WORK_DIR/tldr.md"
    echo ""
    echo "---"
    echo ""
  fi

  # Blocks — sorted naturally, frontmatter stripped, renumbered
  BLOCK_NUM=1
  mapfile -t SORTED_BLOCK_FILES < <(printf '%s\n' "${BLOCK_FILES[@]}" | sort -V)
  for f in "${SORTED_BLOCK_FILES[@]}"; do
    # Strip YAML frontmatter, renumber block heading, trim trailing ---
    awk -v n="$BLOCK_NUM" -v fname="$(basename "$f")" '
      BEGIN { fm=0 }
      /^---$/ { fm++; if(fm<=2) next }
      fm>=2 {
        if ($0 ~ /^## (Block|Блок)/) {
          # Transform "## Block | 00:01–09:30 | Topic" into "## Topic (00:01–09:30)"
          # Also handle new format "## Topic (00:01–09:30)" — pass through as-is
          nf = split($0, parts, "|")
          if (nf >= 3) {
            ts = parts[2]; gsub(/^[[:space:]]+|[[:space:]]+$/, "", ts)
            topic = parts[3]; gsub(/^[[:space:]]+|[[:space:]]+$/, "", topic)
            $0 = "## " topic " (" ts ")"
          }
        }
        lines[++count] = $0
      }
      { all_lines[++total] = $0 }
      END {
        if (count == 0) {
          print "WARNING: " fname " has no YAML frontmatter — using full file content" > "/dev/stderr"
          for (i = 1; i <= total; i++) print all_lines[i]
        } else {
          while (count > 0 && (lines[count] ~ /^[[:space:]]*$/ || lines[count] == "---")) count--
          for (i = 1; i <= count; i++) print lines[i]
        }
      }
    ' "$f"
    echo ""
    echo "---"
    echo ""
    BLOCK_NUM=$((BLOCK_NUM + 1))
  done

  # Appendix
  if [[ -f "$WORK_DIR/appendix.md" ]]; then
    cat "$WORK_DIR/appendix.md"
  fi
} > "$OUTPUT_MD"

MD_SIZE=$(wc -c < "$OUTPUT_MD" | tr -d ' ')
MD_LINES=$(wc -l < "$OUTPUT_MD" | tr -d ' ')
echo "Markdown: $MD_SIZE bytes, $MD_LINES lines"

# ─── Step 7: Convert to HTML via pandoc ───

echo ""
echo "--- Generating HTML ---"
if ! command -v pandoc &>/dev/null; then
  echo "WARNING: pandoc not found — skipping HTML. Install: brew install pandoc"
  echo "=== Done (Markdown only) ==="
  exit 0
fi

# Detect source URL for YouTube timestamp linking
SOURCE_URL=""
for candidate in \
  "$WORK_DIR/../source-url.txt" \
  "$WORK_DIR/source-url.txt"; do
  if [[ -f "$candidate" ]]; then
    SOURCE_URL="$(head -1 "$candidate" | tr -d '[:space:]')"
    break
  fi
done

# Build CSS header file for pandoc
CSS_HEADER=$(mktemp)
trap 'rm -f "$CSS_HEADER"' EXIT
echo "<style>" > "$CSS_HEADER"
if [[ -f "$CSS_FILE" ]]; then
  cat "$CSS_FILE" >> "$CSS_HEADER"
fi
echo "</style>" >> "$CSS_HEADER"

PANDOC_ARGS=(
  -f markdown -t html5 --standalone
  --template="$TEMPLATE"
  --include-in-header="$CSS_HEADER"
  --toc --toc-depth=2
  --metadata title="$TITLE"
)
if [[ -n "$SOURCE_URL" ]]; then
  PANDOC_ARGS+=(--metadata "source-url=$SOURCE_URL")
  echo "Source URL: $SOURCE_URL"
fi

pandoc "${PANDOC_ARGS[@]}" "$OUTPUT_MD" -o "$OUTPUT_HTML"

rm -f "$CSS_HEADER"

HTML_SIZE=$(wc -c < "$OUTPUT_HTML" | tr -d ' ')
echo "HTML: $HTML_SIZE bytes"

# ─── Step 8: PDF (optional) ───

echo ""
echo "--- Generating PDF ---"
OUTPUT_PDF="${OUTPUT_HTML%.html}.pdf"
if command -v weasyprint &>/dev/null; then
  weasyprint "$OUTPUT_HTML" "$OUTPUT_PDF" 2>/dev/null && {
    PDF_SIZE=$(wc -c < "$OUTPUT_PDF" | tr -d ' ')
    echo "PDF: $OUTPUT_PDF ($PDF_SIZE bytes)"
  } || echo "WARNING: weasyprint failed — skipping PDF"
elif command -v wkhtmltopdf &>/dev/null; then
  wkhtmltopdf --enable-local-file-access "$OUTPUT_HTML" "$OUTPUT_PDF" 2>/dev/null && {
    PDF_SIZE=$(wc -c < "$OUTPUT_PDF" | tr -d ' ')
    echo "PDF: $OUTPUT_PDF ($PDF_SIZE bytes)"
  } || echo "WARNING: wkhtmltopdf failed — skipping PDF"
else
  echo "No PDF tool found — skipping. Install: pip install weasyprint"
fi

# ─── Summary ───

echo ""
echo "=== Done ==="
echo "Markdown: $OUTPUT_MD ($MD_SIZE bytes, $MD_LINES lines)"
echo "HTML:     $OUTPUT_HTML ($HTML_SIZE bytes)"
echo "Blocks:   $BLOCK_COUNT"
echo "Quotes:   $TOTAL_QUOTES"
echo "Cases:    $TOTAL_CASES"
if (( SHALLOW_COUNT > 0 )); then
  echo "WARNING:  $SHALLOW_COUNT shallow blocks detected"
fi
if (( DUP_COUNT > 0 )); then
  echo "WARNING:  $DUP_COUNT boundary duplicates detected"
fi
