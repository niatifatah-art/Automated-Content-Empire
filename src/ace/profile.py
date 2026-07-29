from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


from ace.catalog import platform_names
from ace.config import load as load_config
from ace.config import save as save_config
from ace.errors import ACEError, ConfigurationError
from ace.paths import accounts_dir, profiles_dir
from ace.storage import slugify
from ace.yaml_compat import dump_data, load_data



def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def profile_path(slug: str, workspace: str | Path | None = None) -> Path:
    """Return the v1.7 account source-of-truth path.

    The public API keeps the historical ``profile_*`` names for compatibility,
    while the filesystem and CLI now call these objects accounts.
    """

    return accounts_dir(workspace) / slugify(slug) / "account.yaml"


def legacy_profile_path(slug: str, workspace: str | Path | None = None) -> Path:
    return profiles_dir(workspace) / slugify(slug) / "profile.json"


def default_profile(name: str) -> dict[str, Any]:
    slug = slugify(name)
    return {
        "schema_version": 2,
        "account": {
            "name": name,
            "slug": slug,
            "description": "",
            "niche": "",
            "sub_niches": [],
        },
        # Flat compatibility keys remain available to v0.x code.
        "name": name,
        "slug": slug,
        "description": "",
        "niche": "",
        "sub_niches": [],
        "identity": {
            "personality": ["clear", "credible", "human"],
            "voice_description": "Natural and recognizable across every platform",
            "values": [],
            "preferred_vocabulary": [],
            "avoid": ["invented claims", "misleading promises"],
            "humor_style": "",
            "explanation_style": "",
        },
        "audience": {
            "description": "General audience",
            "knowledge_level": "general",
            "age_range": "broad",
            "problems": [],
            "interests": [],
        },
        "goals": ["grow_audience", "build_authority"],
        "offers": [],
        "languages": {
            "primary": "en",
            "enabled": ["en"],
            "arabic_style": "neutral_mashriqi_social",
            "arabic_fallback": "spoken_modern_standard",
            "rules": {},
        },
        "platforms": {name: {"enabled": False, "adaptation": {}} for name in platform_names()},
        "content": {
            "pillars": [],
            "calls_to_action": [],
            "avoid": [],
            "variants": 5,
            "selection_mode": "hybrid",
            "review": True,
            "ask_for_extras": True,
            "recent_topic_memory": True,
        },
        "voice": {
            "configured": False,
            "provider": None,
            "voice_id": None,
            "pace": 1.0,
            "energy": "natural",
            "sentence_pause_ms": 260,
            "paragraph_pause_ms": 520,
            "language_overrides": {},
            "pronunciations": {},
        },
        "visual": {
            "description": "",
            "colors": [],
            "fonts": [],
            "logo": None,
            "fallback_style": "branded_motion_text",
        },
        "automation": {
            "default_mode": "assisted",
            "candidates": 5,
            "minimum_quality_score": 85,
            "maximum_retries": 3,
            "output": "both",
            "extras": {},
            "ask_only_when_relevant": True,
        },
        "research": {
            "fact_check_news": "strict",
            "require_sources_for_factual_claims": True,
            "allow_unconfirmed_reports": False,
        },
        "approval": {
            "script": "major_checkpoint",
            "facts": "critical_only",
            "voice": "automatic",
            "resources": "automatic",
            "final_render": "major_checkpoint",
        },
        "memory": {
            "creative_preferences": {},
            "rejected_patterns": [],
            "profile_suggestions": [],
        },
        "created_at": _now(),
        "updated_at": _now(),
    }


def _normalize(data: dict[str, Any]) -> dict[str, Any]:
    """Migrate a v0.x profile or incomplete YAML into the current schema."""

    name = str(data.get("name") or data.get("account", {}).get("name") or "Account")
    base = default_profile(name)

    def merge(left: dict[str, Any], right: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(left)
        for key, value in right.items():
            if isinstance(value, dict) and isinstance(result.get(key), dict):
                result[key] = merge(result[key], value)
            else:
                result[key] = deepcopy(value)
        return result

    normalized = merge(base, data)
    account = normalized.setdefault("account", {})
    account["name"] = str(account.get("name") or normalized.get("name") or name)
    account["slug"] = slugify(str(account.get("slug") or normalized.get("slug") or account["name"]))
    for key in ("description", "niche", "sub_niches"):
        if key not in account or not account.get(key):
            account[key] = normalized.get(key, base["account"][key])
    normalized["name"] = account["name"]
    normalized["slug"] = account["slug"]
    normalized["description"] = account.get("description", "")
    normalized["niche"] = account.get("niche", "")
    normalized["sub_niches"] = account.get("sub_niches", [])
    normalized["schema_version"] = 2
    return normalized


def _next_history_path(path: Path) -> Path:
    history = path.parent / "history"
    history.mkdir(parents=True, exist_ok=True)
    versions = []
    for existing in history.glob("account-v*.yaml"):
        try:
            versions.append(int(existing.stem.rsplit("v", 1)[1]))
        except (ValueError, IndexError):
            continue
    return history / f"account-v{(max(versions, default=0) + 1):03d}.yaml"


def save(profile: dict[str, Any], workspace: str | Path | None = None, *, version: bool = True) -> Path:
    profile = _normalize(profile)
    profile["updated_at"] = _now()
    path = profile_path(str(profile["slug"]), workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    (path.parent / "assets").mkdir(exist_ok=True)
    if version and path.exists():
        shutil.copy2(path, _next_history_path(path))
    path.write_text(dump_data(profile), encoding="utf-8")
    return path


def _load_path(path: Path) -> dict[str, Any]:
    try:
        if path.suffix.lower() == ".json":
            value = json.loads(path.read_text(encoding="utf-8"))
        else:
            value = load_data(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise ConfigurationError(f"Invalid account at {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ConfigurationError(f"Account at {path} must be a mapping/object.")
    return _normalize(value)


def load(slug: str, workspace: str | Path | None = None) -> dict[str, Any]:
    path = profile_path(slug, workspace)
    if path.exists():
        return _load_path(path)
    legacy = legacy_profile_path(slug, workspace)
    if legacy.exists():
        migrated = _load_path(legacy)
        save(migrated, workspace, version=False)
        return migrated
    raise ConfigurationError(f"Account not found: {slug}")


def list_profiles(workspace: str | Path | None = None) -> list[dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(accounts_dir(workspace).glob("*/account.yaml")):
        try:
            item = _load_path(path)
        except ConfigurationError:
            continue
        result[str(item["slug"])] = item
    for path in sorted(profiles_dir(workspace).glob("*/profile.json")):
        try:
            item = _load_path(path)
        except ConfigurationError:
            continue
        result.setdefault(str(item["slug"]), item)
    return sorted(result.values(), key=lambda item: str(item.get("name", "")).lower())


def active_slug(workspace: str | Path | None = None) -> str | None:
    value = load_config(workspace).get("active_profile") or load_config(workspace).get("active_account")
    return str(value) if value else None


def active(workspace: str | Path | None = None, *, required: bool = True) -> dict[str, Any] | None:
    slug = active_slug(workspace)
    if not slug:
        if required:
            raise ConfigurationError(
                "No ACE account is active. Run 'ace new', 'ace account use NAME', "
                "or add --no-profile for a one-time generation."
            )
        return None
    return load(slug, workspace)


def use(slug: str, workspace: str | Path | None = None) -> dict[str, Any]:
    profile = load(slug, workspace)
    config = load_config(workspace)
    config["active_profile"] = profile["slug"]
    config["active_account"] = profile["slug"]
    save_config(config, workspace)
    return profile


def create(
    name: str,
    *,
    description: str = "",
    niche: str = "",
    audience: str = "General audience",
    primary_language: str = "en",
    enabled_languages: list[str] | None = None,
    enabled_platforms: list[str] | None = None,
    personality: list[str] | None = None,
    goals: list[str] | None = None,
    workspace: str | Path | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    profile = default_profile(name)
    profile["description"] = description
    profile["niche"] = niche
    profile["account"].update({"description": description, "niche": niche})
    profile["audience"]["description"] = audience
    profile["languages"]["primary"] = primary_language
    profile["languages"]["enabled"] = list(dict.fromkeys(enabled_languages or [primary_language]))
    if personality:
        profile["identity"]["personality"] = personality
    if goals:
        profile["goals"] = goals
    selected = set(enabled_platforms or [])
    for platform in profile["platforms"]:
        profile["platforms"][platform]["enabled"] = platform in selected
    save(profile, workspace, version=False)
    if activate:
        use(profile["slug"], workspace)
    return profile


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    answer = input(f"{prompt}{suffix}: ").strip()
    return answer or default


def _choose_many(options: list[str], prompt: str, defaults: list[str] | None = None) -> list[str]:
    defaults = defaults or []
    print(prompt)
    for index, value in enumerate(options, 1):
        marker = "*" if value in defaults else " "
        print(f"  {index}. [{marker}] {value}")
    raw = input("Choose comma-separated numbers (Enter keeps defaults): ").strip()
    if not raw:
        return defaults
    selected: list[str] = []
    for part in raw.split(","):
        try:
            index = int(part.strip())
        except ValueError:
            continue
        if 1 <= index <= len(options):
            selected.append(options[index - 1])
    return selected


def _profile_json_prompt(description: str, name: str) -> str:
    return f"""You are compiling a persistent social-media account profile for ACE.
Return valid JSON only. Do not add markdown. Do not invent private facts.
The profile represents one consistent brand identity across all platforms.

Account name: {name}
User description:
{description}

Return an object with these keys:
name, description, niche, sub_niches, personality, values, audience_description,
audience_knowledge_level, audience_interests, goals, content_pillars, content_avoid,
preferred_vocabulary, calls_to_action, primary_language, enabled_languages,
enabled_platforms, humor_style, explanation_style, visual_description.
Use arrays where appropriate. If information is unknown, use an empty value rather than guessing.
"""


def build_from_description(
    name: str,
    description: str,
    *,
    workspace: str | Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    activate: bool = True,
) -> dict[str, Any]:
    """Use the configured LLM to compile a validated account file.

    A deterministic fallback still creates a useful account when no model is
    ready, so profile setup never becomes an all-or-nothing cloud dependency.
    """

    draft: dict[str, Any] = {}
    try:
        from ace.ai import AIEngine
        from ace.content import _extract_json

        with AIEngine.from_workspace(workspace) as engine:
            result = engine.generate(
                "profile",
                _profile_json_prompt(description, name),
                provider=provider,
                model=model,
                no_fallback=False,
                temperature=0.2,
                max_output_tokens=2400,
            )
        draft = _extract_json(result.text) or {}
    except ACEError:
        draft = {}

    primary = str(draft.get("primary_language") or "en").lower()
    platforms = [str(item).lower() for item in draft.get("enabled_platforms", []) if str(item).lower() in platform_names()]
    if not platforms:
        platforms = ["tiktok", "instagram", "youtube"]
    profile = create(
        str(draft.get("name") or name),
        description=str(draft.get("description") or description),
        niche=str(draft.get("niche") or ""),
        audience=str(draft.get("audience_description") or "General audience"),
        primary_language=primary,
        enabled_languages=[primary, *[str(item).lower() for item in draft.get("enabled_languages", [])]],
        enabled_platforms=platforms,
        personality=[str(item) for item in draft.get("personality", [])] or ["clear", "credible", "human"],
        goals=[str(item) for item in draft.get("goals", [])] or ["grow_audience", "build_authority"],
        workspace=workspace,
        activate=activate,
    )
    profile["sub_niches"] = [str(item) for item in draft.get("sub_niches", [])]
    profile["account"]["sub_niches"] = profile["sub_niches"]
    profile["identity"]["values"] = [str(item) for item in draft.get("values", [])]
    profile["identity"]["preferred_vocabulary"] = [str(item) for item in draft.get("preferred_vocabulary", [])]
    profile["identity"]["humor_style"] = str(draft.get("humor_style") or "")
    profile["identity"]["explanation_style"] = str(draft.get("explanation_style") or "")
    profile["audience"]["knowledge_level"] = str(draft.get("audience_knowledge_level") or "general")
    profile["audience"]["interests"] = [str(item) for item in draft.get("audience_interests", [])]
    profile["content"]["pillars"] = [str(item) for item in draft.get("content_pillars", [])]
    profile["content"]["avoid"] = [str(item) for item in draft.get("content_avoid", [])]
    profile["content"]["calls_to_action"] = [str(item) for item in draft.get("calls_to_action", [])]
    profile["visual"]["description"] = str(draft.get("visual_description") or "")
    save(profile, workspace)
    return profile


def wizard(workspace: str | Path | None = None) -> dict[str, Any]:
    print("ACE account setup")
    print("One account is one consistent brand identity across all its platforms.\n")
    name = _ask("Account name")
    if not name:
        raise ConfigurationError("Account name is required.")
    description = _ask("Describe the account, its niche, audience, personality, and goals")
    use_ai = _ask("Let an AI compile the full editable account file? (Y/n)", "y").lower() in {"", "y", "yes"}
    if use_ai and description:
        profile = build_from_description(name, description, workspace=workspace)
        print(f"AI account draft created: {profile_path(profile['slug'], workspace)}")
    else:
        niche = _ask("Main niche")
        audience = _ask("Target audience", "General audience")
        personality_text = _ask("Personality (comma-separated)", "clear, credible, human")
        personality = [item.strip() for item in personality_text.split(",") if item.strip()]
        primary = _ask("Primary language code", "en").lower()
        extra = _ask("Other language codes (comma-separated)", "")
        languages = [primary, *[item.strip().lower() for item in extra.split(",") if item.strip()]]
        platforms = _choose_many(platform_names(), "Platforms used by this account:", ["tiktok", "instagram", "youtube"])
        goal_options = ["grow_audience", "build_authority", "educate", "sell_products", "sell_services", "entertain"]
        goals = _choose_many(goal_options, "Account goals:", ["grow_audience", "build_authority"])
        profile = create(
            name,
            description=description,
            niche=niche,
            audience=audience,
            primary_language=primary,
            enabled_languages=list(dict.fromkeys(languages)),
            enabled_platforms=platforms,
            personality=personality,
            goals=goals,
            workspace=workspace,
        )

    configure_voice = _ask("Configure/test a voice now? (y/N)", "n").lower() in {"y", "yes"}
    if configure_voice:
        from ace.engines.voice import audition_voice, available_voice_providers

        providers = available_voice_providers(workspace)
        print("Available voice providers:")
        for index, provider in enumerate(providers, 1):
            print(f"  {index}. {provider}")
        raw = _ask("Choose a provider", "1")
        try:
            chosen = providers[max(0, int(raw) - 1)]
        except (ValueError, IndexError):
            chosen = providers[0]
        try:
            manifest = audition_voice(workspace=workspace, provider=chosen)
        except ACEError as exc:
            print(f"Voice setup skipped: {exc}")
        else:
            print(f"Selected voice: {manifest['provider']}/{manifest['selected_voice']}")

    print(f"\nAccount ready: {profile['name']} ({profile['slug']})")
    return load(profile["slug"], workspace)


def edit_profile(slug: str | None = None, workspace: str | Path | None = None) -> Path:
    profile = load(slug, workspace) if slug else active(workspace)
    path = profile_path(str(profile["slug"]), workspace)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        command = [*shlex.split(editor), str(path)]
    elif shutil.which("nano"):
        command = ["nano", str(path)]
    elif shutil.which("vi"):
        command = ["vi", str(path)]
    else:
        print(path)
        return path
    if not sys.stdin.isatty():
        print(path)
        return path
    subprocess.run(command, check=False)
    return path


def validate_profile(profile: dict[str, Any]) -> list[str]:
    problems: list[str] = []
    for key in ("name", "slug", "identity", "audience", "languages", "platforms", "automation"):
        if not profile.get(key):
            problems.append(f"Missing required field: {key}")
    primary = profile.get("languages", {}).get("primary")
    enabled = profile.get("languages", {}).get("enabled", [])
    if primary and primary not in enabled:
        problems.append("Primary language must also be enabled.")
    if not any(value.get("enabled") for value in profile.get("platforms", {}).values() if isinstance(value, dict)):
        problems.append("At least one platform should be enabled.")
    mode = profile.get("automation", {}).get("default_mode", "assisted")
    if mode not in {"manual", "assisted", "auto"}:
        problems.append("automation.default_mode must be manual, assisted, or auto.")
    return problems


def context_text(profile: dict[str, Any] | None) -> str:
    if not profile:
        return "No persistent account profile is being used for this one-time generation."
    safe = deepcopy(profile)
    safe.pop("memory", None)
    return dump_data(safe)


def history(slug: str | None = None, workspace: str | Path | None = None) -> list[Path]:
    account = load(slug, workspace) if slug else active(workspace)
    return sorted(profile_path(str(account["slug"]), workspace).parent.glob("history/account-v*.yaml"))


def rollback(version: int, slug: str | None = None, workspace: str | Path | None = None) -> Path:
    account = load(slug, workspace) if slug else active(workspace)
    path = profile_path(str(account["slug"]), workspace).parent / "history" / f"account-v{version:03d}.yaml"
    if not path.exists():
        raise ConfigurationError(f"Account history version not found: {version}")
    restored = _load_path(path)
    return save(restored, workspace)

# v0.x public API compatibility.
edit = edit_profile
validate = validate_profile
