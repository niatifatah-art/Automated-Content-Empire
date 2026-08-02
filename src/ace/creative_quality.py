from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Any

from ace.creative import profile_for
from ace.storage import metadata, resolve_generation
from ace.utils import read_json, write_json
from ace.visual_intelligence.contracts import VisualFormat


BROLL_FORMATS = {
    VisualFormat.ACCOUNT_ASSET.value,
    VisualFormat.STOCK_VIDEO.value,
}
DYNAMIC_FORMATS = {
    *BROLL_FORMATS,
    VisualFormat.BROWSER_DEMO.value,
    VisualFormat.APPLICATION_DEMO.value,
    VisualFormat.TERMINAL_DEMO.value,
    VisualFormat.OFFICIAL_EVIDENCE.value,
    VisualFormat.ANIMATED_EXPLAINER.value,
    VisualFormat.COMPARISON_GRAPHIC.value,
    VisualFormat.DATA_CHART.value,
    VisualFormat.TIMELINE.value,
}
STATIC_CARD_FORMATS = {
    VisualFormat.KINETIC_TYPOGRAPHY.value,
    VisualFormat.MINIMAL_SCREEN.value,
    VisualFormat.ARTICLE_CARD.value,
    VisualFormat.SOCIAL_POST_CARD.value,
    VisualFormat.STOCK_IMAGE.value,
}


def _max_run(values: list[str]) -> int:
    maximum = current = 0
    previous: str | None = None
    for value in values:
        if value == previous:
            current += 1
        else:
            current = 1
            previous = value
        maximum = max(maximum, current)
    return maximum


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    info = metadata(folder)
    shots = read_json(folder / "visuals" / "shot-plan.json", []) or []
    formats = [str(item.get("visual_type") or "unknown") for item in shots]
    visual_signatures = [
        f"{str(item.get('visual_type') or 'unknown')}:{str((((item.get('metadata') or {}).get('intent') or {}).get('subject')) or '')}"
        for item in shots
    ]
    transitions = [str(item.get("transition") or "cut") for item in shots]
    motions = [str((item.get("metadata") or {}).get("creative", {}).get("motion") or "steady") for item in shots]
    durations = [float(item.get("duration") or 0) for item in shots]
    count = len(shots)
    profile = profile_for(str(info.get("editing_mood") or info.get("creative_style") or "technical_dynamic"))

    secondary_usages = [dict((item.get("metadata") or {}).get("secondary_usage") or {}) for item in shots]
    secondary_visuals = [dict((item.get("metadata") or {}).get("secondary_visual") or {}) for item in shots]
    cutaway_count = sum(str(item.get("mode") or "none") == "cutaway" for item in secondary_usages)
    pip_count = sum(str(item.get("mode") or "none") == "pip" for item in secondary_usages)
    broll_secondary_count = sum(
        str(usage.get("mode") or "none") == "cutaway"
        and str(visual.get("format") or "") in BROLL_FORMATS
        for usage, visual in zip(secondary_usages, secondary_visuals)
    )
    broll_count = sum(item in BROLL_FORMATS for item in formats) + broll_secondary_count
    dynamic_secondary_count = sum(
        str(usage.get("mode") or "none") in {"cutaway", "pip"}
        and str(visual.get("format") or "") in DYNAMIC_FORMATS
        for usage, visual in zip(secondary_usages, secondary_visuals)
    )
    dynamic_count = sum(item in DYNAMIC_FORMATS for item in formats) + dynamic_secondary_count
    static_count = sum(
        item in STATIC_CARD_FORMATS and str(secondary_usages[index].get("mode") or "none") != "cutaway"
        for index, item in enumerate(formats)
    )
    meme_count = formats.count(VisualFormat.MEME.value)
    format_counts = Counter(formats)
    motion_counts = Counter(motions)
    transition_counts = Counter(transitions)
    broll_ratio = broll_count / max(1, count)
    dynamic_ratio = min(1.0, dynamic_count / max(1, count))
    static_ratio = static_count / max(1, count)
    literal_rows = [
        item for item in shots
        if str(((item.get("metadata") or {}).get("intent") or {}).get("literalness") or "") in {"literal", "creator"}
    ]
    literal_covered = sum(
        str(item.get("visual_type") or "") in BROLL_FORMATS
        or (
            str(((item.get("metadata") or {}).get("secondary_usage") or {}).get("mode") or "none") == "cutaway"
            and str(((item.get("metadata") or {}).get("secondary_visual") or {}).get("format") or "") in BROLL_FORMATS
        )
        for item in literal_rows
    )
    literal_broll_coverage = literal_covered / len(literal_rows) if literal_rows else None
    average_duration = sum(durations) / max(1, len(durations))
    max_same_format = _max_run(formats)
    max_same_signature = _max_run(visual_signatures)
    dominant_format_ratio = max(format_counts.values(), default=0) / max(1, count)

    warnings: list[str] = []
    score = 100.0
    media_mode = str(info.get("media_mode") or "auto")
    if media_mode == "broll" and count >= 4 and broll_ratio < 0.35:
        warnings.append(f"Real B-roll coverage is low ({broll_ratio:.0%}) for B-roll mode.")
        score -= 22
    elif media_mode != "original" and len(literal_rows) >= 2 and (literal_broll_coverage or 0.0) < 0.5:
        warnings.append(f"Literal moments lack real B-roll ({(literal_broll_coverage or 0.0):.0%} covered).")
        score -= 16
    if dynamic_ratio < 0.65 and count >= 4:
        warnings.append(f"Dynamic visual coverage is low ({dynamic_ratio:.0%}).")
        score -= 12
    if static_ratio > 0.45:
        warnings.append(f"Static-card coverage is high ({static_ratio:.0%}); the edit may feel like a slideshow.")
        score -= 22
    if max_same_signature > 2:
        warnings.append(f"The same visual concept repeats {max_same_signature} times in a row.")
        score -= min(20, (max_same_signature - 2) * 6)
    elif dominant_format_ratio > 0.78 and count >= 5:
        warnings.append(f"One visual language dominates the edit ({dominant_format_ratio:.0%}).")
        score -= 12
    if len(motion_counts) < 2 and count >= 4:
        warnings.append("Shot motion has little variation.")
        score -= 12
    if len(transition_counts) < 2 and count >= 6:
        warnings.append("Transition rhythm has little variation.")
        score -= 6
    allowed_memes = max(0, min(2, math.ceil(profile.max_memes_per_minute * sum(durations) / 60.0)))
    if meme_count > allowed_memes:
        warnings.append(f"Meme count {meme_count} exceeds the style budget {allowed_memes}.")
        score -= 14
    if profile.humor_budget == 0 and meme_count:
        warnings.append("A serious style contains a meme.")
        score -= 24
    if average_duration > 4.5 and profile.pace in {"fast", "very_fast"}:
        warnings.append(f"Average shot duration {average_duration:.2f}s is slow for {profile.name}.")
        score -= 10

    status = "not_run" if not shots else "warning" if warnings else "passed"
    report = {
        "status": status,
        "score": round(max(0.0, score), 2),
        "shot_count": count,
        "style": profile.name,
        "live_broll_ratio": round(broll_ratio, 4),
        "literal_broll_coverage": round(literal_broll_coverage, 4) if literal_broll_coverage is not None else None,
        "dynamic_visual_ratio": round(dynamic_ratio, 4),
        "static_card_ratio": round(static_ratio, 4),
        "meme_count": meme_count,
        "cutaway_count": cutaway_count,
        "pip_count": pip_count,
        "maximum_same_format_run": max_same_format,
        "maximum_same_visual_signature_run": max_same_signature,
        "dominant_format_ratio": round(dominant_format_ratio, 4),
        "average_shot_seconds": round(average_duration, 3),
        "format_counts": dict(format_counts),
        "motion_counts": dict(motion_counts),
        "transition_counts": dict(transition_counts),
        "warnings": warnings,
    }
    write_json(folder / "quality" / "creative-report.json", report)
    return report
