#!/usr/bin/env bash
# replace-speakers.sh — thin shim delegating to notes-runner replace-speakers
# Usage: replace-speakers.sh <work_dir>
#
# Preserved for backward compatibility with SKILL.md which calls:
#   bash ${CLAUDE_SKILL_DIR}/scripts/replace-speakers.sh "$WORK_DIR"

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
exec "$SCRIPT_DIR/notes-runner" replace-speakers "${1:?Usage: replace-speakers.sh <work_dir>}"
