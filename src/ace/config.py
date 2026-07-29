from __future__ import annotations

import json
import shutil
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace.errors import ConfigurationError
from ace.paths import (
    accounts_dir,
    assets_dir,
    cache_home,
    catalog_path,
    config_home,
    config_path,
    content_dir,
    data_home,
    logs_dir,
    model_catalog_path,
    models_dir,
    profiles_dir,
    projects_dir,
    prompts_dir,
    resource_text,
    workspace_root,
)
from ace.secrets import ensure as ensure_secrets


def default_config() -> dict[str, Any]:
    return json.loads(resource_text("default_config.json"))


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = deepcopy(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def _migrate_legacy(config: dict[str, Any]) -> dict[str, Any]:
    if int(config.get("schema_version", 0) or 0) >= 3:
        return config
    migrated = default_config()
    if isinstance(config.get("providers"), dict):
        migrated["providers"] = _deep_merge(migrated["providers"], config["providers"])
    if isinstance(config.get("routes"), dict):
        migrated["routes"] = _deep_merge(migrated["routes"], config["routes"])
    legacy_model = config.get("ai_model")
    if isinstance(legacy_model, str) and legacy_model.strip():
        target = {"provider": "ollama", "model": legacy_model.strip()}
        for task in ("default", "writing", "script", "review"):
            migrated["routes"][task] = [target]
    for key in (
        "content_language",
        "default_audience",
        "default_tone",
        "generation",
        "storage",
        "voice",
    ):
        if key in config:
            if isinstance(config[key], dict) and isinstance(migrated.get(key), dict):
                migrated[key] = _deep_merge(migrated[key], config[key])
            else:
                migrated[key] = config[key]
    return migrated


def load(workspace: str | Path | None = None) -> dict[str, Any]:
    path = config_path(workspace)
    if not path.exists():
        return default_config()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ConfigurationError(f"Cannot read configuration at {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Configuration at {path} must contain a JSON object.")
    return _deep_merge(default_config(), _migrate_legacy(raw))


def save(config: dict[str, Any], workspace: str | Path | None = None) -> Path:
    path = config_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def initialize(workspace: str | Path | None = None, force: bool = False) -> Path:
    root = workspace_root(workspace)
    for folder in (
        config_home(workspace),
        prompts_dir(workspace),
        accounts_dir(workspace),
        profiles_dir(workspace),
        data_home(workspace),
        content_dir(workspace),
        projects_dir(workspace),
        assets_dir(workspace),
        logs_dir(workspace),
        models_dir(workspace),
        cache_home(workspace),
    ):
        folder.mkdir(parents=True, exist_ok=True)

    defaults = {
        config_path(workspace): resource_text("default_config.json"),
        catalog_path(workspace): resource_text("content_catalog.json"),
        model_catalog_path(workspace): resource_text("model_catalog.json"),
    }
    for path, text in defaults.items():
        if force or not path.exists():
            path.write_text(text.rstrip() + "\n", encoding="utf-8")

    for name in ("content.txt", "review.txt", "variants.txt", "selection.txt", "localize.txt", "profile.txt", "tts.txt", "quality.txt", "fact_check.txt"):
        prompt_path = prompts_dir(workspace) / name
        try:
            text = resource_text(f"prompts/{name}")
        except FileNotFoundError:
            continue
        if force or not prompt_path.exists():
            prompt_path.write_text(text.rstrip() + "\n", encoding="utf-8")

    ensure_secrets(workspace)
    return root


def upgrade(workspace: str | Path | None = None) -> dict[str, Path]:
    """Upgrade shipped catalogs/prompts while preserving user settings and accounts.

    Existing editable system files are copied to a timestamped backup first.
    Secrets and accounts are never overwritten. The user's configuration is
    deep-merged with the v1.7 defaults, then saved with the current schema.
    """

    initialize(workspace)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup = config_home(workspace) / "backups" / f"upgrade-{stamp}"
    backup.mkdir(parents=True, exist_ok=True)

    candidates = [config_path(workspace), catalog_path(workspace), model_catalog_path(workspace)]
    candidates.extend(sorted(prompts_dir(workspace).glob("*.txt")))
    for source in candidates:
        if not source.exists():
            continue
        relative = source.relative_to(config_home(workspace))
        destination = backup / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    merged = load(workspace)
    shipped = default_config()
    merged["schema_version"] = shipped.get("schema_version", merged.get("schema_version"))
    save(merged, workspace)
    catalog_path(workspace).write_text(resource_text("content_catalog.json").rstrip() + "\n", encoding="utf-8")
    model_catalog_path(workspace).write_text(resource_text("model_catalog.json").rstrip() + "\n", encoding="utf-8")
    for name in ("content.txt", "review.txt", "variants.txt", "selection.txt", "localize.txt", "profile.txt", "tts.txt", "quality.txt", "fact_check.txt"):
        (prompts_dir(workspace) / name).write_text(
            resource_text(f"prompts/{name}").rstrip() + "\n", encoding="utf-8"
        )
    ensure_secrets(workspace)
    return {"root": workspace_root(workspace), "backup": backup, "config": config_path(workspace)}


def show(workspace: str | Path | None = None) -> None:
    print(json.dumps(load(workspace), indent=2, ensure_ascii=False))


def get_value(config: dict[str, Any], dotted_key: str) -> Any:
    current: Any = config
    for part in dotted_key.split("."):
        if not isinstance(current, dict) or part not in current:
            raise ConfigurationError(f"Unknown configuration key: {dotted_key}")
        current = current[part]
    return current


def set_value(config: dict[str, Any], dotted_key: str, value: Any) -> None:
    parts = dotted_key.split(".")
    current: dict[str, Any] = config
    for part in parts[:-1]:
        child = current.get(part)
        if child is None:
            child = {}
            current[part] = child
        if not isinstance(child, dict):
            raise ConfigurationError(f"Cannot set child value below '{part}'.")
        current = child
    current[parts[-1]] = value


def parse_cli_value(value: str) -> Any:
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value
