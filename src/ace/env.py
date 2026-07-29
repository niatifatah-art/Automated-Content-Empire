from __future__ import annotations

from pathlib import Path

from ace.secrets import load as load_secrets


def load_env(workspace: str | Path | None = None) -> None:
    """Load ACE's protected secrets file without overriding process variables."""

    load_secrets(workspace)
