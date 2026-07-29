"""Visual-resource engine for ACE v1.7.

It searches account-owned and strictly reusable media. When no reusable file is
available the renderer uses ACE's branded motion-graphics fallback rather than
a black frame or an unlicensed download.
"""
from __future__ import annotations

from pathlib import Path

from ace.resources_engine import Resource, collect_for_generation


def run(
    generation: str | Path,
    *,
    workspace: str | Path | None = None,
    query: str | None = None,
    limit: int | None = None,
) -> list[Resource]:
    return collect_for_generation(generation, workspace=workspace, query=query, limit=limit)
