from __future__ import annotations

from pathlib import Path

from ace.content import generate
from ace.project import load


def run(project_path: str | Path, workspace: str | Path | None = None):
    metadata = load(project_path, workspace)
    project = Path(project_path)
    output = project / "content" / "main.md"
    return generate(
        metadata["platform"],
        metadata["content_type"],
        topic=metadata["topic"],
        output=output,
        workspace=workspace,
    )
