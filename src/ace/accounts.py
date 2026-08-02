from __future__ import annotations

import shutil
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml

from ace.paths import resolve_paths
from ace.utils import deep_merge, ensure_dir, slugify


DEFAULT_ACCOUNT: dict[str, Any] = {
    "schema_version": 2,
    "name": "Creator",
    "slug": "creator",
    "description": "Technology and educational content.",
    "identity": {
        "personality": ["human", "clear", "credible"],
        "age_energy": "young_adult",
        "humor": {
            "default_level": "moderate",
            "allow_light_cringe": True,
            "allow_memes": True,
            "avoid_forced_jokes": True,
            "avoid_mocking_victims": True,
        },
    },
    "audience": {"description": "General audience", "knowledge_level": "general", "age_range": "broad"},
    "languages": {"primary": "en", "enabled": ["en"]},
    "platforms": {"youtube": {"enabled": True}, "tiktok": {"enabled": True}, "instagram": {"enabled": True}},
    "content": {"pillars": ["technology"], "avoid": ["fake urgency", "unsupported statistics"]},
    "voice": {"configured": False, "provider": "kokoro", "voice_id": "af_sarah", "pace": "natural", "energy": "conversational"},
    "editing": {
        "style": "adaptive",
        "default_mood": "technical_dynamic",
        "audience_mentality": "young_adult",
        "captions": {"mode": "director", "maximum_lines": 2},
        "humor": {"adaptive": True, "controlled_cringe": True},
    },
    "automation": {"candidates": 5, "minimum_quality_score": 85, "maximum_retries": 2},
}


def account_path(slug: str, workspace: str | Path | None = None) -> Path:
    return resolve_paths(workspace).accounts_dir / slugify(slug) / "account.yaml"


def _load_raw(name: str | None = None, workspace: str | Path | None = None) -> dict[str, Any]:
    slug = slugify(name) if name else active_slug(workspace)
    target = account_path(slug, workspace)
    if not target.exists():
        raise FileNotFoundError(f"Account not found: {slug}. Run 'ace new'.")
    value = yaml.safe_load(target.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"Invalid account file: {target}")
    return value


def migrate_account(account: dict[str, Any]) -> dict[str, Any]:
    """Fill new account fields without overwriting user choices.

    ACE 1.x accounts did not contain the v2 editing/personality blocks.  Loading
    through this function makes old accounts immediately usable, while
    ``migrate_all`` persists the upgrade with a history snapshot.
    """
    migrated = deep_merge(deepcopy(DEFAULT_ACCOUNT), account)
    migrated["schema_version"] = DEFAULT_ACCOUNT["schema_version"]
    migrated["slug"] = slugify(str(migrated.get("slug") or migrated.get("name") or "creator"))
    return migrated


def migrate_all(workspace: str | Path | None = None) -> list[str]:
    migrated_slugs: list[str] = []
    for slug in list_accounts(workspace):
        raw = _load_raw(slug, workspace)
        migrated = migrate_account(raw)
        if migrated != raw:
            save(migrated, workspace, snapshot=True)
            migrated_slugs.append(slug)
    return migrated_slugs


def create(
    name: str,
    *,
    description: str = "",
    niche: str = "technology",
    audience: str = "General audience",
    language: str = "en",
    platforms: list[str] | None = None,
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    account = deepcopy(DEFAULT_ACCOUNT)
    account["name"] = name.strip() or "Creator"
    account["slug"] = slugify(account["name"])
    account["description"] = description.strip() or f"{niche.capitalize()} content explained clearly."
    account["audience"]["description"] = audience
    account["languages"] = {"primary": language, "enabled": [language]}
    enabled = platforms or ["youtube", "tiktok", "instagram"]
    account["platforms"] = {item: {"enabled": True} for item in enabled}
    account["content"]["pillars"] = [niche]
    save(account, workspace)
    use(account["slug"], workspace)
    return account


def save(account: dict[str, Any], workspace: str | Path | None = None, *, snapshot: bool = True) -> Path:
    slug = slugify(str(account.get("slug") or account.get("name") or "creator"))
    account["slug"] = slug
    target = account_path(slug, workspace)
    ensure_dir(target.parent)
    if snapshot and target.exists():
        history = ensure_dir(target.parent / "history")
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        history_target = history / f"{stamp}-account.yaml"
        counter = 1
        while history_target.exists():
            history_target = history / f"{stamp}-{counter:02d}-account.yaml"
            counter += 1
        shutil.copy2(target, history_target)
    target.write_text(yaml.safe_dump(account, sort_keys=False, allow_unicode=True), encoding="utf-8")
    return target


def load(name: str | None = None, workspace: str | Path | None = None) -> dict[str, Any]:
    return migrate_account(_load_raw(name, workspace))


def list_accounts(workspace: str | Path | None = None) -> list[str]:
    root = resolve_paths(workspace).accounts_dir
    return sorted(path.parent.name for path in root.glob("*/account.yaml"))


def use(name: str, workspace: str | Path | None = None) -> str:
    slug = slugify(name)
    if not account_path(slug, workspace).exists():
        raise FileNotFoundError(f"Account not found: {slug}")
    resolve_paths(workspace).active_account_file.write_text(slug + "\n", encoding="utf-8")
    return slug


def active_slug(workspace: str | Path | None = None) -> str:
    path = resolve_paths(workspace).active_account_file
    if path.exists() and path.read_text(encoding="utf-8").strip():
        return slugify(path.read_text(encoding="utf-8").strip())
    accounts = list_accounts(workspace)
    if accounts:
        return accounts[0]
    raise FileNotFoundError("No ACE account exists. Run 'ace new'.")


def validate(account: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("name", "slug", "languages", "platforms", "content", "editing", "automation"):
        if not account.get(key):
            problems.append(f"Missing required account field: {key}")
    languages = account.get("languages", {})
    if languages.get("primary") not in languages.get("enabled", []):
        problems.append("Primary language must be included in enabled languages.")
    if not any(bool(value.get("enabled")) for value in account.get("platforms", {}).values() if isinstance(value, dict)):
        problems.append("At least one platform must be enabled.")
    return problems


def asset_dir(account_slug: str | None = None, workspace: str | Path | None = None) -> Path:
    slug = account_slug or active_slug(workspace)
    return ensure_dir(resolve_paths(workspace).account_assets_dir / slugify(slug) / "assets")
