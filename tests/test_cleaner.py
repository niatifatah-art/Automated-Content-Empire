import unittest

from ace.script_cleaner import clean_narration, clean_response


class CleanerTests(unittest.TestCase):
    def test_response_cleanup_preserves_markdown(self):
        raw = "\x1b[?25lSure, here is the LinkedIn post:\n```markdown\n# Hook\n\n**Body**\n```\x1b[0m"
        self.assertEqual(clean_response(raw), "# Hook\n\n**Body**")

    def test_narration_cleanup_removes_directions_and_markdown(self):
        raw = "# Opening\n\n[Camera pans]\n\n**Host:** Start now.\n\n- Second line"
        self.assertEqual(clean_narration(raw), "Opening\n\nStart now.\n\nSecond line")
