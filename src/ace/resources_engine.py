from __future__ import annotations

import json
import os
import re
import shutil
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace import assets
from ace.config import load as load_config
from ace.errors import ACEError, ProviderUnavailable
from ace.storage import file_sha256, resolve_generation, slugify, write_json


USER_AGENT = "ACE/1.7.0 (Automated Content Empire; resource discovery)"


@dataclass
class Resource:
    id: str
    title: str
    type: str
    source_provider: str
    source_url: str
    download_url: str | None
    creator: str | None
    license: str
    license_url: str | None
    status: str
    commercial_use: bool
    modification: bool
    attribution_required: bool
    local_path: str | None = None
    notes: str | None = None


def _fetch_json(url: str, *, headers: dict[str, str] | None = None, timeout: float = 30) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            value = json.loads(response.read().decode("utf-8"))
    except Exception as exc:
        raise ProviderUnavailable(f"Resource provider request failed: {exc}") from exc
    if not isinstance(value, dict):
        raise ProviderUnavailable("Resource provider returned invalid JSON.")
    return value


def _download(url: str, destination: Path, *, headers: dict[str, str] | None = None) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **(headers or {})})
    with urllib.request.urlopen(request, timeout=90) as response, destination.open("wb") as output:
        shutil.copyfileobj(response, output)
    return destination


def _license_status(license_name: str) -> tuple[str, bool, bool, bool]:
    normalized = re.sub(r"\s+", " ", license_name.lower()).strip()
    if "public domain" in normalized or normalized in {"cc0", "cc zero"}:
        return "publishable", True, True, False
    if "share alike" in normalized or "by-sa" in normalized or "by sa" in normalized:
        return "blocked", False, False, True
    if "cc by" in normalized and "nc" not in normalized and "nd" not in normalized:
        return "publishable_with_credit", True, True, True
    if normalized in {"pexels", "pixabay", "unsplash", "user_owned"}:
        return "publishable", True, True, False
    if "noncommercial" in normalized or "nc" in normalized or "no derivatives" in normalized or "nd" in normalized:
        return "blocked", False, False, True
    return "blocked", False, False, True


def search_openverse(query: str, *, limit: int = 10) -> list[Resource]:
    """Search Openverse for public-domain, CC0, and commercial CC BY images."""

    params = {
        "q": query,
        "license": "pdm,cc0,by",
        "page_size": str(max(1, min(20, limit))),
        "mature": "false",
    }
    headers: dict[str, str] = {}
    token = os.environ.get("OPENVERSE_ACCESS_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    raw = _fetch_json(
        "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params),
        headers=headers,
    )
    results: list[Resource] = []
    for row in raw.get("results", []):
        if not isinstance(row, dict):
            continue
        license_code = str(row.get("license") or "unknown").lower()
        if license_code == "pdm":
            license_name = "Public Domain Mark"
        elif license_code == "cc0":
            license_name = "CC0"
        elif license_code == "by":
            version = str(row.get("license_version") or "").strip()
            license_name = f"CC BY {version}".strip()
        else:
            continue
        status, commercial, modification, attribution = _license_status(license_name)
        if status == "blocked":
            continue
        download_url = row.get("url") or row.get("thumbnail")
        if not isinstance(download_url, str):
            continue
        results.append(
            Resource(
                id=f"openverse-{row.get('id')}",
                title=str(row.get("title") or "Openverse image"),
                type="image",
                source_provider="openverse",
                source_url=str(row.get("foreign_landing_url") or row.get("detail_url") or download_url),
                download_url=download_url,
                creator=str(row.get("creator") or "").strip() or None,
                license=license_name,
                license_url=str(row.get("license_url") or "").strip() or None,
                status=status,
                commercial_use=commercial,
                modification=modification,
                attribution_required=attribution,
                notes=str(row.get("attribution") or "").strip() or None,
            )
        )
    return results[:limit]


def search_wikimedia(query: str, *, limit: int = 10, media_type: str | None = None) -> list[Resource]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}" if media_type != "video" else query,
        "gsrnamespace": "6",
        "gsrlimit": str(limit * 3),
        "prop": "imageinfo",
        "iiprop": "url|mime|extmetadata",
        "iiurlwidth": "1920",
    }
    raw = _fetch_json("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params))
    results: list[Resource] = []
    for page in raw.get("query", {}).get("pages", {}).values():
        if not isinstance(page, dict):
            continue
        info_list = page.get("imageinfo", [])
        if not info_list or not isinstance(info_list[0], dict):
            continue
        info = info_list[0]
        mime = str(info.get("mime", ""))
        kind = "video" if mime.startswith("video/") else "image" if mime.startswith("image/") else "file"
        if media_type and kind != media_type:
            continue
        metadata = info.get("extmetadata", {}) if isinstance(info.get("extmetadata"), dict) else {}
        license_name = str(metadata.get("LicenseShortName", {}).get("value") or metadata.get("UsageTerms", {}).get("value") or "unknown")
        status, commercial, modification, attribution = _license_status(license_name)
        if status == "blocked":
            continue
        download_url = info.get("thumburl") or info.get("url")
        if not isinstance(download_url, str):
            continue
        results.append(
            Resource(
                id=f"wikimedia-{page.get('pageid')}",
                title=str(page.get("title", "")).removeprefix("File:"),
                type=kind,
                source_provider="wikimedia",
                source_url=str(info.get("descriptionurl") or info.get("url") or ""),
                download_url=download_url,
                creator=re.sub("<[^>]+>", "", str(metadata.get("Artist", {}).get("value") or "")).strip() or None,
                license=license_name,
                license_url=str(metadata.get("LicenseUrl", {}).get("value") or "") or None,
                status=status,
                commercial_use=commercial,
                modification=modification,
                attribution_required=attribution,
            )
        )
        if len(results) >= limit:
            break
    return results


def search_pexels(query: str, *, limit: int = 10, media_type: str = "image") -> list[Resource]:
    key = os.environ.get("PEXELS_API_KEY", "").strip()
    if not key:
        return []
    if media_type == "video":
        url = "https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": query, "per_page": limit})
        raw = _fetch_json(url, headers={"Authorization": key})
        rows = raw.get("videos", [])
    else:
        url = "https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": query, "per_page": limit})
        raw = _fetch_json(url, headers={"Authorization": key})
        rows = raw.get("photos", [])
    results: list[Resource] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        if media_type == "video":
            files = [item for item in row.get("video_files", []) if isinstance(item, dict) and item.get("link")]
            files.sort(key=lambda item: int(item.get("width") or 0), reverse=True)
            download_url = files[0].get("link") if files else None
            title = f"Pexels video {row.get('id')}"
        else:
            download_url = row.get("src", {}).get("large2x") or row.get("src", {}).get("original")
            title = str(row.get("alt") or f"Pexels photo {row.get('id')}")
        if not isinstance(download_url, str):
            continue
        results.append(
            Resource(
                id=f"pexels-{row.get('id')}",
                title=title,
                type=media_type,
                source_provider="pexels",
                source_url=str(row.get("url") or ""),
                download_url=download_url,
                creator=str(row.get("photographer") or row.get("user", {}).get("name") or "") or None,
                license="Pexels",
                license_url="https://www.pexels.com/license/",
                status="publishable",
                commercial_use=True,
                modification=True,
                attribution_required=False,
            )
        )
    return results


def search_pixabay(query: str, *, limit: int = 10, media_type: str = "image") -> list[Resource]:
    key = os.environ.get("PIXABAY_API_KEY", "").strip()
    if not key:
        return []
    endpoint = "https://pixabay.com/api/videos/" if media_type == "video" else "https://pixabay.com/api/"
    params = {"key": key, "q": query, "per_page": max(3, min(200, limit)), "safesearch": "true"}
    raw = _fetch_json(endpoint + "?" + urllib.parse.urlencode(params))
    results: list[Resource] = []
    for row in raw.get("hits", []):
        if not isinstance(row, dict):
            continue
        if media_type == "video":
            videos = row.get("videos", {})
            chosen = videos.get("large") or videos.get("medium") or videos.get("small") or {}
            download_url = chosen.get("url")
        else:
            download_url = row.get("largeImageURL") or row.get("webformatURL")
        if not isinstance(download_url, str):
            continue
        results.append(
            Resource(
                id=f"pixabay-{row.get('id')}",
                title=str(row.get("tags") or f"Pixabay {media_type} {row.get('id')}") ,
                type=media_type,
                source_provider="pixabay",
                source_url=str(row.get("pageURL") or ""),
                download_url=download_url,
                creator=str(row.get("user") or "") or None,
                license="Pixabay",
                license_url="https://pixabay.com/service/license-summary/",
                status="publishable",
                commercial_use=True,
                modification=True,
                attribution_required=False,
            )
        )
    return results


def search_news_references(query: str, *, limit: int = 8) -> list[Resource]:
    url = "https://news.google.com/rss/search?" + urllib.parse.urlencode({"q": query, "hl": "en", "gl": "US", "ceid": "US:en"})
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            root = ET.fromstring(response.read())
    except Exception:
        return []
    results: list[Resource] = []
    for index, item in enumerate(root.findall("./channel/item")[:limit], 1):
        title = item.findtext("title") or "News reference"
        link = item.findtext("link") or ""
        source = item.find("source")
        creator = source.text if source is not None else None
        results.append(
            Resource(
                id=f"news-{index}-{slugify(title, 24)}",
                title=title,
                type="article",
                source_provider="news_rss",
                source_url=link,
                download_url=None,
                creator=creator,
                license="reference_only",
                license_url=None,
                status="reference_only",
                commercial_use=False,
                modification=False,
                attribution_required=True,
                notes="Use as a research lead. Verify important claims with primary or authoritative sources before publishing.",
            )
        )
    return results


def _local_resources(query: str, profile_slug: str, workspace: str | Path | None, media_type: str | None) -> list[Resource]:
    rows = assets.search(query, profile_slug, asset_type=media_type, workspace=workspace)
    return [
        Resource(
            id=str(item["id"]),
            title=str(item.get("filename", item["id"])),
            type=str(item.get("type", "file")),
            source_provider="library",
            source_url=str(item.get("path", "")),
            download_url=str(item.get("path", "")),
            creator=None,
            license=str(item.get("license", "user_owned")),
            license_url=None,
            status="publishable",
            commercial_use=True,
            modification=True,
            attribution_required=False,
            local_path=str(item.get("path", "")),
        )
        for item in rows
    ]


def find_resources(
    query: str,
    profile_slug: str,
    *,
    media_type: str | None = None,
    limit: int = 8,
    workspace: str | Path | None = None,
) -> list[Resource]:
    config = load_config(workspace).get("resources", {})
    providers = config.get("providers", {})
    results: list[Resource] = []
    if providers.get("library", {}).get("enabled", True):
        results.extend(_local_resources(query, profile_slug, workspace, media_type))
    if providers.get("pexels", {}).get("enabled", False):
        results.extend(search_pexels(query, limit=limit, media_type=media_type or "image"))
    if providers.get("pixabay", {}).get("enabled", False):
        results.extend(search_pixabay(query, limit=limit, media_type=media_type or "image"))
    if media_type in {None, "image"} and providers.get("openverse", {}).get("enabled", True):
        try:
            results.extend(search_openverse(query, limit=limit))
        except ACEError:
            pass
    if providers.get("wikimedia", {}).get("enabled", True):
        try:
            results.extend(search_wikimedia(query, limit=limit, media_type=media_type))
        except ACEError:
            pass
    seen: set[str] = set()
    unique: list[Resource] = []
    for item in results:
        key = item.download_url or item.source_url or item.id
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    source_priority = {"library": 0, "pexels": 1, "pixabay": 2, "openverse": 3, "wikimedia": 4}
    unique.sort(key=lambda item: (source_priority.get(item.source_provider, 9), item.attribution_required, item.title))
    return unique[:limit]


def _extension(resource: Resource) -> str:
    source = resource.download_url or resource.source_url
    suffix = Path(urllib.parse.urlparse(source).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".svg", ".mp4", ".webm", ".mov", ".mkv"}:
        return suffix
    return ".mp4" if resource.type == "video" else ".jpg"


def collect_for_generation(
    generation: str | Path,
    *,
    query: str | None = None,
    profile_slug: str | None = None,
    media_type: str | None = None,
    limit: int | None = None,
    workspace: str | Path | None = None,
    include_news: bool = True,
) -> list[Resource]:
    folder = resolve_generation(generation, workspace)
    metadata_path = folder / "metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {}
    profile_slug = profile_slug or str(metadata.get("profile_slug") or "no-profile")
    query = query or str(metadata.get("topic") or folder.name)
    config = load_config(workspace)
    limit = limit or int(config.get("resources", {}).get("download_limit_per_generation", 8))
    if media_type:
        candidates = find_resources(query, profile_slug, media_type=media_type, limit=limit * 2, workspace=workspace)
        selected = candidates[:limit]
        resource_strategy = media_type
    else:
        content_type = str(metadata.get("content_type") or "")
        video_deliverables = {"short", "reel", "story", "long_video", "video_script", "ad"}
        wants_video = content_type in video_deliverables
        video_limit = max(1, round(limit * 0.6)) if wants_video else max(1, round(limit * 0.25))
        image_limit = max(1, limit - video_limit)
        video_candidates = find_resources(query, profile_slug, media_type="video", limit=video_limit * 2, workspace=workspace)
        image_candidates = find_resources(query, profile_slug, media_type="image", limit=image_limit * 2, workspace=workspace)
        combined = [*(video_candidates if wants_video else image_candidates), *(image_candidates if wants_video else video_candidates)]
        selected = []
        seen_sources: set[str] = set()
        for candidate in combined:
            key = candidate.download_url or candidate.source_url or candidate.id
            if key in seen_sources:
                continue
            seen_sources.add(key)
            selected.append(candidate)
            if len(selected) >= limit:
                break
        resource_strategy = "video_first" if wants_video else "image_first"
    publishable = folder / "resources" / "publishable"
    attribution = folder / "resources" / "attribution-required"
    records: list[dict[str, Any]] = []
    for index, resource in enumerate(selected, 1):
        destination_dir = attribution if resource.attribution_required else publishable
        if resource.local_path:
            source = Path(resource.local_path)
            destination = destination_dir / f"{index:02d}-{source.name}"
            if not destination.exists():
                try:
                    destination.symlink_to(source)
                except OSError:
                    shutil.copy2(source, destination)
        elif resource.download_url:
            destination = destination_dir / f"{index:02d}-{slugify(resource.title, 48)}{_extension(resource)}"
            try:
                _download(resource.download_url, destination)
            except Exception as exc:
                resource.notes = f"Download failed: {exc}"
                continue
        else:
            continue
        resource.local_path = str(destination)
        records.append(asdict(resource))

    references = search_news_references(query) if include_news else []
    references_dir = folder / "resources" / "reference-only"
    references_dir.mkdir(parents=True, exist_ok=True)
    write_json(references_dir / "news-references.json", [asdict(item) for item in references])

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "query": query,
        "license_policy": config.get("resources", {}).get("license_policy", "strict"),
        "selection_strategy": resource_strategy,
        "publishable": records,
        "reference_only": [asdict(item) for item in references],
    }
    write_json(folder / "licenses" / "manifest.json", manifest)
    lines = ["# Asset attribution", ""]
    for record in records:
        if record.get("attribution_required"):
            lines.append(f"- {record.get('title')} — {record.get('creator') or 'Unknown creator'} — {record.get('license')} — {record.get('source_url')}")
    if len(lines) == 2:
        lines.append("No downloaded asset in this generation requires attribution according to its recorded license metadata.")
    (folder / "licenses" / "ATTRIBUTION.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return [Resource(**record) for record in records]


def classify_license(license_name: str) -> tuple[str, bool, bool, bool]:
    """Public license classifier used by readiness checks and self-tests."""
    return _license_status(license_name)
