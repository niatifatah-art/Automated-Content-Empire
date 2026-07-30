from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable

from ace.captions import CaptionCue, adapt_to_visuals, plan as plan_captions
from ace.creative import build_broll_queries, edit_directive, profile_for
from ace.config import load as load_config
from ace.storage import metadata, resolve_generation, update_metadata
from ace.utils import read_json, write_json
from ace.visual_intelligence.contracts import ShotIntent, VisualCandidate, VisualFormat, VisualScore
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


def _shot_target(config: dict[str, Any], mood: str, target_override: float | None = None) -> tuple[float, float, float]:
    editing = config.get("editing", {})
    style = editing.get("styles", {}).get(mood, {})
    pace = str(style.get("pace") or "medium")
    target_by_pace = {"very_fast": 1.9, "fast": 2.3, "medium": 2.8, "controlled": 3.2}
    target = float(target_override or target_by_pace.get(pace, editing.get("average_shot_seconds", 2.6)))
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


def _group_cues(cues: list[CaptionCue], mood: str, config: dict[str, Any], *, target_override: float | None = None) -> list[list[CaptionCue]]:
    """Group caption phrases by narrated idea, not by subtitle timing.

    Caption chunks can change every second while the visual should normally stay
    with the full sentence/concept. This prevents three nearly identical network
    diagrams from appearing during one explanation merely because its subtitle
    was split into three readable phrases.
    """

    target, minimum, maximum = _shot_target(config, mood, target_override)
    configured_sentence_max = float(config.get("editing", {}).get("maximum_sentence_shot_seconds", 7.2))
    # Keep a complete spoken idea together whenever possible. Fast captions can
    # change inside one shot; changing the visual for every caption fragment
    # creates repetitive templates. Only genuinely long sentences are split.
    sentence_maximum = max(maximum, min(configured_sentence_max, max(6.0, target * 2.5)))
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
    creative_style = str(info.get("creative_style") or "adaptive")
    media_mode = str(info.get("media_mode") or "auto")
    meme_mode = str(info.get("meme_mode") or "auto")
    script_path = folder / "script" / "tts-ready.txt"
    if not script_path.exists():
        script_path = folder / "selected.md"
    script = script_path.read_text(encoding="utf-8")
    mood = creative_style if creative_style not in {"", "adaptive"} else choose_mood(topic, script)
    update_metadata(folder, editing_mood=mood, visual_intelligence_version=2)
    cue_rows = read_json(folder / "captions" / "caption-plan.json", [])
    if refresh_captions or not cue_rows:
        cues = plan_captions(folder, workspace, mood=mood)
    else:
        cues = [CaptionCue(**row) for row in cue_rows]
    config = load_config(workspace)
    style = config.get("editing", {}).get("styles", {}).get(mood, {})
    transition = str(style.get("transition") or "quick_fade")
    settings = config.get("visual_intelligence", {})
    quality_mode = str(info.get("quality_mode") or "balanced")
    cloud_enabled = bool(settings.get("cloud_intent_planner", True)) if cloud_intents is None else bool(cloud_intents)
    intent_budgets = settings.get("cloud_intent_budget_by_quality", {"quick": 0, "balanced": 1, "best": 2})
    intent_budget = int(intent_budgets.get(quality_mode, 1)) if cloud_enabled else 0
    baseline_planner = IntentPlanner(str(workspace) if workspace is not None else None, allow_cloud=False)
    cloud_planner = IntentPlanner(str(workspace) if workspace is not None else None, allow_cloud=True)
    cloud_intents_used = 0
    reference_style = info.get("reference_style") or {}
    reference_target = float(reference_style.get("average_shot_seconds") or 0) or None
    groups = _group_cues(cues, mood, config, target_override=reference_target)
    shots: list[Shot] = []
    intents: list[ShotIntent] = []
    for shot_index, group in enumerate(groups, 1):
        first, last = group[0], group[-1]
        narration = " ".join(cue.spoken_text for cue in group).strip()
        visible_cues = [cue for cue in group if cue.mode not in {"none", "accessibility_only"}]
        representative = visible_cues[0] if visible_cues else first
        purpose = _purpose(shot_index, len(groups), representative)
        shot_id = f"shot-{shot_index:03d}"
        intent = baseline_planner.plan(
            narration,
            shot_id=shot_id,
            purpose=purpose,
            mood=mood,
            topic=topic,
            caption_strategy=representative.mode,
        )
        should_refine = (
            cloud_intents_used < intent_budget
            and (intent.evidence_required or intent.importance >= 0.86 or purpose == "hook")
        )
        if should_refine:
            refined = cloud_planner.plan(
                narration,
                shot_id=shot_id,
                purpose=purpose,
                mood=mood,
                topic=topic,
                caption_strategy=representative.mode,
            )
            if refined.metadata.get("planner") == "cloud_refined":
                intent = refined
                cloud_intents_used += 1
        if meme_mode == "off":
            intent.preferred_formats = [item for item in intent.preferred_formats if item != VisualFormat.MEME.value]
        elif meme_mode == "on" and intent.humor_allowed and VisualFormat.MEME.value not in intent.preferred_formats:
            intent.preferred_formats.insert(min(2, len(intent.preferred_formats)), VisualFormat.MEME.value)
        if media_mode == "broll" and intent.literalness == "literal" and VisualFormat.STOCK_VIDEO.value not in intent.preferred_formats:
            intent.preferred_formats.insert(0, VisualFormat.STOCK_VIDEO.value)
        intent.search_queries[VisualFormat.STOCK_VIDEO.value] = [item.query for item in build_broll_queries(intent)]
        intents.append(intent)
        directive = edit_directive(intent, shot_index, style=mood)
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
                transition=directive.transition or transition,
                mood=mood,
                reason=intent.rationale,
                metadata={
                    "shot_id": shot_id,
                    "caption_cue_indices": [cue.index for cue in group],
                    "intent": intent.to_dict(),
                    "creative": directive.to_dict(),
                    "broll_queries": [item.to_dict() for item in build_broll_queries(intent)],
                },
            )
        )
    write_json(folder / "visuals" / "shot-intents.json", [item.to_dict() for item in intents])
    write_json(folder / "visuals" / "shot-plan.json", [asdict(item) for item in shots])
    return shots


_LIVE_SECONDARY_FORMATS = {
    VisualFormat.ACCOUNT_ASSET.value,
    VisualFormat.STOCK_VIDEO.value,
}
_DEMO_SECONDARY_FORMATS = {
    VisualFormat.BROWSER_DEMO.value,
    VisualFormat.APPLICATION_DEMO.value,
    VisualFormat.TERMINAL_DEMO.value,
    VisualFormat.OFFICIAL_EVIDENCE.value,
}
_NEVER_SECONDARY_FORMATS = {
    VisualFormat.KINETIC_TYPOGRAPHY.value,
    VisualFormat.MINIMAL_SCREEN.value,
    VisualFormat.ARTICLE_CARD.value,
    VisualFormat.SOCIAL_POST_CARD.value,
    VisualFormat.STOCK_IMAGE.value,
    VisualFormat.GENERATED_CONCEPT_IMAGE.value,
    VisualFormat.MEME.value,
}


def _select_secondary_visual(
    *,
    selected: VisualCandidate,
    selected_score: VisualScore,
    candidates: list[VisualCandidate],
    scores: list[VisualScore],
    shot: Shot,
    intent: ShotIntent,
) -> tuple[VisualCandidate | None, VisualScore | None, dict[str, Any]]:
    """Choose a complementary insert, not a random second-place candidate.

    A secondary visual must be strong enough to stand alone and must add a new
    layer: literal B-roll over an explainer, or a small verified UI/evidence PIP
    over literal footage. Text cards, memes and generated concept stills are never
    used as PIP because they clutter the frame and duplicate captions.
    """
    disabled = {"mode": "none", "reason": "No complementary secondary visual passed the creative gate."}
    if shot.duration < 2.6 or intent.purpose in {"show_evidence", "show_data", "call_to_action"}:
        return None, None, disabled

    score_map = {item.candidate_id: item for item in scores}
    pool: list[tuple[VisualCandidate, VisualScore, float, str]] = []
    selected_is_live = selected.format in _LIVE_SECONDARY_FORMATS
    selected_is_demo = selected.format in _DEMO_SECONDARY_FORMATS

    for candidate in candidates:
        if candidate.candidate_id == selected.candidate_id or candidate.format == selected.format:
            continue
        if candidate.format in _NEVER_SECONDARY_FORMATS:
            continue
        if not candidate.path or not Path(candidate.path).exists():
            continue
        score = score_map.get(candidate.candidate_id)
        if not score or score.decision not in {"accepted", "needs_approval"}:
            continue
        if score.overall < 82 or score.semantic_relevance < 78 or score.clarity < 70 or score.duplicate_risk > 25:
            continue

        presentation = "none"
        creative_bonus = 0.0
        if candidate.format in _LIVE_SECONDARY_FORMATS and not selected_is_live:
            presentation = "cutaway"
            creative_bonus = 8.0
        elif candidate.format in _DEMO_SECONDARY_FORMATS and selected_is_live:
            presentation = "pip"
            creative_bonus = 5.0
        elif candidate.format in _LIVE_SECONDARY_FORMATS and selected_is_demo:
            presentation = "cutaway"
            creative_bonus = 6.0
        else:
            continue

        # Hooks should open cleanly. A live cutaway is useful only when the primary
        # is non-live; a small PIP on a hook is usually clutter.
        if intent.purpose == "hook" and presentation != "cutaway":
            continue
        if intent.purpose == "hook" and selected_is_live:
            continue

        delta = max(0.0, selected_score.overall - score.overall)
        if delta > 14:
            continue
        rank = score.overall + score.semantic_relevance * 0.08 + creative_bonus - delta * 0.3
        pool.append((candidate, score, rank, presentation))

    if not pool:
        return None, None, disabled
    candidate, score, _, presentation = max(pool, key=lambda item: item[2])
    insert_duration = min(1.45, max(0.72, shot.duration * (0.30 if presentation == "cutaway" else 0.42)))
    start = min(max(0.42, shot.duration * 0.34), max(0.42, shot.duration - insert_duration - 0.25))
    usage = {
        "mode": presentation,
        "start": round(start, 3),
        "duration": round(insert_duration, 3),
        "reason": "Adds literal context." if presentation == "cutaway" else "Adds a relevant UI/evidence detail without replacing the primary action.",
    }
    return candidate, score, usage


def collect_for_plan(
    generation: str | Path,
    workspace: str | Path | None = None,
    *,
    resource_finder: Callable[..., Any] | None = None,
    cloud_judge: bool | None = None,
    animate_explainers: bool = True,
    generate_cloud_images: bool | None = None,
) -> list[Shot]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "visuals" / "shot-plan.json", [])
    shots = [Shot(**row) for row in rows] if rows else plan(folder, workspace)
    intents = {intent.shot_id: intent for intent in load_intents(folder)}
    used_fingerprints: set[str] = set()
    generation_meta = metadata(folder)
    media_mode = str(generation_meta.get("media_mode") or "auto")
    profile = profile_for(str(generation_meta.get("editing_mood") or generation_meta.get("creative_style") or "technical_dynamic"))
    total_duration = sum(max(0.0, float(item.duration)) for item in shots)
    meme_budget = max(0, min(2, math.ceil(profile.max_memes_per_minute * total_duration / 60.0)))
    selected_memes = 0
    quality_mode = str(generation_meta.get("quality_mode") or "balanced")
    judge_budgets = load_config(workspace).get("visual_intelligence", {}).get(
        "cloud_judge_shot_budget_by_quality", {"quick": 0, "balanced": 0, "best": 2}
    )
    judge_budget = int(judge_budgets.get(quality_mode, 0))
    ranked_intents = sorted(intents.values(), key=lambda item: (item.evidence_required, item.importance), reverse=True)
    cloud_judge_ids = {item.shot_id for item in ranked_intents[:judge_budget]}
    effective_resource_finder = resource_finder
    if effective_resource_finder is None and media_mode == "original":
        effective_resource_finder = lambda *args, **kwargs: []
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
        if selected_memes >= meme_budget and VisualFormat.MEME.value in intent.preferred_formats:
            intent.preferred_formats = [item for item in intent.preferred_formats if item != VisualFormat.MEME.value]
            intent.metadata["meme_suppressed"] = "Generation meme budget reached."
        selected, score, decision, candidates, scores = run_tournament(
            folder,
            intent,
            duration=shot.duration,
            workspace=workspace,
            used_fingerprints=used_fingerprints,
            resource_finder=effective_resource_finder,
            cloud_judge=(shot_id in cloud_judge_ids) if cloud_judge is None else cloud_judge,
            animate_explainers=animate_explainers,
            generate_cloud_images=(
                bool(load_config(workspace).get("visual_intelligence", {}).get("automatic_cloud_images", False))
                if generate_cloud_images is None else generate_cloud_images
            ),
        )
        shot.resource_path = selected.path
        shot.resource_id = selected.candidate_id
        shot.source_url = selected.source_url
        shot.visual_type = selected.format
        shot.reason = decision.reason
        shot.approval_required = decision.approval_required
        if selected.format == VisualFormat.MEME.value:
            selected_memes += 1
        secondary, secondary_score, secondary_usage = _select_secondary_visual(
            selected=selected,
            selected_score=score,
            candidates=candidates,
            scores=scores,
            shot=shot,
            intent=intent,
        )
        shot.metadata.update(
            {
                "visual_candidate": selected.to_dict(),
                "visual_score": score.to_dict(),
                "visual_decision": decision.to_dict(),
                "candidate_count": len(candidates),
                "candidate_scores": {item.candidate_id: item.overall for item in scores},
                "secondary_visual": secondary.to_dict() if secondary else None,
                "secondary_score": secondary_score.to_dict() if secondary_score else None,
                "secondary_usage": secondary_usage,
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
