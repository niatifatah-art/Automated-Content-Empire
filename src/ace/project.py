from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace.catalog import resolve_content_type, resolve_platform
from ace.errors import ACEError
from ace.paths import projects_dir
from ace.storage import slugify
from ace.profile import active_slug


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def resolve(project: str | Path, workspace: str | Path | None = None) -> Path:
    supplied = Path(project).expanduser()
    if supplied.exists():
        return supplied.resolve()
    candidate = projects_dir(workspace) / str(project)
    if candidate.exists():
        return candidate.resolve()
    raise FileNotFoundError(f"Project not found: {project}")


def create(
    title: str,
    *,
    platform: str = "youtube",
    content_type: str | None = None,
    topic: str | None = None,
    pack: bool = False,
    workspace: str | Path | None = None,
) -> Path:
    platform_key, platform_spec = resolve_platform(platform, workspace)
    selected_type = content_type or str(platform_spec.get("default_type", "post"))
    _, type_key, _, _ = resolve_content_type(platform_key, selected_type, workspace)

    project = projects_dir(workspace) / slugify(title)
    project.mkdir(parents=True, exist_ok=True)
    for folder in (
        "content",
        "scripts",
        "voice",
        "images",
        "videos",
        "exports",
        "logs",
    ):
        (project / folder).mkdir(exist_ok=True)

    metadata = {
        "schema_version": 2,
        "title": title,
        "slug": project.name,
        "topic": topic or title,
        "platform": platform_key,
        "content_type": type_key,
        "pack": pack,
        "profile_slug": active_slug(workspace),
        "status": "created",
        "created_at": _now(),
        "updated_at": _now(),
    }
    save_metadata(project, metadata)
    return project


def save_metadata(project: str | Path, metadata: dict[str, Any]) -> Path:
    path = Path(project) / "project.json"
    metadata["updated_at"] = _now()
    path.write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return path


def load(project: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    path = resolve(project, workspace) / "project.json"
    if not path.exists():
        raise FileNotFoundError(f"project.json not found in {path.parent}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ACEError(f"Invalid project metadata in {path}")
    data.setdefault("topic", data.get("title", "Untitled"))
    data.setdefault("platform", "youtube")
    data.setdefault("content_type", "long_video")
    data.setdefault("pack", False)
    return data


def list_projects(workspace: str | Path | None = None) -> list[tuple[Path, dict[str, Any]]]:
    root = projects_dir(workspace)
    if not root.exists():
        return []
    results: list[tuple[Path, dict[str, Any]]] = []
    for metadata_path in sorted(root.glob("*/project.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict):
            results.append((metadata_path.parent, metadata))
    return results


def status(project: str | Path, workspace: str | Path | None = None) -> dict[str, bool]:
    path = resolve(project, workspace)
    return {
        "content": any((path / "content").glob("*.md")),
        "script": any((path / "scripts").glob("*.md")),
        "voice": any((path / "voice").glob("*")),
        "images": any((path / "images").glob("*")),
        "video": any((path / "videos").glob("*")),
    }
