from __future__ import annotations

import json
import re
import urllib.parse
from typing import Any

from ace.http import HTTPError, request
from ace.providers.base import GenerationRequest, GenerationResult, ProviderFailure


class GeminiProvider:
    name = "gemini"
    cloud = True

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    @staticmethod
    def _retry_after_from_body(message: str) -> float | None:
        try:
            payload = json.loads(message)
            details = payload.get("error", {}).get("details", [])
            for detail in details:
                delay = detail.get("retryDelay") if isinstance(detail, dict) else None
                if isinstance(delay, str):
                    match = re.match(r"([0-9.]+)s$", delay.strip())
                    if match:
                        return float(match.group(1))
        except (ValueError, TypeError, json.JSONDecodeError):
            pass
        match = re.search(r"retry(?:\s+in|Delay[^0-9]*)\s*([0-9.]+)s", message, re.I)
        return float(match.group(1)) if match else None

    @classmethod
    def _failure(cls, exc: HTTPError) -> ProviderFailure:
        category = "unknown"
        retryable = False
        retry_after = None
        if exc.status == 400:
            category = "invalid_request"
        elif exc.status == 401:
            category = "authentication"
        elif exc.status == 403:
            category = "permission"
        elif exc.status == 404:
            category = "model_not_found"
        elif exc.status == 429:
            category = "rate_limit"
            retryable = True
        elif exc.status in {500, 502, 503, 504}:
            category = "outage"
            retryable = True
        raw = exc.headers.get("Retry-After")
        if raw:
            try:
                retry_after = float(raw)
            except ValueError:
                pass
        if retry_after is None:
            retry_after = cls._retry_after_from_body(str(exc))
        return ProviderFailure(str(exc), category=category, retryable=retryable, status=exc.status, retry_after=retry_after)

    @staticmethod
    def _generation_config(req: GenerationRequest) -> dict[str, Any]:
        config: dict[str, Any] = {"maxOutputTokens": req.max_output_tokens}
        # Google deprecated sampling parameters for the newest Gemini 3.x
        # models.  Keeping them out also avoids future 400 errors.
        if not req.model.startswith(("gemini-3.5-", "gemini-3.6-")):
            config["temperature"] = req.temperature
        if req.json_mode:
            config["responseMimeType"] = "application/json"
        return config

    def generate(self, req: GenerationRequest, credential: str | None = None) -> GenerationResult:
        if not credential:
            raise ProviderFailure("Gemini API key is missing.", category="authentication")
        url = f"{self.base_url}/models/{urllib.parse.quote(req.model, safe='')}:generateContent?key={urllib.parse.quote(credential)}"
        parts: list[dict[str, Any]] = []
        if req.system:
            parts.append({"text": f"SYSTEM INSTRUCTIONS:\n{req.system}\n\n"})
        parts.append({"text": req.prompt})
        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": self._generation_config(req),
        }
        try:
            response = request("POST", url, json_body=body, timeout=90, retries=0)
        except HTTPError as exc:
            raise self._failure(exc) from exc
        except RuntimeError as exc:
            raise ProviderFailure(str(exc), category="network", retryable=True) from exc
        data = response.json()
        candidates = data.get("candidates") or []
        if not candidates:
            feedback = data.get("promptFeedback") or {}
            raise ProviderFailure(f"Gemini returned no candidates: {feedback}", category="blocked")
        candidate = candidates[0]
        text_parts = candidate.get("content", {}).get("parts", [])
        text = "".join(str(item.get("text", "")) for item in text_parts if isinstance(item, dict)).strip()
        if not text:
            finish_reason = candidate.get("finishReason") or "unknown"
            category = "max_tokens" if finish_reason == "MAX_TOKENS" else "malformed"
            raise ProviderFailure(
                f"Gemini returned no visible text (finishReason={finish_reason}).",
                category=category,
                retryable=finish_reason == "MAX_TOKENS",
            )
        usage = data.get("usageMetadata", {}) if isinstance(data, dict) else {}
        return GenerationResult(text=text, provider=self.name, model=req.model, usage=usage)

    def test(self, model: str, credential: str | None = None) -> GenerationResult:
        return self.generate(GenerationRequest("test", "Reply with exactly: ACE provider test passed", model, temperature=0.0, max_output_tokens=512), credential)
