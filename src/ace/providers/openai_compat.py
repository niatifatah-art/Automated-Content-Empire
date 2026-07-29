from __future__ import annotations

from ace.http import HTTPError, request
from ace.providers.base import GenerationRequest, GenerationResult, ProviderFailure


class OpenAICompatibleProvider:
    cloud = True

    def __init__(self, name: str, base_url: str, *, extra_headers: dict[str, str] | None = None):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.extra_headers = extra_headers or {}

    def generate(self, req: GenerationRequest, credential: str | None = None) -> GenerationResult:
        if not credential:
            raise ProviderFailure(f"{self.name} API key is missing.", category="authentication")
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        body = {
            "model": req.model,
            "messages": messages,
            "temperature": req.temperature,
            "max_tokens": req.max_output_tokens,
        }
        if req.json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {credential}", **self.extra_headers}
        try:
            response = request("POST", f"{self.base_url}/chat/completions", headers=headers, json_body=body, timeout=90, retries=0)
        except HTTPError as exc:
            category = "rate_limit" if exc.status == 429 else "authentication" if exc.status == 401 else "permission" if exc.status == 403 else "outage" if exc.status >= 500 else "unknown"
            raise ProviderFailure(str(exc), category=category, retryable=exc.status == 429 or exc.status >= 500, status=exc.status) from exc
        data = response.json()
        choices = data.get("choices") or []
        if not choices:
            raise ProviderFailure(f"{self.name} returned no choices.", category="malformed")
        text = str(choices[0].get("message", {}).get("content", "")).strip()
        if not text:
            raise ProviderFailure(f"{self.name} returned an empty response.", category="malformed")
        return GenerationResult(text, self.name, req.model, usage=data.get("usage", {}))

    def test(self, model: str, credential: str | None = None) -> GenerationResult:
        return self.generate(GenerationRequest("test", "Reply with exactly: ACE provider test passed", model, temperature=0.0, max_output_tokens=32), credential)
