from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, TextIO


@dataclass(frozen=True)
class DoctorCommandDependencies:
    build_doctor_checks: Callable[..., dict[str, object]]
    render_doctor_report: Callable[[dict[str, object]], str]
    platform: str
    python_version: str
    which: Callable[[str], str | None]
    groq_api_key_present: bool
    skill_root: Path | str
    config_path: Path | str
    load_notes_config: Callable[[Path], object]
    env_flag_enabled: Callable[[str], bool]
    is_macos: Callable[[], bool]
    parakeet_available: Callable[[], bool]
    mlx_whisper_available: Callable[[], bool]
    python_module_available: Callable[[str], bool]
    stdout: TextIO | None = None


def run_doctor_command(args: argparse.Namespace, *, deps: DoctorCommandDependencies) -> int:
    checks = deps.build_doctor_checks(
        platform=deps.platform,
        python_version=deps.python_version,
        which=deps.which,
        groq_api_key_present=deps.groq_api_key_present,
        skill_root=deps.skill_root,
        config_path=deps.config_path,
        load_notes_config=deps.load_notes_config,
        env_flag_enabled=deps.env_flag_enabled,
        is_macos=deps.is_macos,
        parakeet_available=deps.parakeet_available,
        mlx_whisper_available=deps.mlx_whisper_available,
        python_module_available=deps.python_module_available,
    )

    stdout = deps.stdout if deps.stdout is not None else sys.stdout
    if getattr(args, "json", False):
        print(json.dumps(checks, indent=2, default=str), file=stdout)
        return 0

    print(deps.render_doctor_report(checks), end="", file=stdout)
    return 0


cmd_doctor = run_doctor_command


__all__ = ["DoctorCommandDependencies", "cmd_doctor", "run_doctor_command"]
