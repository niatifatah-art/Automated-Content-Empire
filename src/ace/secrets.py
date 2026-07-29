from __future__ import annotations

import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

from ace.paths import secrets_path


KNOWN_SECRET_KEYS = (
    "GEMINI_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "OPENROUTER_API_KEY",
    "PEXELS_API_KEY",
    "PIXABAY_API_KEY",
    "OPENVERSE_ACCESS_TOKEN",
    "UNSPLASH_ACCESS_KEY",
    "HF_TOKEN",
    "ELEVENLABS_API_KEY",
)


def ensure(workspace: str | Path | None = None) -> Path:
    path = secrets_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        lines = [
            "# ACE API secrets. Never commit this file.",
            "# Add only the providers you use.",
            "",
            *(f"{key}=" for key in KNOWN_SECRET_KEYS),
            "",
        ]
        path.write_text("\n".join(lines), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


def load(workspace: str | Path | None = None) -> Path:
    path = ensure(workspace)
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key:
            os.environ.setdefault(key, value)
    return path


def masked_status(workspace: str | Path | None = None) -> dict[str, str]:
    load(workspace)
    result: dict[str, str] = {}
    for key in KNOWN_SECRET_KEYS:
        value = os.environ.get(key, "").strip()
        if not value:
            result[key] = "not set"
        elif len(value) <= 8:
            result[key] = "set (hidden)"
        else:
            result[key] = f"set ({value[:3]}…{value[-4:]})"
    return result


def edit(workspace: str | Path | None = None) -> Path:
    path = ensure(workspace)
    editor = os.environ.get("VISUAL") or os.environ.get("EDITOR")
    if editor:
        command = [*shlex.split(editor), str(path)]
    elif shutil.which("nano"):
        command = ["nano", str(path)]
    elif shutil.which("vi"):
        command = ["vi", str(path)]
    else:
        print(path)
        return path
    if not sys.stdin.isatty():
        print(path)
        return path
    subprocess.run(command, check=False)
    return path
