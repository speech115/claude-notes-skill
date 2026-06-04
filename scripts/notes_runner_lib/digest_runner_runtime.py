from __future__ import annotations

import os
from collections.abc import Callable
from pathlib import Path

WhichCallback = Callable[[str], str | None]


def digest_runner_from_config(config: object) -> str | None:
    if not isinstance(config, dict):
        return None
    top_level = config.get("digest_runner")
    if isinstance(top_level, str) and top_level.strip():
        return top_level.strip()
    delivery = config.get("telegram_delivery")
    if isinstance(delivery, dict):
        nested = delivery.get("digest_runner")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
    return None


def candidate_digest_runner_paths(*, skill_root: Path, config_path: Path | None = None) -> list[Path]:
    candidates: list[Path] = []
    bin_wrapper = skill_root / "bin" / "digest-runner"
    if bin_wrapper.is_file():
        candidates.append(bin_wrapper)
    if config_path and config_path.is_file():
        try:
            from .bundle_runtime import load_json_if_exists

            payload = load_json_if_exists(config_path)
            configured = digest_runner_from_config(payload)
            if configured:
                candidates.append(Path(configured).expanduser())
        except Exception:
            pass
    return candidates


def resolve_digest_runner_path(
    *,
    config_path: Path,
    skill_root: Path,
    env_get: Callable[[str], str | None] | None = None,
    which: WhichCallback | None = None,
) -> Path:
    import shutil

    getenv = env_get or os.environ.get
    which_impl = which or shutil.which

    override = getenv("NOTES_RUNNER_DIGEST_RUNNER")
    if override:
        resolved = Path(override).expanduser()
        if not resolved.is_file():
            raise FileNotFoundError(f"NOTES_RUNNER_DIGEST_RUNNER points to a missing file: {resolved}")
        return resolved

    for candidate in candidate_digest_runner_paths(skill_root=skill_root, config_path=config_path):
        if candidate.is_file():
            return candidate

    found = which_impl("digest-runner")
    if found:
        path = Path(found)
        if path.is_file():
            return path

    raise FileNotFoundError(
        "digest-runner not found. Set telegram_delivery.digest_runner in config.json, "
        "NOTES_RUNNER_DIGEST_RUNNER, install digest-runner into PATH, or add skill_root/bin/digest-runner."
    )


__all__ = [
    "candidate_digest_runner_paths",
    "digest_runner_from_config",
    "resolve_digest_runner_path",
]