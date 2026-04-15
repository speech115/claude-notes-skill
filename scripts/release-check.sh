#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

python3 -m py_compile "$REPO_DIR/scripts/notes-runner"
bash "$REPO_DIR/scripts/test-pipeline.sh" --quick
