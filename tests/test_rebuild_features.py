import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ace.ai import AIEngine
from ace.cli import create_parser
from ace.config import initialize, load as load_config, save as save_config
from ace.content import generate
from ace.memory import MemoryManager
from ace.models import load_catalog
from ace.profile import create as create_profile, load as load_profile
from ace.providers.base import ProviderResponse
from ace.secrets import masked_status
from ace.storage import create_generation_dir


class RecordingProvider:
    def __init__(self, responder=None):
        self.requests = []
        self.responder = responder or (lambda request: "ok")

    def generate(self, request):
        self.requests.append(request)
        return ProviderResponse(self.responder(request), {"ok": True})

    def list_models(self):
        return ["live-model-a", "live-model-b"]


class SecurityAndProfileTests(unittest.TestCase):
    def test_initialize_creates_protected_secrets_outside_content_tree(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            secrets = Path(directory) / "config" / "secrets.env"
            self.assertTrue(secrets.exists())
            self.assertEqual(stat.S_IMODE(secrets.stat().st_mode), 0o600)
            self.assertFalse(str(secrets).startswith(str(Path(directory) / "data" / "content")))
            self.assertIn("GEMINI_API_KEY=", secrets.read_text(encoding="utf-8"))

    def test_secret_status_never_prints_complete_key(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            secrets = Path(directory) / "config" / "secrets.env"
            secret = "sk-test-1234567890"
            secrets.write_text(f"OPENAI_API_KEY={secret}\n", encoding="utf-8")
            old = os.environ.pop("OPENAI_API_KEY", None)
            try:
                value = masked_status(directory)["OPENAI_API_KEY"]
            finally:
                os.environ.pop("OPENAI_API_KEY", None)
                if old is not None:
                    os.environ["OPENAI_API_KEY"] = old
            self.assertNotIn(secret, value)
            self.assertIn("sk-", value)

    def test_one_profile_keeps_identity_across_enabled_platforms(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            profile = create_profile(
                "Knockout Coaching",
                niche="Boxing",
                audience="Beginner and intermediate boxers",
                primary_language="fr",
                enabled_languages=["fr", "ar", "en"],
                enabled_platforms=["tiktok", "youtube", "facebook"],
                personality=["direct", "motivating", "credible"],
                workspace=directory,
            )
            loaded = load_profile(profile["slug"], directory)
            self.assertEqual(loaded["identity"]["personality"], ["direct", "motivating", "credible"])
            self.assertTrue(loaded["platforms"]["tiktok"]["enabled"])
            self.assertTrue(loaded["platforms"]["youtube"]["enabled"])
            self.assertEqual(loaded["languages"]["arabic_style"], "neutral_mashriqi_social")

    def test_cli_language_and_all_profile_shortcuts(self):
        args = create_parser().parse_args(
            ["tiktok", "short", "Boxing", "cardio", "-ar", "-A", "--variants", "5", "--both"]
        )
        self.assertEqual(args.language_shortcut, "ar")
        self.assertTrue(args.all_profiles)
        self.assertEqual(args.production_mode, "both")
        self.assertEqual(args.topic, ["Boxing", "cardio"])


class ModelAndMemoryTests(unittest.TestCase):
    def test_model_catalog_is_editable_and_contains_local_and_cloud_models(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            catalog = load_catalog(directory)
            providers = catalog["providers"]
            self.assertIn("gemini", providers)
            self.assertIn("openai", providers)
            self.assertIn("anthropic", providers)
            self.assertIn("ollama", providers)
            self.assertIn("qwen3:8b", [item["id"] for item in providers["ollama"]["models"]])
            self.assertIn("local-balanced", catalog["aliases"])

    def test_low_memory_mode_passes_immediate_unload(self):
        config = load_config()
        config["memory"]["mode"] = "low"
        config["routes"]["script"] = [{"provider": "ollama", "model": "qwen3:4b"}]
        provider = RecordingProvider()
        with patch("ace.ai.create_provider", return_value=provider):
            with AIEngine(config) as engine:
                engine.generate("script", "hello")
        self.assertEqual(provider.requests[0].keep_alive, 0)

    def test_smart_memory_reuses_then_unloads_before_cloud_and_at_end(self):
        config = load_config()
        manager = MemoryManager(config)
        ollama = config["providers"]["ollama"]
        gemini = config["providers"]["gemini"]
        calls = []

        def fake_request(method, url, **kwargs):
            calls.append((method, url, kwargs.get("payload")))
            return {"response": ""}

        with patch("ace.memory.request_json", side_effect=fake_request):
            manager.before_target("ollama", "qwen3:8b", ollama)
            manager.before_target("ollama", "qwen3:8b", ollama)
            self.assertEqual(calls, [])
            manager.before_target("gemini", "gemini-3.6-flash", gemini)
            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0][2]["keep_alive"], 0)
            manager.before_target("ollama", "qwen3:4b", ollama)
            manager.close()
            self.assertEqual(len(calls), 2)
            self.assertEqual(calls[-1][2]["model"], "qwen3:4b")

    def test_missing_cloud_key_does_not_unload_reused_local_fallback(self):
        from ace.providers.gemini import GeminiProvider

        config = load_config()
        config["routes"]["script"] = [
            {"provider": "gemini", "model": "gemini-test"},
            {"provider": "ollama", "model": "qwen3:8b"},
        ]
        local = RecordingProvider()
        unload_calls = []

        def provider_factory(name, provider_config):
            if name == "gemini":
                return GeminiProvider(name, provider_config)
            return local

        def fake_memory_request(method, url, **kwargs):
            unload_calls.append((method, url, kwargs.get("payload")))
            return {"response": ""}

        with patch.dict(os.environ, {"GEMINI_API_KEY": ""}), \
             patch("ace.ai.create_provider", side_effect=provider_factory), \
             patch("ace.memory.request_json", side_effect=fake_memory_request):
            with AIEngine(config) as engine:
                first = engine.generate("script", "first")
                second = engine.generate("script", "second")
                self.assertEqual(unload_calls, [])

        self.assertEqual(first.provider, "ollama")
        self.assertEqual(second.provider, "ollama")
        self.assertEqual(len(local.requests), 2)
        self.assertEqual(len(unload_calls), 1)
        self.assertEqual(unload_calls[0][2]["keep_alive"], 0)


class GenerationFolderTests(unittest.TestCase):
    def test_every_generation_gets_a_unique_folder(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            first = create_generation_dir("brand", "tiktok", "short", "same topic", directory)
            second = create_generation_dir("brand", "tiktok", "short", "same topic", directory)
            self.assertNotEqual(first, second)
            self.assertTrue((first / "resources" / "publishable").exists())
            self.assertTrue((second / "editing").exists())

    def test_variants_selection_extras_and_profile_snapshot_are_saved(self):
        def responder(request):
            prompt = request.prompt
            if "Return valid JSON only" in prompt:
                return json.dumps({
                    "recommended": 2,
                    "scores": [
                        {"candidate": 1, "overall": 70},
                        {"candidate": 2, "overall": 95},
                        {"candidate": 3, "overall": 80},
                    ],
                })
            if "Generate exactly 3" in prompt:
                return (
                    "=== CANDIDATE 1 ===\nFirst option\n"
                    "=== CANDIDATE 2 ===\nSecond option\n"
                    "=== CANDIDATE 3 ===\nThird option"
                )
            return "Finished output"

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            config = load_config(directory)
            for task in ("script", "writing", "selection", "review"):
                config["routes"][task] = [{"provider": "ollama", "model": "test-model"}]
            save_config(config, directory)
            profile = create_profile(
                "Brand",
                enabled_platforms=["tiktok"],
                workspace=directory,
            )
            provider = RecordingProvider(responder)
            with patch("ace.ai.create_provider", return_value=provider), patch("ace.memory.MemoryManager.close"):
                result = generate(
                    "tiktok",
                    "short",
                    topic="Boxing cardio",
                    workspace=directory,
                    profile_slug=profile["slug"],
                    variants=3,
                    selection_mode="auto",
                    review=False,
                    extras=["caption"],
                    interactive=False,
                )
            self.assertEqual(result.text, "Second option")
            self.assertEqual(result.selected_index, 1)
            self.assertEqual(len(list((result.folder / "candidates").glob("candidate-*.md"))), 3)
            self.assertTrue((result.folder / "evaluation.json").exists())
            self.assertTrue((result.folder / "profile-snapshot.json").exists())
            self.assertTrue((result.folder / "extras" / "caption" / "selected.md").exists())
            metadata = json.loads((result.folder / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["profile_slug"], profile["slug"])
            self.assertEqual(metadata["selected_candidate"], 2)


if __name__ == "__main__":
    unittest.main()

class ResourceAndEditingTests(unittest.TestCase):
    def test_strict_license_policy_blocks_share_alike_and_noncommercial(self):
        from ace.resources_engine import _license_status

        self.assertEqual(_license_status("CC BY 4.0")[0], "publishable_with_credit")
        self.assertEqual(_license_status("CC BY-SA 4.0")[0], "blocked")
        self.assertEqual(_license_status("CC BY-NC 4.0")[0], "blocked")

    def _generation(self, directory):
        from ace.storage import save_generation

        folder = create_generation_dir("brand", "tiktok", "short", "Cyber security alert", directory)
        save_generation(
            folder,
            "A new security alert matters. Update your browser today.",
            metadata={
                "schema_version": 3,
                "profile_slug": "brand",
                "platform": "tiktok",
                "content_type": "short",
                "topic": "Cyber security alert",
            },
        )
        return folder

    def test_resources_separate_publishable_media_from_research_references(self):
        from ace.resources_engine import Resource, collect_for_generation

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = self._generation(directory)
            owned = Path(directory) / "owned.jpg"
            owned.write_bytes(b"owned")
            media = Resource(
                id="owned-1",
                title="Owned image",
                type="image",
                source_provider="library",
                source_url=str(owned),
                download_url=str(owned),
                creator=None,
                license="user_owned",
                license_url=None,
                status="publishable",
                commercial_use=True,
                modification=True,
                attribution_required=False,
                local_path=str(owned),
            )
            reference = Resource(
                id="news-1",
                title="Security advisory",
                type="article",
                source_provider="news_rss",
                source_url="https://example.invalid/advisory",
                download_url=None,
                creator="Example",
                license="reference_only",
                license_url=None,
                status="reference_only",
                commercial_use=False,
                modification=False,
                attribution_required=True,
            )
            with patch("ace.resources_engine.find_resources", return_value=[media]), patch(
                "ace.resources_engine.search_news_references", return_value=[reference]
            ):
                selected = collect_for_generation(folder, workspace=directory)
            self.assertEqual(len(selected), 1)
            manifest = json.loads((folder / "licenses" / "manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["publishable"][0]["status"], "publishable")
            self.assertEqual(manifest["reference_only"][0]["status"], "reference_only")
            self.assertTrue(any((folder / "resources" / "publishable").iterdir()))
            self.assertFalse(any((folder / "resources" / "reference-only").glob("*.jpg")))

    def test_editing_package_creates_timeline_and_subtitles(self):
        from ace.editing import create_package

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = self._generation(directory)
            package = create_package(folder, workspace=directory)
            plan = json.loads(package.plan.read_text(encoding="utf-8"))
            self.assertEqual(plan["orientation"], "vertical")
            self.assertGreaterEqual(len(plan["timeline"]), 2)
            self.assertIn("00:00:00,000", package.subtitles.read_text(encoding="utf-8"))

    @unittest.skipUnless(__import__("shutil").which("ffmpeg"), "FFmpeg is not installed")
    def test_ffmpeg_preview_render_creates_playable_file(self):
        from ace.editing import render

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = self._generation(directory)
            output = render(folder, workspace=directory, preview=True)
            self.assertTrue(output.exists())
            self.assertGreater(output.stat().st_size, 1000)


class VoiceAuditionTests(unittest.TestCase):
    def test_audition_keeps_only_selected_sample_and_updates_profile(self):
        from ace.engines.voice import audition_voice

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            profile = create_profile("Voice Brand", enabled_platforms=["youtube"], workspace=directory)

            def fake_generate(text, output, **kwargs):
                path = Path(output)
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes((kwargs["model"] + " sample").encode("utf-8"))
                return path, kwargs["provider"], kwargs["model"]

            with patch("ace.engines.voice.generate_voice", side_effect=fake_generate), patch(
                "ace.engines.voice.kokoro_unload"
            ):
                manifest = audition_voice(
                    workspace=directory,
                    provider="kokoro",
                    voices=["voice-a", "voice-b", "voice-c"],
                    language="en",
                    select=2,
                    interactive=False,
                    keep_samples=False,
                )
            self.assertEqual(manifest["selected_voice"], "voice-b")
            selected = Path(manifest["selected_sample"])
            self.assertTrue(selected.exists())
            self.assertIn(b"voice-b", selected.read_bytes())
            updated = load_profile(profile["slug"], directory)
            self.assertTrue(updated["voice"]["configured"])
            self.assertEqual(updated["voice"]["voice_id"], "voice-b")
            audition_cache = Path(directory) / "cache" / "voice-auditions" / profile["slug"]
            self.assertFalse(any(audition_cache.glob("*")) if audition_cache.exists() else False)

class StoragePolicyTests(unittest.TestCase):
    def test_preserved_generation_is_excluded_from_cleanup(self):
        import time
        from ace.storage import cleanup, preserve

        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = create_generation_dir("brand", "x", "post", "old item", directory)
            candidate = folder / "candidates" / "candidate-01.md"
            candidate.write_text("old", encoding="utf-8")
            old = time.time() - 20 * 86400
            os.utime(folder / "candidates", (old, old))
            preserve(folder, directory)
            targets = cleanup(directory, retention_days=7, preview=True)
            self.assertNotIn(folder / "candidates", targets)
