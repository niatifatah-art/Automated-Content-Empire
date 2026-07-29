from __future__ import annotations

import os

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ace.config import load
from ace.errors import AllProvidersFailed, ConfigurationError, ProviderError
from ace.memory import MemoryManager
from ace.providers import create_provider
from ace.providers.base import GenerationRequest


@dataclass(frozen=True)
class ModelTarget:
    provider: str
    model: str


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    task: str
    attempts: tuple[str, ...]


class AIEngine:
    def __init__(self, config: dict[str, Any]):
        self.config = config
        self.memory = MemoryManager(config)
        self._closed = False
        self._model_cache: dict[str, list[str]] = {}

    @classmethod
    def from_workspace(cls, workspace: str | Path | None = None) -> "AIEngine":
        return cls(load(workspace))

    def __enter__(self) -> "AIEngine":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close(failed=exc is not None)

    def close(self, *, failed: bool = False) -> None:
        if not self._closed:
            self.memory.close(failed=failed)
            self._closed = True

    def _route(self, task: str) -> list[ModelTarget]:
        routes = self.config.get("routes", {})
        raw_route = routes.get(task) or routes.get("default") or []
        targets: list[ModelTarget] = []
        for item in raw_route:
            if not isinstance(item, dict):
                continue
            provider = item.get("provider")
            model = item.get("model")
            if isinstance(provider, str) and isinstance(model, str):
                targets.append(ModelTarget(provider=provider, model=model))
        if not targets:
            raise ConfigurationError(f"No model route is configured for task '{task}' or 'default'.")
        return targets

    def route(self, task: str) -> tuple[ModelTarget, ...]:
        return tuple(self._route(task))

    def _targets(
        self,
        task: str,
        provider: str | None,
        model: str | None,
        no_fallback: bool,
    ) -> list[ModelTarget]:
        route = self._route(task)
        if provider is None and model is None:
            return route[:1] if no_fallback else route
        if not provider or not model:
            raise ConfigurationError("--provider and --model must be used together.")
        selected = ModelTarget(provider=provider, model=model)
        if no_fallback:
            return [selected]
        return [selected, *(target for target in route if target != selected)]


    def _resolve_dynamic_model(self, provider_name: str, model: str, provider_config: dict[str, Any], adapter: Any | None = None) -> str:
        if provider_name != "ollama" or model not in {"auto", "auto-small"}:
            return model
        installed = self._model_cache.get(provider_name)
        if installed is None:
            candidate = adapter or create_provider(provider_name, provider_config)
            list_models = getattr(candidate, "list_models", None)
            if not callable(list_models):
                # Lightweight test/dry-run adapters may not implement discovery.
                # Keep the symbolic model; real Ollama adapters always discover.
                return model
            installed = list_models()
            self._model_cache[provider_name] = installed
        if not installed:
            raise ConfigurationError(
                "No Ollama models are installed. Run 'ace models recommend' or 'ollama pull qwen3:8b'."
            )
        normalized = {item.lower(): item for item in installed}
        if model == "auto-small":
            preferences = [
                "qwen3.5:4b", "qwen3:4b", "qwen2.5:3b", "llama3.2:3b",
                "gemma3:4b", "phi4-mini", "qwen2.5:latest", "llama3:8b",
            ]
        else:
            preferences = [
                "qwen3.5:9b", "qwen3:8b", "qwen2.5:latest", "qwen2.5:7b",
                "llama3:8b", "qwen3.5:4b", "qwen3:4b", "gemma3:4b", "phi4-mini",
            ]
        for preferred in preferences:
            if preferred in normalized:
                return normalized[preferred]
        # Prefer an 8/9/7B model for balanced work, then any installed model.
        if model == "auto":
            for item in installed:
                lowered = item.lower()
                if any(size in lowered for size in (":9b", ":8b", ":7b")):
                    return item
        else:
            for item in installed:
                lowered = item.lower()
                if any(size in lowered for size in (":1b", ":2b", ":3b", ":4b", "mini")):
                    return item
        return installed[0]

    def generate(
        self,
        task: str,
        prompt: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        no_fallback: bool = False,
        temperature: float | None = None,
        max_output_tokens: int | None = None,
    ) -> GenerationResult:
        if not prompt.strip():
            raise ConfigurationError("The prompt cannot be empty.")
        if self._closed:
            raise ConfigurationError("This AI session has already been closed.")

        generation = self.config.get("generation", {})
        request_temperature = float(generation.get("temperature", 0.7) if temperature is None else temperature)
        request_tokens = int(generation.get("max_output_tokens", 4096) if max_output_tokens is None else max_output_tokens)

        attempts: list[str] = []
        provider_configs = self.config.get("providers", {})

        for target in self._targets(task, provider, model, no_fallback):
            provider_config = provider_configs.get(target.provider)
            initial_label = f"{target.provider}/{target.model}"
            if not isinstance(provider_config, dict):
                attempts.append(f"{initial_label}: provider is not configured")
                continue
            if not provider_config.get("enabled", True):
                attempts.append(f"{initial_label}: provider is disabled")
                continue
            if os.environ.get("ACE_FREE_ONLY", "").lower() in {"1", "true", "yes"} and provider_config.get("paid", False):
                attempts.append(f"{initial_label}: skipped by free/local-only policy")
                continue

            label = initial_label
            try:
                adapter = create_provider(target.provider, provider_config)
                validate = getattr(adapter, "validate", None)
                if callable(validate):
                    validate()
                resolved_model = self._resolve_dynamic_model(
                    target.provider, target.model, provider_config, adapter
                )
                label = f"{target.provider}/{resolved_model}"
                self.memory.before_target(target.provider, resolved_model, provider_config)
                response = adapter.generate(
                    GenerationRequest(
                        prompt=prompt,
                        model=resolved_model,
                        temperature=request_temperature,
                        max_output_tokens=request_tokens,
                        keep_alive=self.memory.request_keep_alive(target.provider, provider_config),
                    )
                )
                self.memory.after_target(target.provider, resolved_model, provider_config)
            except (ProviderError, ConfigurationError) as exc:
                attempts.append(f"{label}: {exc}")
                continue

            text = response.text.strip()
            if not text:
                attempts.append(f"{label}: empty response")
                continue
            return GenerationResult(
                text=text,
                provider=target.provider,
                model=resolved_model,
                task=task,
                attempts=tuple(attempts),
            )

        raise AllProvidersFailed(task, attempts)

    def list_models(self, provider_name: str) -> list[str]:
        provider_configs = self.config.get("providers", {})
        provider_config = provider_configs.get(provider_name)
        if not isinstance(provider_config, dict):
            raise ConfigurationError(f"Unknown provider '{provider_name}'.")
        provider = create_provider(provider_name, provider_config)
        return provider.list_models()

    def test_provider(self, provider_name: str, model: str) -> GenerationResult:
        try:
            return self.generate(
                "default",
                "Reply with exactly: ACE provider test passed",
                provider=provider_name,
                model=model,
                no_fallback=True,
                temperature=0,
                max_output_tokens=32,
            )
        finally:
            self.close()


def ask(
    model: str,
    prompt: str,
    *,
    provider: str = "ollama",
    workspace: str | Path | None = None,
) -> str:
    with AIEngine.from_workspace(workspace) as engine:
        result = engine.generate(
            "default",
            prompt,
            provider=provider,
            model=model,
            no_fallback=True,
        )
    print(result.text)
    return result.text


def get_models(provider: str = "ollama", workspace: str | Path | None = None) -> list[str]:
    with AIEngine.from_workspace(workspace) as engine:
        return engine.list_models(provider)


def list_models(
    default_model: str | None = None,
    provider: str = "ollama",
    workspace: str | Path | None = None,
) -> None:
    models = get_models(provider, workspace)
    print(f"ACE Models — {provider}")
    print("-" * 40)
    if not models:
        print("No models reported by this provider.")
        return
    for model in models:
        marker = "★" if model == default_model else "✓"
        print(f"{marker} {model}")
