from ace.evidence import build_article_cards
from ace.sources import SourceRecord, save_sources


def test_article_card_is_original_generated_evidence(generation, workspace):
    source = SourceRecord(
        id="nvidia-official",
        url="https://www.nvidia.com/example",
        title="NVIDIA announces a new partnership",
        publisher="NVIDIA Newsroom",
        official=True,
        credibility="primary",
        credibility_score=0.95,
        description="An official announcement about a company partnership.",
    )
    save_sources(generation, [source], workspace)
    items = build_article_cards(generation, workspace)
    assert len(items) == 1
    assert items[0].official is True
    assert "ACE-rendered card" in items[0].modifications
    assert items[0].content_hash
