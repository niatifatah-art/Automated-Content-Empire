from __future__ import annotations

import os
from typing import Any

from ace.errors import ProviderRequestError, ProviderUnavailable
from ace.providers.base import AIProvider, GenerationRequest, ProviderResponse
from ace.providers.http import request_json


class OpenAICompatibleProvider(AIProvider):
    def _api_key(self) -> str | None:
        env_name = self.config.get("api_key_env")
        if not env_name:
            if self.config.get("requires_api_key", False):
                raise ProviderUnavailable("No API-key environment variable is configured.")
            return None
        key = os.environ.get(str(env_name), "").strip()
        if not key and self.config.get("requires_api_key", True):
            raise ProviderUnavailable(f"Environment variable {env_name} is not set.")
        return key or None

    def _headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        key = self._api_key()
        if key:
            headers["Authorization"] = f"Bearer {key}"
        for name, value in self.config.get("headers", {}).items():
            headers[str(name)] = str(value)
        return headers

    def _url(self, path: str) -> str:
        base = self.config.get("base_url")
        if not base:
            raise ProviderUnavailable(f"Provider '{self.name}' has no base_url.")
        return f"{str(base).rstrip('/')}{path}"

    @property
    def timeout(self) -> float:
        return float(self.config.get("timeout_seconds", 120))

    def validate(self) -> None:
        self._api_key()
        self._url("")

    def _responses_text(self, raw: dict[str, Any]) -> str:
        if isinstance(raw.get("output_text"), str):
            return str(raw["output_text"])
        pieces: list[str] = []
        for item in raw.get("output", []):
            if not isinstance(item, dict):
                continue
            for part in item.get("content", []):
                if not isinstance(part, dict):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    pieces.append(text)
        return "".join(pieces)

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        api_mode = str(self.config.get("api_mode", "chat"))
        if api_mode == "responses":
            raw = request_json(
                "POST",
                self._url("/responses"),
                headers=self._headers(),
                payload={
                    "model": request.model,
                    "input": request.prompt,
                    "temperature": request.temperature,
                    "max_output_tokens": request.max_output_tokens,
                },
                timeout=self.timeout,
            )
            text = self._responses_text(raw)
        else:
            raw = request_json(
                "POST",
                self._url("/chat/completions"),
                headers=self._headers(),
                payload={
                    "model": request.model,
                    "messages": [{"role": "user", "content": request.prompt}],
                    "temperature": request.temperature,
                    "max_tokens": request.max_output_tokens,
                    "stream": False,
                },
                timeout=self.timeout,
            )
            try:
                content: Any = raw["choices"][0]["message"]["content"]
            except (KeyError, IndexError, TypeError) as exc:
                raise ProviderRequestError(f"{self.name} returned no message content.") from exc
            if isinstance(content, list):
                text = "".join(
                    str(part.get("text", ""))
                    for part in content
                    if isinstance(part, dict) and part.get("type") in (None, "text")
                )
            else:
                text = str(content)

        if not text.strip():
            raise ProviderRequestError(f"{self.name} returned empty text.")
        return ProviderResponse(text=text.strip(), raw=raw)

    def list_models(self) -> list[str]:
        raw = request_json("GET", self._url("/models"), headers=self._headers(), timeout=self.timeout)
        result: list[str] = []
        for item in raw.get("data", []):
            if isinstance(item, dict) and isinstance(item.get("id"), str):
                result.append(item["id"])
        return sorted(set(result))
