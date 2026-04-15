#!/usr/bin/env bash
# test-pipeline.sh — Notes skill stress test
# Usage: bash test-pipeline.sh [--quick|--full]
#   --quick  Deterministic tests only (no API, no LLM) ~90s
#   --full   + API tests (Groq, yt-dlp) ~5 min
set -uo pipefail

SKILL_DIR="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$SKILL_DIR/scripts/notes-runner"
FIXTURES="$SKILL_DIR/test-fixtures"
UV_CACHE_DIR="${UV_CACHE_DIR:-/tmp/notes-uv-cache}"
mkdir -p "$UV_CACHE_DIR"
PYTHON_MODE="system"

if command -v uv > /dev/null 2>&1; then
  if UV_CACHE_DIR="$UV_CACHE_DIR" uv run python -c "import json" >/dev/null 2>&1; then
    PYTHON_MODE="uv"
  fi
fi

run_py() {
  if [[ "$PYTHON_MODE" == "uv" ]]; then
    UV_CACHE_DIR="$UV_CACHE_DIR" uv run python "$@"
  else
    python3 "$@"
  fi
}

run_runner() {
  run_py "$RUNNER" "$@"
}

RUN_CMD="run_runner"

# Known-good bundles
BUNDLE_SHORT="$HOME/Downloads/конспекты/gjpEwA5zky4-you-need-to-work-100x-harder"
BUNDLE_MEDIUM="$HOME/Downloads/конспекты/-5DylM1EdI4-7-insane-use-cases-for-manus-ai-with-zero-code"
BUNDLE_LONG="$HOME/Downloads/конспекты/2026-03-27-2630926a"

# ── Colors & counters ───────────────────────────────────────────────────────
GREEN='\033[0;32m'; RED='\033[0;31m'; YELLOW='\033[0;33m'; BOLD='\033[1m'; RESET='\033[0m'
PASS_COUNT=0; FAIL_COUNT=0; SKIP_COUNT=0
TMPDIRS=()

# ── Harness ─────────────────────────────────────────────────────────────────
mk_tmpdir() {
  local d
  d=$(/usr/bin/mktemp -d /tmp/notes-test-XXXXXX)
  TMPDIRS+=("$d")
  echo "$d"
}

# Disable Telegram delivery during tests by temporarily hiding config.json
disable_telegram() {
  if [[ -f "$SKILL_DIR/config.json" ]]; then
    /bin/mv "$SKILL_DIR/config.json" "$SKILL_DIR/config.json.test-backup"
    TELEGRAM_DISABLED=1
  fi
}

restore_telegram() {
  if [[ "${TELEGRAM_DISABLED:-0}" == "1" && -f "$SKILL_DIR/config.json.test-backup" ]]; then
    /bin/mv "$SKILL_DIR/config.json.test-backup" "$SKILL_DIR/config.json"
    TELEGRAM_DISABLED=0
  fi
}

cleanup() {
  restore_telegram
  for d in "${TMPDIRS[@]}"; do
    rm -rf "$d" 2>/dev/null || true
  done
}
trap cleanup EXIT

pass() { echo -e "  ${GREEN}PASS${RESET}  $1"; PASS_COUNT=$((PASS_COUNT + 1)); }
fail() { echo -e "  ${RED}FAIL${RESET}  $1 — $2"; FAIL_COUNT=$((FAIL_COUNT + 1)); }
skip() { echo -e "  ${YELLOW}SKIP${RESET}  $1 — $2"; SKIP_COUNT=$((SKIP_COUNT + 1)); }

# JSON assertion helper: json_check <file> <python_expr> <desc>
# The python expr has access to variable `d` (parsed JSON)
json_check() {
  local file="$1" expr="$2" desc="$3"
  if ! run_py -c "
import json, sys
d = json.load(open('$file'))
assert $expr, 'Assertion failed: $desc'
" 2>/dev/null; then
    return 1
  fi
  return 0
}

copy_fixture() {
  local src="$1"
  local dst
  dst=$(mk_tmpdir)
  /bin/cp -r "$src/." "$dst/"
  echo "$dst"
}

# ── T01: prepare short transcript (75 lines, 1 chunk) ──────────────────────
test_prepare_short() {
  echo -e "${BOLD}T01: prepare short transcript (75 lines)${RESET}"
  local transcript="$BUNDLE_SHORT/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T01" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T01" "notes-runner exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('prepare',{}).get('total_chunks') == 1" "total_chunks==1" || errors+="total_chunks!=1; "
  json_check "$json_out" "d.get('prepare',{}).get('stage_hints',{}).get('speaker_identification') == 'skip'" "speaker_stage==skip" || errors+="speaker_stage!=skip; "
  json_check "$json_out" "'bundle_dir' in d" "has bundle_dir" || errors+="no bundle_dir; "
  json_check "$json_out" "'transcript_path' in d" "has transcript_path" || errors+="no transcript_path; "
  json_check "$json_out" "d.get('execution_plan',{}).get('mode') == 'single'" "execution_plan.mode==single" || errors+="execution_plan.mode!=single; "
  json_check "$json_out" "d.get('execution_plan',{}).get('extraction',{}).get('inline_tldr') is True" "single path inline_tldr" || errors+="execution_plan.inline_tldr!=true; "
  json_check "$json_out" "d.get('execution_plan',{}).get('speaker_identification',{}).get('should_run') is False" "speaker id skipped in single mode" || errors+="execution_plan speaker-id mismatch; "
  json_check "$json_out" "bool(d.get('prepare',{}).get('prompt_packs',{}).get('extract',{}).get('A'))" "prompt pack for chunk A" || errors+="missing chunk prompt pack; "
  json_check "$json_out" "bool(d.get('execution_plan',{}).get('title_header',{}).get('header_seed_path'))" "header seed path present" || errors+="missing header seed path; "
  json_check "$json_out" "bool(d.get('prepare',{}).get('chunk_plan',[{}])[0].get('chunk_fingerprint'))" "chunk fingerprint present" || errors+="missing chunk fingerprint; "

  local work_dir
  work_dir=$(run_py -c "import json; print(json.load(open('$json_out')).get('prepare',{}).get('work_dir',''))" 2>/dev/null)
  if [[ -z "$work_dir" || ! -d "$work_dir" ]]; then
    errors+="work_dir missing; "
  else
    [[ -f "$work_dir/prepare_state.json" ]] || errors+="no prepare_state.json; "
    [[ -f "$work_dir/prescan_context.txt" ]] || errors+="no prescan_context.txt; "
    [[ -f "$work_dir/prepare_report.txt" ]] || errors+="no prepare_report.txt; "
    [[ -f "$work_dir/prompts/extract-A.md" ]] || errors+="no extract-A prompt; "
    [[ -f "$work_dir/prompts/header.md" ]] || errors+="no header prompt; "
    if [[ -f "$work_dir/prompts/extract-A.md" ]]; then
      grep -q '### Практический смысл' "$work_dir/prompts/extract-A.md" || errors+="extract prompt missing practical meaning section; "
      grep -q 'conclusion-style title' "$work_dir/prompts/extract-A.md" || errors+="extract prompt missing conclusion-style title rule; "
    fi
    if [[ -f "$work_dir/prompts/header.md" ]]; then
      grep -q '\*\*Формат:\*\*' "$work_dir/prompts/header.md" || errors+="header prompt missing format line; "
      grep -q '## Главная рамка автора' "$work_dir/prompts/header.md" || errors+="header prompt missing author frame section; "
    fi
  fi

  if [[ -z "$errors" ]]; then pass "T01"; else fail "T01" "$errors"; fi
}

# ── T02: prepare medium transcript (643 lines, multi-chunk) ────────────────
test_prepare_medium() {
  echo -e "${BOLD}T02: prepare medium transcript (643 lines, expect 2+ chunks)${RESET}"
  local transcript="$BUNDLE_MEDIUM/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T02" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T02" "notes-runner exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('prepare',{}).get('total_chunks', 0) >= 2" "total_chunks>=2" || errors+="total_chunks<2; "
  json_check "$json_out" "len(d.get('prepare',{}).get('chunk_plan',[])) >= 2" "chunk_plan has 2+ entries" || errors+="chunk_plan<2; "
  json_check "$json_out" "d.get('execution_plan',{}).get('mode') == 'micro-multi'" "execution_plan.mode==micro-multi" || errors+="execution_plan.mode!=micro-multi; "
  json_check "$json_out" "len(d.get('execution_plan',{}).get('extraction',{}).get('chunks_to_extract',[])) >= 2" "execution_plan has chunks to extract" || errors+="execution_plan chunks missing; "
  json_check "$json_out" "d.get('execution_plan',{}).get('tldr',{}).get('should_run') is False" "tldr deferred until extraction is ready" || errors+="execution_plan.tldr.should_run!=false; "
  json_check "$json_out" "d.get('execution_plan',{}).get('tldr',{}).get('strategy') == 'deterministic-merge'" "micro-multi uses deterministic tldr" || errors+="wrong tldr strategy; "
  json_check "$json_out" "bool(d.get('execution_plan',{}).get('prompt_packs',{}).get('tldr_deterministic'))" "deterministic tldr prompt pack present" || errors+="missing deterministic tldr prompt; "

  if [[ -z "$errors" ]]; then pass "T02"; else fail "T02" "$errors"; fi
}

# ── T03: prepare long transcript (3221 lines, multi-speaker) ───────────────
test_prepare_long() {
  echo -e "${BOLD}T03: prepare long transcript (3221 lines, expect 3+ chunks)${RESET}"
  local transcript="$BUNDLE_LONG/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T03" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T03" "notes-runner exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('prepare',{}).get('total_chunks', 0) >= 3" "total_chunks>=3" || errors+="total_chunks<3; "
  json_check "$json_out" "d.get('execution_plan',{}).get('mode') == 'multi'" "execution_plan.mode==multi" || errors+="execution_plan.mode!=multi; "
  json_check "$json_out" "bool(d.get('execution_plan',{}).get('prompt_packs',{}).get('speaker_identification'))" "speaker prompt pack present" || errors+="missing speaker prompt pack; "
  json_check "$json_out" "bool(d.get('execution_plan',{}).get('prompt_packs',{}).get('tldr_agent'))" "agent tldr prompt pack present" || errors+="missing agent tldr prompt; "

  if [[ -z "$errors" ]]; then pass "T03"; else fail "T03" "$errors"; fi
}

# ── T03b: long sparse transcript should not over-split ────────────────────
test_prepare_long_not_oversplit() {
  echo -e "${BOLD}T03b: long transcript avoids excessive chunk fan-out${RESET}"
  local transcript="$BUNDLE_LONG/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T03b" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T03b" "notes-runner exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('prepare',{}).get('total_chunks') == 5" "total_chunks==5" || errors+="total_chunks!=5; "

  if [[ -z "$errors" ]]; then pass "T03b"; else fail "T03b" "$errors"; fi
}

# ── T04: status on fresh prepare dir ───────────────────────────────────────
test_status_fresh() {
  echo -e "${BOLD}T04: status on fresh prepare dir${RESET}"
  local transcript="$BUNDLE_SHORT/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T04" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local prep_json="$tmpout/prep.json"
  local output_root="$tmpout/output-root"
  $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$prep_json" 2>/dev/null || true

  local work_dir
  work_dir=$(run_py -c "import json; print(json.load(open('$prep_json')).get('prepare',{}).get('work_dir',''))" 2>/dev/null)
  if [[ -z "$work_dir" ]]; then fail "T04" "no work_dir from prepare"; return; fi

  local status_json="$tmpout/status.json"
  if ! $RUN_CMD status "$work_dir" --json > "$status_json" 2>/dev/null; then
    fail "T04" "status command failed"; return
  fi

  local errors=""
  json_check "$status_json" "d.get('next_action') == 'extract-chunks'" "next_action==extract-chunks" || errors+="wrong next_action; "
  json_check "$status_json" "d.get('exists',{}).get('prepare_state') == True" "prepare_state exists" || errors+="no prepare_state; "
  json_check "$status_json" "d.get('exists',{}).get('prescan_context') == True" "prescan_context exists" || errors+="no prescan_context; "
  json_check "$status_json" "d.get('execution_plan',{}).get('mode') == 'single'" "status execution_plan.mode==single" || errors+="status execution_plan.mode!=single; "
  json_check "$status_json" "d.get('execution_plan',{}).get('assemble',{}).get('blocked_by') == ['extraction']" "assemble blocked by extraction" || errors+="status assemble.blocked_by mismatch; "

  if [[ -z "$errors" ]]; then pass "T04"; else fail "T04" "$errors"; fi
}

# ── T04b: repeated prepare reuses existing work dir ───────────────────────
test_prepare_reuse() {
  echo -e "${BOLD}T04b: repeated prepare reuses existing work dir${RESET}"
  local transcript="$BUNDLE_SHORT/transcript.md"
  if [[ ! -f "$transcript" ]]; then skip "T04b" "transcript not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local output_root="$tmpout/output-root"
  local first_json="$tmpout/first.json"
  local second_json="$tmpout/second.json"

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$first_json" 2>/dev/null; then
    fail "T04b" "first prepare exited non-zero"; return
  fi
  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$second_json" 2>/dev/null; then
    fail "T04b" "second prepare exited non-zero"; return
  fi

  local first_work_dir
  first_work_dir=$(run_py -c "import json; print(json.load(open('$first_json')).get('prepare',{}).get('work_dir',''))" 2>/dev/null)
  local second_work_dir
  second_work_dir=$(run_py -c "import json; print(json.load(open('$second_json')).get('prepare',{}).get('work_dir',''))" 2>/dev/null)
  local first_real=""
  local second_real=""
  if [[ -n "$first_work_dir" ]]; then first_real=$(python3 - <<PY
from pathlib import Path
print(Path("$first_work_dir").resolve())
PY
); fi
  if [[ -n "$second_work_dir" ]]; then second_real=$(python3 - <<PY
from pathlib import Path
print(Path("$second_work_dir").resolve())
PY
); fi

  local errors=""
  [[ -n "$first_work_dir" ]] || errors+="first work_dir missing; "
  [[ -n "$second_work_dir" ]] || errors+="second work_dir missing; "
  [[ "$first_real" == "$second_real" ]] || errors+="work_dir not reused; "
  json_check "$second_json" "d.get('prepare',{}).get('reused') == True" "prepare reused" || errors+="prepare.reused!=true; "
  json_check "$second_json" "isinstance(d.get('status'), dict)" "status present" || errors+="status missing; "
  json_check "$second_json" "d.get('status',{}).get('work_dir') == d.get('prepare',{}).get('work_dir')" "status/work_dir aligned" || errors+="status work_dir mismatch; "
  json_check "$second_json" "d.get('execution_plan',{}).get('resume') == True" "execution_plan resume" || errors+="execution_plan.resume!=true; "

  if [[ -z "$errors" ]]; then pass "T04b"; else fail "T04b" "$errors"; fi
}

# ── T04c: local title normalization should avoid noisy transcript stems ────
test_local_title_normalization() {
  echo -e "${BOLD}T04c: local title normalization prefers clean parent hint over noisy transcript line${RESET}"

  local tmpout
  tmpout=$(mk_tmpdir)
  local source_dir="$tmpout/deep-learning-intro"
  mkdir -p "$source_dir"
  local transcript="$source_dir/transcript.md"
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  cat > "$transcript" << 'TRANSCRIPT'
*00:00* **Speaker 1**: привет всем, сегодня разбираем основы глубинного обучения
*00:15* **Speaker 1**: начнем с базовых понятий и практических примеров
TRANSCRIPT

  if ! $RUN_CMD local "$transcript" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T04c" "notes-runner exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('title') == 'Deep learning intro'" "title normalized from parent hint" || errors+="title not normalized; "
  json_check "$json_out" "'*00:00*' not in d.get('title','') and 'Speaker 1' not in d.get('title','')" "title stripped of transcript noise" || errors+="title still noisy; "

  if [[ -z "$errors" ]]; then pass "T04c"; else fail "T04c" "$errors"; fi
}

# ── T04d: prepare should preserve YouTube author hints in header seed ─────
test_prepare_source_hints() {
  echo -e "${BOLD}T04d: prepare carries YouTube author hints into header seed and execution plan${RESET}"

  local tmpout
  tmpout=$(mk_tmpdir)
  local transcript="$tmpout/transcript.md"
  cat > "$transcript" << 'TRANSCRIPT'
*00:00* alright, so you guys can probably hear from my voice that i'm sick
*00:10* i still got up and started working this morning
TRANSCRIPT

  if ! python3 - <<PY >/dev/null 2>&1
import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

runner_path = Path("$RUNNER")
loader = importlib.machinery.SourceFileLoader("notes_runner", str(runner_path))
spec = importlib.util.spec_from_loader("notes_runner", loader)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

source_hints = module.build_youtube_source_hints({
    "id": "7qq5zNqA3Wk",
    "title": "you settled for a 9-5 but you know you're capable of more",
    "channel": "Haroon Khan",
    "uploader": "Haroon Khan",
    "uploader_id": "@HaroonKhaans",
})
result = module.run_prepare_logic([Path("$transcript")], source_hints=source_hints)
work_dir = Path(result["work_dir"])
header_seed = json.loads((work_dir / "header-seed.json").read_text(encoding="utf-8"))
plan = json.loads((work_dir / "prepare_plan.json").read_text(encoding="utf-8"))
prescan = (work_dir / "prescan_context.txt").read_text(encoding="utf-8")

assert header_seed["author_hint"] == "Haroon Khan"
assert "Haroon Khan" in header_seed.get("speaker_candidates", [])
assert "Haroon Khan" in prescan
assert plan.get("header_seed", {}).get("author_hint") == "Haroon Khan"
PY
  then
    fail "T04d" "prepare/source hints regression"; return
  fi

  pass "T04d"
}

# ── T05: status on completed work dir ──────────────────────────────────────
test_status_complete() {
  echo -e "${BOLD}T05: status on completed work dir (single-chunk fixture)${RESET}"
  if [[ ! -d "$FIXTURES/single-chunk" ]]; then skip "T05" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/single-chunk")
  local status_json="$work_dir/status_out.json"

  if ! $RUN_CMD status "$work_dir" --json > "$status_json" 2>/dev/null; then
    fail "T05" "status command failed"; return
  fi

  local errors=""
  # Check chunk-level status (chunk A should be ready since block files exist)
  json_check "$status_json" "all(v.get('status')=='ready' for v in d.get('chunk_statuses',{}).values())" "all chunks ready" || errors+="chunks not ready; "
  json_check "$status_json" "d.get('exists',{}).get('tldr') == True" "tldr exists" || errors+="no tldr; "
  json_check "$status_json" "d.get('exists',{}).get('header') == True" "header exists" || errors+="no header; "

  if [[ -z "$errors" ]]; then pass "T05"; else fail "T05" "$errors"; fi
}

# ── T05b: deterministic TL;DR merge for micro-multi flows ─────────────────
test_build_tldr_deterministic() {
  echo -e "${BOLD}T05b: build-tldr deterministically merges summary chunks${RESET}"
  if [[ ! -d "$FIXTURES/multi-chunk" ]]; then skip "T05b" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/multi-chunk")
  rm -f "$work_dir/tldr.md"
  local state_path="$work_dir/prepare_state.json"
  python3 - <<PY >/dev/null
import json
from pathlib import Path
path = Path("$state_path")
payload = json.loads(path.read_text())
payload["fingerprint"] = payload.get("fingerprint") or "fixture-fingerprint"
payload["execution_mode"] = "micro-multi"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

  local json_out="$work_dir/tldr-result.json"
  if ! $RUN_CMD build-tldr "$work_dir" --json > "$json_out" 2>/dev/null; then
    fail "T05b" "build-tldr exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "d.get('strategy') == 'deterministic-merge'" "deterministic tldr strategy" || errors+="wrong tldr strategy; "
  json_check "$json_out" "d.get('takeaways', 0) >= 4" "has enough takeaways" || errors+="too few takeaways; "
  [[ -f "$work_dir/tldr.md" ]] || errors+="no tldr.md; "
  [[ -f "$work_dir/stages/tldr.json" ]] || errors+="no tldr sentinel; "

  if [[ -f "$work_dir/tldr.md" ]]; then
    grep -q '^1\. ' "$work_dir/tldr.md" || errors+="tldr not numbered; "
  fi

  if [[ -z "$errors" ]]; then pass "T05b"; else fail "T05b" "$errors"; fi
}

# ── T05c: status should trust ready chunk files over stale prepare state ───
test_status_prefers_observed_ready_chunks() {
  echo -e "${BOLD}T05c: status prefers observed ready chunks over stale extraction flag${RESET}"
  if [[ ! -d "$FIXTURES/multi-chunk" ]]; then skip "T05c" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/multi-chunk")
  python3 - <<PY >/dev/null
import json
from pathlib import Path

path = Path("$work_dir/prepare_state.json")
payload = json.loads(path.read_text())
payload.setdefault("stage_statuses", {})
payload["stage_statuses"]["extraction"] = "missing"
path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
PY

  local status_json="$work_dir/status_out.json"
  if ! $RUN_CMD status "$work_dir" --json > "$status_json" 2>/dev/null; then
    fail "T05c" "status command failed"; return
  fi

  local errors=""
  json_check "$status_json" "d.get('stages',{}).get('extraction',{}).get('status') == 'ready'" "observed extraction ready" || errors+="extraction status not ready; "
  json_check "$status_json" "d.get('execution_plan',{}).get('extraction',{}).get('should_run') is False" "no redundant extraction rerun" || errors+="extraction rerun still requested; "

  if [[ -z "$errors" ]]; then pass "T05c"; else fail "T05c" "$errors"; fi
}

# ── T06: replace-speakers basic ────────────────────────────────────────────
test_replace_basic() {
  echo -e "${BOLD}T06: replace-speakers basic substitution${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  # Create speakers.txt
  printf 'Speaker 1 → Иван\nSpeaker 2 → Мария\n' > "$work_dir/speakers.txt"

  # Create block file with speaker markers
  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
---
block_id: A_01
timestamp_start: "00:00"
timestamp_end: "05:00"
topic: "Test topic"
---

## Test topic (00:00–05:00)

### Тезисы:
1. **Speaker 1** говорит о важности тестов *(00:01)*
2. **Speaker 2** соглашается с этим *(00:03)*
BLOCK

  if ! $RUN_CMD replace-speakers "$work_dir" > /dev/null 2>&1; then
    fail "T06" "replace-speakers exited non-zero"; return
  fi

  local content
  content=$(cat "$work_dir/chunk_A_block_01.md")
  local errors=""
  echo "$content" | grep -qF '**Иван**' || errors+="no Иван; "
  echo "$content" | grep -qF '**Мария**' || errors+="no Мария; "
  echo "$content" | grep -qF 'Speaker 1' && errors+="Speaker 1 still present; "
  echo "$content" | grep -qF 'Speaker 2' && errors+="Speaker 2 still present; "

  if [[ -z "$errors" ]]; then pass "T06"; else fail "T06" "$errors"; fi
}

# ── T07: replace-speakers collision (Speaker 1 vs 10 vs 11) ───────────────
test_replace_collision() {
  echo -e "${BOLD}T07: replace-speakers Speaker 1/10/11 collision${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  # Mappings — Speaker 10 and 11 must be replaced BEFORE Speaker 1
  printf 'Speaker 1 → Первый\nSpeaker 10 → Десятый\nSpeaker 11 → Одиннадцатый\n' > "$work_dir/speakers.txt"

  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
---
block_id: A_01
timestamp_start: "00:00"
timestamp_end: "10:00"
topic: "Collision test"
---

## Collision test (00:00–10:00)

### Тезисы:
1. **Speaker 1** начинает дискуссию *(00:01)*
2. **Speaker 10** отвечает на вопрос *(03:00)*
3. **Speaker 11** подводит итоги *(07:00)*
4. Speaker 1 снова берёт слово *(09:00)*
5. Speaker 10 завершает *(09:30)*
BLOCK

  if ! $RUN_CMD replace-speakers "$work_dir" > /dev/null 2>&1; then
    fail "T07" "replace-speakers exited non-zero"; return
  fi

  local content
  content=$(cat "$work_dir/chunk_A_block_01.md")
  local errors=""

  # Check correct replacements
  echo "$content" | grep -qF '**Первый**' || errors+="no Первый; "
  echo "$content" | grep -qF '**Десятый**' || errors+="no Десятый; "
  echo "$content" | grep -qF '**Одиннадцатый**' || errors+="no Одиннадцатый; "

  # Check NO collision artifacts
  echo "$content" | grep -qF 'Первый0' && errors+="COLLISION: Первый0 found; "
  echo "$content" | grep -qF 'Первый1' && errors+="COLLISION: Первый1 found; "

  # Check originals are gone
  echo "$content" | grep -qF 'Speaker 10' && errors+="Speaker 10 still present; "
  echo "$content" | grep -qF 'Speaker 11' && errors+="Speaker 11 still present; "

  if [[ -z "$errors" ]]; then pass "T07"; else fail "T07" "$errors"; fi
}

# ── T08: replace-speakers no speakers.txt ──────────────────────────────────
test_replace_no_speakers() {
  echo -e "${BOLD}T08: replace-speakers with no speakers.txt${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  # Create a block file but NO speakers.txt
  echo "## Some block" > "$work_dir/chunk_A_block_01.md"

  local output
  output=$($RUN_CMD replace-speakers "$work_dir" 2>&1) || true

  # Should not crash — just skip gracefully
  local errors=""
  # Exit code 0 is fine, or non-zero with graceful message
  echo "$output" | grep -qi 'skip\|no speakers\|nothing' || errors+="no skip message; "

  if [[ -z "$errors" ]]; then pass "T08"; else fail "T08" "$errors"; fi
}

# ── T09: assemble single-chunk ─────────────────────────────────────────────
test_assemble_single() {
  echo -e "${BOLD}T09: assemble single-chunk fixture${RESET}"
  if [[ ! -d "$FIXTURES/single-chunk" ]]; then skip "T09" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/single-chunk")
  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "Test Single Chunk" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T09" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "
  [[ -f "$out_html" ]] || errors+="no HTML output; "

  if [[ -f "$out_md" ]]; then
    local md_lines
    md_lines=$(wc -l < "$out_md")
    (( md_lines > 20 )) || errors+="MD too short ($md_lines lines); "
    grep -q 'Коротко о главном' "$out_md" || errors+="no TL;DR section; "
    grep -q 'Упомянутые' "$out_md" || errors+="no appendix section; "
  fi

  if [[ -f "$out_html" ]]; then
    grep -q '<html' "$out_html" || errors+="invalid HTML; "
    grep -q 'Test Single Chunk' "$out_html" || errors+="title not in HTML; "
  fi

  if [[ -z "$errors" ]]; then pass "T09"; else fail "T09" "$errors"; fi
}

# ── T10: assemble multi-chunk ──────────────────────────────────────────────
test_assemble_multi() {
  echo -e "${BOLD}T10: assemble multi-chunk fixture (2 chunks, 4 blocks)${RESET}"
  if [[ ! -d "$FIXTURES/multi-chunk" ]]; then skip "T10" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/multi-chunk")
  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "Test Multi Chunk" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T10" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "
  [[ -f "$out_html" ]] || errors+="no HTML output; "

  if [[ -f "$out_md" ]]; then
    local h2_count
    h2_count=$(grep -c '^## ' "$out_md" || true)
    (( h2_count >= 4 )) || errors+="expected 4+ h2 headings, got $h2_count; "

    # Check blocks from both chunks are present
    local md_lines
    md_lines=$(wc -l < "$out_md")
    (( md_lines > 50 )) || errors+="MD too short ($md_lines lines); "
  fi

  if [[ -z "$errors" ]]; then pass "T10"; else fail "T10" "$errors"; fi
}

# ── T11: assemble with no-frontmatter blocks ──────────────────────────────
test_assemble_no_frontmatter() {
  echo -e "${BOLD}T11: assemble with block files missing YAML frontmatter${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  # Minimal header and tldr
  echo "# Test (полный конспект)" > "$work_dir/header.md"
  printf '1. Первый тезис\n2. Второй тезис\n' > "$work_dir/tldr.md"

  # Block WITHOUT frontmatter
  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
## Test Block (00:00–05:00)

### Тезисы:
1. First thesis *(00:01)*
2. Second thesis *(02:30)*
BLOCK

  # Minimal manifest
  printf 'block_file\ttimestamp_start\ttimestamp_end\ttopic\tnames\tresources\tquotes_count\tcases\n' > "$work_dir/manifest_chunk_A.tsv"
  printf 'chunk_A_block_01.md\t00:00\t05:00\tTest Block\t\t\t0\t\n' >> "$work_dir/manifest_chunk_A.tsv"

  # Minimal prepare_state.json
  echo '{"total_chunks":1,"chunk_plan":[{"chunk_id":"A"}]}' > "$work_dir/prepare_state.json"

  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"
  local stderr_log="$tmpout/stderr.log"

  $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "No Frontmatter Test" --json > "$tmpout/result.json" 2>"$stderr_log"
  local exit_code=$?

  local errors=""
  (( exit_code == 0 )) || errors+="exit code $exit_code; "
  [[ -f "$out_md" ]] || errors+="no MD output; "

  if [[ -f "$out_md" ]]; then
    grep -q 'Test Block' "$out_md" || errors+="block content missing from MD; "
  fi

  # Note: frontmatter warning goes to stderr inside assemble.sh but may be captured by notes-runner
  # The key assertion is that block content appears in the MD output (tested above)

  if [[ -z "$errors" ]]; then pass "T11"; else fail "T11" "$errors"; fi
}

# ── T12: assemble with missing manifest ────────────────────────────────────
test_assemble_no_manifest() {
  echo -e "${BOLD}T12: assemble with no manifest files${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  echo "# Test (полный конспект)" > "$work_dir/header.md"
  printf '1. Тезис без манифеста\n' > "$work_dir/tldr.md"

  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
---
block_id: A_01
timestamp_start: "00:00"
timestamp_end: "03:00"
topic: "No manifest test"
---

## No manifest test (00:00–03:00)

### Тезисы:
1. Test thesis *(00:01)*
BLOCK

  echo '{"total_chunks":1,"chunk_plan":[{"chunk_id":"A"}]}' > "$work_dir/prepare_state.json"

  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "No Manifest Test" --json > "$tmpout/result.json" 2>/dev/null
  local exit_code=$?

  local errors=""
  (( exit_code == 0 )) || errors+="exit code $exit_code; "
  [[ -f "$out_md" ]] || errors+="no MD output; "

  if [[ -f "$out_md" ]]; then
    grep -q '# Упомянутые люди и ресурсы' "$out_md" || errors+="no combined people/resources section; "
    grep -q 'не были явно извлечены из материалов' "$out_md" || errors+="no fallback text in appendix; "
  fi

  if [[ -z "$errors" ]]; then pass "T12"; else fail "T12" "$errors"; fi
}

# ── T12b: deterministic appendix must not invent action plan ──────────────
test_appendix_no_invented_actions() {
  echo -e "${BOLD}T12b: deterministic appendix omits action plan when summaries contain no actions${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  echo "# Test (полный конспект)" > "$work_dir/header.md"
  printf '1. Основная тема и контекст.\n' > "$work_dir/tldr.md"

  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
---
block_id: A_01
timestamp_start: "00:00"
timestamp_end: "04:00"
topic: "Введение"
---

## Блок | 00:00–04:00 | Введение

### Тезисы:
1. Это обзор темы. *(00:00)*
2. Здесь описывается контекст. *(00:40)*
3. Объясняется терминология. *(01:20)*
4. Дается рамка обсуждения. *(02:00)*
5. Уточняются ограничения. *(02:40)*
6. Формулируется итог блока. *(03:20)*
BLOCK

  printf 'block_file\ttimestamp_start\ttimestamp_end\ttopic\tnames\tresources\tquotes_count\tcases\n' > "$work_dir/manifest_chunk_A.tsv"
  printf 'chunk_A_block_01.md\t00:00\t04:00\tВведение\tИван\tpandoc\t0\t0\n' >> "$work_dir/manifest_chunk_A.tsv"

  cat > "$work_dir/summary_chunk_A.md" << 'SUMMARY'
1. Вводится основная тема и контекст разговора.
2. Объясняются ключевые термины и рамка обсуждения.
3. Уточняются ограничения и базовые допущения.
SUMMARY

  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "No Actions Test" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T12b" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "

  if [[ -f "$out_md" ]]; then
    grep -q '# Упомянутые люди и ресурсы' "$out_md" || errors+="no people/resources section; "
    grep -q '# План действий' "$out_md" && errors+="invented action plan section present; "
    grep -q 'Автоматизировать повторяющиеся' "$out_md" && errors+="legacy boilerplate action present; "
    grep -q 'Стабилизировать chunk plan' "$out_md" && errors+="legacy chunk-plan action present; "
    grep -q 'Секция собрана детерминированно' "$out_md" && errors+="technical deterministic footer present; "
    grep -q 'Конспект составлен на основе транскриптов' "$out_md" && errors+="technical transcript footer present; "
  fi

  if [[ -z "$errors" ]]; then pass "T12b"; else fail "T12b" "$errors"; fi
}

# ── T12ba: deterministic appendix supports current manifest schema ────────
test_appendix_current_manifest_schema() {
  echo -e "${BOLD}T12ba: deterministic appendix uses current manifest schema and source author hints${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  echo "# Haroon Khan — тест" > "$work_dir/header.md"
  printf '1. Короткий вывод.\n' > "$work_dir/tldr.md"
  cat > "$work_dir/header-seed.json" << 'JSON'
{
  "author_hint": "Haroon Khan",
  "speaker_candidates": ["Haroon Khan"]
}
JSON

  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
# Блок 1: Осознание несоответствия — сравнение себя с другими

- *(11:03)* Необходимо начать смотреть на свою ситуацию трезво и замечать, что реальность не совпадает с тем, кем ты себя считаешь.
- *(12:13)* Наблюдение за чужим успехом должно не угнетать, а мотивировать к действию.
- *(15:43)* Выбор из двух путей: оставаться в рабстве у нелюбимой работы — или сказать «всё, хватит» и действовать.
BLOCK

  printf 'block_file\ttitle\tstart_time\tend_time\n' > "$work_dir/manifest_chunk_A.tsv"
  printf 'chunk_A_block_01.md\tОсознание несоответствия — сравнение себя с другими\t10:51\t15:43\n' >> "$work_dir/manifest_chunk_A.tsv"

  cat > "$work_dir/summary_chunk_A.md" << 'SUMMARY'
1. Необходимо начать смотреть на свою ситуацию трезво.
2. Наблюдение за чужим успехом должно мотивировать к действию.
3. Нужно выбрать действие вместо смирения.
SUMMARY

  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "Appendix Schema Test" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T12ba" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "
  if [[ -f "$out_md" ]]; then
    grep -q 'Haroon Khan' "$out_md" || errors+="author hint missing from appendix; "
    grep -q '# План действий' "$out_md" || errors+="no action plan section; "
    grep -q 'Необходимо начать смотреть на свою ситуацию трезво' "$out_md" || errors+="missing immediate action; "
    grep -q 'Осознание несоответствия — сравнение себя с другими' "$out_md" || errors+="topic table did not use current manifest title; "
    grep -q '# Упомянутые люди и ресурсы' "$out_md" || errors+="missing combined people/resources section; "
    grep -q '### На этой неделе' "$out_md" || errors+="missing weekly action bucket; "
    grep -q 'Секция собрана детерминированно' "$out_md" && errors+="technical deterministic footer present; "
  fi

  if [[ -z "$errors" ]]; then pass "T12ba"; else fail "T12ba" "$errors"; fi
}

# ── T12bb: deterministic appendix extracts actions from numbered theses ───
test_appendix_numbered_theses_actions() {
  echo -e "${BOLD}T12bb: deterministic appendix derives multiple actions from numbered theses${RESET}"
  local work_dir
  work_dir=$(mk_tmpdir)

  echo "# Мечтатель — тест" > "$work_dir/header.md"
  printf '1. Короткий вывод.\n' > "$work_dir/tldr.md"

  cat > "$work_dir/chunk_A_block_01.md" << 'BLOCK'
---
block_id: A_01
timestamp_start: "17:02"
timestamp_end: "22:38"
topic: "Пять вопросов и переход к действию"
---

## Пять вопросов и переход к действию (17:02–22:38)

### Тезисы:
1. Практический метод диагностики: скажи себе «завтра я буду делать только это», зафиксируй первую ответную мысль. *(17:02)*
2. Третий вопрос-провокация: «представь, что завтра ты начинаешь именно этим заниматься» — и заметь первое возражение. *(16:28)*
3. Пятый вопрос-практика: «Что конкретно сегодня или завтра я могу сделать, чтобы вернуть ту самую конфигурацию себя?» *(19:52)*
4. Финальный совет: не сопротивляйся изменениям и не бойся двигаться к образам, в которые страшно поверить. *(22:31)*
BLOCK

  printf 'block_file\ttimestamp_start\ttimestamp_end\ttopic\tnames\tresources\tquotes_count\tcases\n' > "$work_dir/manifest_chunk_A.tsv"
  printf 'chunk_A_block_01.md\t17:02\t22:38\tПять вопросов и переход к действию\tМечтатель\t\t0\t0\n' >> "$work_dir/manifest_chunk_A.tsv"

  cat > "$work_dir/summary_chunk_A.md" << 'SUMMARY'
1. Практический метод диагностики строится вокруг одного конкретного действия на завтра.
2. Первый шаг — заметить и назвать первое возражение, которое всплывает мгновенно.
3. Финальный принцип — не сопротивляться изменениям и не бояться двигаться в сторону пугающих образов.
SUMMARY

  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "Numbered Actions Test" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T12bb" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "
  if [[ -f "$out_md" ]]; then
    grep -q '# План действий' "$out_md" || errors+="no action plan section; "
    grep -q 'скажи себе' "$out_md" || errors+="missing numbered-thesis immediate action; "
    grep -q 'сегодня или завтра я могу сделать' "$out_md" || errors+="missing question-practice action; "
    grep -q 'не сопротивляйся изменениям и не бойся' "$out_md" || errors+="missing ongoing action; "
    grep -q '# Упомянутые люди и ресурсы' "$out_md" || errors+="missing combined people/resources section; "
    grep -q '# Ключевые идеи и модели' "$out_md" || errors+="missing models section; "
    grep -q 'Секция собрана детерминированно' "$out_md" && errors+="technical deterministic footer present; "
    grep -q 'Конспект составлен на основе транскриптов' "$out_md" && errors+="technical transcript footer present; "
  fi

  if [[ -z "$errors" ]]; then pass "T12bb"; else fail "T12bb" "$errors"; fi
}

# ── T12c: assemble skip-telegram should stay successful ───────────────────
test_assemble_skip_telegram() {
  echo -e "${BOLD}T12c: assemble --skip-telegram keeps notes generation deterministic${RESET}"
  if [[ ! -d "$FIXTURES/single-chunk" ]]; then skip "T12c" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/single-chunk")
  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"
  local json_out="$tmpout/result.json"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "Skip Telegram Test" --skip-telegram --json > "$json_out" 2>/dev/null; then
    fail "T12c" "assemble exited non-zero"; return
  fi

  local errors=""
  [[ -f "$out_md" ]] || errors+="no MD output; "
  [[ -f "$out_html" ]] || errors+="no HTML output; "
  json_check "$json_out" "d.get('telegram_delivery',{}).get('attempted') is False" "telegram not attempted" || errors+="telegram attempted; "
  json_check "$json_out" "d.get('telegram_delivery',{}).get('reason') == 'skipped-by-request'" "telegram skipped by request" || errors+="telegram reason mismatch; "

  if [[ -z "$errors" ]]; then pass "T12c"; else fail "T12c" "$errors"; fi
}

# ── T12d: youtube metadata falls back to URL-derived id ───────────────────
test_youtube_metadata_fallback() {
  echo -e "${BOLD}T12d: YouTube metadata falls back to URL-derived video id${RESET}"

  if ! NOTES_RUNNER_YTDLP_BIN=/definitely/missing python3 - <<PY >/dev/null 2>&1
import importlib.machinery
import importlib.util
import sys
from pathlib import Path

runner_path = Path("$RUNNER")
loader = importlib.machinery.SourceFileLoader("notes_runner", str(runner_path))
spec = importlib.util.spec_from_loader("notes_runner", loader)
module = importlib.util.module_from_spec(spec)
assert spec is not None and spec.loader is not None
sys.modules[spec.name] = module
spec.loader.exec_module(module)

payload = module.extract_youtube_metadata("https://www.youtube.com/watch?v=gjpEwA5zky4")
assert payload["id"] == "gjpEwA5zky4"
assert payload["title"] == "gjpEwA5zky4"
assert "_metadata_warning" in payload
PY
  then
    fail "T12d" "URL-derived metadata fallback failed"; return
  fi

  pass "T12d"
}

# ── T13: prepare audio with Cyrillic filename (FULL only) ─────────────────
test_audio_cyrillic() {
  echo -e "${BOLD}T13: prepare audio with Cyrillic filename via Groq${RESET}"
  local audio_file="$HOME/Downloads/ии от сергея иванова 2.m4a"
  if [[ ! -f "$audio_file" ]]; then skip "T13" "audio file not found"; return; fi

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD audio "$audio_file" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T13" "notes-runner audio exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "'bundle_dir' in d" "has bundle_dir" || errors+="no bundle_dir; "
  json_check "$json_out" "'transcript_path' in d" "has transcript_path" || errors+="no transcript_path; "

  local transcript_path
  transcript_path=$(run_py -c "import json; print(json.load(open('$json_out')).get('transcript_path',''))" 2>/dev/null)
  if [[ -n "$transcript_path" && -f "$transcript_path" ]]; then
    local lines
    lines=$(wc -l < "$transcript_path")
    (( lines > 10 )) || errors+="transcript too short ($lines lines); "
  else
    errors+="transcript file missing; "
  fi

  if [[ -z "$errors" ]]; then pass "T13"; else fail "T13" "$errors"; fi
}

# ── T14: youtube short video prepare (FULL only) ──────────────────────────
test_youtube_prepare() {
  echo -e "${BOLD}T14: youtube prepare (4 min video, gjpEwA5zky4)${RESET}"

  local tmpout
  tmpout=$(mk_tmpdir)
  local json_out="$tmpout/result.json"
  local output_root="$tmpout/output-root"

  if ! $RUN_CMD youtube "https://www.youtube.com/watch?v=gjpEwA5zky4" --output-root "$output_root" --prepare --json > "$json_out" 2>/dev/null; then
    fail "T14" "notes-runner youtube exited non-zero"; return
  fi

  local errors=""
  json_check "$json_out" "'bundle_dir' in d" "has bundle_dir" || errors+="no bundle_dir; "
  json_check "$json_out" "d.get('prepare',{}).get('total_chunks') == 1" "total_chunks==1" || errors+="total_chunks!=1; "
  json_check "$json_out" "'transcript_path' in d" "has transcript_path" || errors+="no transcript_path; "

  if [[ -z "$errors" ]]; then pass "T14"; else fail "T14" "$errors"; fi
}

# ── T15: full e2e YouTube short — prepare + assemble (FULL only) ──────────
test_e2e_youtube_short() {
  echo -e "${BOLD}T15: e2e YouTube short (prepare → assemble with existing extraction)${RESET}"

  # Use existing known-good bundle
  if [[ ! -d "$BUNDLE_SHORT/work" ]]; then skip "T15" "no work dir link in bundle"; return; fi

  local work_link
  work_link=$(readlink -f "$BUNDLE_SHORT/work" 2>/dev/null || echo "")
  if [[ -z "$work_link" || ! -d "$work_link" ]]; then
    # Try to find work dir from run.json
    skip "T15" "work dir not resolvable"; return
  fi

  local work_dir
  work_dir=$(copy_fixture "$work_link")
  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "E2E Short Test" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T15" "assemble failed"; return
  fi

  local errors=""
  [[ -f "$out_html" ]] || errors+="no HTML; "
  [[ -f "$out_md" ]] || errors+="no MD; "

  if [[ -f "$out_html" ]]; then
    local html_size
    html_size=$(wc -c < "$out_html")
    (( html_size > 5000 )) || errors+="HTML too small ($html_size bytes); "
  fi

  if [[ -z "$errors" ]]; then pass "T15"; else fail "T15" "$errors"; fi
}

# ── T16: full e2e local text 2 chunks (FULL only) ─────────────────────────
test_e2e_local_multichunk() {
  echo -e "${BOLD}T16: e2e local text multi-chunk (assemble from multi-chunk fixture)${RESET}"
  if [[ ! -d "$FIXTURES/multi-chunk" ]]; then skip "T16" "fixture missing"; return; fi

  local work_dir
  work_dir=$(copy_fixture "$FIXTURES/multi-chunk")
  local tmpout
  tmpout=$(mk_tmpdir)
  local out_md="$tmpout/output.md"
  local out_html="$tmpout/output.html"

  if ! $RUN_CMD assemble "$work_dir" "$out_md" "$out_html" "E2E Multi Chunk" --json > "$tmpout/result.json" 2>/dev/null; then
    fail "T16" "assemble failed"; return
  fi

  local errors=""
  [[ -f "$out_html" ]] || errors+="no HTML; "
  [[ -f "$out_md" ]] || errors+="no MD; "

  if [[ -f "$out_md" ]]; then
    local h2_count
    h2_count=$(grep -c '^## ' "$out_md" || true)
    (( h2_count >= 4 )) || errors+="expected 4+ blocks, got $h2_count; "
  fi

  if [[ -f "$out_html" ]]; then
    grep -q '<nav' "$out_html" || errors+="no TOC nav in HTML; "
  fi

  if [[ -z "$errors" ]]; then pass "T16"; else fail "T16" "$errors"; fi
}

# ── Main ────────────────────────────────────────────────────────────────────
MODE="${1:---quick}"

echo ""
echo -e "${BOLD}Notes Skill Stress Test${RESET}"
echo "Mode: $MODE"
echo "Skill dir: $SKILL_DIR"
echo ""

# Preflight checks
echo -e "${BOLD}Preflight${RESET}"
[[ -f "$RUNNER" ]] && echo "  runner: OK" || { echo "  runner: MISSING"; exit 1; }
if command -v uv > /dev/null 2>&1; then
  echo "  uv: OK"
else
  echo "  uv: MISSING (using system python)"
fi
run_py -c "import json" 2>/dev/null && echo "  python: OK ($PYTHON_MODE)" || { echo "  python: FAIL"; exit 1; }

disable_telegram

echo ""
echo -e "${BOLD}=== Layer 1: Deterministic tests ===${RESET}"
echo ""

test_prepare_short
test_prepare_medium
test_prepare_long
test_prepare_long_not_oversplit
test_status_fresh
test_prepare_reuse
test_local_title_normalization
test_prepare_source_hints
test_status_complete
test_build_tldr_deterministic
test_status_prefers_observed_ready_chunks
test_replace_basic
test_replace_collision
test_replace_no_speakers
test_assemble_single
test_assemble_multi
test_assemble_no_frontmatter
test_assemble_no_manifest
test_appendix_no_invented_actions
test_assemble_skip_telegram
test_appendix_current_manifest_schema
test_appendix_numbered_theses_actions
test_youtube_metadata_fallback

if [[ "$MODE" == "--full" ]]; then
  echo ""
  echo -e "${BOLD}=== Layer 2: API + Integration tests ===${RESET}"
  echo ""

  test_audio_cyrillic
  test_youtube_prepare
  test_e2e_youtube_short
  test_e2e_local_multichunk
fi

echo ""
echo -e "${BOLD}════════════════════════════════════════${RESET}"
echo -e "  ${GREEN}PASS: $PASS_COUNT${RESET}  ${RED}FAIL: $FAIL_COUNT${RESET}  ${YELLOW}SKIP: $SKIP_COUNT${RESET}"
echo -e "${BOLD}════════════════════════════════════════${RESET}"
echo ""

if (( FAIL_COUNT > 0 )); then
  exit 1
else
  exit 0
fi
