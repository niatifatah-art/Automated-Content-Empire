from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ace.captions import CaptionCue, plan as plan_captions
from ace.config import load as load_config
from ace.graphics import create_card, create_abstract_visual
from ace.memes import generate as generate_meme
from ace.resources import Resource, find as find_resources
from ace.storage import metadata, resolve_generation, update_metadata
from ace.utils import ensure_dir, read_json, sha256_bytes, slugify, write_json


@dataclass
class Shot:
    index: int
    start: float
    end: float
    duration: float
    narration: str
    purpose: str
    visual_type: str
    search_query: str
    resource_id: str | None = None
    resource_path: str | None = None
    source_url: str | None = None
    crop_focus: str = "center"
    caption_mode: str = "none"
    caption_position: str = "bottom"
    transition: str = "quick_fade"
    mood: str = "technical_dynamic"
    reason: str = ""
    approval_required: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)


def choose_mood(topic: str, script: str) -> str:
    text = f"{topic} {script}".lower()
    if any(term in text for term in ("breach", "vulnerability", "malware", "ransomware", "attack", "victim", "layoff")):
        return "serious_technical"
    if any(term in text for term in ("challenge", "for 7 days", "can i", "i tried", "without google")):
        return "challenge"
    if any(term in text for term in ("announced", "breaking", "deal", "partnership", "acquisition")):
        return "clean_documentary"
    if any(term in text for term in ("gpu", "gaming", "fps", "console", "playstation", "xbox")):
        return "gaming_hype"
    if any(term in text for term in ("weird", "mistake", "why does", "linux", "programming", "bug")):
        return "playful_tech"
    return "technical_dynamic"


def _keywords(text: str, topic: str, limit: int = 8) -> str:
    stop = {"this", "that", "with", "from", "your", "they", "will", "have", "into", "because", "about", "just", "what", "when", "where", "which", "their", "there"}
    words = [token.lower() for token in re.findall(r"[A-Za-z0-9_+-]{3,}", f"{topic} {text}")]
    unique: list[str] = []
    for word in words:
        if word in stop or word in unique:
            continue
        unique.append(word)
    return " ".join(unique[:limit])


def _abstract(text: str) -> bool:
    return any(term in text.lower() for term in ("encryption", "authentication", "algorithm", "workflow", "architecture", "privacy", "security model", "data flow"))


def _purpose(index: int, total: int, cue: CaptionCue) -> str:
    if index == 1:
        return "hook"
    if index == total:
        return "call_to_action"
    if cue.mode == "article_headline":
        return "evidence"
    if cue.mode in {"statistic", "code_panel", "challenge_counter"}:
        return "explanation"
    return "support"


def _visual_type(cue: CaptionCue, mood: str, index: int, has_evidence: bool) -> str:
    lower = cue.spoken_text.lower()
    if has_evidence and (cue.mode == "article_headline" or any(term in lower for term in ("announced", "deal", "partnership", "confirmed", "official"))):
        return "evidence_card"
    if cue.mode == "social_post" and has_evidence:
        return "social_post_card"
    if cue.mode == "code_panel":
        return "generated_graphic"
    if _abstract(cue.spoken_text):
        return "generated_diagram"
    if mood in {"gaming_hype", "playful_tech", "challenge"} and index > 2 and index % 8 == 0:
        return "meme_card"
    return "stock_video"


def _evidence_files(folder: Path, kind: str) -> list[Path]:
    if kind == "evidence_card":
        return sorted((folder / "evidence" / "article-cards").glob("*.png"))
    if kind == "social_post_card":
        return sorted((folder / "evidence" / "social-posts").glob("*.png"))
    return []


def _generated_graphic(folder: Path, cue: CaptionCue, index: int, kind: str) -> Path:
    output = ensure_dir(folder / "visuals" / "generated") / f"shot-{index:03d}-{kind}.png"
    label = "EXPLAINER" if kind == "generated_diagram" else "CODE" if cue.mode == "code_panel" else "ACE VISUAL"
    concept = " ".join(_keywords(cue.spoken_text, "", limit=3).split()[:3])
    create_abstract_visual(
        output,
        concept=concept or "TECH",
        label=label,
        show_concept=cue.mode in {"none", "accessibility_only"},
    )
    return output



def _shot_target(config: dict[str, Any], mood: str) -> tuple[float, float, float]:
    editing = config.get("editing", {})
    style = editing.get("styles", {}).get(mood, {})
    pace = str(style.get("pace") or "medium")
    target_by_pace = {
        "very_fast": 1.9,
        "fast": 2.3,
        "medium": 2.8,
        "controlled": 3.2,
    }
    target = float(target_by_pace.get(pace, editing.get("average_shot_seconds", 2.6)))
    minimum = float(editing.get("minimum_shot_seconds", 1.4))
    maximum = float(editing.get("maximum_shot_seconds", 4.2))
    return target, minimum, maximum


def _group_cues(cues: list[CaptionCue], mood: str, has_evidence: bool, config: dict[str, Any]) -> list[list[CaptionCue]]:
    """Group phrase-level captions into calmer visual shots.

    Captions may change every few words, but stock footage should not. Evidence
    cues are kept together so one source card is shown long enough to read.
    """
    target, minimum, maximum = _shot_target(config, mood)
    evidence_types = {"evidence_card", "social_post_card"}
    groups: list[list[CaptionCue]] = []
    current: list[CaptionCue] = []
    current_kind: str | None = None
    for cue in cues:
        kind = _visual_type(cue, mood, cue.index, has_evidence)
        cue_duration = cue.end - cue.start
        if current:
            duration = current[-1].end - current[0].start
            evidence_boundary = (current_kind in evidence_types) != (kind in evidence_types)
            evidence_kind_changed = current_kind in evidence_types and kind != current_kind
            reaches_limit = duration + cue_duration > maximum
            reaches_target = duration >= target and current_kind not in evidence_types
            if evidence_boundary or evidence_kind_changed or reaches_limit or reaches_target:
                groups.append(current)
                current = []
                current_kind = None
        if not current:
            current_kind = kind
        current.append(cue)
    if current:
        groups.append(current)

    # Avoid a tiny final shot when it can safely join the previous non-evidence shot.
    if len(groups) > 1:
        tail = groups[-1]
        previous = groups[-2]
        tail_duration = tail[-1].end - tail[0].start
        merged_duration = tail[-1].end - previous[0].start
        previous_kind = _visual_type(previous[0], mood, previous[0].index, has_evidence)
        tail_kind = _visual_type(tail[0], mood, tail[0].index, has_evidence)
        if tail_duration < minimum and merged_duration <= maximum and previous_kind not in evidence_types and tail_kind not in evidence_types:
            groups[-2] = [*previous, *tail]
            groups.pop()
    return groups


def _group_visual_type(group: list[CaptionCue], mood: str, shot_index: int, has_evidence: bool) -> str:
    kinds = [_visual_type(cue, mood, shot_index, has_evidence) for cue in group]
    for preferred in ("evidence_card", "social_post_card", "code_panel", "generated_diagram", "generated_graphic", "meme_card"):
        if preferred in kinds:
            return "generated_graphic" if preferred == "code_panel" else preferred
    return "stock_video"

def plan(generation: str | Path, workspace: str | Path | None = None, *, refresh_captions: bool = False) -> list[Shot]:
    folder = resolve_generation(generation, workspace)
    info = metadata(folder)
    topic = str(info.get("topic") or "")
    script_path = folder / "script" / "tts-ready.txt"
    if not script_path.exists():
        script_path = folder / "selected.md"
    script = script_path.read_text(encoding="utf-8")
    mood = choose_mood(topic, script)
    update_metadata(folder, editing_mood=mood)
    cue_rows = read_json(folder / "captions" / "caption-plan.json", [])
    if refresh_captions or not cue_rows:
        cues = plan_captions(folder, workspace, mood=mood)
    else:
        cues = [CaptionCue(**row) for row in cue_rows]
    evidence_manifest = read_json(folder / "evidence" / "evidence-plan.json", []) or []
    has_evidence = bool(evidence_manifest)
    config = load_config(workspace)
    style = config.get("editing", {}).get("styles", {}).get(mood, {})
    transition = str(style.get("transition") or "quick_fade")
    groups = _group_cues(cues, mood, has_evidence, config)
    shots: list[Shot] = []
    evidence_offsets = {"evidence_card": 0, "social_post_card": 0}
    for shot_index, group in enumerate(groups, 1):
        first, last = group[0], group[-1]
        narration = " ".join(cue.spoken_text for cue in group).strip()
        visible_cues = [cue for cue in group if cue.mode not in {"none", "accessibility_only"}]
        representative = visible_cues[0] if visible_cues else first
        visual_type = _group_visual_type(group, mood, shot_index, has_evidence)
        resource_path = None
        resource_id = None
        source_url = None
        reason = "Semantic stock footage matching this narration section."
        if visual_type in {"evidence_card", "social_post_card"}:
            candidates = _evidence_files(folder, visual_type)
            offset = evidence_offsets[visual_type]
            if candidates and offset < len(candidates):
                selected = candidates[offset]
                evidence_offsets[visual_type] += 1
                resource_path = str(selected)
                resource_id = f"evidence-{selected.stem}"
                reason = "Source evidence is more useful than generic stock footage for this claim."
            else:
                visual_type = "generated_graphic"
        if visual_type in {"generated_graphic", "generated_diagram"}:
            selected = _generated_graphic(folder, representative, shot_index, visual_type)
            resource_path = str(selected)
            resource_id = f"generated-{selected.stem}"
            reason = "An original diagram explains this abstract idea more clearly than generic stock footage."
        elif visual_type == "meme_card":
            meme = generate_meme(folder, setup="Tech users after the latest update:", punchline=representative.visible_text or narration, workspace=workspace)
            resource_path = meme.local_path
            resource_id = meme.id
            reason = "A controlled ACE-owned meme moment matches the young-adult playful style."
        query = _keywords(narration, topic)
        if any(cue.mode == "article_headline" for cue in group):
            caption_mode = "article_headline"
            caption_position = "top"
        elif any(cue.mode == "social_post" for cue in group):
            caption_mode = "social_post"
            caption_position = "top"
        else:
            caption_mode = representative.mode
            caption_position = representative.position
        shots.append(
            Shot(
                index=shot_index,
                start=first.start,
                end=last.end,
                duration=round(last.end - first.start, 3),
                narration=narration,
                purpose=_purpose(shot_index, len(groups), representative),
                visual_type=visual_type,
                search_query=query,
                resource_id=resource_id,
                resource_path=resource_path,
                source_url=source_url,
                crop_focus="face_and_device" if any(term in narration.lower() for term in ("face", "phone", "fingerprint", "person")) else "center",
                caption_mode=caption_mode,
                caption_position=caption_position,
                transition=transition,
                mood=mood,
                reason=reason,
                metadata={"caption_cue_indices": [cue.index for cue in group]},
            )
        )
    write_json(folder / "visuals" / "shot-plan.json", [asdict(item) for item in shots])
    return shots


def _tokens(value: str) -> set[str]:
    return set(re.findall(r"[a-zA-Z0-9_]{3,}", value.lower()))


def _score(resource: Resource, shot: Shot, used: set[str]) -> float:
    resource_tokens = _tokens(" ".join([resource.title, *resource.tags, resource.query or ""]))
    query_tokens = _tokens(shot.search_query)
    overlap = len(resource_tokens & query_tokens) / max(1, len(query_tokens))
    orientation = 0.0
    if resource.width and resource.height:
        orientation = 0.18 if resource.height >= resource.width else -0.04
    diversity = -0.35 if resource.id in used else 0.12
    provider_bonus = 0.08 if resource.source_provider in {"library", "pexels", "pixabay"} else 0.0
    return overlap * 0.62 + orientation + diversity + provider_bonus


def collect_for_plan(generation: str | Path, workspace: str | Path | None = None) -> list[Shot]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "visuals" / "shot-plan.json", [])
    if not rows:
        shots = plan(folder, workspace)
    else:
        shots = [Shot(**row) for row in rows]
    used: set[str] = set()
    collected_records: list[dict[str, Any]] = []
    publishable = ensure_dir(folder / "resources" / "publishable")
    for shot in shots:
        if shot.resource_path:
            continue
        candidates = find_resources(shot.search_query, media_type="video", workspace=workspace, limit=8)
        if not candidates:
            candidates = find_resources(shot.search_query, media_type="image", workspace=workspace, limit=8)
        if candidates:
            candidates.sort(key=lambda item: _score(item, shot, used), reverse=True)
            selected = candidates[0]
            used.add(selected.id)
            suffix = Path(selected.download_url or selected.source_url).suffix
            if not suffix or len(suffix) > 6:
                suffix = ".mp4" if selected.type == "video" else ".jpg"
            target = publishable / f"shot-{shot.index:03d}-{slugify(selected.title, 36)}{suffix}"
            try:
                if selected.local_path:
                    source = Path(selected.local_path)
                    if not target.exists():
                        import shutil
                        shutil.copy2(source, target)
                elif selected.download_url:
                    from ace.http import request
                    response = request("GET", selected.download_url, timeout=90, retries=2)
                    target.write_bytes(response.body)
                else:
                    raise ValueError("No downloadable resource")
                selected.local_path = str(target)
                shot.resource_path = str(target)
                shot.resource_id = selected.id
                shot.source_url = selected.source_url
                shot.metadata["resource"] = asdict(selected)
                collected_records.append(asdict(selected))
                continue
            except Exception as exc:
                shot.metadata["resource_error"] = str(exc)
        # Guaranteed visible fallback.
        fallback = _generated_graphic(folder, CaptionCue(shot.index, shot.start, shot.end, shot.narration, shot.narration, shot.caption_mode, shot.caption_position, 60, [shot.narration], "fallback"), shot.index, "generated_graphic")
        shot.visual_type = "generated_graphic"
        shot.resource_path = str(fallback)
        shot.resource_id = f"generated-{fallback.stem}"
        shot.reason = "No reusable semantic media was available; ACE generated a branded explanatory visual."
    write_json(folder / "visuals" / "shot-plan.json", [asdict(item) for item in shots])
    manifest_path = folder / "licenses" / "manifest.json"
    existing = read_json(manifest_path, {}) or {}
    existing.update({"schema_version": 2, "publishable": collected_records, "selection_strategy": "semantic_per_shot"})
    write_json(manifest_path, existing)
    return shots


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
    missing = [row for row in rows if not row.get("resource_path")]
    repeated: dict[str, int] = {}
    for row in rows:
        resource_id = str(row.get("resource_id") or "")
        if resource_id:
            repeated[resource_id] = repeated.get(resource_id, 0) + 1
    repeats = {key: count for key, count in repeated.items() if count > 1 and not key.startswith("generated-")}
    average = round(sum(float(row.get("duration", 0)) for row in rows) / max(1, len(rows)), 2)
    report = {
        "status": "not_run" if not rows else "failed" if missing else "warning" if repeats else "passed",
        "shot_count": len(rows),
        "missing_visuals": len(missing),
        "repeated_external_visuals": repeats,
        "average_shot_seconds": average,
        "moods": sorted({str(row.get("mood")) for row in rows}),
        "semantic_queries": [row.get("search_query") for row in rows],
    }
    write_json(folder / "quality" / "visual-report.json", report)
    return report
