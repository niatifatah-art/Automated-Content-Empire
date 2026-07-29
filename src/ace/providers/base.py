from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GenerationRequest:
    prompt: str
    model: str
    temperature: float = 0.7
    max_output_tokens: int = 4096
    keep_alive: Any = None


@dataclass(frozen=True)
class ProviderResponse:
    text: str
    raw: dict[str, Any]


class AIProvider(ABC):
    def __init__(self, name: str, config: dict[str, Any]):
        self.name = name
        self.config = config

    @abstractmethod
    def generate(self, request: GenerationRequest) -> ProviderResponse:
        raise NotImplementedError

    def validate(self) -> None:
        """Validate static configuration before ACE changes local-model state.

        Providers should use this for checks that do not make a generation
        request, such as required API keys or a missing base URL. Network
        availability remains the responsibility of ``generate``/``list_models``.
        """

        return None

    def list_models(self) -> list[str]:
        return []

    def check(self) -> tuple[bool, str]:
        try:
            self.list_models()
        except Exception as exc:  # pragma: no cover - provider-specific detail
            return False, str(exc)
        return True, "Ready"
