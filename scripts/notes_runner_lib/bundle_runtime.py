from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

from .common import (
    collapse_blank_lines,
    compute_file_sha256,
    iso_now,
    load_json_if_exists,
    read_first_line,
    resolved_path_string,
    sha1_text,
    write_json,
)

TRACE_FILENAME = "trace.jsonl"
TIMELINE_FILENAME = "timeline.jsonl"
RUNS_DIRNAME = "runs"
DEFAULT_TELEGRAM_MCP_URL = "http://127.0.0.1:8799/mcp"
DEFAULT_TELEGRAM_CAPTION_TEMPLATE = ""
DEFAULT_TELEGRAM_CHAT = "-1003850136767"


def bundle_paths(bundle_dir: Path) -> dict[str, Path]:
    return {
        "metadata": bundle_dir / "metadata.json",
        "source_url": bundle_dir / "source-url.txt",
        "source_file": bundle_dir / "source-file.txt",
        "state": bundle_dir / "run.json",
        "trace": bundle_dir / TRACE_FILENAME,
        "timeline": bundle_dir / TIMELINE_FILENAME,
        "runs_dir": bundle_dir / RUNS_DIRNAME,
        "source_dir": bundle_dir / "source",
        "subs_dir": bundle_dir / "subs",
        "audio_dir": bundle_dir / "audio",
        "transcript": bundle_dir / "transcript.md",
        "raw_transcript": bundle_dir / "transcript.raw.json",
        "notes_md": bundle_dir / "конспект.md",
        "notes_html": bundle_dir / "конспект.html",
    }


def load_bundle_metadata(bundle_dir: Path) -> dict | None:
    return load_json_if_exists(bundle_paths(bundle_dir)["metadata"])


def infer_bundle_note_id(bundle_dir: Path, state: dict | None = None, metadata: dict | None = None) -> str:
    if isinstance(state, dict):
        existing = str(state.get("note_id") or "").strip()
        if existing:
            return existing
    if metadata is None:
        metadata = load_bundle_metadata(bundle_dir) or {}
    if state is None:
        state = load_json_if_exists(bundle_paths(bundle_dir)["state"]) or {}
    source_kind = str((state.get("source_kind") if isinstance(state, dict) else None) or metadata.get("source_kind") or "").strip()
    video_id = str((state.get("video_id") if isinstance(state, dict) else None) or metadata.get("id") or "").strip()
    if source_kind == "youtube" and video_id:
        return f"youtube:{video_id}"
    telegram_chat = str((state.get("telegram_chat") if isinstance(state, dict) else None) or metadata.get("telegram_chat") or "").strip()
    telegram_message_id = str((state.get("telegram_message_id") if isinstance(state, dict) else None) or metadata.get("telegram_message_id") or "").strip()
    if source_kind == "telegram" and telegram_chat and telegram_message_id:
        return f"telegram:{telegram_chat}:{telegram_message_id}"
    source_path = str((state.get("source_path") if isinstance(state, dict) else None) or metadata.get("source_path") or "").strip()
    if not source_path:
        source_path = str(read_first_line(bundle_paths(bundle_dir)["source_file"]) or "").strip()
    if source_path:
        return f"file:{sha1_text(resolved_path_string(source_path))}"
    source_url = str((state.get("source_url") if isinstance(state, dict) else None) or "").strip()
    if not source_url:
        source_url = str(read_first_line(bundle_paths(bundle_dir)["source_url"]) or "").strip()
    if source_url:
        return f"url:{sha1_text(source_url)}"
    return f"bundle:{sha1_text(str(bundle_dir.resolve()))}"


def load_bundle_context(output_html: Path) -> dict:
    return load_json_if_exists(output_html.parent / "run.json") or {}


def build_source_reference(context: dict) -> str:
    source_kind = str(context.get("source_kind") or "").strip()
    source_url = str(context.get("source_url") or "").strip()
    if source_kind == "youtube" and source_url:
        return source_url
    source_name = str(context.get("source_name") or "").strip()
    if source_kind == "local" and source_name:
        return f"Файл: {source_name}"
    return source_url or source_name


def default_telegram_caption(*, title: str, context: dict) -> str:
    source_kind = str(context.get("source_kind") or "").strip()
    if source_kind == "youtube":
        lines = [f"📝 Конспект видео: {title}"]
        reference = build_source_reference(context)
        if reference:
            lines.append(reference)
        return "\n".join(lines)
    if source_kind == "local":
        lines = [f"📝 Конспект материала: {title}"]
        reference = build_source_reference(context)
        if reference:
            lines.append(reference)
        return "\n".join(lines)
    return f"📝 Конспект: {title}"


def render_caption(template: str, *, title: str, output_html: Path, context: dict) -> str:
    try:
        rendered = template.format(
            title=title,
            file_name=output_html.name,
            stem=output_html.stem,
            path=str(output_html),
            source_url=str(context.get("source_url") or ""),
            source_name=str(context.get("source_name") or ""),
            source_kind=str(context.get("source_kind") or ""),
            source_reference=build_source_reference(context),
            material_label="видео" if str(context.get("source_kind") or "") == "youtube" else "материала",
            video_id=str(context.get("video_id") or ""),
        )
        return collapse_blank_lines(rendered)
    except KeyError as exc:
        raise ValueError(f"Caption template uses unsupported placeholder: {exc}") from exc


def load_notes_config(config_path: Path) -> dict:
    default_delivery = {
        "enabled": True,
        "chat": DEFAULT_TELEGRAM_CHAT,
        "mcp_url": DEFAULT_TELEGRAM_MCP_URL,
        "parse_mode": "md",
    }
    default_config = {
        "telegram_delivery": default_delivery,
    }
    if not config_path.is_file():
        return default_config
    payload = load_json_if_exists(config_path)
    if payload is None:
        raise ValueError(f"Notes config is not valid JSON: {config_path}")
    if not isinstance(payload, dict):
        raise ValueError(f"Notes config must be a JSON object: {config_path}")
    merged = dict(payload)
    raw_delivery = payload.get("telegram_delivery")
    if raw_delivery is None:
        merged["telegram_delivery"] = default_delivery
        return merged
    if not isinstance(raw_delivery, dict):
        raise ValueError("notes config field 'telegram_delivery' must be a JSON object")
    merged_delivery = dict(default_delivery)
    merged_delivery.update(raw_delivery)
    if not str(merged_delivery.get("chat") or "").strip():
        merged_delivery["chat"] = DEFAULT_TELEGRAM_CHAT
    merged["telegram_delivery"] = merged_delivery
    return merged


def build_telegram_delivery_disabled(reason: str) -> dict:
    return {
        "enabled": False,
        "attempted": False,
        "success": False,
        "reason": reason,
    }


def effective_telegram_chat(
    chat_override: str | None = None,
    *,
    config_path: Path,
) -> str | None:
    if chat_override:
        chat = chat_override.strip()
        return chat or None
    config = load_notes_config(config_path)
    delivery = config.get("telegram_delivery")
    if not isinstance(delivery, dict) or not delivery.get("enabled", False):
        return None
    chat = str(delivery.get("chat") or "").strip() or DEFAULT_TELEGRAM_CHAT
    return chat or None


def build_telegram_delivery_skipped(reason: str, *, output_html: Path, previous: dict | None = None) -> dict:
    payload = {
        "enabled": True,
        "attempted": False,
        "success": bool(isinstance(previous, dict) and previous.get("success")),
        "reason": reason,
        "file_path": str(output_html),
    }
    if isinstance(previous, dict):
        for key in ("chat", "caption", "parse_mode", "mcp_url", "runner", "result", "file_sha256"):
            if previous.get(key) is not None:
                payload[key] = previous[key]
    return payload


def existing_successful_telegram_delivery(
    output_html: Path,
    *,
    title: str,
    config_path: Path,
    chat_override: str | None = None,
    force_resend: bool = False,
) -> dict | None:
    if force_resend or not output_html.is_file():
        return None
    context = load_bundle_context(output_html)
    if not isinstance(context, dict):
        return None
    previous = context.get("telegram_delivery")
    if not isinstance(previous, dict) or not previous.get("success"):
        return None
    if str(context.get("title") or "").strip() != title.strip():
        return None
    if str(previous.get("file_path") or "").strip() != str(output_html):
        return None

    target_chat = effective_telegram_chat(chat_override, config_path=config_path)
    previous_chat = str(previous.get("chat") or "").strip()
    if target_chat and previous_chat and previous_chat != target_chat:
        return None

    current_sha = compute_file_sha256(output_html)
    previous_sha = str(previous.get("file_sha256") or "").strip()
    if previous_sha:
        return previous if previous_sha == current_sha else None

    return previous


def deliver_html_to_telegram(
    output_html: Path,
    *,
    title: str,
    config_path: Path,
    resolve_digest_runner: Callable[[], Path],
    run_command: Callable[[list[str]], object],
    env_flag_enabled: Callable[[str], bool],
    chat_override: str | None = None,
) -> dict:
    if env_flag_enabled("NOTES_RUNNER_DISABLE_TELEGRAM"):
        return build_telegram_delivery_disabled("disabled-by-env")
    config = load_notes_config(config_path)
    delivery = config.get("telegram_delivery")

    if chat_override:
        if not isinstance(delivery, dict):
            delivery = {}
        chat = chat_override.strip()
    else:
        if not isinstance(delivery, dict):
            delivery = {}
        if not delivery.get("enabled", False):
            return build_telegram_delivery_disabled("disabled")
        chat = str(delivery.get("chat") or "").strip() or DEFAULT_TELEGRAM_CHAT
        if not chat:
            return {
                "enabled": True,
                "attempted": False,
                "success": False,
                "error": "notes config missing telegram_delivery.chat",
            }

    context = load_bundle_context(output_html)
    caption_template = str(delivery.get("caption_template") or DEFAULT_TELEGRAM_CAPTION_TEMPLATE)
    if caption_template:
        caption = render_caption(caption_template, title=title, output_html=output_html, context=context)
    else:
        caption = default_telegram_caption(title=title, context=context)
    parse_mode = str(delivery.get("parse_mode") or "md").strip() or "md"
    mcp_url = str(delivery.get("mcp_url") or DEFAULT_TELEGRAM_MCP_URL).strip()
    delivery_file = output_html
    runner_path = resolve_digest_runner()

    command = [
        str(runner_path),
        "send-file",
        "--input",
        str(delivery_file),
        "--chat",
        chat,
        "--caption",
        caption,
        "--parse-mode",
        parse_mode,
        "--mcp-url",
        mcp_url,
        "--json",
    ]
    result = run_command(command)
    payload = {
        "enabled": True,
        "attempted": True,
        "success": result.returncode == 0,
        "chat": chat,
        "caption": caption,
        "parse_mode": parse_mode,
        "mcp_url": mcp_url,
        "runner": str(runner_path),
        "file_path": str(delivery_file),
        "file_sha256": compute_file_sha256(delivery_file),
    }
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    if result.returncode != 0:
        detail = stderr or stdout or f"exit code {result.returncode}"
        payload["error"] = f"telegram delivery failed: {detail}"
        return payload
    if stdout:
        try:
            payload["result"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload["stdout"] = stdout
    return payload


def update_bundle_run_state(
    output_md: Path,
    output_html: Path,
    *,
    title: str,
    telegram_delivery: dict,
) -> None:
    outputs = {
        "markdown": str(output_md),
        "html": str(output_html),
    }
    if telegram_delivery.get("file_path"):
        outputs["telegram_html"] = str(telegram_delivery["file_path"])
    state_path = bundle_paths(output_html.parent)["state"]
    existing = load_json_if_exists(state_path) or {}
    if not isinstance(existing, dict):
        existing = {}
    existing["updated_at"] = iso_now()
    existing["title"] = title
    existing["outputs"] = outputs
    existing["telegram_delivery"] = telegram_delivery
    existing.setdefault("timeline_path", str(bundle_paths(output_html.parent)["timeline"]))
    existing.setdefault("runs_dir", str(bundle_paths(output_html.parent)["runs_dir"]))
    if not str(existing.get("note_id") or "").strip():
        existing["note_id"] = infer_bundle_note_id(output_html.parent, state=existing)
    write_json(state_path, existing)
