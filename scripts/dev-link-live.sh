#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
CODEX_HOME_DIR="${CODEX_HOME:-${HOME}/.codex}"
CODEX_SKILL_DIR="${CODEX_HOME_DIR}/skills/notes"
AGENTS_SKILL_DIR="${HOME}/.agents/skills/notes"
LEGACY_SKILL_DIR="${HOME}/.claude/skills/notes"

choose_live_dir() {
  if [[ -n "${NOTES_LIVE_DIR:-}" ]]; then
    echo "${NOTES_LIVE_DIR}"
    return
  fi
  if [[ -d "$CODEX_SKILL_DIR" ]]; then
    echo "$CODEX_SKILL_DIR"
    return
  fi
  if [[ -d "$AGENTS_SKILL_DIR" ]]; then
    echo "$AGENTS_SKILL_DIR"
    return
  fi
  if [[ -d "$LEGACY_SKILL_DIR" ]]; then
    echo "$LEGACY_SKILL_DIR"
    return
  fi
  echo "$CODEX_SKILL_DIR"
}

TARGET_DIR="$(choose_live_dir)"
SKIP_BACKUP=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --skip-backup)
      SKIP_BACKUP=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ ! -d "$REPO_DIR/.git" ]]; then
  echo "Expected a git checkout at $REPO_DIR" >&2
  exit 1
fi

mkdir -p "$TARGET_DIR" "$TARGET_DIR/backups" "$TARGET_DIR/.ai"

readarray -t MANAGED_ENTRIES < <(
  python3 - <<'PY' "$REPO_DIR"
from pathlib import Path
import sys

root = Path(sys.argv[1])
excluded = {".git", ".ai", "backups", "config.json"}
for path in sorted(root.iterdir(), key=lambda p: p.name.lower()):
    if path.name in excluded:
        continue
    print(path.name)
PY
)

if [[ "$SKIP_BACKUP" -ne 1 ]]; then
  EXISTING_ENTRIES=()
  for entry in "${MANAGED_ENTRIES[@]}"; do
    if [[ -e "$TARGET_DIR/$entry" || -L "$TARGET_DIR/$entry" ]]; then
      EXISTING_ENTRIES+=("$entry")
    fi
  done
  if [[ ${#EXISTING_ENTRIES[@]} -gt 0 ]]; then
    TS="$(date +%Y%m%d-%H%M%S)"
    BACKUP_TAR="$TARGET_DIR/backups/notes-skill-${TS}-pre-link.tar.gz"
    (
      cd "$TARGET_DIR"
      tar -czf "$BACKUP_TAR" "${EXISTING_ENTRIES[@]}"
    )
    echo "Backup created: $BACKUP_TAR"
  fi
fi

for entry in "${MANAGED_ENTRIES[@]}"; do
  src="$REPO_DIR/$entry"
  dst="$TARGET_DIR/$entry"
  mkdir -p "$(dirname "$dst")"
  if [[ -L "$dst" ]] && [[ "$(readlink "$dst")" == "$src" ]]; then
    continue
  fi
  rm -rf "$dst"
  ln -s "$src" "$dst"
done

python3 - <<'PY' "$REPO_DIR" "$TARGET_DIR" "${#MANAGED_ENTRIES[@]}"
from datetime import datetime
from pathlib import Path
import json
import subprocess
import sys

repo_dir = Path(sys.argv[1])
target_dir = Path(sys.argv[2])
managed_count = int(sys.argv[3])
try:
    commit = subprocess.check_output(
        ["git", "-C", str(repo_dir), "rev-parse", "HEAD"],
        text=True,
    ).strip()
except Exception:
    commit = None

payload = {
    "mode": "dev-linked",
    "repo_dir": str(repo_dir),
    "target_dir": str(target_dir),
    "managed_entries": managed_count,
    "commit": commit,
    "linked_at": datetime.now().isoformat(timespec="seconds"),
}
(target_dir / ".live-link.json").write_text(
    json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
    encoding="utf-8",
)
PY

echo "Linked live skill to repo: $TARGET_DIR -> $REPO_DIR"
echo "Preserved local-only paths: config.json, backups/, .ai/"
