from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ace.errors import ConfigurationError
from ace.profile import active as active_account, load as load_account, save as save_account


def ensure_task_context(
    platform: str,
    content_type: str,
    *, workspace: str | Path | None = None,
    account_slug: str | None = None,
    mode: str = "assisted",
    no_profile: bool = False,
) -> dict[str, Any] | None:
    """Load the permanent account source of truth and ask only for critical gaps."""

    if no_profile:
        return None
    account = load_account(account_slug, workspace) if account_slug else active_account(workspace)
    changed = False
    description = str(account.get("description") or account.get("account", {}).get("description") or "").strip()
    niche = str(account.get("niche") or account.get("account", {}).get("niche") or "").strip()
    if not description and not niche:
        if mode == "auto" or not sys.stdin.isatty():
            raise ConfigurationError(
                "The active account does not explain what it is about. Run 'ace account edit' or 'ace account build'."
            )
        answer = input("ACE needs one missing detail. What is this account about? ").strip()
        if not answer:
            raise ConfigurationError("Account description is required for reliable generation.")
        account["description"] = answer
        account.setdefault("account", {})["description"] = answer
        changed = True
    platform_config = account.setdefault("platforms", {}).setdefault(platform, {"enabled": False, "adaptation": {}})
    if not platform_config.get("enabled", False):
        if mode == "auto" or not sys.stdin.isatty():
            raise ConfigurationError(
                f"{platform} is not enabled for account {account['name']}. Enable it with 'ace account edit'."
            )
        answer = input(f"{platform} is not enabled for this account. Enable it now? [Y/n] ").strip().lower()
        if answer in {"", "y", "yes"}:
            platform_config["enabled"] = True
            changed = True
        else:
            raise ConfigurationError(f"Generation cancelled because {platform} is disabled for this account.")
    audience = account.setdefault("audience", {})
    if not str(audience.get("description") or "").strip():
        audience["description"] = "General audience"
        changed = True
    if changed:
        save_account(account, workspace)
    return account
