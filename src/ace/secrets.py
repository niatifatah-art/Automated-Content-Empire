from __future__ import annotations

import os
import stat
from pathlib import Path
from typing import Iterable

from ace.paths import resolve_paths


def parse_env_file(path: str | Path) -> dict[str, str]:
    result: dict[str, str] = {}
    target = Path(path)
    if not target.exists():
        return result
    for raw in target.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        result[key.strip()] = value
    return result


def load(workspace: str | Path | None = None) -> dict[str, str]:
    paths = resolve_paths(workspace)
    file_values = parse_env_file(paths.secrets_file)
    merged = dict(file_values)
    for key, value in os.environ.items():
        if key.endswith("_API_KEY") or key.endswith("_TOKEN") or key.startswith("GEMINI_API_KEY"):
            merged[key] = value
    return merged


def get(name: str, workspace: str | Path | None = None) -> str | None:
    value = load(workspace).get(name)
    return value if value else None


def status(names: Iterable[str], workspace: str | Path | None = None) -> dict[str, bool]:
    values = load(workspace)
    return {name: bool(values.get(name)) for name in names}


def ensure_permissions(workspace: str | Path | None = None) -> bool:
    path = resolve_paths(workspace).secrets_file
    if not path.exists():
        return False
    current = stat.S_IMODE(path.stat().st_mode)
    if current != 0o600:
        path.chmod(0o600)
    return True
