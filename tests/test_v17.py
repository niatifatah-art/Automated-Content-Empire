import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


from ace.account_context import ensure_task_context
from ace.account_memory import record_generation, similar_topics
from ace.ai import AIEngine
from ace.cli import create_parser
from ace.config import initialize, load as load_config, save as save_config, upgrade
from ace.fact_check import run_fact_check
from ace.generation_status import inspect_generation
from ace.models import search_models
from ace.profile import create, history, load, rollback, save
from ace.providers.base import ProviderResponse
from ace.speech import normalize_for_speech
from ace.storage import write_json


class DiscoveryProvider:
    def __init__(self, models=None, text="ok"):
        self.models = models or ["qwen2.5:latest"]
        self.text = text

    def list_models(self):
        return self.models

    def generate(self, request):
        return ProviderResponse(self.text, {})


class V17CLITests(unittest.TestCase):
    def test_creator_commands_and_nested_help_parse(self):
        parser = create_parser()
        for argv in (
            ["guide"], ["check"], ["status", "last"], ["fix", "last"],
            ["create", "youtube", "short", "Passkeys", "--auto"],
            ["models", "search", "qwen"], ["voice", "prepare", "last"],
            ["account", "build", "A technology account", "--name", "Fatah"],
            ["release", "verify"],
        ):
            parser.parse_args(argv)
        self.assertIn("Focused help", parser.format_help())

    def test_manual_assisted_auto_flags_are_exclusive(self):
        parser = create_parser()
        self.assertEqual(parser.parse_args(["create", "youtube", "short", "X", "--manual"]).interaction_mode, "manual")
        self.assertEqual(parser.parse_args(["create", "youtube", "short", "X", "--assisted"]).interaction_mode, "assisted")
        self.assertEqual(parser.parse_args(["create", "youtube", "short", "X", "-a"]).interaction_mode, "auto")


class V17UpgradeTests(unittest.TestCase):
    def test_safe_upgrade_preserves_user_settings_and_backs_up_prompts(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            config = load_config(directory)
            config["schema_version"] = 3
            config["memory"]["mode"] = "performance"
            save_config(config, directory)
            prompt = Path(directory) / "config/prompts/content.txt"
            prompt.write_text("custom old prompt\n", encoding="utf-8")
            result = upgrade(directory)
            upgraded = load_config(directory)
            self.assertEqual(upgraded["schema_version"], 4)
            self.assertEqual(upgraded["memory"]["mode"], "performance")
            self.assertTrue((result["backup"] / "prompts/content.txt").exists())
            self.assertNotEqual(prompt.read_text(encoding="utf-8"), "custom old prompt\n")


class V17AccountTests(unittest.TestCase):
    def test_yaml_source_of_truth_and_history_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            account = create("Tech", description="Technology explained simply", enabled_platforms=["youtube"], workspace=directory)
            account["identity"]["humor_style"] = "light tech jokes"
            save(account, directory)
            account["identity"]["humor_style"] = "dry"
            save(account, directory)
            path = Path(directory) / "config" / "accounts" / "tech" / "account.yaml"
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("&id", text)
            self.assertGreaterEqual(len(history("tech", directory)), 2)
            rollback(1, "tech", directory)
            self.assertEqual(load("tech", directory)["identity"]["humor_style"], "")

    def test_task_context_rejects_disabled_platform_in_auto(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            create("Tech", description="Tech", enabled_platforms=["youtube"], workspace=directory)
            with self.assertRaisesRegex(Exception, "not enabled"):
                ensure_task_context("tiktok", "short", workspace=directory, mode="auto")

    def test_account_memory_detects_similar_topics(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            create("Tech", description="Tech", enabled_platforms=["youtube"], workspace=directory)
            folder = Path(directory) / "data/content/tech/youtube/short/run"
            folder.mkdir(parents=True)
            write_json(folder / "metadata.json", {"profile_slug": "tech", "topic": "Why passkeys replace passwords", "platform": "youtube", "content_type": "short"})
            record_generation(folder, directory)
            matches = similar_topics("Passkeys replacing passwords", "tech", directory)
            self.assertTrue(matches)


class V17ModelAndQualityTests(unittest.TestCase):
    def test_auto_local_model_uses_installed_balanced_model(self):
        config = load_config()
        config["routes"]["script"] = [{"provider": "ollama", "model": "auto"}]
        provider = DiscoveryProvider(["qwen2.5:latest", "qwen3:4b"])
        with patch("ace.ai.create_provider", return_value=provider), patch("ace.memory.MemoryManager.close"):
            result = AIEngine(config).generate("script", "Write")
        self.assertEqual(result.model, "qwen2.5:latest")

    def test_free_only_skips_paid_route(self):
        config = load_config()
        config["routes"]["script"] = [
            {"provider": "gemini", "model": "gemini-test"},
            {"provider": "ollama", "model": "auto"},
        ]
        local = DiscoveryProvider(["qwen2.5:latest"], "local")
        with patch.dict("os.environ", {"ACE_FREE_ONLY": "1"}), patch("ace.ai.create_provider", return_value=local), patch("ace.memory.MemoryManager.close"):
            result = AIEngine(config).generate("script", "Write")
        self.assertEqual(result.provider, "ollama")
        self.assertIn("free/local-only", result.attempts[0])

    def test_model_search_has_readiness(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            rows = search_models("gemini", load_config(directory), directory)
            self.assertTrue(rows)
            self.assertIn("readiness", rows[0])

    def test_tts_cleanup_removes_artifacts(self):
        cleaned = normalize_for_speech('## HOST\n"Use the API." https://example.com #security 🚀')
        self.assertNotIn("HOST", cleaned)
        self.assertNotIn("https", cleaned)
        self.assertNotIn('"', cleaned)
        self.assertNotIn("🚀", cleaned)
        self.assertIn("A P I", cleaned)

    def test_fact_check_blocks_precise_claims_without_sources(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = Path(directory) / "data/content/no-profile/youtube/short/run"
            (folder / "quality").mkdir(parents=True)
            (folder / "selected.md").write_text("Exactly 97% of users will switch by 2027.\n", encoding="utf-8")
            write_json(folder / "metadata.json", {"platform": "youtube", "content_type": "short"})
            report = run_fact_check(folder, workspace=directory, use_ai=False)
            self.assertEqual(report.status, "failed")
            self.assertTrue(report.critical)


class V17StatusTests(unittest.TestCase):
    def test_complete_generation_can_report_nonblocking_warnings(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = Path(directory) / "data/content/no-profile/youtube/short/run"
            for relative in ("quality", "script", "voice", "subtitles", "editing", "exports", "research", "licenses"):
                (folder / relative).mkdir(parents=True, exist_ok=True)
            (folder / "selected.md").write_text("A complete enough script for this test.\n", encoding="utf-8")
            (folder / "script/tts-ready.txt").write_text("A complete enough script for this test.\n", encoding="utf-8")
            (folder / "voice/narration.wav").write_bytes(b"wave")
            (folder / "subtitles/subtitles.srt").write_text("1\n00:00:00,000 --> 00:00:01,000\nTest\n", encoding="utf-8")
            (folder / "exports/final.mp4").write_bytes(b"video")
            write_json(folder / "metadata.json", {"platform": "youtube", "content_type": "short", "final_model": "test", "selected_candidate": 1})
            write_json(folder / "evaluation.json", {"recommended": 1})
            write_json(folder / "research/sources.json", [])
            write_json(folder / "quality/script-report.json", {"status": "passed", "score": 95, "warnings": []})
            write_json(folder / "quality/fact-report.json", {"status": "warning", "critical": [], "source_count": 0})
            write_json(folder / "quality/tts-report.json", {"status": "ready"})
            write_json(folder / "quality/media-report.json", {"status": "passed"})
            write_json(folder / "editing/edit-plan.json", {"fallback_visuals": True})
            write_json(folder / "licenses/manifest.json", {"publishable": []})
            report = inspect_generation(folder, directory)
            self.assertEqual(report["overall"], "COMPLETE_WITH_WARNINGS")
            self.assertTrue(report["warnings"])

    def test_status_explains_incomplete_video(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = Path(directory) / "data/content/no-profile/youtube/short/run"
            (folder / "quality").mkdir(parents=True)
            (folder / "selected.md").write_text("A complete enough script for this test.\n", encoding="utf-8")
            write_json(folder / "metadata.json", {"platform": "youtube", "content_type": "short", "final_model": "test"})
            write_json(folder / "quality/script-report.json", {"status": "passed", "score": 95})
            write_json(folder / "quality/fact-report.json", {"status": "warning", "critical": [], "source_count": 0})
            report = inspect_generation(folder, directory)
            self.assertEqual(report["overall"], "INCOMPLETE")
            self.assertIn("narration", report["missing"])
            self.assertIn("final_validation", report["missing"])


if __name__ == "__main__":
    unittest.main()
