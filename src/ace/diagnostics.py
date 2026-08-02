from __future__ import annotations

import importlib.util
import shutil
from pathlib import Path
from typing import Any

from ace.accounts import active_slug, load as load_account, validate as validate_account
from ace.config import load as load_config
from ace.graphics import font_path
from ace.providers.router import ProviderRouter
from ace.secrets import ensure_permissions, load as load_secrets


def check(workspace: str | Path | None = None, *, live: bool = False) -> dict[str, Any]:
    config = load_config(workspace)
    secrets = load_secrets(workspace)
    report: dict[str, Any] = {"status": "ready", "checks": []}
    try:
        account = load_account(active_slug(workspace), workspace)
        problems = validate_account(account)
        report["checks"].append({"name": "account", "status": "ready" if not problems else "problem", "detail": account.get("name"), "problems": problems})
    except Exception as exc:
        report["checks"].append({"name": "account", "status": "problem", "detail": str(exc)})
    report["checks"].append({"name": "ffmpeg", "status": "ready" if shutil.which("ffmpeg") and shutil.which("ffprobe") else "problem", "detail": shutil.which("ffmpeg") or "missing"})
    try:
        report["checks"].append({"name": "font", "status": "ready", "detail": font_path()})
    except Exception as exc:
        report["checks"].append({"name": "font", "status": "problem", "detail": str(exc)})
    ensure_permissions(workspace)
    router = ProviderRouter(workspace)
    credentials = router.credential_status()
    cloud_ready = any(row["provider"] != "ollama" and row["configured"] and row["available"] for row in credentials)
    report["checks"].append({"name": "cloud_models", "status": "ready" if cloud_ready else "problem", "detail": credentials})
    ollama_ready = any(row["provider"] == "ollama" and row["available"] for row in credentials)
    report["checks"].append({"name": "local_emergency", "status": "ready" if ollama_ready else "optional", "detail": "degraded mode only; never treated as cloud-equivalent"})
    stock = {name: bool(secrets.get(env)) for name, env in {"pexels": "PEXELS_API_KEY", "pixabay": "PIXABAY_API_KEY", "openverse": "OPENVERSE_ACCESS_TOKEN"}.items()}
    report["checks"].append({"name": "stock_resources", "status": "ready" if any(stock.values()) else "fallback", "detail": stock})
    report["checks"].append({"name": "browser_capture", "status": "ready" if importlib.util.find_spec("playwright") else "optional", "detail": "Playwright installed" if importlib.util.find_spec("playwright") else "install .[browser] for official-page screenshots"})
    report["checks"].append({"name": "voice", "status": "ready" if importlib.util.find_spec("kokoro") else "optional", "detail": "Kokoro installed" if importlib.util.find_spec("kokoro") else "install .[voice]"})
    report["checks"].append({"name": "generated_images", "status": "ready" if secrets.get("GEMINI_API_KEY_PRIMARY") or secrets.get("GEMINI_API_KEY") or secrets.get("OPENAI_API_KEY") else "optional", "detail": config.get("generated_images", {})})
    if live and cloud_ready:
        try:
            result = router.generate("classification", "Reply with exactly: ACE live check passed", temperature=0.0, max_output_tokens=32)
            report["checks"].append({"name": "live_cloud_test", "status": "ready", "detail": f"{result.provider}/{result.model}/{result.credential_name}: {result.text[:80]}"})
        except Exception as exc:
            report["checks"].append({"name": "live_cloud_test", "status": "problem", "detail": str(exc)})
    if any(item["status"] == "problem" for item in report["checks"]):
        report["status"] = "needs_attention"
    return report


def quota_status(workspace: str | Path | None = None) -> list[dict[str, Any]]:
    router = ProviderRouter(workspace)
    rows = router.credential_status()
    for row in rows:
        row["capacity"] = "available" if row.get("available") else "cooldown_or_disabled"
        row["note"] = "ACE tracks observed failures/cooldowns; exact provider quota requires provider-specific response headers or dashboards."
    return rows
