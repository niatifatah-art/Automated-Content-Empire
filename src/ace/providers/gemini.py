from __future__ import annotations

import os
from urllib.parse import quote

from ace.errors import ProviderRequestError, ProviderUnavailable
from ace.providers.base import AIProvider, GenerationRequest, ProviderResponse
from ace.providers.http import request_json


class GeminiProvider(AIProvider):
    def _api_key(self) -> str:
        env_name = self.config.get("api_key_env", "GEMINI_API_KEY")
        key = os.environ.get(str(env_name), "").strip()
        if not key:
            raise ProviderUnavailable(f"Environment variable {env_name} is not set.")
        return key

    def _url(self, path: str) -> str:
        base = self.config.get(
            "base_url", "https://generativelanguage.googleapis.com/v1beta"
        )
        return f"{str(base).rstrip('/')}{path}"

    @property
    def timeout(self) -> float:
        return float(self.config.get("timeout_seconds", 120))

    def validate(self) -> None:
        self._api_key()

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        model = request.model.removeprefix("models/")
        raw = request_json(
            "POST",
            self._url(f"/models/{quote(model, safe='-._')}:generateContent"),
            headers={"x-goog-api-key": self._api_key()},
            payload={
                "contents": [{"role": "user", "parts": [{"text": request.prompt}]}],
                "generationConfig": {
                    "temperature": request.temperature,
                    "maxOutputTokens": request.max_output_tokens,
                },
            },
            timeout=self.timeout,
        )

        pieces: list[str] = []
        for candidate in raw.get("candidates", []):
            if not isinstance(candidate, dict):
                continue
            content = candidate.get("content", {})
            if not isinstance(content, dict):
                continue
            for part in content.get("parts", []):
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    pieces.append(part["text"])

        text = "".join(pieces).strip()
        if not text:
            feedback = raw.get("promptFeedback") or raw.get("error")
            raise ProviderRequestError(f"Gemini returned no text: {feedback or 'unknown reason'}")
        return ProviderResponse(text=text, raw=raw)

    def list_models(self) -> list[str]:
        raw = request_json(
            "GET",
            self._url("/models?pageSize=1000"),
            headers={"x-goog-api-key": self._api_key()},
            timeout=self.timeout,
        )
        result: list[str] = []
        for model in raw.get("models", []):
            if not isinstance(model, dict):
                continue
            methods = model.get("supportedGenerationMethods", [])
            name = model.get("name")
            if isinstance(name, str) and (
                not methods or "generateContent" in methods
            ):
                result.append(name.removeprefix("models/"))
        return sorted(set(result))
