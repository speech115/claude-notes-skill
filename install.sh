#!/usr/bin/env bash
set -euo pipefail

# Public GitHub default for remote installs.
REPO_SLUG="${NOTES_INSTALL_REPO:-speech115/notes-skill}"
REPO_REF="${NOTES_INSTALL_REF:-main}"
CODEX_SKILL_DIR="${HOME}/.agents/skills/notes"
LEGACY_SKILL_DIR="${HOME}/.claude/skills/notes"

choose_skill_dir() {
  if [[ -n "${NOTES_SKILL_TARGET_DIR:-}" ]]; then
    echo "${NOTES_SKILL_TARGET_DIR}"
    return
  fi
  if [[ -d "$CODEX_SKILL_DIR" || ! -d "$LEGACY_SKILL_DIR" ]]; then
    echo "$CODEX_SKILL_DIR"
  else
    echo "$LEGACY_SKILL_DIR"
  fi
}

SKILL_DIR="$(choose_skill_dir)"
SCRIPT_PATH="${BASH_SOURCE[0]}"
SCRIPT_DIR="$(cd "$(dirname "$SCRIPT_PATH")" && pwd)"
TMPDIR=""

cleanup() {
  if [[ -n "${TMPDIR:-}" && -d "${TMPDIR:-}" ]]; then
    rm -rf "$TMPDIR"
  fi
}
trap cleanup EXIT

echo "=== Notes Skill Installer ==="
echo ""

# Platform detection
detect_platform() {
  case "${OSTYPE:-unknown}" in
    darwin*)  echo "macos" ;;
    linux*)
      if [[ -f /proc/version ]] && grep -qi microsoft /proc/version 2>/dev/null; then
        echo "wsl"
      else
        echo "linux"
      fi
      ;;
    msys*|cygwin*|mingw*) echo "windows" ;;
    *)        echo "linux" ;;
  esac
}

PLATFORM="$(detect_platform)"
echo "Platform: $PLATFORM"

if [[ "$PLATFORM" == "windows" ]]; then
  echo ""
  echo "Windows detected without WSL."
  echo "Please install WSL first: wsl --install"
  echo "Then re-run this script from WSL."
  exit 1
fi

# Dependency checker
check_dep() {
  local cmd="$1" install_hint="$2"
  if command -v "$cmd" &>/dev/null; then
    echo "  ✓ $cmd"
  else
    echo "  ✗ $cmd — install with: $install_hint"
    MISSING_DEPS=1
  fi
}

echo ""
echo "Checking dependencies..."
MISSING_DEPS=0

case "$PLATFORM" in
  macos)
    check_dep python3 "brew install python"
    check_dep pandoc  "brew install pandoc"
    check_dep yt-dlp  "brew install yt-dlp"
    check_dep ffmpeg  "brew install ffmpeg"
    ;;
  linux|wsl)
    check_dep python3 "sudo apt install python3"
    check_dep pandoc  "sudo apt install pandoc"
    check_dep yt-dlp  "pip install yt-dlp"
    check_dep ffmpeg  "sudo apt install ffmpeg"
    ;;
esac

if [[ "$MISSING_DEPS" -eq 1 ]]; then
  echo ""
  echo "Install missing dependencies above, then re-run."
  exit 1
fi

# Source selection
echo ""
echo "Installing to $SKILL_DIR ..."

if [[ -f "$SCRIPT_DIR/SKILL.md" && -f "$SCRIPT_DIR/scripts/notes-runner" ]]; then
  SOURCE_DIR="$SCRIPT_DIR"
else
  TMPDIR="$(mktemp -d -t notes-skill-install-XXXXXX)"
  curl -fsSL "https://github.com/$REPO_SLUG/archive/refs/heads/$REPO_REF.tar.gz" \
    | tar -xz -C "$TMPDIR" --strip-components=1
  SOURCE_DIR="$TMPDIR"
fi

mkdir -p "$SKILL_DIR"
rsync -a --delete \
  --exclude '.git/' \
  --exclude 'backups/' \
  --exclude 'config.json' \
  --exclude '.ai/runtime/' \
  --exclude 'scripts/__pycache__/' \
  --exclude 'RELEASE.md' \
  --exclude 'VERSION' \
  "$SOURCE_DIR/" "$SKILL_DIR/"

if [[ ! -f "$SKILL_DIR/config.json" ]]; then
  cp "$SOURCE_DIR/config.example.json" "$SKILL_DIR/config.json"
fi

chmod +x "$SKILL_DIR/scripts/notes-runner" "$SKILL_DIR/assemble.sh" "$SKILL_DIR/prepare.sh" 2>/dev/null || true
chmod 600 "$SKILL_DIR/config.json" 2>/dev/null || true

echo ""
echo "=== Installed! ==="
echo ""
echo "Restart your agent client, then try:"
echo "  /notes https://www.youtube.com/watch?v=..."
echo "  /notes /path/to/file.md"
echo ""
echo "Config note:"
echo "  config.json is local-only and should not be committed or shared."
echo ""

# Audio transcription guidance
if [[ "$PLATFORM" != "macos" ]]; then
  echo "Audio transcription (Linux/WSL):"
  echo "  Get a free Groq API key at https://console.groq.com"
  echo "  Then add to your shell config: export GROQ_API_KEY=your-key-here"
  echo ""
else
  echo "Audio transcription (macOS):"
  echo "  Option A (local):  pip install mlx-whisper"
  echo "  Option B (cloud):  export GROQ_API_KEY=your-key-here"
  echo "  Get a free key at https://console.groq.com"
  echo ""
fi

echo "Run 'notes-runner doctor' to verify your setup."
