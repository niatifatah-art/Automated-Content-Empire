from __future__ import annotations

from ace.errors import ProviderRequestError
from ace.providers.base import AIProvider, GenerationRequest, ProviderResponse
from ace.providers.http import request_json


class OllamaProvider(AIProvider):
    def _url(self, path: str) -> str:
        return f"{self.config.get('base_url', 'http://127.0.0.1:11434').rstrip('/')}{path}"

    @property
    def timeout(self) -> float:
        return float(self.config.get("timeout_seconds", 300))

    def generate(self, request: GenerationRequest) -> ProviderResponse:
        payload = {
            "model": request.model,
            "prompt": request.prompt,
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_output_tokens,
            },
        }
        if request.keep_alive is not None:
            payload["keep_alive"] = request.keep_alive
        raw = request_json("POST", self._url("/api/generate"), payload=payload, timeout=self.timeout)
        text = raw.get("response")
        if not isinstance(text, str) or not text.strip():
            error = raw.get("error")
            raise ProviderRequestError(str(error or "Ollama returned no text."))
        return ProviderResponse(text=text.strip(), raw=raw)

    def list_models(self) -> list[str]:
        raw = request_json("GET", self._url("/api/tags"), timeout=self.timeout)
        result: list[str] = []
        for model in raw.get("models", []):
            if isinstance(model, dict):
                name = model.get("name") or model.get("model")
                if isinstance(name, str):
                    result.append(name)
        return sorted(set(result))
