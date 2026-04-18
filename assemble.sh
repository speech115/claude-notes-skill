#!/usr/bin/env bash
# Notes assembly pipeline v3
# Usage: assemble.sh <work_dir> <output_md> <output_html> <title>
#
# Expects in <work_dir>:
#   chunk_*_block_*.md    — extracted blocks with YAML frontmatter
#   manifest_chunk_*.tsv  — per-agent metadata (merged here into manifest.tsv)
#   header.md             — title block
#   tldr.md               — TL;DR section
#   appendix.md           — names, resources, action plan, key ideas
#
# Quality checks, contract enforcement, and deterministic appendix generation
# are owned by scripts/notes-runner. This shell script stays focused on
# compatibility, markdown assembly, and HTML rendering.

set -euo pipefail

WORK_DIR="${1:?Usage: assemble.sh <work_dir> <output_md> <output_html> <title>}"
OUTPUT_MD="${2:?Missing output markdown path}"
OUTPUT_HTML="${3:?Missing output HTML path}"
TITLE="${4:?Missing title}"

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
CSS_FILE="$SCRIPT_DIR/dark-theme.css"
TEMPLATE="$SCRIPT_DIR/template.html"
RUNNER_BIN="$SCRIPT_DIR/scripts/notes-runner"

build_deterministic_appendix() {
  if [[ -f "$WORK_DIR/appendix.md" ]]; then
    return 0
  fi

  if [[ ! -x "$RUNNER_BIN" ]]; then
    echo "WARNING: notes-runner not found — skipping deterministic appendix generation"
    return 0
  fi

  echo "No appendix.md found — generating deterministic appendix via notes-runner"
  "$RUNNER_BIN" ensure-appendix "$WORK_DIR" >/dev/null
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

# ─── Step 2: Ensure manifests / appendix ───

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

# ─── Step 3: Assemble Markdown with block renumbering ───

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

# ─── Step 4: Convert to HTML via pandoc ───

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

# ─── Summary ───

echo ""
echo "=== Done ==="
echo "Markdown: $OUTPUT_MD ($MD_SIZE bytes, $MD_LINES lines)"
echo "HTML:     $OUTPUT_HTML ($HTML_SIZE bytes)"
echo "Blocks:   $BLOCK_COUNT"
