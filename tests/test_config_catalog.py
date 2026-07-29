import json
import tempfile
import unittest
from pathlib import Path

from ace.catalog import default_pack, resolve_content_type, resolve_platform
from ace.config import initialize, load, save, set_value
from ace.paths import config_path, prompts_dir, model_catalog_path


class ConfigCatalogTests(unittest.TestCase):
    def test_workspace_initialization_creates_editable_defaults(self):
        with tempfile.TemporaryDirectory() as directory:
            root = initialize(directory)
            self.assertTrue(config_path(root).exists())
            self.assertTrue((root / "config" / "content_catalog.json").exists())
            self.assertTrue((prompts_dir(root) / "content.txt").exists())
            config = load(root)
            self.assertEqual(config["routes"]["script"][0]["provider"], "gemini")
            self.assertEqual(config["routes"]["script"][0]["model"], "gemini-3.6-flash")
            self.assertEqual(config["routes"]["script"][1]["model"], "auto")
            self.assertTrue(model_catalog_path(root).exists())

    def test_config_deep_set_is_persisted(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            config = load(directory)
            set_value(config, "generation.temperature", 0.25)
            save(config, directory)
            self.assertEqual(load(directory)["generation"]["temperature"], 0.25)

    def test_platform_and_type_aliases(self):
        platform, _ = resolve_platform("TT")
        self.assertEqual(platform, "tiktok")
        platform, content_type, _, _ = resolve_content_type("insta", "cover")
        self.assertEqual((platform, content_type), ("instagram", "thumbnail"))
        self.assertIn("short", default_pack("youtube"))

class UnicodeStorageTests(unittest.TestCase):
    def test_slugify_preserves_non_latin_words(self):
        from ace.storage import slugify

        self.assertEqual(slugify("محتوى رياضي"), "محتوى-رياضي")
