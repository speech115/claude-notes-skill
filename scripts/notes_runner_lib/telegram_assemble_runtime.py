from __future__ import annotations

from pathlib import Path
from typing import Callable

from .bundle_runtime import (
    build_telegram_delivery_disabled,
    build_telegram_delivery_skipped,
    deliver_html_to_telegram,
    effective_telegram_chat,
    existing_successful_telegram_delivery,
    update_bundle_run_state,
)


def build_telegram_delivery_failure(output_html: Path, exc: Exception) -> dict:
    return {
        "enabled": True,
        "attempted": True,
        "success": False,
        "file_path": str(output_html),
        "error": f"telegram delivery failed: {exc}",
    }


def resolve_assemble_telegram_delivery(
    *,
    output_md: Path,
    output_html: Path,
    title: str,
    contract_errors: list[str] | tuple[str, ...],
    config_path: Path,
    chat_override: str | None = None,
    skip_telegram: bool = False,
    force_telegram_resend: bool = False,
    resolve_digest_runner: Callable[[], Path],
    run_command: Callable[[list[str]], object],
    env_flag_enabled: Callable[[str], bool],
    build_telegram_delivery_disabled_fn: Callable[[str], dict] = build_telegram_delivery_disabled,
    effective_telegram_chat_fn: Callable[..., str | None] = effective_telegram_chat,
    build_telegram_delivery_skipped_fn: Callable[..., dict] = build_telegram_delivery_skipped,
    existing_successful_telegram_delivery_fn: Callable[..., dict | None] = existing_successful_telegram_delivery,
    deliver_html_to_telegram_fn: Callable[..., dict] = deliver_html_to_telegram,
    update_bundle_run_state_fn: Callable[..., None] = update_bundle_run_state,
) -> dict:
    if contract_errors:
        if skip_telegram:
            telegram_delivery = build_telegram_delivery_disabled_fn("skipped-by-request")
        elif effective_telegram_chat_fn(chat_override, config_path=config_path):
            telegram_delivery = build_telegram_delivery_skipped_fn("contract-errors", output_html=output_html)
        else:
            telegram_delivery = build_telegram_delivery_disabled_fn("disabled")
    elif skip_telegram:
        telegram_delivery = build_telegram_delivery_disabled_fn("skipped-by-request")
    else:
        previous_delivery = existing_successful_telegram_delivery_fn(
            output_html,
            title=title,
            config_path=config_path,
            chat_override=chat_override,
            force_resend=force_telegram_resend,
        )
        if previous_delivery is not None:
            telegram_delivery = build_telegram_delivery_skipped_fn(
                "already-delivered-current-html",
                output_html=output_html,
                previous=previous_delivery,
            )
        else:
            try:
                telegram_delivery = deliver_html_to_telegram_fn(
                    output_html,
                    title=title,
                    config_path=config_path,
                    resolve_digest_runner=resolve_digest_runner,
                    run_command=run_command,
                    env_flag_enabled=env_flag_enabled,
                    chat_override=chat_override,
                )
            except (ValueError, FileNotFoundError) as exc:
                telegram_delivery = build_telegram_delivery_failure(output_html, exc)

    update_bundle_run_state_fn(
        output_md,
        output_html,
        title=title,
        telegram_delivery=telegram_delivery,
    )
    return telegram_delivery
