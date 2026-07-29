from __future__ import annotations

import os

from ace.errors import ProviderRequestError, ProviderUnavailable
from ace.providers.base import AIProvider, GenerationRequest, ProviderResponse
from ace.providers.http import request_json


class AnthropicProvider(AIProvider):
    def _api_key(self) -> str:
        env_name = self.config.get("api_key_env", "ANTHROPIC_API_KEY")
        key = os.environ.get(str(env_name), "").strip()
        if not key:
            raise ProviderUnavailable(f"Environment variable {env_name} is not set.")
        return key

    def _url(self, path: str) -> str:
        base = self.config.get("base_url", "https://api.anthropic.com/v1")
        return f"{str(base).rstrip('/')}{path}"

    @property
    def timeout(self) -> float:
        return float(self.config.get("timeout_seconds", 120))

    def validate(self) -> None:
        self._api_key()

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        raw = request_json(
            "POST",
            self._url("/messages"),
            headers={
                "x-api-key": self._api_key(),
                "anthropic-version": str(
                    self.config.get("anthropic_version", "2023-06-01")
                ),
            },
            payload={
                "model": request.model,
                "max_tokens": request.max_output_tokens,
                "temperature": request.temperature,
                "messages": [{"role": "user", "content": request.prompt}],
            },
            timeout=self.timeout,
        )
        pieces = [
            block.get("text", "")
            for block in raw.get("content", [])
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        text = "".join(pieces).strip()
        if not text:
            raise ProviderRequestError("Anthropic returned no text content.")
        return ProviderResponse(text=text, raw=raw)
