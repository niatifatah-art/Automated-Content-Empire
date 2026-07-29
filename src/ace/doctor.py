from __future__ import annotations

import os
import platform
import shutil
from pathlib import Path

from ace.ai import AIEngine
from ace.config import load
from ace.paths import config_path, workspace_root


def run(workspace: str | Path | None = None, live: bool = False) -> bool:
    root = workspace_root(workspace)
    config = load(workspace)
    healthy = True

    print("ACE Diagnostics")
    print("-" * 60)
    print(f"Python        : {platform.python_version()}")
    print(f"Workspace     : {root}")
    print(f"Configuration : {'Found' if config_path(workspace).exists() else 'Using packaged defaults'}")

    for executable in ("git", "ollama", "ffmpeg", "piper"):
        state = shutil.which(executable)
        print(f"{executable.capitalize():13}: {state or 'Not found'}")

    print("\nText providers")
    print("-" * 60)
    engine = AIEngine(config)
    for name, provider in config.get("providers", {}).items():
        if not isinstance(provider, dict):
            continue
        enabled = bool(provider.get("enabled", True))
        provider_type = provider.get("type", "unknown")
        key_env = provider.get("api_key_env")
        configured = not key_env or bool(os.environ.get(str(key_env))) or not provider.get(
            "requires_api_key", provider_type in {"gemini", "anthropic"}
        )
        status = "enabled" if enabled else "disabled"
        if key_env and not configured:
            status += f", missing {key_env}"
        print(f"{name:13}: {provider_type} ({status})")

        if live and enabled:
            try:
                models = engine.list_models(name)
            except Exception as exc:
                healthy = False
                print(f"  live check   : FAILED — {exc}")
            else:
                detail = f"{len(models)} model(s)" if models else "reachable"
                print(f"  live check   : OK — {detail}")

    print("\nModel routes")
    print("-" * 60)
    for task, route in config.get("routes", {}).items():
        labels = [
            f"{item.get('provider')}/{item.get('model')}"
            for item in route
            if isinstance(item, dict)
        ]
        print(f"{task:13}: {' -> '.join(labels)}")

    return healthy
