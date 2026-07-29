from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.config import load as load_config, save as save_config
from ace.providers.router import ProviderRouter


ALIASES = {
    "cloud-balanced": ("gemini", "gemini-3.6-flash"),
    "cloud-fast": ("gemini", "gemini-3.5-flash-lite"),
    "cloud-quality": ("openai", "gpt-5-mini"),
    "local-balanced": ("ollama", "auto"),
    "local-fast": ("ollama", "auto-small"),
}


def routes(workspace: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    return load_config(workspace).get("routes", {})


def use(task: str, model_or_alias: str, workspace: str | Path | None = None) -> tuple[str, str]:
    config = load_config(workspace)
    if model_or_alias in ALIASES:
        provider, model = ALIASES[model_or_alias]
    elif "/" in model_or_alias:
        provider, model = model_or_alias.split("/", 1)
    else:
        raise ValueError("Use a named alias or provider/model.")
    current = list(config.setdefault("routes", {}).get(task, []))
    replacement = {"provider": provider, "model": model, "critical": task in {"research", "script", "review", "fact_check", "visual_planning", "quality"}}
    config["routes"][task] = [replacement, *[item for item in current if item.get("provider") != provider or item.get("model") != model]]
    save_config(config, workspace)
    return provider, model


def test(provider: str, model: str, workspace: str | Path | None = None, *, allow_degraded: bool = False) -> str:
    router = ProviderRouter(workspace, allow_degraded=allow_degraded)
    result = router.generate("script", "Reply with exactly: ACE provider test passed", provider=provider, model=model, temperature=0.0, max_output_tokens=512, no_fallback=True)
    return result.text
