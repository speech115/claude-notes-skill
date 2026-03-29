#!/usr/bin/env bash
set -euo pipefail

REPO="speech115/claude-notes-skill"
BRANCH="main"
SKILL_DIR="${HOME}/.claude/skills/notes"

echo "=== Claude Notes Skill Installer ==="
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

# Download and install
echo ""
echo "Installing to $SKILL_DIR ..."

TMPDIR="$(mktemp -d)"
trap 'rm -rf "$TMPDIR"' EXIT

if [[ -d "$SKILL_DIR/.git" ]]; then
  echo "Git repo detected, pulling latest..."
  cd "$SKILL_DIR" && git pull origin "$BRANCH" --ff-only
else
  curl -fsSL "https://github.com/$REPO/archive/refs/heads/$BRANCH.tar.gz" \
    | tar -xz -C "$TMPDIR" --strip-components=1

  mkdir -p "$SKILL_DIR/block-templates" "$SKILL_DIR/scripts"

  # Copy core files
  for f in SKILL.md README.md ADVANCED.md assemble.sh prepare.sh template.html dark-theme.css config.example.json; do
    cp "$TMPDIR/$f" "$SKILL_DIR/$f" 2>/dev/null || true
  done
  cp "$TMPDIR"/block-templates/*.md "$SKILL_DIR/block-templates/" 2>/dev/null || true
  cp "$TMPDIR"/scripts/notes-runner "$SKILL_DIR/scripts/notes-runner" 2>/dev/null || true
  cp "$TMPDIR"/scripts/replace-speakers.sh "$SKILL_DIR/scripts/replace-speakers.sh" 2>/dev/null || true

  # Create config.json only if it doesn't exist
  if [[ ! -f "$SKILL_DIR/config.json" ]]; then
    cp "$TMPDIR/config.example.json" "$SKILL_DIR/config.json"
  fi
fi

chmod +x "$SKILL_DIR/scripts/notes-runner" "$SKILL_DIR/assemble.sh" "$SKILL_DIR/prepare.sh" 2>/dev/null || true

echo ""
echo "=== Installed! ==="
echo ""
echo "Restart Claude Code, then try:"
echo "  /notes https://www.youtube.com/watch?v=..."
echo "  /notes /path/to/file.md"
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
