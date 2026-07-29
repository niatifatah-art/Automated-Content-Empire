from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from ace.ai import AIEngine
from ace.errors import ConfigurationError
from ace.paths import model_catalog_path, resource_text


def load_catalog(workspace: str | Path | None = None) -> dict[str, Any]:
    path = model_catalog_path(workspace)
    text = path.read_text(encoding="utf-8") if path.exists() else resource_text("model_catalog.json")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ConfigurationError(f"Invalid model catalog at {path}: {exc}") from exc
    if not isinstance(data.get("providers"), dict):
        raise ConfigurationError("Model catalog must define a providers object.")
    return data


def save_catalog(data: dict[str, Any], workspace: str | Path | None = None) -> Path:
    path = model_catalog_path(workspace)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def catalog_models(
    provider: str | None = None,
    *,
    kind: str | None = None,
    workspace: str | Path | None = None,
) -> list[dict[str, Any]]:
    data = load_catalog(workspace)
    rows: list[dict[str, Any]] = []
    for provider_name, provider_data in data["providers"].items():
        if provider and provider_name != provider:
            continue
        for item in provider_data.get("models", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            if kind and item.get("kind") != kind:
                continue
            rows.append({"provider": provider_name, **item})
    return rows


def aliases(workspace: str | Path | None = None) -> dict[str, dict[str, str]]:
    raw = load_catalog(workspace).get("aliases", {})
    return {
        str(name): {"provider": str(value.get("provider")), "model": str(value.get("model"))}
        for name, value in raw.items()
        if isinstance(value, dict) and value.get("provider") and value.get("model")
    }


def resolve_alias(value: str, workspace: str | Path | None = None) -> tuple[str, str] | None:
    target = aliases(workspace).get(value)
    if not target:
        return None
    return target["provider"], target["model"]


def discover(provider: str, config: dict[str, Any]) -> list[str]:
    with AIEngine(config) as engine:
        return engine.list_models(provider)


def edit_catalog(workspace: str | Path | None = None) -> Path:
    path = model_catalog_path(workspace)
    if not path.exists():
        save_catalog(load_catalog(workspace), workspace)
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


def search_models(query: str, config: dict[str, Any], workspace: str | Path | None = None) -> list[dict[str, Any]]:
    """Return curated and live model matches with actionable readiness states."""

    needle = query.lower().strip()
    rows = []
    for item in catalog_models(workspace=workspace):
        haystack = f"{item.get('provider')} {item.get('id')} {item.get('name')} {item.get('kind')}".lower()
        if needle and needle not in haystack:
            continue
        provider = str(item["provider"])
        status, detail = model_readiness(provider, str(item["id"]), config)
        rows.append({**item, "readiness": status, "detail": detail})
    return rows


def model_readiness(provider: str, model: str, config: dict[str, Any]) -> tuple[str, str]:
    provider_config = config.get("providers", {}).get(provider)
    if not isinstance(provider_config, dict):
        return "UNCONFIGURED", "provider is not configured"
    if not provider_config.get("enabled", True):
        return "DISABLED", "enable the provider first"
    key_env = str(provider_config.get("api_key_env") or "")
    if provider_config.get("requires_api_key") and not os.environ.get(key_env, "").strip():
        return "KEY MISSING", f"set {key_env} with 'ace guide'"
    if provider == "ollama":
        try:
            installed = discover(provider, config)
        except Exception as exc:
            return "UNREACHABLE", str(exc)
        if model in {"auto", "auto-small"}:
            return ("READY", f"will select from {len(installed)} installed model(s)") if installed else ("MODEL MISSING", "no Ollama models installed")
        return ("READY", "installed") if model in installed else ("NOT INSTALLED", f"run: ollama pull {model}")
    return "UNTESTED", "credentials/configuration are present; run ace models test"


def installed_models(config: dict[str, Any]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for provider in config.get("providers", {}):
        try:
            for model in discover(provider, config):
                rows.append({"provider": provider, "model": model, "status": "READY"})
        except Exception:
            continue
    return rows


def recommend_models(config: dict[str, Any], workspace: str | Path | None = None) -> dict[str, Any]:
    try:
        installed = discover("ollama", config)
    except Exception as exc:
        installed = []
        ollama_error = str(exc)
    else:
        ollama_error = None
    balanced_preferences = ["qwen3.5:9b", "qwen3:8b", "qwen2.5:latest", "qwen2.5:7b", "llama3:8b", "qwen3.5:4b", "qwen3:4b"]
    fast_preferences = ["qwen3.5:4b", "qwen3:4b", "qwen2.5:3b", "llama3.2:3b", "gemma3:4b", "phi4-mini"]
    balanced = next((item for item in balanced_preferences if item in installed), None)
    fast = next((item for item in fast_preferences if item in installed), None)
    return {
        "installed": installed,
        "balanced": balanced or (installed[0] if installed else None),
        "fast": fast or (installed[0] if installed else None),
        "ollama_error": ollama_error,
        "suggest_install": "qwen3:8b" if not balanced else None,
    }
