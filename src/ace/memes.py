from __future__ import annotations

import json
import urllib.parse
from dataclasses import asdict, dataclass
from importlib.resources import files
from pathlib import Path
from typing import Any

from ace.graphics import create_meme_card
from ace.http import request
from ace.resources import Resource
from ace.secrets import load as load_secrets
from ace.storage import resolve_generation
from ace.utils import ensure_dir, sha256_file, slugify, utc_now_iso, write_json


@dataclass
class MemeCandidate:
    id: str
    provider: str
    title: str
    preview_url: str
    source_url: str
    download_url: str | None
    attribution: str | None
    approval_required: bool
    reuse_status: str
    meaning: list[str]
    mood_fit: float
    notes: list[str]


def catalog() -> dict[str, Any]:
    return json.loads(files("ace.data").joinpath("meme_catalog.json").read_text(encoding="utf-8"))


def template_fit(topic: str, mood: str) -> list[dict[str, Any]]:
    tokens = set(topic.lower().split())
    scored: list[dict[str, Any]] = []
    for template in catalog().get("templates", []):
        if mood in template.get("blocked_moods", []):
            continue
        meaning = " ".join(template.get("meaning", [])).lower()
        score = sum(token in meaning for token in tokens) / max(1, len(tokens))
        if mood in template.get("moods", []):
            score += 0.35
        scored.append({**template, "score": round(min(1.0, score), 2)})
    return sorted(scored, key=lambda item: item["score"], reverse=True)


def search_giphy(query: str, key: str, limit: int = 10) -> list[MemeCandidate]:
    params = urllib.parse.urlencode({"api_key": key, "q": query, "limit": min(25, limit), "rating": "pg-13", "lang": "en"})
    data = request("GET", f"https://api.giphy.com/v1/gifs/search?{params}", timeout=30, retries=1).json()
    results: list[MemeCandidate] = []
    for row in data.get("data", []):
        images = row.get("images") or {}
        original = images.get("original") or {}
        preview = images.get("fixed_width_small") or original
        results.append(
            MemeCandidate(
                id=f"giphy-{row.get('id')}",
                provider="giphy",
                title=str(row.get("title") or "GIPHY reaction"),
                preview_url=str(preview.get("url") or original.get("url") or ""),
                source_url=str(row.get("url") or ""),
                download_url=str(original.get("mp4") or original.get("url") or "") or None,
                attribution="Powered by GIPHY",
                approval_required=True,
                reuse_status="provider_terms_review_required",
                meaning=[query],
                mood_fit=0.6,
                notes=["Preview/search result only until the user approves and provider terms are suitable for the intended render."],
            )
        )
    return results


def search_tenor(query: str, key: str, limit: int = 10) -> list[MemeCandidate]:
    params = urllib.parse.urlencode({"key": key, "q": query, "limit": min(50, limit), "media_filter": "gif,tinygif,mp4"})
    data = request("GET", f"https://tenor.googleapis.com/v2/search?{params}", timeout=30, retries=1).json()
    results: list[MemeCandidate] = []
    for row in data.get("results", []):
        media = row.get("media_formats") or {}
        mp4 = media.get("mp4") or {}
        gif = media.get("gif") or {}
        tiny = media.get("tinygif") or {}
        results.append(
            MemeCandidate(
                id=f"tenor-{row.get('id')}",
                provider="tenor",
                title=str(row.get("content_description") or "Tenor reaction"),
                preview_url=str(tiny.get("url") or gif.get("url") or mp4.get("url") or ""),
                source_url=str(row.get("itemurl") or ""),
                download_url=str(mp4.get("url") or gif.get("url") or "") or None,
                attribution="Via Tenor",
                approval_required=True,
                reuse_status="provider_terms_review_required",
                meaning=[query],
                mood_fit=0.6,
                notes=["Preview/search result only until the user approves and provider terms are suitable for the intended render."],
            )
        )
    return results


def search(query: str, workspace: str | Path | None = None, *, limit: int = 10) -> list[MemeCandidate]:
    secrets = load_secrets(workspace)
    results: list[MemeCandidate] = []
    if secrets.get("GIPHY_API_KEY"):
        try:
            results.extend(search_giphy(query, secrets["GIPHY_API_KEY"], limit))
        except Exception:
            pass
    if secrets.get("TENOR_API_KEY"):
        try:
            results.extend(search_tenor(query, secrets["TENOR_API_KEY"], limit))
        except Exception:
            pass
    return results[:limit]


def generate(generation: str | Path, *, setup: str, punchline: str, workspace: str | Path | None = None) -> Resource:
    folder = resolve_generation(generation, workspace)
    output = ensure_dir(folder / "visuals" / "generated") / f"meme-{slugify(punchline, 48)}.png"
    create_meme_card(output, setup=setup, punchline=punchline)
    resource = Resource(
        id=f"ace-meme-{sha256_file(output)[:12]}",
        title=punchline,
        type="image",
        source_provider="ace_generated",
        source_url="ace://generated/meme",
        download_url=None,
        license="user_owned",
        attribution_required=False,
        creator="ACE",
        publishable=True,
        local_path=str(output),
        tags=["meme", "generated"],
        notes=["ACE-generated meme-style card; not a copied internet meme."],
    )
    manifest_path = folder / "visuals" / "generated" / "manifest.json"
    existing = []
    if manifest_path.exists():
        existing = json.loads(manifest_path.read_text(encoding="utf-8"))
    existing.append({**asdict(resource), "created_at": utc_now_iso(), "setup": setup, "punchline": punchline})
    write_json(manifest_path, existing)
    return resource


def import_candidate(
    generation: str | Path,
    candidate: MemeCandidate,
    *,
    approved: bool,
    workspace: str | Path | None = None,
) -> Resource:
    if candidate.approval_required and not approved:
        raise PermissionError("This internet meme/GIF requires explicit approval before import.")
    if not candidate.download_url:
        raise ValueError("Candidate has no downloadable media URL.")
    folder = resolve_generation(generation, workspace)
    suffix = Path(urllib.parse.urlparse(candidate.download_url).path).suffix or ".mp4"
    target = ensure_dir(folder / "resources" / "attribution-required") / f"{candidate.id}{suffix}"
    response = request("GET", candidate.download_url, timeout=60, retries=2)
    target.write_bytes(response.body)
    return Resource(
        id=candidate.id,
        title=candidate.title,
        type="video" if suffix.lower() in {".mp4", ".webm", ".mov"} else "image",
        source_provider=candidate.provider,
        source_url=candidate.source_url,
        download_url=candidate.download_url,
        license="provider_terms",
        attribution_required=True,
        creator=candidate.attribution,
        approval_required=True,
        publishable=True,
        local_path=str(target),
        tags=["meme", candidate.provider],
        notes=[*candidate.notes, f"Approved for this generation: {approved}"],
    )
