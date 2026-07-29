from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

from ace.resources_engine import search_news_references
from ace.storage import resolve_generation, write_json


def collect_research(
    generation: str | Path,
    *,
    query: str,
    workspace: str | Path | None = None,
    limit: int = 10,
) -> list[dict]:
    folder = resolve_generation(generation, workspace)
    try:
        resources = search_news_references(query, limit=limit)
    except Exception:
        resources = []
    rows = [asdict(item) for item in resources]
    write_json(folder / "research" / "sources.json", rows)
    brief = folder / "research" / "brief.md"
    lines = ["# Research brief", "", f"Query: {query}", ""]
    for index, item in enumerate(rows, 1):
        lines.append(f"{index}. {item.get('title')} — {item.get('source_url')}")
    brief.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    return rows
