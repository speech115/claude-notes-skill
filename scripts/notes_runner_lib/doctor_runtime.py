from __future__ import annotations

from collections.abc import Callable, Mapping
from pathlib import Path

REQUIRED_TOOLS = ("pandoc", "yt-dlp", "ffmpeg", "uv")
MACOS_ONLY_STATUS = "n/a (macOS only)"

DoctorChecks = dict[str, object]
WhichCallback = Callable[[str], str | None]
ConfigLoader = Callable[[Path], object]
FlagCallback = Callable[[str], bool]
AvailabilityCallback = Callable[[], bool]
ModuleAvailabilityCallback = Callable[[str], bool]


def _config_path(path: Path | str) -> Path:
    return path if isinstance(path, Path) else Path(path)


def _extract_telegram_delivery(config_payload: object) -> tuple[bool, str]:
    effective_delivery = config_payload.get("telegram_delivery") if isinstance(config_payload, dict) else {}
    enabled = bool(isinstance(effective_delivery, dict) and effective_delivery.get("enabled", False))
    chat = str(effective_delivery.get("chat") or "").strip() if isinstance(effective_delivery, dict) else ""
    return enabled, chat


def build_doctor_checks(
    *,
    platform: str,
    python_version: str,
    which: WhichCallback,
    groq_api_key_present: bool,
    skill_root: Path | str,
    config_path: Path | str,
    config_json_exists: bool | None = None,
    load_notes_config: ConfigLoader,
    env_flag_enabled: FlagCallback,
    is_macos: AvailabilityCallback,
    parakeet_available: AvailabilityCallback,
    mlx_whisper_available: AvailabilityCallback,
    python_module_available: ModuleAvailabilityCallback,
) -> DoctorChecks:
    config_file = _config_path(config_path)
    macos = is_macos()
    telegram_delivery_enabled, telegram_delivery_chat = _extract_telegram_delivery(load_notes_config(config_file))

    checks: DoctorChecks = {}
    checks["platform"] = platform
    checks["python_version"] = python_version

    for tool in REQUIRED_TOOLS:
        checks[tool] = which(tool) is not None

    checks["GROQ_API_KEY"] = groq_api_key_present
    checks["parakeet_mlx"] = parakeet_available() if macos else MACOS_ONLY_STATUS
    checks["mlx_whisper"] = mlx_whisper_available() if macos else MACOS_ONLY_STATUS
    checks["whisperx"] = which("whisperx") is not None
    checks["youtube_transcript_api"] = python_module_available("youtube_transcript_api")

    checks["skill_root"] = str(skill_root)
    checks["config_json"] = config_file.is_file() if config_json_exists is None else config_json_exists
    checks["telegram_delivery_enabled"] = telegram_delivery_enabled
    checks["telegram_delivery_chat"] = telegram_delivery_chat
    checks["trace_stderr_enabled"] = env_flag_enabled("NOTES_RUNNER_TRACE_STDERR")

    checks["audio_transcription_ready"] = bool(
        checks["GROQ_API_KEY"]
        or (macos and (checks["parakeet_mlx"] is True or checks["mlx_whisper"] is True))
    )
    return checks


def render_doctor_report(checks: Mapping[str, object]) -> str:
    lines = ["notes-runner doctor", ""]
    for key, value in checks.items():
        if isinstance(value, bool):
            icon = "\u2713" if value else "\u2717"
            lines.append(f"  {icon}  {key}")
        else:
            lines.append(f"  -  {key}: {value}")

    lines.append("")
    if not bool(checks.get("audio_transcription_ready")):
        lines.append("  ! No audio transcription backend available.")
        if str(checks.get("platform") or "") == "darwin":
            lines.append("    Install mlx-whisper: pip install mlx-whisper")
            lines.append("    Or set GROQ_API_KEY (free at console.groq.com)")
        else:
            lines.append("    Set GROQ_API_KEY (free at console.groq.com)")
    else:
        lines.append("  Ready to create notes!")

    return "\n".join(lines).rstrip() + "\n"


__all__ = ["build_doctor_checks", "render_doctor_report"]
