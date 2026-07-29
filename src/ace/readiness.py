from __future__ import annotations

import importlib.util
import os
import shutil
from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.models import model_readiness, recommend_models
from ace.profile import active as active_account
from ace.secrets import masked_status


def _voice_state(config: dict[str, Any], account: dict[str, Any] | None) -> tuple[str, str]:
    voice = (account or {}).get("voice", {})
    if voice.get("configured"):
        provider = str(voice.get("provider"))
        model = str(voice.get("voice_id"))
        if provider == "kokoro" and importlib.util.find_spec("kokoro") is None:
            return "NOT INSTALLED", "Kokoro selected; install ACE voice extras"
        if provider == "pocket_tts" and importlib.util.find_spec("pocket_tts") is None:
            return "NOT INSTALLED", "Pocket TTS selected; install pocket-tts extras"
        if provider == "piper" and shutil.which("piper") is None:
            return "NOT INSTALLED", "Piper selected; install piper and a voice model"
        if provider == "openai_tts" and not os.environ.get("OPENAI_API_KEY", "").strip():
            return "KEY MISSING", "OpenAI TTS selected; add OPENAI_API_KEY"
        return "READY", f"{provider}/{model}"
    return "NOT CONFIGURED", "run ace voice audition"


def inspect_readiness(workspace: str | Path | None = None, *, live: bool = True) -> dict[str, Any]:
    config = load_config(workspace)
    account = active_account(workspace, required=False)
    rows: list[dict[str, str]] = []
    rows.append({"area": "Account", "item": "active account", "status": "READY" if account else "MISSING", "detail": (account or {}).get("name", "run ace new")})
    rows.append({"area": "System", "item": "FFmpeg", "status": "READY" if shutil.which("ffmpeg") else "NOT INSTALLED", "detail": shutil.which("ffmpeg") or "sudo apt install ffmpeg"})
    rows.append({"area": "System", "item": "Ollama", "status": "READY" if shutil.which("ollama") else "NOT INSTALLED", "detail": shutil.which("ollama") or "install Ollama"})
    secrets = masked_status(workspace)
    for task in ("script", "review", "research", "quality"):
        route = config.get("routes", {}).get(task, [])
        for index, target in enumerate(route[:2], 1):
            if not isinstance(target, dict):
                continue
            provider, model = str(target.get("provider")), str(target.get("model"))
            if live or provider != "ollama":
                status, detail = model_readiness(provider, model, config)
            else:
                status, detail = "UNTESTED", "run ace check --live"
            rows.append({"area": "Model", "item": f"{task} #{index}: {provider}/{model}", "status": status, "detail": detail})
    voice_status, voice_detail = _voice_state(config, account)
    rows.append({"area": "Voice", "item": "account voice", "status": voice_status, "detail": voice_detail})
    publishable = []
    if account:
        from ace.assets import load_index
        publishable = [item for item in load_index(str(account["slug"]), workspace) if item.get("status") == "publishable"]
    media_key = any("set (" in secrets.get(key, "") for key in ("PEXELS_API_KEY", "PIXABAY_API_KEY", "UNSPLASH_ACCESS_KEY", "OPENVERSE_ACCESS_TOKEN"))
    rows.append({
        "area": "Resources", "item": "publishable visuals", "status": "READY" if publishable or media_key else "FALLBACK ONLY",
        "detail": f"{len(publishable)} account asset(s)" if publishable else "branded fallback available; add stock API keys or account assets",
    })
    recommendations = recommend_models(config, workspace) if live else {}
    ready_for = {
        "scripts": any(row["area"] == "Model" and row["item"].startswith("script") and row["status"] == "READY" for row in rows),
        "narration": voice_status == "READY",
        "editing_package": bool(shutil.which("ffmpeg")),
        "complete_video": bool(shutil.which("ffmpeg")) and voice_status == "READY",
    }
    return {"rows": rows, "ready_for": ready_for, "recommendations": recommendations}


def print_readiness(workspace: str | Path | None = None, *, live: bool = True) -> bool:
    report = inspect_readiness(workspace, live=live)
    print("ACE readiness")
    print("-" * 76)
    for row in report["rows"]:
        print(f"{row['area']:10} {row['status']:15} {row['item']} — {row['detail']}")
    print("\nReady for:")
    for name, ready in report["ready_for"].items():
        print(f"  {'✓' if ready else '✗'} {name.replace('_', ' ')}")
    return report["ready_for"]["scripts"]
