from __future__ import annotations

import shutil
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from ace.graphics import create_card
from ace.creative import choose_meme_beat
from ace.memes import generate as generate_meme
from ace.http import request
from ace.media_fingerprint import fingerprint_bundle
from ace.resources import Resource, find as find_resources
from ace.utils import ensure_dir, sha256_bytes, sha256_file, slugify
from ace.visual_intelligence.contracts import CandidateOrigin, ShotIntent, VisualCandidate, VisualFormat
from ace.visual_intelligence.explainer import render_explainer


EVIDENCE_FORMATS = {
    VisualFormat.OFFICIAL_EVIDENCE.value,
    VisualFormat.ARTICLE_CARD.value,
    VisualFormat.SOCIAL_POST_CARD.value,
}


def _candidate_id(shot_id: str, provider: str, value: str) -> str:
    digest = sha256_bytes(value.encode("utf-8", errors="ignore"))[:12]
    return f"{shot_id}-{provider}-{digest}"


def _origin(resource: Resource) -> str:
    if resource.source_provider == "library":
        return CandidateOrigin.ACCOUNT_OWNED.value
    if resource.license in {"pexels", "pixabay", "cc0", "public_domain", "user_owned"}:
        return CandidateOrigin.LICENSED_STOCK.value if resource.source_provider != "library" else CandidateOrigin.ACCOUNT_OWNED.value
    if resource.attribution_required:
        return CandidateOrigin.ATTRIBUTION_REQUIRED.value
    return CandidateOrigin.REFERENCE_ONLY.value


def from_resource(resource: Resource, intent: ShotIntent, visual_format: str | None = None) -> VisualCandidate:
    path = resource.local_path
    fingerprint = None
    fingerprint_bundle_value = None
    if path and Path(path).exists():
        fingerprint_bundle_value = fingerprint_bundle(path, include_perceptual=False)
        fingerprint = fingerprint_bundle_value.get("sha256")
    elif resource.download_url or resource.source_url:
        fingerprint = sha256_bytes(str(resource.download_url or resource.source_url).encode("utf-8"))
    return VisualCandidate(
        candidate_id=_candidate_id(intent.shot_id, resource.source_provider, resource.id),
        shot_id=intent.shot_id,
        format=visual_format or (VisualFormat.STOCK_VIDEO.value if resource.type == "video" else VisualFormat.STOCK_IMAGE.value),
        provider=resource.source_provider,
        title=resource.title,
        description=" ".join([resource.title, resource.query or "", *resource.tags]).strip(),
        path=path,
        source_url=resource.source_url,
        download_url=resource.download_url,
        origin=_origin(resource),
        license_status=resource.license,
        tags=[*resource.tags, *(resource.query or "").split()],
        semantic_elements=[*resource.tags, *(resource.query or "").split()],
        width=resource.width,
        height=resource.height,
        duration=resource.duration,
        approval_required=resource.approval_required or not resource.publishable,
        metadata={"resource": asdict(resource), "fingerprint": fingerprint, "fingerprint_bundle": fingerprint_bundle_value},
    )


def evidence_candidates(folder: Path, intent: ShotIntent) -> list[VisualCandidate]:
    output: list[VisualCandidate] = []
    locations = [
        (folder / "evidence" / "webpage-captures", VisualFormat.OFFICIAL_EVIDENCE.value, CandidateOrigin.OFFICIAL_CAPTURE.value),
        (folder / "evidence" / "article-cards", VisualFormat.ARTICLE_CARD.value, CandidateOrigin.ACE_GENERATED.value),
        (folder / "evidence" / "social-posts", VisualFormat.SOCIAL_POST_CARD.value, CandidateOrigin.ACE_GENERATED.value),
    ]
    for root, visual_format, origin in locations:
        if visual_format not in intent.preferred_formats and not intent.evidence_required:
            continue
        for path in sorted(root.glob("*")):
            if not path.is_file() or path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp", ".mp4"}:
                continue
            output.append(
                VisualCandidate(
                    candidate_id=_candidate_id(intent.shot_id, "evidence", str(path)),
                    shot_id=intent.shot_id,
                    format=visual_format,
                    provider="ace_evidence",
                    title=path.stem.replace("-", " "),
                    description=f"Stored evidence visual for {intent.subject}",
                    path=str(path),
                    origin=origin,
                    license_status="source_capture" if origin == CandidateOrigin.OFFICIAL_CAPTURE.value else "account_owned",
                    tags=[intent.subject, "source", "headline", "official"],
                    semantic_elements=["source_name", "headline", "date"],
                    width=1080,
                    height=1920,
                    metadata={"fingerprint": sha256_file(path), "fingerprint_bundle": fingerprint_bundle(path, include_perceptual=False)},
                )
            )
    return output


def explainer_candidate(
    folder: Path,
    intent: ShotIntent,
    duration: float,
    *,
    animate: bool = True,
    visual_format: str | None = None,
) -> VisualCandidate:
    start = time.monotonic()
    result = render_explainer(
        intent,
        folder / "visuals" / "generated" / "explainers",
        duration=duration,
        animate=animate,
        visual_format=visual_format,
    )
    elapsed = time.monotonic() - start
    provider = "ace_explainer" if result.visual_format == VisualFormat.ANIMATED_EXPLAINER.value else "ace_" + result.visual_format
    return VisualCandidate(
        candidate_id=_candidate_id(intent.shot_id, provider, str(result.path)),
        shot_id=intent.shot_id,
        format=result.visual_format,
        provider=provider,
        title=f"ACE {result.visual_format.replace('_', ' ')} — {intent.subject.replace('_', ' ')}",
        description=result.description,
        path=str(result.path),
        origin=CandidateOrigin.ACE_GENERATED.value,
        license_status="account_owned",
        tags=[intent.subject, *intent.required_elements, result.visual_format, "ace_original", "vertical"],
        semantic_elements=result.semantic_elements,
        width=720,
        height=1280,
        duration=duration,
        generation_time_seconds=elapsed,
        metadata={"animated": result.animated, "fingerprint": sha256_file(result.path), "fingerprint_bundle": fingerprint_bundle(result.path, include_perceptual=False), "resolved_format": result.visual_format},
    )


def generated_concept_candidate(folder: Path, intent: ShotIntent, workspace: str | Path | None = None) -> VisualCandidate:
    """Generate an original concept illustration only when the intent asks for it.

    This path is deliberately separate from evidence. The prompt forbids fake
    webpages, social posts, quotations, and source documents.
    """
    from ace.image_generation import generate as generate_image

    prompt = (
        f"Create a clear vertical technical illustration for this narration: {intent.narration}. "
        f"Subject: {intent.subject.replace('_', ' ')}. Required visual elements: {', '.join(intent.required_elements) or 'the central concept'}. "
        f"Avoid: {', '.join(intent.forbidden_elements) or 'unrelated generic technology imagery'}. "
        "Make the concept understandable in under three seconds, with no logos, no article screenshot, no social post, and minimal or no text."
    )
    start = time.monotonic()
    item = generate_image(folder, prompt, workspace, aspect_ratio="9:16")
    path = Path(item.path)
    return VisualCandidate(
        candidate_id=_candidate_id(intent.shot_id, item.provider, item.content_hash),
        shot_id=intent.shot_id,
        format=VisualFormat.GENERATED_CONCEPT_IMAGE.value,
        provider=item.provider,
        title=f"Generated concept — {intent.subject.replace('_', ' ')}",
        description="Original AI-generated concept illustration, never used as factual evidence.",
        path=str(path),
        origin=CandidateOrigin.AI_GENERATED.value,
        license_status="configured_provider_output",
        tags=[intent.subject, *intent.required_elements, "generated_concept", "illustration"],
        semantic_elements=list(intent.required_elements),
        width=1024,
        height=1536,
        generation_time_seconds=time.monotonic() - start,
        metadata={
            "prompt": prompt,
            "model": item.model,
            "label": item.label,
            "used_as_evidence": False,
            "fingerprint": item.content_hash,
            "fingerprint_bundle": fingerprint_bundle(path, include_perceptual=False),
        },
    )


def meme_candidate(folder: Path, intent: ShotIntent, *, mode: str = "auto") -> VisualCandidate | None:
    beat = choose_meme_beat(intent, mode=mode)
    if not beat.allowed:
        return None
    resource = generate_meme(folder, setup=beat.setup, punchline=beat.punchline)
    candidate = from_resource(resource, intent, VisualFormat.MEME.value)
    candidate.provider = "ace_meme"
    candidate.origin = CandidateOrigin.ACE_GENERATED.value
    candidate.approval_required = False
    candidate.width = 1080
    candidate.height = 1920
    candidate.semantic_elements = [*intent.required_elements, "reaction", "punchline"]
    candidate.tags = [*candidate.tags, "ace_original", "reaction", intent.mood]
    candidate.metadata.update({"meme_beat": beat.to_dict(), "used_as_evidence": False})
    return candidate



def _typography_title(intent: ShotIntent) -> str:
    """Create a concise on-screen idea without repeating a subtitle paragraph."""
    text = " ".join(intent.narration.strip().split())
    words = text.rstrip(" .!?").split()
    if len(words) <= 9:
        return " ".join(words)
    if intent.purpose == "call_to_action":
        # The last clause usually contains the payoff/action. Keep enough context
        # for it to stand alone while remaining readable on a phone.
        return " ".join(words[-7:])
    if intent.purpose == "hook":
        return " ".join(words[:8]) + "…"
    subject = intent.subject.replace("_", " " ).strip()
    return subject.title() if subject else " ".join(words[:8]) + "…"

def typography_candidate(folder: Path, intent: ShotIntent, *, label: str = "KEY IDEA") -> VisualCandidate:
    root = ensure_dir(folder / "visuals" / "generated" / "typography")
    path = root / f"{intent.shot_id}-{slugify(intent.subject, 38)}.png"
    create_card(
        path,
        title=_typography_title(intent),
        label=label,
        footer="ACE ORIGINAL VISUAL",
        size=(720, 1280),
    )
    return VisualCandidate(
        candidate_id=_candidate_id(intent.shot_id, "ace_typography", str(path)),
        shot_id=intent.shot_id,
        format=VisualFormat.KINETIC_TYPOGRAPHY.value,
        provider="ace_typography",
        title=f"Typography card — {intent.subject.replace('_', ' ')}",
        description="A clean ACE-owned title or keyword card using the exact narration.",
        path=str(path),
        origin=CandidateOrigin.ACE_GENERATED.value,
        license_status="account_owned",
        tags=[intent.subject, "typography", "title", *intent.required_elements],
        semantic_elements=[*intent.required_elements, "exact_text"],
        width=720,
        height=1280,
        metadata={"fingerprint": sha256_file(path), "fingerprint_bundle": fingerprint_bundle(path, include_perceptual=False)},
    )


def stock_candidates(
    intent: ShotIntent,
    workspace: str | Path | None,
    *,
    finder: Callable[..., list[Resource]] = find_resources,
    limit_per_query: int = 5,
) -> list[VisualCandidate]:
    output: list[VisualCandidate] = []
    requested = set(intent.preferred_formats)
    media_types: list[tuple[str, str]] = []
    if VisualFormat.ACCOUNT_ASSET.value in requested or VisualFormat.STOCK_VIDEO.value in requested:
        media_types.append(("video", VisualFormat.STOCK_VIDEO.value))
    if VisualFormat.ACCOUNT_ASSET.value in requested or VisualFormat.STOCK_IMAGE.value in requested:
        media_types.append(("image", VisualFormat.STOCK_IMAGE.value))
    for media_type, visual_format in media_types:
        queries = intent.search_queries.get(visual_format, [])
        if not queries:
            queries = intent.search_queries.get(VisualFormat.ACCOUNT_ASSET.value, [])
        for query in queries[:4]:
            try:
                resources = finder(query, media_type=media_type, workspace=workspace, limit=limit_per_query)
            except Exception:
                continue
            for resource in resources:
                candidate_format = VisualFormat.ACCOUNT_ASSET.value if resource.source_provider == "library" else visual_format
                output.append(from_resource(resource, intent, candidate_format))
    # Deduplicate by source URL/path.
    seen: set[str] = set()
    unique: list[VisualCandidate] = []
    for candidate in output:
        key = str(candidate.path or candidate.download_url or candidate.source_url or candidate.candidate_id)
        if key in seen:
            continue
        seen.add(key)
        unique.append(candidate)
    return unique


def materialize(candidate: VisualCandidate, folder: Path) -> VisualCandidate:
    if candidate.is_local:
        return candidate
    if not candidate.download_url:
        return candidate
    suffix = Path(candidate.download_url.split("?", 1)[0]).suffix.lower()
    if suffix not in {".mp4", ".mov", ".mkv", ".webm", ".jpg", ".jpeg", ".png", ".webp"}:
        suffix = ".mp4" if candidate.format == VisualFormat.STOCK_VIDEO.value else ".jpg"
    target = ensure_dir(folder / "resources" / "publishable") / f"{candidate.shot_id}-{slugify(candidate.title, 42)}{suffix}"
    if not target.exists():
        response = request("GET", candidate.download_url, timeout=90, retries=2)
        target.write_bytes(response.body)
    candidate.path = str(target)
    candidate.metadata["fingerprint"] = sha256_file(target)
    candidate.metadata["fingerprint_bundle"] = fingerprint_bundle(target, include_perceptual=False)
    return candidate


def copy_local_candidate(candidate: VisualCandidate, folder: Path) -> VisualCandidate:
    if not candidate.path or not Path(candidate.path).exists():
        return candidate
    source = Path(candidate.path)
    # Account assets should remain in the account library; generated/evidence
    # visuals already live inside the generation. Only external local stock is copied.
    if folder in source.parents:
        return candidate
    target = ensure_dir(folder / "resources" / "publishable") / f"{candidate.shot_id}-{slugify(candidate.title, 42)}{source.suffix.lower()}"
    if not target.exists():
        shutil.copy2(source, target)
    candidate.path = str(target)
    candidate.metadata["fingerprint"] = sha256_file(target)
    candidate.metadata["fingerprint_bundle"] = fingerprint_bundle(target, include_perceptual=False)
    return candidate
