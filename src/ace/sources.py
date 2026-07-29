from __future__ import annotations

import html
import json
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any

from ace.cache import Cache
from ace.config import load as load_config
from ace.http import request
from ace.storage import resolve_generation
from ace.utils import read_json, sha256_bytes, utc_now_iso, write_json


@dataclass
class SourceRecord:
    id: str
    url: str
    title: str
    publisher: str | None = None
    published_at: str | None = None
    retrieved_at: str = field(default_factory=utc_now_iso)
    source_type: str = "article"
    domain: str = ""
    official: bool = False
    credibility: str = "unknown"
    credibility_score: float = 0.4
    description: str | None = None
    author: str | None = None
    text_excerpt: str | None = None
    content_hash: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    social_identity: dict[str, Any] | None = None
    notes: list[str] = field(default_factory=list)


class _MetaParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.title_parts: list[str] = []
        self.in_title = False
        self.meta: dict[str, str] = {}
        self.text_parts: list[str] = []
        self.in_ignored = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {str(k).lower(): str(v or "") for k, v in attrs}
        if tag == "title":
            self.in_title = True
        if tag in {"script", "style", "noscript", "svg"}:
            self.in_ignored += 1
        if tag == "meta":
            key = (attrs_dict.get("property") or attrs_dict.get("name") or "").lower()
            content = attrs_dict.get("content") or ""
            if key and content:
                self.meta[key] = content

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self.in_title = False
        if tag in {"script", "style", "noscript", "svg"} and self.in_ignored:
            self.in_ignored -= 1

    def handle_data(self, data: str) -> None:
        if self.in_title:
            self.title_parts.append(data)
        if not self.in_ignored:
            compact = re.sub(r"\s+", " ", data).strip()
            if len(compact) > 20:
                self.text_parts.append(compact)


def _domain(url: str) -> str:
    host = urllib.parse.urlparse(url).netloc.lower().split(":")[0]
    return host[4:] if host.startswith("www.") else host


def _is_official(domain: str, config: dict[str, Any]) -> bool:
    trusted = config.get("research", {}).get("trusted_domains", {})
    for domains in trusted.values():
        for allowed in domains:
            allowed = str(allowed).lower()
            if domain == allowed or domain.endswith("." + allowed):
                return True
    return False


def _credibility(domain: str, official: bool, source_type: str) -> tuple[str, float]:
    if official:
        return "primary", 0.95
    if source_type == "social_post":
        return "social", 0.35
    if domain.endswith(".gov") or ".gov." in domain:
        return "government", 0.93
    if domain.endswith(".edu"):
        return "research", 0.85
    major = {"reuters.com", "apnews.com", "bbc.com", "theverge.com", "arstechnica.com", "techcrunch.com", "wired.com"}
    if domain in major or any(domain.endswith("." + item) for item in major):
        return "reputable_news", 0.82
    return "secondary", 0.55


def inspect_url(url: str, workspace: str | Path | None = None, *, source_type: str = "article") -> SourceRecord:
    config = load_config(workspace)
    cache = Cache(workspace)
    response = request("GET", url, timeout=30, retries=1, cache=cache, cache_ttl=6 * 3600)
    content_type = response.headers.get("Content-Type", "")
    if "html" not in content_type and not url.lower().endswith((".html", "/")):
        raise ValueError(f"URL is not an HTML page: {content_type}")
    raw = response.body.decode("utf-8", errors="replace")
    parser = _MetaParser()
    parser.feed(raw)
    title = parser.meta.get("og:title") or parser.meta.get("twitter:title") or " ".join(parser.title_parts).strip() or url
    description = parser.meta.get("og:description") or parser.meta.get("description") or parser.meta.get("twitter:description")
    publisher = parser.meta.get("og:site_name") or parser.meta.get("application-name")
    author = parser.meta.get("author") or parser.meta.get("article:author")
    published = parser.meta.get("article:published_time") or parser.meta.get("date") or parser.meta.get("datepublished")
    domain = _domain(url)
    official = _is_official(domain, config)
    credibility, score = _credibility(domain, official, source_type)
    text = " ".join(parser.text_parts)
    excerpt = text[:1200] if text else description
    source_id = sha256_bytes(url.encode("utf-8"))[:16]
    usage = {
        "research": True,
        "headline_card": True,
        "page_screenshot": "official" if official else "approval_required",
        "embedded_media": "not_assumed_reusable",
    }
    return SourceRecord(
        id=source_id,
        url=url,
        title=html.unescape(title).strip(),
        publisher=html.unescape(publisher).strip() if publisher else domain,
        published_at=published,
        source_type=source_type,
        domain=domain,
        official=official,
        credibility=credibility,
        credibility_score=score,
        description=html.unescape(description).strip() if description else None,
        author=author,
        text_excerpt=excerpt,
        content_hash=sha256_bytes(response.body),
        usage=usage,
    )


def _source_file(folder: Path) -> Path:
    return folder / "research" / "sources.json"


def load_sources(generation: str | Path, workspace: str | Path | None = None) -> list[SourceRecord]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(_source_file(folder), []) or []
    return [SourceRecord(**row) for row in rows if isinstance(row, dict)]


def save_sources(generation: str | Path, sources: list[SourceRecord], workspace: str | Path | None = None) -> Path:
    folder = resolve_generation(generation, workspace)
    unique: dict[str, SourceRecord] = {item.url: item for item in sources}
    return write_json(_source_file(folder), [asdict(item) for item in unique.values()])


def add_url(generation: str | Path, url: str, workspace: str | Path | None = None, *, source_type: str = "article") -> SourceRecord:
    source = inspect_url(url, workspace, source_type=source_type)
    current = load_sources(generation, workspace)
    current = [item for item in current if item.url != url]
    current.append(source)
    save_sources(generation, current, workspace)
    return source


def add_post(generation: str | Path, url: str, workspace: str | Path | None = None) -> SourceRecord:
    source = inspect_url(url, workspace, source_type="social_post")
    source.usage.update({"factual_proof": source.official, "visual_reaction": True})
    if not source.official:
        source.notes.append("Opinion or reaction; corroboration required before factual use.")
    current = load_sources(generation, workspace)
    current = [item for item in current if item.url != url]
    current.append(source)
    save_sources(generation, current, workspace)
    return source


def discover_news_rss(query: str, workspace: str | Path | None = None, *, limit: int = 10) -> list[SourceRecord]:
    encoded = urllib.parse.quote_plus(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en&gl=US&ceid=US:en"
    cache = Cache(workspace)
    response = request("GET", url, timeout=25, retries=1, cache=cache, cache_ttl=3600)
    root = ET.fromstring(response.body)
    results: list[SourceRecord] = []
    for item in root.findall(".//item")[:limit]:
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        published = (item.findtext("pubDate") or "").strip() or None
        source_node = item.find("source")
        publisher = source_node.text.strip() if source_node is not None and source_node.text else None
        if not link:
            continue
        domain = _domain(link)
        official = _is_official(domain, load_config(workspace))
        credibility, score = _credibility(domain, official, "article")
        results.append(
            SourceRecord(
                id=sha256_bytes(link.encode("utf-8"))[:16],
                url=link,
                title=title,
                publisher=publisher,
                published_at=published,
                source_type="article",
                domain=domain,
                official=official,
                credibility=credibility,
                credibility_score=score,
                usage={"research": True, "headline_card": True, "page_screenshot": "official" if official else "approval_required"},
            )
        )
    return results
