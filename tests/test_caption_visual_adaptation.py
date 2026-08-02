from ace.captions import adapt_to_visuals, plan
from ace.utils import read_json, write_json
from ace.voice import create_test_tone, prepare


def test_explainer_moves_full_title_away_from_header(generation, workspace):
    (generation / "selected.md").write_text("Public Wi-Fi is convenient, but every device shares the same access point.\n", encoding="utf-8")
    prepare(generation, workspace)
    create_test_tone(generation / "voice" / "narration.wav", duration=4.0)
    cues = plan(generation, workspace)
    assert cues[0].mode == "full_title"
    write_json(
        generation / "visuals" / "shot-plan.json",
        [{"visual_type": "animated_explainer", "metadata": {"caption_cue_indices": [cue.index for cue in cues]}}],
    )
    adapted = adapt_to_visuals(generation, workspace)
    assert adapted[0].position == "bottom"
    assert adapted[0].mode == "short_phrase"
    assert len(adapted[0].visible_text.split()) <= 6
