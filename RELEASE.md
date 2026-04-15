# Release Workflow

This repo is the single source of truth for `notes`.

The live install in `~/.agents/skills/notes` is a deployment target, not the place to make product changes by hand.

## Default flow

1. Create a feature branch.
2. Make changes in this repo only.
3. Run:
   - `scripts/release-check.sh`
4. Promote the checked-out repo to the live skill:
   - `scripts/promote-live.sh`
5. Smoke-check a real `/notes` run on a known video or transcript.
6. Commit the release-ready state.
7. Tag the stable version:
   - `git tag v$(cat VERSION)`

## Promote behavior

`scripts/promote-live.sh` will:

- run the release checks by default
- create a timestamped backup of the current live skill
- preserve local-only files such as `config.json` and `backups/`
- sync this repo into the live target with `rsync --delete`

## Rules

- Do not patch `~/.agents/skills/notes` directly unless you are doing emergency forensics.
- If you must inspect or hotfix live state, pull it back into a branch immediately after.
- Treat git tags as the rollback surface; treat tarball backups as the emergency surface.
