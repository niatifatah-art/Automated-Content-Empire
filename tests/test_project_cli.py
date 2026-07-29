import tempfile
import unittest

from ace.cli import create_parser
from ace.config import initialize
from ace.project import create, load, status


class ProjectCliTests(unittest.TestCase):
    def test_project_metadata_supports_platform_and_pack(self):
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            project = create(
                "Fight Camp",
                platform="instagram",
                content_type="reel",
                pack=True,
                workspace=directory,
            )
            metadata = load(project, directory)
            self.assertEqual(metadata["platform"], "instagram")
            self.assertEqual(metadata["content_type"], "reel")
            self.assertTrue(metadata["pack"])
            self.assertFalse(status(project, directory)["content"])

    def test_shortcut_parser_keeps_full_topic(self):
        args = create_parser().parse_args(
            ["tt", "short", "boxing", "footwork", "drill"]
        )
        self.assertEqual(args.shortcut_platform, "tiktok")
        self.assertEqual(args.content_type, "short")
        self.assertEqual(args.topic, ["boxing", "footwork", "drill"])
