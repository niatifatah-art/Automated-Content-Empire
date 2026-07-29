from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class GenerationRequest:
    task: str
    prompt: str
    model: str
    temperature: float = 0.4
    max_output_tokens: int = 4096
    json_mode: bool = False
    system: str | None = None


@dataclass(frozen=True)
class GenerationResult:
    text: str
    provider: str
    model: str
    credential_name: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    degraded: bool = False


class ProviderFailure(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        category: str = "unknown",
        retryable: bool = False,
        status: int | None = None,
        retry_after: float | None = None,
    ):
        super().__init__(message)
        self.category = category
        self.retryable = retryable
        self.status = status
        self.retry_after = retry_after


class TextProvider(Protocol):
    name: str
    cloud: bool

    def generate(self, request: GenerationRequest, credential: str | None = None) -> GenerationResult:
        ...

    def test(self, model: str, credential: str | None = None) -> GenerationResult:
        ...
