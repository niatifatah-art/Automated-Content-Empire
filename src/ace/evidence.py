from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from ace.config import load as load_config
from ace.graphics import create_card
from ace.sources import SourceRecord, load_sources
from ace.storage import resolve_generation
from ace.utils import ensure_dir, sha256_file, slugify, utc_now_iso, write_json


@dataclass
class EvidenceItem:
    id: str
    source_id: str
    kind: str
    path: str
    source_url: str
    title: str
    official: bool
    created_at: str
    content_hash: str
    modifications: list[str]
    approval_required: bool = False
    notes: list[str] | None = None


def build_article_cards(generation: str | Path, workspace: str | Path | None = None, *, limit: int = 5) -> list[EvidenceItem]:
    folder = resolve_generation(generation, workspace)
    sources = load_sources(folder, workspace)
    output_dir = ensure_dir(folder / "evidence" / "article-cards")
    items: list[EvidenceItem] = []
    for source in sources[:limit]:
        if source.source_type == "social_post":
            continue
        target = output_dir / f"{source.id}-{slugify(source.title, 40)}.png"
        footer_parts = [source.publisher or source.domain]
        if source.published_at:
            footer_parts.append(source.published_at)
        create_card(
            target,
            title=source.title,
            kicker=source.description,
            footer=" • ".join(footer_parts),
            label="Official source" if source.official else "Source",
        )
        items.append(
            EvidenceItem(
                id=f"article-{source.id}",
                source_id=source.id,
                kind="article_card",
                path=str(target),
                source_url=source.url,
                title=source.title,
                official=source.official,
                created_at=utc_now_iso(),
                content_hash=sha256_file(target),
                modifications=["ACE-rendered card", "headline preserved", "publisher/date displayed"],
                approval_required=False,
            )
        )
    _save_manifest(folder, items)
    return items


def build_social_cards(generation: str | Path, workspace: str | Path | None = None, *, limit: int = 4) -> list[EvidenceItem]:
    folder = resolve_generation(generation, workspace)
    config = load_config(workspace)
    sources = [item for item in load_sources(folder, workspace) if item.source_type == "social_post"]
    output_dir = ensure_dir(folder / "evidence" / "social-posts")
    items: list[EvidenceItem] = []
    for source in sources[:limit]:
        ordinary = not source.official and source.credibility == "social"
        anonymize = ordinary and bool(config.get("social", {}).get("anonymize_ordinary_users", True))
        identity = "Public reaction" if anonymize else (source.publisher or source.domain)
        target = output_dir / f"{source.id}-{slugify(source.title, 40)}.png"
        create_card(
            target,
            title=source.title,
            kicker=source.description,
            footer=f"{identity} • Opinion/reaction, not independent proof" if not source.official else f"{identity} • Official post",
            label="Official post" if source.official else "Online reaction",
            accent=(255, 184, 77) if not source.official else (72, 208, 255),
        )
        items.append(
            EvidenceItem(
                id=f"social-{source.id}",
                source_id=source.id,
                kind="social_post_card",
                path=str(target),
                source_url=source.url,
                title=source.title,
                official=source.official,
                created_at=utc_now_iso(),
                content_hash=sha256_file(target),
                modifications=["ACE-rendered card", "identity anonymized" if anonymize else "identity retained", "opinion label added"],
                approval_required=False,
            )
        )
    _save_manifest(folder, items, append=True)
    return items


def _trusted(url: str, config: dict[str, Any]) -> bool:
    domain = urlparse(url).netloc.lower().removeprefix("www.")
    for domains in config.get("research", {}).get("trusted_domains", {}).values():
        for item in domains:
            allowed = str(item).lower()
            if domain == allowed or domain.endswith("." + allowed):
                return True
    return False


async def _playwright_capture(url: str, target: Path) -> None:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError("Playwright is not installed. Install ACE with .[browser] and run 'playwright install chromium'.") from exc
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        page = await browser.new_page(viewport={"width": 1280, "height": 1100}, device_scale_factor=1)
        await page.goto(url, wait_until="networkidle", timeout=45000)
        for selector in ("button:has-text('Accept')", "button:has-text('Agree')", "[aria-label*='close' i]"):
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=500):
                    await locator.click(timeout=1000)
            except Exception:
                pass
        candidates = ["article h1", "main h1", "h1", "article", "main"]
        captured = False
        for selector in candidates:
            try:
                locator = page.locator(selector).first
                if await locator.is_visible(timeout=1000):
                    await locator.screenshot(path=str(target))
                    captured = True
                    break
            except Exception:
                continue
        if not captured:
            await page.screenshot(path=str(target), full_page=False)
        await browser.close()


def capture_official_page(generation: str | Path, url: str, workspace: str | Path | None = None, *, approved: bool = False) -> EvidenceItem:
    folder = resolve_generation(generation, workspace)
    config = load_config(workspace)
    trusted = _trusted(url, config)
    if not trusted and not approved:
        raise PermissionError("Non-official webpage screenshots require explicit approval. Use --approve.")
    target = ensure_dir(folder / "evidence" / "webpage-captures") / f"{slugify(urlparse(url).netloc)}-{slugify(urlparse(url).path or 'home', 40)}.png"
    asyncio.run(_playwright_capture(url, target))
    item = EvidenceItem(
        id=f"capture-{sha256_file(target)[:12]}",
        source_id="manual-url",
        kind="webpage_capture",
        path=str(target),
        source_url=url,
        title=url,
        official=trusted,
        created_at=utc_now_iso(),
        content_hash=sha256_file(target),
        modifications=["cropped browser capture", "wording not altered"],
        approval_required=not trusted,
    )
    _save_manifest(folder, [item], append=True)
    return item


def _save_manifest(folder: Path, items: list[EvidenceItem], *, append: bool = False) -> Path:
    path = folder / "evidence" / "evidence-plan.json"
    existing: list[dict[str, Any]] = []
    if append and path.exists():
        import json
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            existing = []
    records = {item.get("id"): item for item in existing if isinstance(item, dict)}
    for item in items:
        records[item.id] = asdict(item)
    return write_json(path, list(records.values()))


def build(generation: str | Path, workspace: str | Path | None = None) -> list[EvidenceItem]:
    return [*build_article_cards(generation, workspace), *build_social_cards(generation, workspace)]
