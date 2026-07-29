from __future__ import annotations

import getpass
import os
import shlex
import subprocess
import sys
from pathlib import Path

from ace.config import load as load_config, save as save_config
from ace.errors import ConfigurationError
from ace.models import search_models
from ace.readiness import print_readiness
from ace.secrets import KNOWN_SECRET_KEYS, ensure as ensure_secrets


def _save_secret(key: str, value: str, workspace: str | Path | None) -> None:
    path = ensure_secrets(workspace)
    lines = path.read_text(encoding="utf-8").splitlines()
    replaced = False
    output = []
    for line in lines:
        if line.startswith(f"{key}="):
            output.append(f"{key}={value}")
            replaced = True
        else:
            output.append(line)
    if not replaced:
        output.append(f"{key}={value}")
    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")
    path.chmod(0o600)
    os.environ[key] = value


def configure_api_keys(workspace: str | Path | None = None) -> None:
    providers = [
        ("Gemini", "GEMINI_API_KEY"), ("OpenAI", "OPENAI_API_KEY"),
        ("Anthropic", "ANTHROPIC_API_KEY"), ("OpenRouter", "OPENROUTER_API_KEY"),
        ("Pexels", "PEXELS_API_KEY"), ("Pixabay", "PIXABAY_API_KEY"),
        ("Unsplash", "UNSPLASH_ACCESS_KEY"), ("Openverse", "OPENVERSE_ACCESS_TOKEN"),
    ]
    print("Configure API keys")
    for index, (name, key) in enumerate(providers, 1):
        state = "set" if os.environ.get(key, "").strip() else "missing"
        print(f"  {index}. {name:12} {state}")
    print("  0. Back")
    raw = input("Choose a provider: ").strip()
    try:
        index = int(raw)
    except ValueError:
        return
    if not 1 <= index <= len(providers):
        return
    name, key = providers[index - 1]
    print(f"\n{name}")
    print("  1. Add or replace key")
    print("  2. Remove key")
    print("  3. Show related models")
    action = input("Choose: ").strip()
    if action == "1":
        value = getpass.getpass(f"Enter {key} (hidden): ").strip()
        if value:
            _save_secret(key, value, workspace)
            print(f"✓ {key} saved with protected file permissions.")
    elif action == "2":
        _save_secret(key, "", workspace)
        print(f"✓ {key} removed.")
    elif action == "3":
        config = load_config(workspace)
        for row in search_models(name.lower(), config, workspace):
            print(f"{row['provider']:10} {row['id']:32} {row['readiness']}")


def explain_command(command: str) -> int:
    parts = shlex.split(command)
    if parts and parts[0] == "ace":
        parts = parts[1:]
    # Use the current Python environment, which also works from an editable install.
    return subprocess.run([sys.executable, "-m", "ace.main", *parts, "--help"], check=False).returncode


def run_guide(workspace: str | Path | None = None, topic: str | None = None) -> int:
    if topic:
        lowered = topic.lower()
        if "api" in lowered or "key" in lowered:
            configure_api_keys(workspace)
            return 0
        if "model" in lowered:
            print("Use: ace models search NAME, ace models ready, or ace models recommend")
            return 0
        if "video" in lowered or "incomplete" in lowered:
            print("Use: ace status last, then ace fix last")
            return 0
    while True:
        print("What do you need help with?\n")
        print("  1. Create my first content")
        print("  2. Configure a model")
        print("  3. Configure API keys")
        print("  4. Set up a voice")
        print("  5. Find visual resources")
        print("  6. Fix an incomplete video")
        print("  7. Understand a command")
        print("  8. Configure Autopilot")
        print("  9. Check whether ACE is ready")
        print("  0. Exit")
        answer = input("Choose: ").strip()
        if answer == "0":
            return 0
        if answer == "1":
            print("Run: ace create\nOr: ace create youtube short \"Your topic\" --assisted")
        elif answer == "2":
            print("Run: ace models search qwen\nThen: ace models recommend\nOr: ace model use script local-balanced")
        elif answer == "3":
            configure_api_keys(workspace)
        elif answer == "4":
            print("Run: ace voice providers\nThen: ace voice audition --provider kokoro")
        elif answer == "5":
            print("Run: ace resources find last\nCheck: ace resources list last\nAdd owned files: ace assets add FILE --tags topic")
        elif answer == "6":
            print("Run: ace status last\nThen: ace fix last")
        elif answer == "7":
            command = input("Enter a command, for example 'ace voice audition': ").strip()
            if command:
                explain_command(command)
        elif answer == "8":
            print("Modes: manual, assisted, auto")
            mode = input("Choose default mode: ").strip().lower()
            if mode in {"manual", "assisted", "auto"}:
                config = load_config(workspace)
                config.setdefault("interaction", {})["default_mode"] = mode
                save_config(config, workspace)
                print(f"✓ Default mode set to {mode}.")
        elif answer == "9":
            print_readiness(workspace, live=True)
        print()
