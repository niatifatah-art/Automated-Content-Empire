from __future__ import annotations

import json

from ace.content import _candidate_prompt, _source_context


def _write_sources(tmp_path, rows):
    research = tmp_path / "research"
    research.mkdir(parents=True, exist_ok=True)
    (research / "sources.json").write_text(json.dumps(rows), encoding="utf-8")


def test_source_context_includes_real_evidence_excerpt(tmp_path):
    _write_sources(
        tmp_path,
        [
            {
                "id": "source-1",
                "url": "https://example.com/article",
                "title": "Example launch details",
                "publisher": "Example News",
                "credibility": "reputable_news",
                "credibility_score": 0.82,
                "text_excerpt": "The product launched on Tuesday with a redesigned battery system and a two-year warranty.",
            }
        ],
    )

    context = _source_context(tmp_path)

    assert "Example launch details" in context
    assert "Evidence excerpt: The product launched on Tuesday" in context
    assert "headline or URL alone is not sufficient support" in context


def test_source_context_marks_headline_only_as_metadata(tmp_path):
    _write_sources(
        tmp_path,
        [
            {
                "id": "source-2",
                "url": "https://example.com/headline-only",
                "title": "Headline only result",
                "publisher": "Example News",
                "credibility": "secondary",
                "credibility_score": 0.55,
            }
        ],
    )

    context = _source_context(tmp_path)

    assert "Evidence excerpt: unavailable" in context
    assert "not proof of details" in context


def test_candidate_prompt_uses_account_identity_instead_of_hardcoded_creator(tmp_path):
    _write_sources(tmp_path, [])
    account = {
        "name": "Ari",
        "description": "A practical home cooking creator",
        "identity": {"personality": ["curious", "calm"], "humor": {"default_level": "light"}},
        "audience": {"description": "beginner home cooks", "knowledge_level": "beginner"},
        "content": {"avoid": ["forced jokes"]},
    }

    prompt = _candidate_prompt(account, "youtube", "short", "How to sharpen a kitchen knife", "", tmp_path, 1)

    assert "A practical home cooking creator" in prompt
    assert "Match the creator identity and audience described above" in prompt
    assert "smart 20-year-old technology creator" not in prompt
