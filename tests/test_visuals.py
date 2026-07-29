from ace.captions import plan as plan_captions
from ace.evidence import build_article_cards
from ace.sources import SourceRecord, save_sources
from ace.visuals import plan
from ace.voice import create_test_tone, prepare


def test_visual_plan_uses_evidence_for_announcement(generation, workspace):
    text = "NVIDIA announced a new partnership today. The companies say it will improve AI infrastructure."
    (generation / "selected.md").write_text(text + "\n", encoding="utf-8")
    source = SourceRecord(id="official", url="https://nvidia.com/news", title="NVIDIA partnership announcement", publisher="NVIDIA", official=True, credibility="primary", credibility_score=0.95)
    save_sources(generation, [source], workspace)
    build_article_cards(generation, workspace)
    prepare(generation, workspace)
    create_test_tone(generation / "voice" / "narration.wav", duration=7)
    plan_captions(generation, workspace)
    shots = plan(generation, workspace)
    assert shots
    assert any(item.visual_type == "evidence_card" for item in shots)
