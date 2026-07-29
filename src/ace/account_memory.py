from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace.paths import account_data_dir


def _tokens(text: str) -> set[str]:
    result: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) <= 2:
            continue
        stem = token
        for suffix in ("ing", "ed", "es", "s"):
            if stem.endswith(suffix) and len(stem) - len(suffix) >= 4:
                stem = stem[:-len(suffix)]
                break
        result.add(stem)
    return result


def history_path(slug: str, workspace: str | Path | None = None) -> Path:
    path = account_data_dir(slug, workspace) / "history" / "generations.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def load_history(slug: str, workspace: str | Path | None = None) -> list[dict[str, Any]]:
    path = history_path(slug, workspace)
    if not path.exists():
        return []
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(item, dict):
            rows.append(item)
    return rows


def similar_topics(topic: str, slug: str, workspace: str | Path | None = None, limit: int = 3) -> list[dict[str, Any]]:
    wanted = _tokens(topic)
    matches: list[tuple[float, dict[str, Any]]] = []
    for item in load_history(slug, workspace):
        existing = _tokens(str(item.get("topic", "")))
        if not wanted or not existing:
            continue
        score = len(wanted & existing) / len(wanted | existing)
        if score >= 0.35:
            matches.append((score, item))
    return [{**item, "similarity": round(score, 2)} for score, item in sorted(matches, key=lambda pair: -pair[0])[:limit]]


def record_generation(folder: Path, workspace: str | Path | None = None) -> None:
    metadata_path = folder / "metadata.json"
    if not metadata_path.exists():
        return
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return
    slug = str(metadata.get("profile_slug") or "")
    if not slug or slug == "no-profile":
        return
    row = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "topic": metadata.get("topic"),
        "platform": metadata.get("platform"),
        "content_type": metadata.get("content_type"),
        "folder": str(folder),
        "selected_candidate": metadata.get("selected_candidate"),
    }
    with history_path(slug, workspace).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")
