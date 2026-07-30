from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ace.captions import CaptionCue, adapt_to_visuals, plan as plan_captions
from ace.config import load as load_config
from ace.storage import metadata, resolve_generation, update_metadata
from ace.utils import read_json, write_json
from ace.visual_intelligence.contracts import ShotIntent, VisualFormat
from ace.visual_intelligence.intent import IntentPlanner
from ace.visual_intelligence.tournament import load_intents, run_tournament, validate as validate_intelligence


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
    if any(term in text for term in ("challenge", "for 7 days", "for seven days", "can i", "i tried", "without google")):
        return "challenge"
    if any(term in text for term in ("announced", "breaking", "deal", "partnership", "acquisition")):
        return "clean_documentary"
    if any(term in text for term in ("gpu", "gaming", "fps", "console", "playstation", "xbox")):
        return "gaming_hype"
    if any(term in text for term in ("weird", "mistake", "why does", "linux", "programming", "bug")):
        return "playful_tech"
    return "technical_dynamic"


def _purpose(index: int, total: int, cue: CaptionCue) -> str:
    if index == 1:
        return "hook"
    if index == total:
        return "call_to_action"
    if cue.mode == "article_headline":
        return "show_evidence"
    if cue.mode in {"statistic", "code_panel", "challenge_counter"}:
        return "explain_mechanism"
    return "support"


def _shot_target(config: dict[str, Any], mood: str) -> tuple[float, float, float]:
    editing = config.get("editing", {})
    style = editing.get("styles", {}).get(mood, {})
    pace = str(style.get("pace") or "medium")
    target_by_pace = {"very_fast": 1.9, "fast": 2.3, "medium": 2.8, "controlled": 3.2}
    target = float(target_by_pace.get(pace, editing.get("average_shot_seconds", 2.6)))
    minimum = float(editing.get("minimum_shot_seconds", 1.4))
    maximum = float(editing.get("maximum_shot_seconds", 4.2))
    return target, minimum, maximum


def _cue_boundary(cue: CaptionCue) -> str:
    if cue.mode in {"article_headline", "social_post", "code_panel", "statistic", "challenge_counter", "full_title"}:
        return cue.mode
    lower = cue.spoken_text.lower()
    if any(term in lower for term in ("announced", "partnership", "official", "according to")):
        return "evidence"
    if any(term in lower for term in ("encryption", "passkey", "vpn", "rogue hotspot", "https", "api", "workflow", "architecture")):
        return "mechanism"
    return "normal"


def _group_cues(cues: list[CaptionCue], mood: str, config: dict[str, Any]) -> list[list[CaptionCue]]:
    """Group caption phrases by narrated idea, not by subtitle timing.

    Caption chunks can change every second while the visual should normally stay
    with the full sentence/concept. This prevents three nearly identical network
    diagrams from appearing during one explanation merely because its subtitle
    was split into three readable phrases.
    """

    target, minimum, maximum = _shot_target(config, mood)
    sentence_maximum = max(maximum, float(config.get("editing", {}).get("maximum_sentence_shot_seconds", 8.0)))
    groups: list[list[CaptionCue]] = []
    current: list[CaptionCue] = []
    current_sentence: int | None = None
    boundary: str | None = None

    for cue in cues:
        cue_sentence = int(getattr(cue, "sentence_index", 0) or cue.index)
        cue_boundary = _cue_boundary(cue)
        if current:
            current_duration = current[-1].end - current[0].start
            combined_duration = cue.end - current[0].start
            sentence_changed = cue_sentence != current_sentence
            mode_changed = sentence_changed and cue_boundary != boundary and (cue_boundary != "normal" or boundary != "normal")
            hard_limit = combined_duration > sentence_maximum
            # A new sentence is a new visual idea unless the previous sentence is
            # extremely short and both are ordinary supporting narration.
            merge_short_sentences = (
                sentence_changed
                and current_duration < minimum
                and cue_boundary == boundary == "normal"
                and combined_duration <= target
            )
            if hard_limit or mode_changed or (sentence_changed and not merge_short_sentences):
                groups.append(current)
                current = []
                current_sentence = None
                boundary = None
        if not current:
            current_sentence = cue_sentence
            boundary = cue_boundary
        current.append(cue)
    if current:
        groups.append(current)
    return groups


def _visual_type(intent: ShotIntent) -> str:
    primary = intent.preferred_formats[0] if intent.preferred_formats else VisualFormat.MINIMAL_SCREEN.value
    mapping = {
        VisualFormat.OFFICIAL_EVIDENCE.value: "evidence_card",
        VisualFormat.ARTICLE_CARD.value: "evidence_card",
        VisualFormat.SOCIAL_POST_CARD.value: "social_post_card",
        VisualFormat.ANIMATED_EXPLAINER.value: "generated_diagram",
        VisualFormat.COMPARISON_GRAPHIC.value: "generated_diagram",
        VisualFormat.DATA_CHART.value: "generated_diagram",
        VisualFormat.TIMELINE.value: "generated_diagram",
        VisualFormat.TERMINAL_DEMO.value: "terminal_demo",
        VisualFormat.BROWSER_DEMO.value: "browser_demo",
        VisualFormat.APPLICATION_DEMO.value: "application_demo",
        VisualFormat.MEME.value: "meme_card",
        VisualFormat.ACCOUNT_ASSET.value: "account_asset",
        VisualFormat.STOCK_IMAGE.value: "stock_image",
        VisualFormat.KINETIC_TYPOGRAPHY.value: "generated_graphic",
        VisualFormat.MINIMAL_SCREEN.value: "generated_graphic",
    }
    return mapping.get(primary, "stock_video")


def plan(
    generation: str | Path,
    workspace: str | Path | None = None,
    *,
    refresh_captions: bool = False,
    cloud_intents: bool | None = None,
) -> list[Shot]:
    folder = resolve_generation(generation, workspace)
    info = metadata(folder)
    topic = str(info.get("topic") or "")
    script_path = folder / "script" / "tts-ready.txt"
    if not script_path.exists():
        script_path = folder / "selected.md"
    script = script_path.read_text(encoding="utf-8")
    mood = choose_mood(topic, script)
    update_metadata(folder, editing_mood=mood, visual_intelligence_version=1)
    cue_rows = read_json(folder / "captions" / "caption-plan.json", [])
    if refresh_captions or not cue_rows:
        cues = plan_captions(folder, workspace, mood=mood)
    else:
        cues = [CaptionCue(**row) for row in cue_rows]
    config = load_config(workspace)
    style = config.get("editing", {}).get("styles", {}).get(mood, {})
    transition = str(style.get("transition") or "quick_fade")
    settings = config.get("visual_intelligence", {})
    if cloud_intents is None:
        cloud_intents = bool(settings.get("cloud_intent_planner", True))
    planner = IntentPlanner(str(workspace) if workspace is not None else None, allow_cloud=cloud_intents)
    groups = _group_cues(cues, mood, config)
    shots: list[Shot] = []
    intents: list[ShotIntent] = []
    for shot_index, group in enumerate(groups, 1):
        first, last = group[0], group[-1]
        narration = " ".join(cue.spoken_text for cue in group).strip()
        visible_cues = [cue for cue in group if cue.mode not in {"none", "accessibility_only"}]
        representative = visible_cues[0] if visible_cues else first
        purpose = _purpose(shot_index, len(groups), representative)
        shot_id = f"shot-{shot_index:03d}"
        intent = planner.plan(
            narration,
            shot_id=shot_id,
            purpose=purpose,
            mood=mood,
            topic=topic,
            caption_strategy=representative.mode,
        )
        intents.append(intent)
        queries = [query for values in intent.search_queries.values() for query in values]
        search_query = queries[0] if queries else intent.subject.replace("_", " ")
        if any(cue.mode == "article_headline" for cue in group):
            caption_mode, caption_position = "article_headline", "top"
        elif any(cue.mode == "social_post" for cue in group):
            caption_mode, caption_position = "social_post", "top"
        else:
            caption_mode, caption_position = representative.mode, representative.position
        shots.append(
            Shot(
                index=shot_index,
                start=first.start,
                end=last.end,
                duration=round(last.end - first.start, 3),
                narration=narration,
                purpose=intent.purpose,
                visual_type=_visual_type(intent),
                search_query=search_query,
                crop_focus="face_and_device" if any(term in narration.lower() for term in ("face", "phone", "fingerprint", "person")) else "center",
                caption_mode=caption_mode,
                caption_position=caption_position,
                transition=transition,
                mood=mood,
                reason=intent.rationale,
                metadata={
                    "shot_id": shot_id,
                    "caption_cue_indices": [cue.index for cue in group],
                    "intent": intent.to_dict(),
                },
            )
        )
    write_json(folder / "visuals" / "shot-intents.json", [item.to_dict() for item in intents])
    write_json(folder / "visuals" / "shot-plan.json", [asdict(item) for item in shots])
    return shots


def collect_for_plan(
    generation: str | Path,
    workspace: str | Path | None = None,
    *,
    resource_finder: Callable[..., Any] | None = None,
    cloud_judge: bool | None = None,
    animate_explainers: bool = True,
) -> list[Shot]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "visuals" / "shot-plan.json", [])
    shots = [Shot(**row) for row in rows] if rows else plan(folder, workspace)
    intents = {intent.shot_id: intent for intent in load_intents(folder)}
    used_fingerprints: set[str] = set()
    for shot in shots:
        shot_id = str(shot.metadata.get("shot_id") or f"shot-{shot.index:03d}")
        intent = intents.get(shot_id)
        if not intent:
            intent = IntentPlanner(str(workspace) if workspace is not None else None, allow_cloud=False).plan(
                shot.narration,
                shot_id=shot_id,
                purpose=shot.purpose,
                mood=shot.mood,
                topic=str(metadata(folder).get("topic") or ""),
                caption_strategy=shot.caption_mode,
            )
        selected, score, decision, candidates, scores = run_tournament(
            folder,
            intent,
            duration=shot.duration,
            workspace=workspace,
            used_fingerprints=used_fingerprints,
            resource_finder=resource_finder,
            cloud_judge=cloud_judge,
            animate_explainers=animate_explainers,
        )
        shot.resource_path = selected.path
        shot.resource_id = selected.candidate_id
        shot.source_url = selected.source_url
        shot.visual_type = selected.format
        shot.reason = decision.reason
        shot.approval_required = decision.approval_required
        shot.metadata.update(
            {
                "visual_candidate": selected.to_dict(),
                "visual_score": score.to_dict(),
                "visual_decision": decision.to_dict(),
                "candidate_count": len(candidates),
                "candidate_scores": {item.candidate_id: item.overall for item in scores},
            }
        )
    write_json(folder / "visuals" / "shot-plan.json", [asdict(item) for item in shots])
    adapt_to_visuals(folder, workspace)
    report = validate_intelligence(folder, workspace)
    manifest_path = folder / "licenses" / "manifest.json"
    existing = read_json(manifest_path, {}) or {}
    selected_assets = [
        {
            "shot": shot.index,
            "candidate_id": shot.resource_id,
            "path": shot.resource_path,
            "source_url": shot.source_url,
            "visual_type": shot.visual_type,
            "approval_required": shot.approval_required,
        }
        for shot in shots
    ]
    existing.update(
        {
            "schema_version": 3,
            "selected_visuals": selected_assets,
            "selection_strategy": "visual_intelligence_candidate_tournament",
            "visual_intelligence_status": report.status,
        }
    )
    write_json(manifest_path, existing)
    return shots


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
    missing = [row for row in rows if not row.get("resource_path") or not Path(str(row.get("resource_path"))).exists()]
    repeated: dict[str, int] = {}
    for row in rows:
        resource_id = str(row.get("resource_id") or "")
        if resource_id:
            repeated[resource_id] = repeated.get(resource_id, 0) + 1
    repeats = {key: count for key, count in repeated.items() if count > 1}
    average = round(sum(float(row.get("duration", 0)) for row in rows) / max(1, len(rows)), 2)
    intelligence = validate_intelligence(folder, workspace).to_dict() if rows else {"status": "not_run"}
    status = "not_run" if not rows else "failed" if missing or intelligence.get("status") == "failed" else "warning" if repeats or intelligence.get("status") == "warning" else "passed"
    report = {
        "status": status,
        "shot_count": len(rows),
        "missing_visuals": len(missing),
        "repeated_external_visuals": repeats,
        "average_shot_seconds": average,
        "moods": sorted({str(row.get("mood")) for row in rows}),
        "semantic_queries": [row.get("search_query") for row in rows],
        "average_visual_relevance": intelligence.get("average_relevance"),
        "average_visual_score": intelligence.get("average_overall"),
        "generic_filler_ratio": intelligence.get("generic_filler_ratio"),
        "unexplained_decisions": intelligence.get("unexplained_decisions"),
        "visual_intelligence": intelligence,
    }
    write_json(folder / "quality" / "visual-report.json", report)
    return report
