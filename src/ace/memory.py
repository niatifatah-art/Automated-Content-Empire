from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.errors import ConfigurationError, ProviderError
from ace.providers.http import request_json


VALID_MODES = ("smart", "low", "performance")


class MemoryManager:
    """Manage local model lifetime for providers ACE can explicitly unload.

    Ollama is currently the only provider with a stable unload API. Other local
    OpenAI-compatible servers remain server-managed and are reported as such.
    """

    def __init__(self, config: dict[str, Any]):
        self.config = config
        memory = config.get("memory", {})
        self.mode = str(memory.get("mode", "smart"))
        if self.mode not in VALID_MODES:
            self.mode = "smart"
        self.smart_keep_alive = memory.get("smart_keep_alive", "5m")
        self.unload_at_end = bool(memory.get("unload_at_pipeline_end", True))
        self.unload_on_error = bool(memory.get("unload_on_error", True))
        self.active: tuple[str, str] | None = None

    @staticmethod
    def is_managed_local(provider_name: str, provider_config: dict[str, Any]) -> bool:
        return str(provider_config.get("type")) == "ollama"

    def request_keep_alive(self, provider_name: str, provider_config: dict[str, Any]) -> Any:
        if not self.is_managed_local(provider_name, provider_config):
            return None
        if self.mode == "low":
            return 0
        if self.mode == "performance":
            return -1
        return self.smart_keep_alive

    def before_target(self, provider_name: str, model: str, provider_config: dict[str, Any]) -> None:
        target_is_local = self.is_managed_local(provider_name, provider_config)
        if self.mode == "smart" and self.active:
            if not target_is_local or self.active != (provider_name, model):
                self.unload(*self.active, ignore_errors=True)
                self.active = None
        if target_is_local and self.mode in {"smart", "performance"}:
            self.active = (provider_name, model)

    def after_target(self, provider_name: str, model: str, provider_config: dict[str, Any]) -> None:
        if self.mode == "low" and self.is_managed_local(provider_name, provider_config):
            self.active = None

    def unload(self, provider_name: str, model: str, *, ignore_errors: bool = False) -> bool:
        provider_config = self.config.get("providers", {}).get(provider_name, {})
        if not isinstance(provider_config, dict) or provider_config.get("type") != "ollama":
            if ignore_errors:
                return False
            raise ConfigurationError(
                f"ACE cannot explicitly unload provider '{provider_name}'. "
                "That provider manages its own memory."
            )
        base = str(provider_config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
        try:
            request_json(
                "POST",
                f"{base}/api/generate",
                payload={"model": model, "prompt": "", "stream": False, "keep_alive": 0},
                timeout=float(provider_config.get("timeout_seconds", 300)),
            )
        except ProviderError:
            if ignore_errors:
                return False
            raise
        if self.active == (provider_name, model):
            self.active = None
        return True

    def unload_all(self, *, ignore_errors: bool = False) -> list[str]:
        unloaded: list[str] = []
        for provider_name, provider_config in self.config.get("providers", {}).items():
            if not isinstance(provider_config, dict) or provider_config.get("type") != "ollama":
                continue
            for item in loaded_models(provider_config):
                model = item.get("name") or item.get("model")
                if not isinstance(model, str):
                    continue
                if self.unload(provider_name, model, ignore_errors=ignore_errors):
                    unloaded.append(f"{provider_name}/{model}")
        self.active = None
        return unloaded

    def close(self, *, failed: bool = False) -> None:
        should_unload = self.mode == "smart" and self.unload_at_end
        if failed and self.unload_on_error:
            should_unload = True
        if should_unload and self.active:
            self.unload(*self.active, ignore_errors=True)
            self.active = None


def loaded_models(provider_config: dict[str, Any]) -> list[dict[str, Any]]:
    base = str(provider_config.get("base_url", "http://127.0.0.1:11434")).rstrip("/")
    raw = request_json(
        "GET",
        f"{base}/api/ps",
        timeout=float(provider_config.get("timeout_seconds", 300)),
    )
    models = raw.get("models", [])
    return [item for item in models if isinstance(item, dict)]


def status(config: dict[str, Any]) -> dict[str, Any]:
    memory = config.get("memory", {})
    result: dict[str, Any] = {
        "mode": memory.get("mode", "smart"),
        "unload_at_pipeline_end": memory.get("unload_at_pipeline_end", True),
        "providers": {},
    }
    for name, provider in config.get("providers", {}).items():
        if not isinstance(provider, dict):
            continue
        if provider.get("type") == "ollama":
            try:
                models = loaded_models(provider)
            except ProviderError as exc:
                result["providers"][name] = {"status": "unavailable", "error": str(exc), "models": []}
            else:
                result["providers"][name] = {"status": "ready", "models": models}
        elif provider.get("type") == "openai_compatible" and not provider.get("requires_api_key", False):
            result["providers"][name] = {"status": "server-managed", "models": []}
    return result
