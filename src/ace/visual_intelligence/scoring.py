from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Any

from ace.media_fingerprint import tokens as fingerprint_tokens
from ace.visual_intelligence.contracts import (
    CandidateOrigin,
    DecisionStatus,
    ShotIntent,
    VisualCandidate,
    VisualFormat,
    VisualScore,
)


_TOKEN_RE = re.compile(r"[a-z0-9_+-]{2,}")

ALIASES: dict[str, set[str]] = {
    "wireless_router": {"router", "wifi", "wireless", "access_point"},
    "shared_access_point": {"router", "access_point", "wifi", "shared_network"},
    "multiple_devices": {"device", "devices", "phone", "laptop", "computer", "tablet"},
    "data_packets": {"packet", "packets", "data", "traffic", "request"},
    "missing_encryption_lock": {"unlocked", "open_lock", "unencrypted", "exposed", "missing_lock"},
    "encryption_lock": {"lock", "encrypted", "protected", "secure"},
    "protected_connection": {"encrypted", "secure", "https", "tls", "lock"},
    "two_similar_wifi_names": {"wifi_names", "lookalike", "evil_twin", "fake_wifi", "ssid"},
    "trusted_network": {"trusted", "real_network", "official_network"},
    "fake_network": {"fake", "rogue", "lookalike", "evil_twin"},
    "attacker_control": {"attacker", "controlled", "rogue"},
    "hotspot_settings": {"hotspot", "settings", "personal_hotspot", "tethering"},
    "biometric_confirmation": {"biometric", "face_id", "fingerprint", "authentication"},
    "public_private_key_flow": {"public_key", "private_key", "signature", "challenge", "signed"},
    "directional_flow": {"arrow", "flow", "request", "response", "pipeline"},
    "comparison_criteria": {"comparison", "criteria", "versus", "option_a", "option_b"},
    "exact_command": {"command", "terminal", "shell", "bash", "code"},
    "visible_result": {"result", "output", "success", "terminal"},
}

GENERIC_TERMS = {
    "technology", "tech", "internet", "digital", "computer", "business", "office", "cybersecurity",
    "network", "data", "innovation", "future", "abstract", "background", "person", "laptop",
}

PROVENANCE_SCORES = {
    CandidateOrigin.OFFICIAL_CAPTURE.value: 100.0,
    CandidateOrigin.ACCOUNT_OWNED.value: 100.0,
    CandidateOrigin.ACE_GENERATED.value: 100.0,
    CandidateOrigin.AI_GENERATED.value: 72.0,
    CandidateOrigin.LICENSED_STOCK.value: 92.0,
    CandidateOrigin.ATTRIBUTION_REQUIRED.value: 80.0,
    CandidateOrigin.REFERENCE_ONLY.value: 30.0,
    CandidateOrigin.SIMULATED.value: 10.0,
    CandidateOrigin.PLACEHOLDER.value: 0.0,
}

TRUTHFULNESS_SCORES = {
    CandidateOrigin.OFFICIAL_CAPTURE.value: 100.0,
    CandidateOrigin.ACCOUNT_OWNED.value: 98.0,
    CandidateOrigin.ACE_GENERATED.value: 100.0,
    CandidateOrigin.AI_GENERATED.value: 72.0,
    CandidateOrigin.LICENSED_STOCK.value: 92.0,
    CandidateOrigin.ATTRIBUTION_REQUIRED.value: 86.0,
    CandidateOrigin.REFERENCE_ONLY.value: 35.0,
    CandidateOrigin.SIMULATED.value: 0.0,
    CandidateOrigin.PLACEHOLDER.value: 0.0,
}


def _tokens(value: str | Iterable[str]) -> set[str]:
    if not isinstance(value, str):
        value = " ".join(str(item) for item in value)
    return set(_TOKEN_RE.findall(value.lower().replace("-", "_")))


def _element_tokens(element: str) -> set[str]:
    normalized = element.lower().replace("-", "_").replace(" ", "_")
    output = {normalized, *normalized.split("_")}
    output.update(ALIASES.get(normalized, set()))
    return {item for item in output if len(item) >= 2}


def _matched_elements(elements: list[str], candidate_tokens: set[str]) -> tuple[list[str], list[str]]:
    matched: list[str] = []
    missing: list[str] = []
    for element in elements:
        aliases = _element_tokens(element)
        if aliases & candidate_tokens:
            matched.append(element)
        else:
            missing.append(element)
    return matched, missing


def _matched_forbidden(elements: list[str], candidate_tokens: set[str], candidate_text: str) -> list[str]:
    """Match forbidden concepts conservatively.

    Required elements may match through one useful alias, but forbidden compound
    concepts must be genuinely present. A harmless word such as ``network`` must
    not trigger ``abstract_ai_network`` or ``generic_wifi_router`` by itself.
    """
    normalized_text = re.sub(r"[^a-z0-9]+", "_", candidate_text.lower()).strip("_")
    matched: list[str] = []
    for element in elements:
        normalized = re.sub(r"[^a-z0-9]+", "_", element.lower()).strip("_")
        if not normalized:
            continue
        if normalized in normalized_text:
            matched.append(element)
            continue
        parts = {part for part in normalized.split("_") if len(part) >= 2}
        aliases = ALIASES.get(normalized, set())
        alias_hit = any(
            re.sub(r"[^a-z0-9]+", "_", alias.lower()).strip("_") in normalized_text
            for alias in aliases
            if alias
        )
        # For compounds, require all meaningful parts. For a single forbidden
        # token, an exact token match is sufficient.
        if alias_hit or (len(parts) == 1 and bool(parts & candidate_tokens)) or (len(parts) > 1 and parts <= candidate_tokens):
            matched.append(element)
    return matched


def _format_score(intent: ShotIntent, candidate: VisualCandidate) -> tuple[float, str]:
    try:
        index = intent.preferred_formats.index(candidate.format)
    except ValueError:
        return 25.0, "The candidate format was not requested by the intent planner."
    scores = [100.0, 91.0, 82.0, 73.0, 65.0, 57.0, 50.0]
    score = scores[index] if index < len(scores) else max(30.0, 50.0 - (index - len(scores) + 1) * 4)
    return score, f"Format preference rank: {index + 1}/{len(intent.preferred_formats)}."


def _vertical_fit(candidate: VisualCandidate) -> float:
    if not candidate.width or not candidate.height:
        if candidate.format in {
            VisualFormat.ANIMATED_EXPLAINER.value,
            VisualFormat.KINETIC_TYPOGRAPHY.value,
            VisualFormat.ARTICLE_CARD.value,
            VisualFormat.SOCIAL_POST_CARD.value,
            VisualFormat.DATA_CHART.value,
            VisualFormat.COMPARISON_GRAPHIC.value,
            VisualFormat.TIMELINE.value,
            VisualFormat.MINIMAL_SCREEN.value,
        }:
            return 95.0
        return 62.0
    ratio = candidate.width / max(1, candidate.height)
    if ratio <= 0.66:
        return 100.0
    if ratio <= 0.9:
        return 90.0
    if ratio <= 1.2:
        return 75.0
    if ratio <= 1.78:
        return 58.0
    return 42.0


def _clarity(intent: ShotIntent, candidate: VisualCandidate, required_coverage: float) -> float:
    score = 55.0 + required_coverage * 0.35
    if candidate.format in {
        VisualFormat.ANIMATED_EXPLAINER.value,
        VisualFormat.TERMINAL_DEMO.value,
        VisualFormat.APPLICATION_DEMO.value,
        VisualFormat.BROWSER_DEMO.value,
        VisualFormat.COMPARISON_GRAPHIC.value,
        VisualFormat.DATA_CHART.value,
        VisualFormat.OFFICIAL_EVIDENCE.value,
    }:
        score += 12.0
    if candidate.format in {VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value} and intent.literalness != "literal":
        score -= 18.0
    if len(candidate.description.strip()) < 15:
        score -= 7.0
    return max(0.0, min(100.0, score))


def _visual_quality(candidate: VisualCandidate) -> float:
    score = 70.0
    if candidate.is_local:
        score += 8.0
    if candidate.width and candidate.height:
        pixels = candidate.width * candidate.height
        if pixels >= 1920 * 1080:
            score += 14.0
        elif pixels >= 1280 * 720:
            score += 9.0
        elif pixels < 640 * 480:
            score -= 20.0
    if candidate.origin == CandidateOrigin.PLACEHOLDER.value:
        return 0.0
    return max(0.0, min(100.0, score))


def score_candidate(
    intent: ShotIntent,
    candidate: VisualCandidate,
    *,
    used_fingerprints: set[str] | None = None,
    thresholds: dict[str, Any] | None = None,
) -> VisualScore:
    thresholds = thresholds or {}
    minimum_relevance = float(thresholds.get("minimum_relevance", 78))
    minimum_clarity = float(thresholds.get("minimum_clarity", 72))
    minimum_vertical = float(thresholds.get("minimum_vertical_fit", 70))
    minimum_truthfulness = float(thresholds.get("minimum_truthfulness", 95))
    maximum_duplicate = float(thresholds.get("maximum_duplicate_risk", 25))

    candidate_tokens = _tokens(candidate.searchable_text())
    narration_tokens = _tokens(intent.narration)
    subject_tokens = _tokens(intent.subject)
    generic_only = bool(candidate_tokens) and candidate_tokens <= GENERIC_TERMS

    matched, missing = _matched_elements(intent.required_elements, candidate_tokens)
    required_coverage = 100.0 if not intent.required_elements else 100.0 * len(matched) / len(intent.required_elements)
    forbidden = _matched_forbidden(intent.forbidden_elements, candidate_tokens, candidate.searchable_text())

    format_score, format_reason = _format_score(intent, candidate)
    lexical_overlap = 100.0 * len(candidate_tokens & (narration_tokens | subject_tokens)) / max(1, len(narration_tokens | subject_tokens))
    semantic_relevance = 0.50 * format_score + 0.40 * required_coverage + 0.10 * lexical_overlap
    if generic_only:
        semantic_relevance -= 28.0
    if candidate.format in {VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value} and intent.literalness != "literal":
        semantic_relevance -= 17.0
    if forbidden:
        semantic_relevance -= min(55.0, 22.0 * len(forbidden))
    semantic_relevance = max(0.0, min(100.0, semantic_relevance))

    vertical_fit = _vertical_fit(candidate)
    truthfulness = TRUTHFULNESS_SCORES.get(candidate.origin, 65.0)
    provenance = PROVENANCE_SCORES.get(candidate.origin, 60.0)
    style_match = 78.0
    if intent.humor_allowed and candidate.format == VisualFormat.MEME.value:
        style_match = 94.0
    elif not intent.humor_allowed and candidate.format == VisualFormat.MEME.value:
        style_match = 25.0
    elif intent.mood == "serious_technical" and candidate.format == VisualFormat.MEME.value:
        style_match = 5.0
    elif candidate.format in intent.preferred_formats[:3]:
        style_match = 90.0

    fingerprint = str(candidate.metadata.get("fingerprint") or candidate.path or candidate.source_url or candidate.candidate_id)
    candidate_fingerprint_tokens = fingerprint_tokens(candidate.metadata.get("fingerprint_bundle"))
    candidate_fingerprint_tokens.add(f"id:{fingerprint}")
    duplicate_risk = 90.0 if used_fingerprints and bool(candidate_fingerprint_tokens & used_fingerprints) else 0.0
    if candidate.metadata.get("near_duplicate"):
        duplicate_risk = max(duplicate_risk, float(candidate.metadata.get("duplicate_risk", 70)))

    clarity = _clarity(intent, candidate, required_coverage)
    visual_quality = _visual_quality(candidate)
    overall = (
        semantic_relevance * 0.31
        + clarity * 0.16
        + required_coverage * 0.12
        + vertical_fit * 0.09
        + style_match * 0.09
        + truthfulness * 0.10
        + visual_quality * 0.07
        + provenance * 0.06
        - duplicate_risk * 0.10
    )
    if forbidden:
        overall -= min(30.0, 12.0 * len(forbidden))
    if intent.evidence_required and candidate.origin not in {
        CandidateOrigin.OFFICIAL_CAPTURE.value,
        CandidateOrigin.ACCOUNT_OWNED.value,
        CandidateOrigin.ACE_GENERATED.value,
    }:
        truthfulness = min(truthfulness, 70.0)
        overall -= 15.0
    overall = max(0.0, min(100.0, overall))

    problems: list[str] = []
    warnings: list[str] = []
    reasoning = [format_reason]
    if matched:
        reasoning.append("Covered required elements: " + ", ".join(matched) + ".")
    if missing:
        warnings.append("Missing required elements: " + ", ".join(missing) + ".")
    if forbidden:
        problems.append("Contains forbidden concepts: " + ", ".join(forbidden) + ".")
    if generic_only:
        warnings.append("Candidate metadata is generic and does not identify the exact concept.")
    if candidate.format in {VisualFormat.STOCK_VIDEO.value, VisualFormat.STOCK_IMAGE.value} and intent.literalness != "literal":
        warnings.append("Stock media is being used for an abstract or evidence-heavy idea.")
    if candidate.approval_required:
        warnings.append("Human approval is required by source or license policy.")

    accepted = (
        semantic_relevance >= minimum_relevance
        and clarity >= minimum_clarity
        and vertical_fit >= minimum_vertical
        and truthfulness >= minimum_truthfulness
        and duplicate_risk <= maximum_duplicate
        and not forbidden
        and candidate.origin not in {CandidateOrigin.REFERENCE_ONLY.value, CandidateOrigin.SIMULATED.value, CandidateOrigin.PLACEHOLDER.value}
    )
    if candidate.approval_required and accepted:
        decision = DecisionStatus.NEEDS_APPROVAL.value
    else:
        decision = DecisionStatus.ACCEPTED.value if accepted else DecisionStatus.REJECTED.value

    if not accepted:
        if semantic_relevance < minimum_relevance:
            problems.append(f"Semantic relevance {semantic_relevance:.1f} is below {minimum_relevance:.1f}.")
        if clarity < minimum_clarity:
            problems.append(f"Clarity {clarity:.1f} is below {minimum_clarity:.1f}.")
        if vertical_fit < minimum_vertical:
            problems.append(f"Vertical fit {vertical_fit:.1f} is below {minimum_vertical:.1f}.")
        if truthfulness < minimum_truthfulness:
            problems.append(f"Truthfulness {truthfulness:.1f} is below {minimum_truthfulness:.1f}.")
        if duplicate_risk > maximum_duplicate:
            problems.append(f"Duplicate risk {duplicate_risk:.1f} exceeds {maximum_duplicate:.1f}.")

    return VisualScore(
        candidate_id=candidate.candidate_id,
        shot_id=candidate.shot_id,
        semantic_relevance=round(semantic_relevance, 2),
        clarity=round(clarity, 2),
        required_element_coverage=round(required_coverage, 2),
        vertical_fit=round(vertical_fit, 2),
        style_match=round(style_match, 2),
        truthfulness=round(truthfulness, 2),
        visual_quality=round(visual_quality, 2),
        provenance_confidence=round(provenance, 2),
        duplicate_risk=round(duplicate_risk, 2),
        overall=round(overall, 2),
        decision=decision,
        forbidden_violations=forbidden,
        warnings=warnings,
        reasoning=[*reasoning, *problems],
    )
