from __future__ import annotations

from typing import Any

from ace.errors import ConfigurationError
from ace.providers.anthropic import AnthropicProvider
from ace.providers.base import AIProvider
from ace.providers.gemini import GeminiProvider
from ace.providers.ollama import OllamaProvider
from ace.providers.openai_compatible import OpenAICompatibleProvider


_PROVIDER_TYPES: dict[str, type[AIProvider]] = {
    "ollama": OllamaProvider,
    "gemini": GeminiProvider,
    "openai_compatible": OpenAICompatibleProvider,
    "anthropic": AnthropicProvider,
}


def create_provider(name: str, config: dict[str, Any]) -> AIProvider:
    provider_type = str(config.get("type", "")).strip()
    provider_class = _PROVIDER_TYPES.get(provider_type)
    if provider_class is None:
        supported = ", ".join(sorted(_PROVIDER_TYPES))
        raise ConfigurationError(
            f"Unknown provider type '{provider_type}' for '{name}'. Supported: {supported}"
        )
    return provider_class(name, config)


def supported_provider_types() -> list[str]:
    return sorted(_PROVIDER_TYPES)
