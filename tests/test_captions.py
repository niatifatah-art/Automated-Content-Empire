from ace.captions import inspect, plan
from ace.voice import create_test_tone, prepare


def test_adaptive_caption_plan_has_clean_moments_and_no_overflow(generation, workspace):
    prepare(generation, workspace)
    create_test_tone(generation / "voice" / "narration.wav", duration=12)
    cues = plan(generation, workspace)
    report = inspect(generation, workspace)
    assert cues
    assert report["overflow_count"] == 0
    assert report["visible_count"] > 0
    assert (generation / "captions" / "styled-captions.ass").exists()
    assert (generation / "subtitles" / "accessibility.srt").exists()


def test_wrap_text_duplicate_words(tmp_path):
    from PIL import Image, ImageDraw
    from ace.graphics import font, wrap_text

    image = Image.new("RGB", (640, 360))
    draw = ImageDraw.Draw(image)
    lines = wrap_text("test test test test result", draw, font(44), 180, max_lines=2)
    assert len(lines) <= 2
    assert "result" in " ".join(lines)
