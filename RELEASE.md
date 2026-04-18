# Release Workflow

This repo is the single source of truth for `notes`.

The live install is a deployment target, not the place to make product changes by hand.
Default target resolution matches `install.sh`: prefer `~/.codex/skills/notes`, fall back to existing `~/.agents/skills/notes` or `~/.claude/skills/notes`. Override with `NOTES_LIVE_DIR` or `--target`.

## Default flow

1. Create a feature branch.
2. Make changes in this repo only.
3. If this machine is your main local dev box, link the live skill once:
   - `scripts/dev-link-live.sh`
4. Run:
   - `git status --short`
   - `scripts/release-check.sh`
5. Promote the checked-out repo to the live skill:
   - `scripts/promote-live.sh`
6. Smoke-check a real `/notes` run on a known video or transcript.
   - safest local path: `NOTES_RUNNER_DISABLE_TELEGRAM=1 ... --skip-telegram`
7. Commit the release-ready state.
8. Tag the stable version:
   - `git tag v$(cat VERSION)`

## Promote behavior

`scripts/promote-live.sh` will:

- run the release checks by default
- refuse a dirty working tree unless you explicitly pass `--allow-dirty`
- create a timestamped backup of the current live skill
- preserve local-only files such as `config.json` and `backups/`
- sync this repo into the live target with `rsync --delete`

## Rules

- Do not patch the live skill directory directly unless you are doing emergency forensics.
- On a local dev machine, prefer `scripts/dev-link-live.sh` so the live install and repo point at the same managed files.
- `scripts/release-check.sh` now expects the quick deterministic layer to finish without `SKIP`.
- If you see `SKIP` in quick mode, treat it as a harness regression and fix the test surface before promoting.
- Optional `--full` checks may still skip external scenarios if local long-form fixtures are missing.
- If you must inspect or hotfix live state, pull it back into a branch immediately after.
- Treat git tags as the rollback surface; treat tarball backups as the emergency surface.
