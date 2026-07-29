from __future__ import annotations

from ace.http import HTTPError, request
from ace.providers.base import GenerationRequest, GenerationResult, ProviderFailure


class OllamaProvider:
    name = "ollama"
    cloud = False

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def installed_models(self) -> list[str]:
        try:
            data = request("GET", f"{self.base_url}/api/tags", timeout=5).json()
        except Exception:
            return []
        return [str(item.get("name")) for item in data.get("models", []) if item.get("name")]

    def resolve_model(self, model: str) -> str:
        if model not in {"auto", "auto-small"}:
            return model
        installed = self.installed_models()
        if not installed:
            raise ProviderFailure("No Ollama models are installed.", category="unavailable")
        preferences = ["qwen2.5", "llama3", "mistral", "gemma"]
        if model == "auto-small":
            small = [item for item in installed if any(token in item.lower() for token in ("1b", "2b", "3b", "4b", "7b", "8b"))]
            if small:
                installed = small
        for preference in preferences:
            match = next((item for item in installed if preference in item.lower()), None)
            if match:
                return match
        return installed[0]

    def generate(self, req: GenerationRequest, credential: str | None = None) -> GenerationResult:
        model = self.resolve_model(req.model)
        messages = []
        if req.system:
            messages.append({"role": "system", "content": req.system})
        messages.append({"role": "user", "content": req.prompt})
        try:
            response = request(
                "POST",
                f"{self.base_url}/api/chat",
                json_body={"model": model, "messages": messages, "stream": False, "options": {"temperature": req.temperature}},
                timeout=180,
                retries=0,
            )
        except (HTTPError, RuntimeError) as exc:
            raise ProviderFailure(str(exc), category="unavailable", retryable=True) from exc
        data = response.json()
        text = str(data.get("message", {}).get("content", "")).strip()
        if not text:
            raise ProviderFailure("Ollama returned an empty response.", category="malformed")
        return GenerationResult(text, self.name, model, usage={"eval_count": data.get("eval_count")}, degraded=True)

    def test(self, model: str, credential: str | None = None) -> GenerationResult:
        return self.generate(GenerationRequest("test", "Reply with exactly: ACE provider test passed", model, temperature=0.0, max_output_tokens=32))
