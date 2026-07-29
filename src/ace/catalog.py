from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ace.errors import CatalogError
from ace.paths import catalog_path, resource_text


def load_catalog(workspace: str | Path | None = None) -> dict[str, Any]:
    path = catalog_path(workspace)
    text = path.read_text(encoding="utf-8") if path.exists() else resource_text("content_catalog.json")
    try:
        catalog = json.loads(text)
    except json.JSONDecodeError as exc:
        raise CatalogError(f"Invalid content catalog: {exc}") from exc
    if not isinstance(catalog.get("platforms"), dict):
        raise CatalogError("Content catalog must define a 'platforms' object.")
    return catalog


def _normalize(value: str) -> str:
    return value.strip().lower().replace("-", "_").replace(" ", "_")


def resolve_platform(name: str, workspace: str | Path | None = None) -> tuple[str, dict[str, Any]]:
    catalog = load_catalog(workspace)
    wanted = _normalize(name)
    for key, platform in catalog["platforms"].items():
        aliases = {_normalize(key), *(_normalize(alias) for alias in platform.get("aliases", []))}
        if wanted in aliases:
            return key, platform
    raise CatalogError(f"Unknown platform '{name}'. Run 'ace content list'.")


def resolve_content_type(
    platform_name: str,
    content_type: str,
    workspace: str | Path | None = None,
) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
    platform_key, platform = resolve_platform(platform_name, workspace)
    wanted = _normalize(content_type)
    for key, specification in platform.get("types", {}).items():
        aliases = {_normalize(key), *(_normalize(alias) for alias in specification.get("aliases", []))}
        if wanted in aliases:
            return platform_key, key, platform, specification
    available = ", ".join(sorted(platform.get("types", {})))
    raise CatalogError(
        f"Unknown content type '{content_type}' for {platform_key}. Available: {available}"
    )


def platform_names(workspace: str | Path | None = None) -> list[str]:
    return sorted(load_catalog(workspace)["platforms"])


def content_types(platform_name: str, workspace: str | Path | None = None) -> list[str]:
    _, platform = resolve_platform(platform_name, workspace)
    return sorted(platform.get("types", {}))


def default_pack(platform_name: str, workspace: str | Path | None = None) -> list[str]:
    _, platform = resolve_platform(platform_name, workspace)
    return list(platform.get("default_pack", []))
