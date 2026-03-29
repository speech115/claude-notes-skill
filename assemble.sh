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
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


work_dir = Path(sys.argv[1]).expanduser().resolve()
manifest_paths = sorted(work_dir.glob("manifest_chunk_*.tsv"))
summary_paths = sorted(work_dir.glob("summary_chunk_*.md"))


def split_values(value: str) -> list[str]:
    items = re.split(r"[;|,]\s*", value or "")
    return [item.strip() for item in items if item.strip()]


def clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip())


def top_items(counter: Counter[str], limit: int = 10) -> list[tuple[str, int]]:
    return counter.most_common(limit)


name_contexts: dict[str, set[str]] = defaultdict(set)
resource_contexts: dict[str, set[str]] = defaultdict(set)
topic_counter: Counter[str] = Counter()
topic_sources: dict[str, set[str]] = defaultdict(set)

for manifest_path in manifest_paths:
    with manifest_path.open("r", encoding="utf-8", errors="replace", newline="") as fh:
        reader = csv.DictReader(fh, delimiter="\t")
        for row in reader:
            topic = clean_text(row.get("topic", ""))
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
            summary_lines.append(clean_text(re.sub(r"^\s*\d+\.\s+", "", line)))


def classify_action(text: str) -> str | None:
    lowered = text.lower()
    if any(token in lowered for token in ("провер", "свер", "собер", "запуст", "исправ", "убер", "зафикс", "измер", "протест", "добав", "сократ")):
        return "immediate"
    if any(token in lowered for token in ("автомат", "стандар", "оптимиз", "внедр", "настро", "структур", "масштаб", "унифиц", "пересмотр")):
        return "month"
    if any(token in lowered for token in ("поддерж", "регуляр", "монитор", "переисп", "синхрон", "контрол", "документ", "обнов")):
        return "ongoing"
    return None


actions = {"immediate": [], "month": [], "ongoing": []}
for line in summary_lines:
    bucket = classify_action(line)
    if bucket and line not in actions[bucket]:
        actions[bucket].append(line)


immediate = actions["immediate"][:5]
month = actions["month"][:5]
ongoing = actions["ongoing"][:6]
has_actions = bool(immediate or month or ongoing)


def table_row(name: str, context: str) -> str:
    return f"| {name} | {context} |"


appendix_lines: list[str] = []
appendix_lines.append("# Упомянутые имена")
appendix_lines.append("| Имя | Контекст |")
appendix_lines.append("|-----|----------|")
if name_contexts:
    for name in sorted(name_contexts):
        contexts = sorted(name_contexts[name])
        appendix_lines.append(table_row(name, "; ".join(contexts[:2])))
else:
    appendix_lines.append("| — | Имена не извлечены из manifest files |")

appendix_lines.extend(["", "---", "", "# Упомянутые инструменты и ресурсы", "| Инструмент/Ресурс | Назначение |", "|--------------------|-----------|"])
if resource_contexts:
    for resource in sorted(resource_contexts):
        contexts = sorted(resource_contexts[resource])
        appendix_lines.append(table_row(resource, "; ".join(contexts[:2])))
else:
    appendix_lines.append("| — | Ресурсы не извлечены из manifest files |")

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
        appendix_lines.extend(["", "### В первый месяц"])
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
    "",
    "## Частые темы",
    "| Тема | Частота | Источники |",
    "|------|---------|-----------|",
])
if topic_counter:
    for topic, count in top_items(topic_counter, 10):
        sources = ", ".join(sorted(topic_sources[topic])[:3])
        appendix_lines.append(f"| {topic} | {count} | {sources} |")
else:
    appendix_lines.append("| — | 0 | Нет данных |")

appendix_lines.extend([
    "",
    "*Секция собрана детерминированно из manifest_chunk_*.tsv и summary_chunk_*.md, потому что appendix.md не был найден.*",
])

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
  to_sec() {
    local t="$1"
    if [[ "$t" == *:*:* ]]; then
      echo "$t" | awk -F: '{print $1*3600+$2*60+$3}'
    elif [[ "$t" == *:* ]]; then
      echo "$t" | awk -F: '{print $1*60+$2}'
    else
      echo 0
    fi
  }
  prev_end=""
  prev_block=""
  tail -n +2 "$WORK_DIR/manifest.tsv" | while IFS=$'\t' read -r block_file ts_start ts_end topic rest; do
    if [[ -n "$prev_end" && -n "$ts_start" ]]; then
      end_sec=$(to_sec "$prev_end")
      start_sec=$(to_sec "$ts_start")
      gap=$(( start_sec - end_sec ))
      if (( gap > 300 )); then
        echo "WARNING: $(( gap / 60 ))min gap after $prev_block ($prev_end -> $ts_start)"
      fi
    fi
    prev_end="$ts_end"
    prev_block="$block_file"
  done
  MANIFEST_ENTRIES=$(( $(wc -l < "$WORK_DIR/manifest.tsv") - 1 ))
  (( MANIFEST_ENTRIES < 0 )) && MANIFEST_ENTRIES=0
  echo "Manifest entries: $MANIFEST_ENTRIES"
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

  echo ""
  echo "*Конспект составлен на основе транскриптов. Содержит только то, что звучало в записи.*"
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
