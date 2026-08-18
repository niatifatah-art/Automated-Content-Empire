from __future__ import annotations

from ace.http import HTTPResponse
from ace.research import hydrate_sources
from ace.sources import SourceRecord, inspect_url


def test_inspect_url_keeps_final_redirect_url(monkeypatch, workspace):
    body = b"""<html><head><title>Publisher story</title><meta name='description' content='Useful source summary'></head><body><p>This paragraph contains enough article text to become real evidence for the script writer.</p></body></html>"""

    def fake_request(*args, **kwargs):
        return HTTPResponse(
            200,
            {"Content-Type": "text/html; charset=utf-8"},
            body,
            "https://publisher.example/story",
        )

    monkeypatch.setattr("ace.sources.request", fake_request)

    source = inspect_url("https://news.google.com/rss/articles/example", workspace)

    assert source.url == "https://publisher.example/story"
    assert source.domain == "publisher.example"
    assert "real evidence" in (source.text_excerpt or "")


def test_hydrate_sources_replaces_metadata_only_result(monkeypatch, workspace):
    discovered = SourceRecord(
        id="rss-1",
        url="https://news.example/redirect",
        title="Original RSS headline",
        publisher="Original Publisher",
        credibility="secondary",
        credibility_score=0.55,
    )
    enriched = SourceRecord(
        id="article-1",
        url="https://publisher.example/article",
        title="Publisher page title",
        publisher="publisher.example",
        domain="publisher.example",
        credibility="secondary",
        credibility_score=0.55,
        text_excerpt="The actual page says the feature shipped after a three-month public beta.",
    )

    monkeypatch.setattr("ace.research.inspect_url", lambda *args, **kwargs: enriched)

    result = hydrate_sources([discovered], workspace, limit=1)

    assert result[0].url == "https://publisher.example/article"
    assert result[0].text_excerpt
    assert "Page content hydrated" in result[0].notes


def test_hydrate_sources_does_not_treat_google_news_page_as_evidence(monkeypatch, workspace):
    discovered = SourceRecord(
        id="rss-2",
        url="https://news.google.com/rss/articles/example",
        title="RSS headline",
        publisher="Publisher",
    )
    aggregator = SourceRecord(
        id="google-page",
        url="https://news.google.com/articles/example",
        title="Google News",
        domain="news.google.com",
        text_excerpt="Aggregator navigation and unrelated page text.",
    )

    monkeypatch.setattr("ace.research.inspect_url", lambda *args, **kwargs: aggregator)

    result = hydrate_sources([discovered], workspace, limit=1)

    assert result[0] is discovered
    assert result[0].text_excerpt is None
