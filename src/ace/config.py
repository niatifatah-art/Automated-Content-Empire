from __future__ import annotations

import json
from importlib.resources import files
from pathlib import Path
from typing import Any

from ace.paths import ACEPaths, resolve_paths
from ace.utils import coerce_scalar, deep_merge, nested_get, nested_set, read_json, write_json


def bundled_defaults() -> dict[str, Any]:
    resource = files("ace.data").joinpath("defaults.json")
    return json.loads(resource.read_text(encoding="utf-8"))


def _version_tuple(value: Any) -> tuple[int, ...]:
    parts: list[int] = []
    for item in str(value or "0").split("."):
        digits = "".join(ch for ch in item if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple(parts)


def _enrich_legacy_routes(defaults: dict[str, Any], current: dict[str, Any], merged: dict[str, Any]) -> None:
    """Add the v2.0.1 cloud fallback ladder without deleting custom routes.

    Older ACE configurations often contain only Gemini 3.6 followed directly
    by local Qwen.  A normal deep merge preserves that old list, so upgrading
    the package alone would not fix quota failover.  This migration inserts the
    new cloud routes before existing local routes and retains custom entries.
    """
    if _version_tuple(current.get("version")) >= (2, 0, 1):
        return
    current_routes = current.get("routes", {}) if isinstance(current.get("routes"), dict) else {}
    output: dict[str, Any] = dict(merged.get("routes", {}))
    for task, desired in defaults.get("routes", {}).items():
        existing = current_routes.get(task, [])
        if not isinstance(existing, list):
            existing = []
        desired = desired if isinstance(desired, list) else []
        cloud_desired = [dict(item) for item in desired if not item.get("degraded")]
        local_existing = [dict(item) for item in existing if item.get("degraded") or item.get("provider") == "ollama"]
        cloud_existing = [dict(item) for item in existing if item not in local_existing]
        local_desired = [dict(item) for item in desired if item.get("degraded")]
        combined: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for item in [*cloud_desired, *cloud_existing, *local_existing, *local_desired]:
            key = (str(item.get("provider")), str(item.get("model")))
            if key in seen:
                continue
            seen.add(key)
            combined.append(item)
        output[task] = combined
    merged["routes"] = output


def initialize(workspace: str | Path | None = None, *, force: bool = False, upgrade: bool = False) -> ACEPaths:
    paths = resolve_paths(workspace)
    defaults = bundled_defaults()
    if not paths.config_file.exists() or force:
        write_json(paths.config_file, defaults)
    elif upgrade:
        current = read_json(paths.config_file, {})
        current = current if isinstance(current, dict) else {}
        merged = deep_merge(defaults, current)
        _enrich_legacy_routes(defaults, current, merged)
        merged["version"] = defaults["version"]
        merged["schema_version"] = defaults["schema_version"]
        write_json(paths.config_file, merged)
    if not paths.secrets_file.exists():
        paths.secrets_file.write_text(
            "# ACE secrets — never commit this file\n"
            "# GEMINI_API_KEY_PRIMARY=\n"
            "# GEMINI_API_KEY_BACKUP=\n"
            "# PEXELS_API_KEY=\n"
            "# PIXABAY_API_KEY=\n",
            encoding="utf-8",
        )
        paths.secrets_file.chmod(0o600)
    return paths


def load(workspace: str | Path | None = None) -> dict[str, Any]:
    paths = initialize(workspace)
    defaults = bundled_defaults()
    current = read_json(paths.config_file, {})
    return deep_merge(defaults, current if isinstance(current, dict) else {})


def save(config: dict[str, Any], workspace: str | Path | None = None) -> Path:
    paths = resolve_paths(workspace)
    return write_json(paths.config_file, config)


def get(key: str, workspace: str | Path | None = None, default: Any = None) -> Any:
    return nested_get(load(workspace), key, default)


def set_value(key: str, raw_value: str, workspace: str | Path | None = None) -> Any:
    config = load(workspace)
    value = coerce_scalar(raw_value)
    nested_set(config, key, value)
    save(config, workspace)
    return value
