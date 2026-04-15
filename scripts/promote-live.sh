#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
TARGET_DIR="${NOTES_LIVE_DIR:-$HOME/.agents/skills/notes}"
ALLOW_DIRTY=0
SKIP_CHECKS=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --target)
      TARGET_DIR="$2"
      shift 2
      ;;
    --allow-dirty)
      ALLOW_DIRTY=1
      shift
      ;;
    --skip-checks)
      SKIP_CHECKS=1
      shift
      ;;
    *)
      echo "Unknown argument: $1" >&2
      exit 1
      ;;
  esac
done

if [[ "$ALLOW_DIRTY" -ne 1 ]] && [[ -n "$(git -C "$REPO_DIR" status --porcelain)" ]]; then
  echo "Refusing to promote with a dirty working tree. Commit/stash first or use --allow-dirty." >&2
  exit 1
fi

if [[ "$SKIP_CHECKS" -ne 1 ]]; then
  "$REPO_DIR/scripts/release-check.sh"
fi

mkdir -p "$TARGET_DIR" "$TARGET_DIR/backups"

if [[ -d "$TARGET_DIR" ]]; then
  TS="$(date +%Y%m%d-%H%M%S)"
  BACKUP_TAR="$TARGET_DIR/backups/notes-skill-${TS}-pre-promote.tar.gz"
  (
    cd "$TARGET_DIR"
    tar -czf "$BACKUP_TAR" --exclude='./backups' .
  )
fi

rsync -a --delete \
  --exclude '.git/' \
  --exclude 'backups/' \
  --exclude 'config.json' \
  --exclude '.ai/runtime/' \
  --exclude 'scripts/__pycache__/' \
  --exclude 'RELEASE.md' \
  --exclude 'VERSION' \
  "$REPO_DIR/" "$TARGET_DIR/"

if [[ ! -f "$TARGET_DIR/config.json" && -f "$REPO_DIR/config.example.json" ]]; then
  cp "$REPO_DIR/config.example.json" "$TARGET_DIR/config.json"
fi

chmod +x "$TARGET_DIR/assemble.sh" "$TARGET_DIR/prepare.sh" "$TARGET_DIR/scripts/notes-runner" 2>/dev/null || true

echo "Promoted notes skill to $TARGET_DIR"
