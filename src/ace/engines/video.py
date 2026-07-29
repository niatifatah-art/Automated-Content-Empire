"""Final-video engine backed by ACE editing plans and FFmpeg."""
from __future__ import annotations

from pathlib import Path

from ace.editing import create_package, render, validate_media


def run(
    generation: str | Path,
    *,
    workspace: str | Path | None = None,
    preview: bool = False,
) -> Path:
    create_package(generation, workspace=workspace)
    return render(generation, workspace=workspace, preview=preview)


__all__ = ["run", "create_package", "render", "validate_media"]
