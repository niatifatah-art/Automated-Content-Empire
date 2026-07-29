import os
import unittest
from unittest.mock import patch

from ace.providers.anthropic import AnthropicProvider
from ace.providers.base import GenerationRequest
from ace.providers.gemini import GeminiProvider
from ace.providers.ollama import OllamaProvider
from ace.providers.openai_compatible import OpenAICompatibleProvider


class ProviderTests(unittest.TestCase):
    @patch("ace.providers.ollama.request_json")
    def test_ollama_generate_uses_non_streaming_api(self, request_json):
        request_json.return_value = {"response": "Hello"}
        provider = OllamaProvider("ollama", {"base_url": "http://local"})
        response = provider.generate(GenerationRequest("Prompt", "qwen2.5:8b"))
        self.assertEqual(response.text, "Hello")
        payload = request_json.call_args.kwargs["payload"]
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["model"], "qwen2.5:8b")

    @patch("ace.providers.gemini.request_json")
    def test_gemini_parses_text(self, request_json):
        request_json.return_value = {
            "candidates": [{"content": {"parts": [{"text": "Gemini output"}]}}]
        }
        with patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"}):
            provider = GeminiProvider("gemini", {})
            response = provider.generate(GenerationRequest("Prompt", "gemini-2.5-flash"))
        self.assertEqual(response.text, "Gemini output")
        self.assertEqual(request_json.call_args.kwargs["headers"]["x-goog-api-key"], "test-key")

    @patch("ace.providers.openai_compatible.request_json")
    def test_openai_compatible_supports_local_server_without_key(self, request_json):
        request_json.return_value = {
            "choices": [{"message": {"content": "Local output"}}]
        }
        provider = OpenAICompatibleProvider(
            "lmstudio",
            {
                "base_url": "http://127.0.0.1:1234/v1",
                "requires_api_key": False,
            },
        )
        response = provider.generate(GenerationRequest("Prompt", "local-model"))
        self.assertEqual(response.text, "Local output")
    @patch("ace.providers.anthropic.request_json")
    def test_anthropic_parses_message_blocks(self, request_json):
        request_json.return_value = {
            "content": [{"type": "text", "text": "Claude output"}]
        }
        with patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"}):
            provider = AnthropicProvider("anthropic", {})
            response = provider.generate(GenerationRequest("Prompt", "claude-model"))
        self.assertEqual(response.text, "Claude output")
        self.assertEqual(request_json.call_args.kwargs["headers"]["x-api-key"], "test-key")

