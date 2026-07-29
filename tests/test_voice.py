import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ace.config import initialize
from ace.engines.voice import generate_voice
from ace.errors import ProviderUnavailable


class VoiceTests(unittest.TestCase):
    def test_voice_route_falls_back_from_piper_to_kokoro(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            output = Path(directory) / "voice.wav"

            def fake_kokoro(text, path, voice):
                Path(path).write_bytes(b"RIFFfake")
                return Path(path)

            with patch(
                "ace.engines.voice.piper_generate",
                side_effect=ProviderUnavailable("piper missing"),
            ), patch("ace.engines.voice.kokoro_generate", side_effect=fake_kokoro):
                path, provider, model = generate_voice(
                    "Narrate this text.", output, workspace=directory
                )

            self.assertEqual(path, output)
            self.assertEqual(provider, "kokoro")
            self.assertEqual(model, "af_heart")
            self.assertTrue(output.exists())

    def test_kokoro_module_import_does_not_load_pipeline(self):
        from ace.providers import kokoro

        self.assertIsNone(kokoro._pipeline)
