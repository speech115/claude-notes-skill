import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from notes_runner_lib.digest_runner_runtime import (
    digest_runner_from_config,
    resolve_digest_runner_path,
)


class DigestRunnerRuntimeTests(unittest.TestCase):
    def test_digest_runner_from_config_prefers_top_level(self) -> None:
        config = {
            "digest_runner": "/tmp/top",
            "telegram_delivery": {"digest_runner": "/tmp/nested"},
        }
        self.assertEqual(digest_runner_from_config(config), "/tmp/top")

    def test_resolve_uses_env_override_first(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            runner = Path(tmp_dir) / "digest-runner"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            with mock.patch.dict(os.environ, {"NOTES_RUNNER_DIGEST_RUNNER": str(runner)}, clear=False):
                resolved = resolve_digest_runner_path(
                    config_path=Path(tmp_dir) / "missing.json",
                    skill_root=Path(tmp_dir),
                )
            self.assertEqual(resolved, runner)

    def test_resolve_reads_nested_config_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            root = Path(tmp_dir)
            runner = root / "runner"
            runner.write_text("#!/bin/sh\n", encoding="utf-8")
            runner.chmod(0o755)
            config_path = root / "config.json"
            config_path.write_text(
                '{"telegram_delivery":{"digest_runner":"' + str(runner) + '"}}',
                encoding="utf-8",
            )
            def env_without_override(key: str, default: str | None = None) -> str | None:
                if key == "NOTES_RUNNER_DIGEST_RUNNER":
                    return None
                return os.environ.get(key, default)

            resolved = resolve_digest_runner_path(
                config_path=config_path,
                skill_root=root,
                env_get=env_without_override,
            )
            self.assertEqual(resolved, runner)


if __name__ == "__main__":
    unittest.main()