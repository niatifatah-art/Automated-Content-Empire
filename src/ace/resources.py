from __future__ import annotations

import shutil
import urllib.parse
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ace.accounts import asset_dir
from ace.cache import Cache
from ace.config import load as load_config
from ace.http import request
from ace.secrets import load as load_secrets
from ace.storage import metadata, resolve_generation
from ace.utils import ensure_dir, read_json, sha256_bytes, slugify, utc_now_iso, write_json


@dataclass
class Resource:
    id: str
    title: str
    type: str
    source_provider: str
    source_url: str
    download_url: str | None
    license: str
    attribution_required: bool
    creator: str | None = None
    width: int | None = None
    height: int | None = None
    duration: float | None = None
    tags: list[str] = field(default_factory=list)
    approval_required: bool = False
    publishable: bool = True
    local_path: str | None = None
    query: str | None = None
    notes: list[str] = field(default_factory=list)


def _key(resource: Resource) -> str:
    return resource.download_url or resource.source_url or resource.id


def _resource_id(provider: str, value: str) -> str:
    return f"{provider}-{sha256_bytes(value.encode('utf-8'))[:14]}"


def _safe_license(name: str) -> tuple[bool, bool]:
    normalized = name.strip().lower().replace(" ", "_")
    if normalized in {"user_owned", "public_domain", "cc0", "pexels", "pixabay"}:
        return True, False
    if normalized.startswith("cc_by"):
        return True, True
    return False, True


def _json_get(url: str, *, headers: dict[str, str] | None = None, workspace: str | Path | None = None, ttl: int = 86400) -> Any:
    cache = Cache(workspace)
    return request("GET", url, headers=headers, timeout=30, retries=1, cache=cache, cache_ttl=ttl).json()


def search_library(query: str, media_type: str, workspace: str | Path | None = None, limit: int = 20) -> list[Resource]:
    root = asset_dir(workspace=workspace)
    tokens = {item.lower() for item in query.replace("-", " ").split() if len(item) > 2}
    results: list[Resource] = []
    video_ext = {".mp4", ".mov", ".mkv", ".webm", ".m4v"}
    image_ext = {".jpg", ".jpeg", ".png", ".webp", ".gif"}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        kind = "video" if path.suffix.lower() in video_ext else "image" if path.suffix.lower() in image_ext else None
        if kind != media_type:
            continue
        sidecar = path.with_suffix(path.suffix + ".tags")
        tag_values = []
        if sidecar.exists():
            tag_values = [item.strip().lower() for item in sidecar.read_text(encoding="utf-8", errors="ignore").replace("\n", ",").split(",") if item.strip()]
        haystack = " ".join([path.stem.lower().replace("-", " ").replace("_", " "), *tag_values])
        score = sum(token in haystack for token in tokens)
        if tokens and score == 0:
            continue
        results.append(
            Resource(
                id=_resource_id("library", str(path.resolve())),
                title=path.stem,
                type=kind,
                source_provider="library",
                source_url=path.as_uri(),
                download_url=None,
                license="user_owned",
                attribution_required=False,
                local_path=str(path.resolve()),
                tags=sorted(set(tag_values) | tokens),
                query=query,
            )
        )
    return results[:limit]


def search_pexels(query: str, media_type: str, key: str, workspace: str | Path | None = None, limit: int = 20) -> list[Resource]:
    encoded = urllib.parse.urlencode({"query": query, "per_page": min(80, max(3, limit)), "orientation": "portrait"})
    endpoint = "videos/search" if media_type == "video" else "v1/search"
    data = _json_get(f"https://api.pexels.com/{endpoint}?{encoded}", headers={"Authorization": key}, workspace=workspace)
    rows = data.get("videos", []) if media_type == "video" else data.get("photos", [])
    results: list[Resource] = []
    for row in rows:
        if media_type == "video":
            files = sorted(row.get("video_files", []), key=lambda item: (item.get("height", 0) < item.get("width", 0), -int(item.get("height", 0) or 0)))
            selected = next((item for item in files if item.get("link")), None)
            if not selected:
                continue
            source = str(row.get("url") or selected["link"])
            results.append(
                Resource(
                    id=f"pexels-{row.get('id')}",
                    title=f"Pexels video {row.get('id')}",
                    type="video",
                    source_provider="pexels",
                    source_url=source,
                    download_url=str(selected["link"]),
                    license="pexels",
                    attribution_required=False,
                    creator=(row.get("user") or {}).get("name"),
                    width=selected.get("width"),
                    height=selected.get("height"),
                    duration=row.get("duration"),
                    query=query,
                )
            )
        else:
            src = row.get("src") or {}
            download = src.get("large2x") or src.get("large") or src.get("portrait") or src.get("original")
            if not download:
                continue
            results.append(
                Resource(
                    id=f"pexels-{row.get('id')}",
                    title=str(row.get("alt") or f"Pexels photo {row.get('id')}"),
                    type="image",
                    source_provider="pexels",
                    source_url=str(row.get("url") or download),
                    download_url=str(download),
                    license="pexels",
                    attribution_required=False,
                    creator=row.get("photographer"),
                    width=row.get("width"),
                    height=row.get("height"),
                    query=query,
                )
            )
    return results


def search_pixabay(query: str, media_type: str, key: str, workspace: str | Path | None = None, limit: int = 20) -> list[Resource]:
    params = {"key": key, "q": query, "safesearch": "true", "per_page": min(200, max(3, limit)), "order": "popular"}
    endpoint = "https://pixabay.com/api/videos/" if media_type == "video" else "https://pixabay.com/api/"
    data = _json_get(endpoint + "?" + urllib.parse.urlencode(params), workspace=workspace)
    results: list[Resource] = []
    for row in data.get("hits", []):
        if media_type == "video":
            variants = row.get("videos") or {}
            selected = variants.get("medium") or variants.get("small") or variants.get("large") or variants.get("tiny") or {}
            download = selected.get("url")
            if not download:
                continue
            results.append(
                Resource(
                    id=f"pixabay-{row.get('id')}",
                    title=f"Pixabay video {row.get('id')}",
                    type="video",
                    source_provider="pixabay",
                    source_url=str(row.get("pageURL") or download),
                    download_url=str(download),
                    license="pixabay",
                    attribution_required=False,
                    creator=row.get("user"),
                    width=selected.get("width"),
                    height=selected.get("height"),
                    duration=row.get("duration"),
                    tags=[tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip()],
                    query=query,
                )
            )
        else:
            download = row.get("largeImageURL") or row.get("webformatURL")
            if not download:
                continue
            results.append(
                Resource(
                    id=f"pixabay-{row.get('id')}",
                    title=str(row.get("tags") or f"Pixabay image {row.get('id')}"),
                    type="image",
                    source_provider="pixabay",
                    source_url=str(row.get("pageURL") or download),
                    download_url=str(download),
                    license="pixabay",
                    attribution_required=False,
                    creator=row.get("user"),
                    width=row.get("imageWidth") or row.get("webformatWidth"),
                    height=row.get("imageHeight") or row.get("webformatHeight"),
                    tags=[tag.strip() for tag in str(row.get("tags", "")).split(",") if tag.strip()],
                    query=query,
                )
            )
    return results


def search_openverse(query: str, media_type: str, token: str | None, workspace: str | Path | None = None, limit: int = 20) -> list[Resource]:
    if media_type != "image":
        return []
    params = {"q": query, "page_size": min(80, max(1, limit)), "mature": "false"}
    headers = {"Authorization": f"Bearer {token}"} if token else None
    data = _json_get("https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params), headers=headers, workspace=workspace)
    results: list[Resource] = []
    for row in data.get("results", []):
        license_name = str(row.get("license") or "unknown").lower()
        if row.get("license_version"):
            license_name = f"{license_name}_{row.get('license_version')}"
        safe, attribution = _safe_license(license_name)
        download = row.get("url") or row.get("thumbnail")
        if not download:
            continue
        results.append(
            Resource(
                id=f"openverse-{row.get('id')}",
                title=str(row.get("title") or "Openverse image"),
                type="image",
                source_provider="openverse",
                source_url=str(row.get("foreign_landing_url") or download),
                download_url=str(download),
                license=license_name,
                attribution_required=attribution,
                creator=row.get("creator"),
                width=row.get("width"),
                height=row.get("height"),
                tags=[str(item.get("name")) for item in row.get("tags", []) if isinstance(item, dict) and item.get("name")],
                publishable=safe,
                query=query,
                notes=[] if safe else ["License was not in ACE's automatic allowlist."],
            )
        )
    return results


def search_wikimedia(query: str, media_type: str, workspace: str | Path | None = None, limit: int = 20) -> list[Resource]:
    if media_type != "image":
        return []
    params = {
        "action": "query",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": 6,
        "gsrlimit": min(50, max(1, limit)),
        "prop": "imageinfo|info",
        "iiprop": "url|extmetadata|size",
        "inprop": "url",
        "format": "json",
        "origin": "*",
    }
    data = _json_get("https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params), workspace=workspace)
    results: list[Resource] = []
    for row in (data.get("query", {}).get("pages", {}) or {}).values():
        info = (row.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata") or {}
        license_name = str((meta.get("LicenseShortName") or {}).get("value") or "unknown").lower().replace(" ", "_")
        safe, attribution = _safe_license(license_name)
        download = info.get("url")
        if not download:
            continue
        results.append(
            Resource(
                id=f"wikimedia-{row.get('pageid')}",
                title=str(row.get("title") or "Wikimedia image").removeprefix("File:"),
                type="image",
                source_provider="wikimedia",
                source_url=str(row.get("fullurl") or download),
                download_url=str(download),
                license=license_name,
                attribution_required=attribution,
                creator=(meta.get("Artist") or {}).get("value"),
                width=info.get("width"),
                height=info.get("height"),
                publishable=safe,
                query=query,
                notes=[] if safe else ["License requires manual verification."],
            )
        )
    return results


def find(query: str, *, media_type: str = "video", workspace: str | Path | None = None, limit: int = 12) -> list[Resource]:
    config = load_config(workspace)
    secrets = load_secrets(workspace)
    provider_cfg = config.get("resources", {}).get("providers", {})
    functions = []
    if provider_cfg.get("library", {}).get("enabled", True):
        functions.append((0, "library", lambda: search_library(query, media_type, workspace, limit * 2)))
    if provider_cfg.get("pexels", {}).get("enabled") and secrets.get("PEXELS_API_KEY"):
        functions.append((1, "pexels", lambda: search_pexels(query, media_type, secrets["PEXELS_API_KEY"], workspace, limit * 2)))
    if provider_cfg.get("pixabay", {}).get("enabled") and secrets.get("PIXABAY_API_KEY"):
        functions.append((2, "pixabay", lambda: search_pixabay(query, media_type, secrets["PIXABAY_API_KEY"], workspace, limit * 2)))
    if provider_cfg.get("openverse", {}).get("enabled"):
        functions.append((3, "openverse", lambda: search_openverse(query, media_type, secrets.get("OPENVERSE_ACCESS_TOKEN"), workspace, limit * 2)))
    if provider_cfg.get("wikimedia", {}).get("enabled"):
        functions.append((4, "wikimedia", lambda: search_wikimedia(query, media_type, workspace, limit * 2)))
    results: list[Resource] = []
    for _, name, function in sorted(functions):
        try:
            results.extend(function())
        except Exception as exc:
            # Provider failures must not destroy the complete visual route.
            results.append(
                Resource(
                    id=_resource_id(name, str(exc)),
                    title=f"{name} provider unavailable",
                    type=media_type,
                    source_provider=name,
                    source_url="",
                    download_url=None,
                    license="reference_only",
                    attribution_required=False,
                    publishable=False,
                    query=query,
                    notes=[str(exc)],
                )
            )
    seen: set[str] = set()
    unique: list[Resource] = []
    for item in results:
        if not item.publishable:
            continue
        key = _key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique[:limit]


def _extension(resource: Resource) -> str:
    source = resource.download_url or resource.source_url
    suffix = Path(urllib.parse.urlparse(source).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".gif", ".mp4", ".webm", ".mov", ".mkv"}:
        return suffix
    return ".mp4" if resource.type == "video" else ".jpg"


def _download(url: str, target: Path, workspace: str | Path | None = None) -> Path:
    response = request("GET", url, timeout=90, retries=2)
    ensure_dir(target.parent)
    target.write_bytes(response.body)
    return target


def collect(
    generation: str | Path,
    *,
    query: str | None = None,
    media_type: str | None = None,
    workspace: str | Path | None = None,
    limit: int | None = None,
) -> list[Resource]:
    folder = resolve_generation(generation, workspace)
    info = metadata(folder)
    query = query or str(info.get("topic") or folder.name)
    config = load_config(workspace)
    limit = limit or int(config.get("resources", {}).get("download_limit_per_generation", 12))
    content_type = str(info.get("content_type") or "")
    wants_video = content_type in {"short", "reel", "story", "long_video", "video_script", "ad"}
    if media_type:
        candidates = find(query, media_type=media_type, workspace=workspace, limit=limit * 2)
    else:
        video_limit = max(1, round(limit * 0.65)) if wants_video else max(1, round(limit * 0.25))
        image_limit = max(1, limit - video_limit)
        videos = find(query, media_type="video", workspace=workspace, limit=video_limit)
        images = find(query, media_type="image", workspace=workspace, limit=image_limit)
        candidates = [*videos, *images] if wants_video else [*images, *videos]
    selected = candidates[:limit]
    publishable_dir = ensure_dir(folder / "resources" / "publishable")
    attribution_dir = ensure_dir(folder / "resources" / "attribution-required")
    records: list[Resource] = []
    for index, resource in enumerate(selected, 1):
        destination_dir = attribution_dir if resource.attribution_required else publishable_dir
        if resource.local_path:
            source = Path(resource.local_path)
            target = destination_dir / f"{index:02d}-{source.name}"
            if not target.exists():
                try:
                    target.symlink_to(source)
                except OSError:
                    shutil.copy2(source, target)
        elif resource.download_url:
            target = destination_dir / f"{index:02d}-{slugify(resource.title, 48)}{_extension(resource)}"
            try:
                _download(resource.download_url, target, workspace)
            except Exception as exc:
                resource.notes.append(f"Download failed: {exc}")
                continue
        else:
            continue
        resource.local_path = str(target)
        records.append(resource)
    manifest = {
        "schema_version": 2,
        "generated_at": utc_now_iso(),
        "query": query,
        "publishable": [asdict(item) for item in records],
        "reference_only": [],
    }
    write_json(folder / "licenses" / "manifest.json", manifest)
    attribution_lines = ["# Asset attribution", ""]
    for item in records:
        if item.attribution_required:
            attribution_lines.append(f"- {item.title} — {item.creator or 'Unknown creator'} — {item.license} — {item.source_url}")
    if len(attribution_lines) == 2:
        attribution_lines.append("No downloaded asset in this generation requires attribution according to its recorded metadata.")
    (folder / "licenses" / "ATTRIBUTION.md").write_text("\n".join(attribution_lines) + "\n", encoding="utf-8")
    return records


def list_collected(generation: str | Path, workspace: str | Path | None = None) -> list[Resource]:
    folder = resolve_generation(generation, workspace)
    manifest = read_json(folder / "licenses" / "manifest.json", {}) or {}
    return [Resource(**row) for row in manifest.get("publishable", []) if isinstance(row, dict)]
