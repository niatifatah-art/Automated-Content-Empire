from __future__ import annotations

import json
import mimetypes
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace.errors import ConfigurationError
from ace.paths import account_data_dir, assets_dir
from ace.storage import file_sha256, slugify, write_json


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def library_dir(profile_slug: str, workspace: str | Path | None = None) -> Path:
    # v1.7 keeps reusable media inside the account data folder. Migrate the
    # old global asset directory lazily so upgrades do not lose files.
    path = account_data_dir(profile_slug, workspace) / "assets"
    legacy = assets_dir(workspace) / profile_slug
    if not path.exists() and legacy.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(legacy, path, dirs_exist_ok=True)
    path.mkdir(parents=True, exist_ok=True)
    return path


def index_path(profile_slug: str, workspace: str | Path | None = None) -> Path:
    return library_dir(profile_slug, workspace) / "index.json"


def load_index(profile_slug: str, workspace: str | Path | None = None) -> list[dict[str, Any]]:
    path = index_path(profile_slug, workspace)
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def save_index(profile_slug: str, items: list[dict[str, Any]], workspace: str | Path | None = None) -> Path:
    return write_json(index_path(profile_slug, workspace), items)


def _asset_type(path: Path) -> str:
    mime, _ = mimetypes.guess_type(path.name)
    if mime:
        return mime.split("/", 1)[0]
    return "file"


def add(
    source: str | Path,
    profile_slug: str,
    *,
    tags: list[str] | None = None,
    collection: str | None = None,
    license_name: str = "user_owned",
    workspace: str | Path | None = None,
) -> dict[str, Any]:
    source_path = Path(source).expanduser().resolve()
    if not source_path.is_file():
        raise FileNotFoundError(f"Asset not found: {source}")
    digest = file_sha256(source_path)
    items = load_index(profile_slug, workspace)
    existing = next((item for item in items if item.get("sha256") == digest), None)
    if existing:
        return existing
    kind = _asset_type(source_path)
    destination_dir = library_dir(profile_slug, workspace) / f"{kind}s"
    destination_dir.mkdir(parents=True, exist_ok=True)
    destination = destination_dir / f"{digest[:12]}-{source_path.name}"
    shutil.copy2(source_path, destination)
    item = {
        "id": f"asset-{digest[:12]}",
        "filename": destination.name,
        "path": str(destination),
        "type": kind,
        "tags": sorted(set(tags or [])),
        "collection": collection,
        "source": "user",
        "license": license_name,
        "status": "publishable",
        "sha256": digest,
        "added_at": _now(),
    }
    items.append(item)
    save_index(profile_slug, items, workspace)
    return item


def import_folder(
    source: str | Path,
    profile_slug: str,
    *,
    tags: list[str] | None = None,
    collection: str | None = None,
    workspace: str | Path | None = None,
) -> list[dict[str, Any]]:
    folder = Path(source).expanduser().resolve()
    if not folder.is_dir():
        raise FileNotFoundError(f"Folder not found: {source}")
    results: list[dict[str, Any]] = []
    for path in sorted(folder.rglob("*")):
        if path.is_file():
            results.append(add(path, profile_slug, tags=tags, collection=collection, workspace=workspace))
    return results


def search(
    query: str,
    profile_slug: str,
    *,
    asset_type: str | None = None,
    tag: str | None = None,
    workspace: str | Path | None = None,
) -> list[dict[str, Any]]:
    terms = {term.lower() for term in query.split() if term.strip()}
    results: list[tuple[int, dict[str, Any]]] = []
    for item in load_index(profile_slug, workspace):
        if asset_type and item.get("type") != asset_type:
            continue
        tags = {str(value).lower() for value in item.get("tags", [])}
        if tag and tag.lower() not in tags:
            continue
        haystack = " ".join(
            [str(item.get("filename", "")), str(item.get("collection", "")), " ".join(tags)]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if not terms or score:
            results.append((score, item))
    return [item for _, item in sorted(results, key=lambda pair: (-pair[0], pair[1].get("filename", "")))]


def get(asset_id: str, profile_slug: str, workspace: str | Path | None = None) -> dict[str, Any]:
    item = next((item for item in load_index(profile_slug, workspace) if item.get("id") == asset_id), None)
    if item is None:
        raise ConfigurationError(f"Unknown asset: {asset_id}")
    return item
