from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from ace.accounts import active_slug
from ace.paths import resolve_paths
from ace.utils import ensure_dir, read_json, slugify, write_json


def create_generation(
    platform: str,
    content_type: str,
    topic: str,
    *,
    account_slug: str | None = None,
    workspace: str | Path | None = None,
) -> Path:
    slug = account_slug or active_slug(workspace)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    folder = ensure_dir(resolve_paths(workspace).content_dir / slug / slugify(platform) / slugify(content_type) / f"{stamp}-{slugify(topic, 54)}")
    for name in (
        "research",
        "script",
        "quality",
        "voice",
        "audio",
        "evidence/article-cards",
        "evidence/webpage-captures",
        "evidence/social-posts",
        "visuals/generated",
        "visuals/stock",
        "resources/publishable",
        "resources/attribution-required",
        "resources/reference-only",
        "captions",
        "subtitles",
        "editing",
        "licenses",
        "exports",
        "temp",
        "publishing",
    ):
        ensure_dir(folder / name)
    write_json(
        folder / "metadata.json",
        {
            "schema_version": 3,
            "account_slug": slug,
            "platform": slugify(platform),
            "content_type": slugify(content_type),
            "topic": topic,
            "created_at": datetime.now().astimezone().isoformat(),
        },
    )
    return folder


def generations(workspace: str | Path | None = None, *, account_slug: str | None = None) -> list[Path]:
    root = resolve_paths(workspace).content_dir
    if account_slug:
        root = root / account_slug
    candidates = [path for path in root.glob("**/metadata.json") if path.is_file()]
    return sorted((path.parent for path in candidates), key=lambda path: path.stat().st_mtime, reverse=True)


def resolve_generation(value: str | Path, workspace: str | Path | None = None) -> Path:
    if isinstance(value, Path) or str(value) not in {"last", "recent"}:
        path = Path(value).expanduser()
        if path.exists():
            return path.resolve()
        # Allow a generation folder name.
        for candidate in generations(workspace):
            if candidate.name == str(value):
                return candidate
        raise FileNotFoundError(f"Generation not found: {value}")
    recent = generations(workspace)
    if not recent:
        raise FileNotFoundError("No ACE generations exist yet.")
    return recent[0]


def metadata(folder: str | Path) -> dict[str, Any]:
    return read_json(Path(folder) / "metadata.json", {}) or {}


def update_metadata(folder: str | Path, **values: Any) -> Path:
    path = Path(folder) / "metadata.json"
    current = read_json(path, {}) or {}
    current.update(values)
    return write_json(path, current)
