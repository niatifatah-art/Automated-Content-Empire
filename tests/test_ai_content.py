import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ace.ai import AIEngine
from ace.config import initialize, load, save
from ace.content import generate
from ace.errors import ProviderUnavailable
from ace.providers.base import ProviderResponse


class FakeProvider:
    def __init__(self, text=None, error=None):
        self.text = text
        self.error = error

    def generate(self, request):
        if self.error:
            raise self.error
        return ProviderResponse(self.text, {"ok": True})


class AIContentTests(unittest.TestCase):
    def test_engine_falls_back_to_second_target(self):
        config = load()
        providers = [
            FakeProvider(error=ProviderUnavailable("missing key")),
            FakeProvider(text="Fallback worked"),
        ]
        with patch("ace.ai.create_provider", side_effect=providers):
            result = AIEngine(config).generate("script", "Write")
        self.assertEqual(result.text, "Fallback worked")
        self.assertEqual(result.provider, "ollama")
        self.assertIn("missing key", result.attempts[0])

    def test_content_generation_saves_clean_output_and_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            config = load(directory)
            config["routes"]["script"] = [{"provider": "ollama", "model": "test"}]
            save(config, directory)
            fake = FakeProvider(
                text="\x1b[?25lHere is the script:\n# Hook\n\nUseful body\x1b[0m"
            )
            with patch("ace.ai.create_provider", return_value=fake):
                result = generate(
                    "tiktok",
                    "short",
                    topic="Boxing cardio",
                    workspace=directory,
                    no_profile=True,
                    variants=1,
                    review=False,
                )
            self.assertEqual(result.text, "# Hook\n\nUseful body")
            self.assertTrue(result.path.exists())
            self.assertTrue((result.folder / "metadata.json").exists())
            self.assertEqual(result.provider, "ollama")
