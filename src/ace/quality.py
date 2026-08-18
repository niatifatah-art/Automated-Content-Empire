from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.providers import ProviderRouter
from ace.storage import metadata, resolve_generation
from ace.utils import write_json


@dataclass(frozen=True)
class QualityReport:
    status: str
    score: int
    critical: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: dict[str, Any]
    provider: str | None = None
    model: str | None = None


_SHORT_TYPES = {"short", "reel", "story", "video_script"}
_GENERIC_OPENINGS = (
    r"^in this video\b",
    r"^today(?:,|\s)+(?:we(?:'re| are)|i(?:'m| am))\b",
    r"^have you ever wondered\b",
    r"^did you know(?: that)?\b",
    r"^welcome (?:back )?to\b",
    r"^let(?:'s| us) (?:talk about|dive into|explore)\b",
)
_AI_FILLER = (
    "in today's fast-paced world",
    "it's important to note",
    "it is important to note",
    "let's dive in",
    "let us dive in",
    "in conclusion",
    "without further ado",
    "game-changer",
    "game changer",
)


def _sentences(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", text.strip())) if part.strip()]


def heuristic(text: str, *, content_type: str | None = None) -> QualityReport:
    critical: list[str] = []
    warnings: list[str] = []
    penalty = 0
    words = text.split()
    normalized = re.sub(r"\s+", " ", text.strip())
    lowered = normalized.lower()
    stage = re.findall(r"(?im)^\s*(?:\[[^\]]+\]|(?:host|narrator|scene|b-roll|music)\s*:)", text)
    headings = re.findall(r"(?m)^\s*#{1,6}\s+", text)
    urls = re.findall(r"https?://\S+", text)
    invented_quote_risk = re.findall(r"[“\"]([^”\"]{8,})[”\"]", text)
    precise = re.findall(r"\b(?:\d{2,}(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion))\b", text, re.I)
    sentences = _sentences(text)
    longest_sentence_words = max((len(sentence.split()) for sentence in sentences), default=0)
    generic_opening = any(re.search(pattern, lowered, re.I) for pattern in _GENERIC_OPENINGS)
    filler_hits = [phrase for phrase in _AI_FILLER if phrase in lowered]

    if not text.strip():
        critical.append("Script is empty.")
    if len(words) < 8:
        critical.append("Script is too short to be a finished deliverable.")

    if stage:
        warnings.append("Script contains stage directions or speaker labels.")
        penalty += 10
    if headings:
        warnings.append("Script contains Markdown headings.")
        penalty += 8
    if urls:
        warnings.append("Script contains URLs that should not be spoken.")
        penalty += 10
    if invented_quote_risk:
        warnings.append("Quotation marks require exact source verification.")
        penalty += 5
    if precise:
        warnings.append("Precise statistics must be mapped to strong sources.")
        penalty += 5

    if content_type in _SHORT_TYPES:
        if len(words) < 55:
            warnings.append("Short-form script is too thin for the requested 35-60 second format.")
            penalty += 14
        elif len(words) > 190:
            warnings.append("Short-form script is too long for the requested 35-60 second format.")
            penalty += 12
        if generic_opening:
            warnings.append("Opening uses a generic creator-template hook instead of earning attention immediately.")
            penalty += 12

    if filler_hits:
        warnings.append("Script contains generic AI/creator filler: " + ", ".join(filler_hits) + ".")
        penalty += min(18, 7 + 4 * (len(filler_hits) - 1))
    if longest_sentence_words > 42:
        warnings.append("At least one sentence is too long for natural spoken delivery.")
        penalty += 7

    score = max(0, min(100, 100 - len(critical) * 35 - penalty))
    status = "failed" if critical else "warning" if warnings or score < 85 else "passed"
    return QualityReport(
        status,
        score,
        tuple(critical),
        tuple(warnings),
        {
            "word_count": len(words),
            "stage_direction_count": len(stage),
            "heading_count": len(headings),
            "url_count": len(urls),
            "quotation_count": len(invented_quote_risk),
            "precise_claim_count": len(precise),
            "generic_opening": generic_opening,
            "generic_filler_count": len(filler_hits),
            "longest_sentence_words": longest_sentence_words,
            "content_type": content_type,
        },
    )


def ai_check(
    text: str,
    router: ProviderRouter,
    *,
    topic: str | None = None,
    platform: str | None = None,
    content_type: str | None = None,
) -> QualityReport | None:
    context = "\n".join(
        line
        for line in (
            f"Topic: {topic}" if topic else "",
            f"Platform: {platform}" if platform else "",
            f"Content type: {content_type}" if content_type else "",
        )
        if line
    )
    prompt = f"""Review this social-media script. Return JSON only with:
status (passed, warning, failed), score (0-100), critical (array), warnings (array), and checks (object).
Judge clarity, opening strength, specificity, natural speech, platform/format fit, factual risk, restrained humor, and TTS compatibility.
A technically clean but generic, vague, repetitive, templated, or low-information script must not receive a high score.
Reject invented quotes, unsupported precise claims, misleading certainty, stage directions, generic AI preambles, and filler openings.
Do not factually verify anything yourself; flag claims needing sources.
{context}

SCRIPT:
{text}
"""
    try:
        result = router.generate("quality", prompt, json_mode=True, temperature=0.1, max_output_tokens=1600)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.I | re.S)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        return QualityReport(
            str(data.get("status", "warning")),
            max(0, min(100, int(data.get("score", 0)))),
            tuple(str(item) for item in data.get("critical", [])),
            tuple(str(item) for item in data.get("warnings", [])),
            data.get("checks", {}) if isinstance(data.get("checks"), dict) else {},
            result.provider,
            result.model,
        )
    except Exception:
        return None


def run(generation: str | Path, workspace: str | Path | None = None, *, router: ProviderRouter | None = None, use_ai: bool = True) -> QualityReport:
    folder = resolve_generation(generation, workspace)
    text = (folder / "selected.md").read_text(encoding="utf-8")
    info = metadata(folder)
    content_type = str(info.get("content_type") or "") or None
    base = heuristic(text, content_type=content_type)
    ai = (
        ai_check(
            text,
            router or ProviderRouter(workspace),
            topic=str(info.get("topic") or "") or None,
            platform=str(info.get("platform") or "") or None,
            content_type=content_type,
        )
        if use_ai
        else None
    )
    if ai:
        critical = tuple(dict.fromkeys([*base.critical, *ai.critical]))
        warnings = tuple(dict.fromkeys([*base.warnings, *ai.warnings]))
        score = min(base.score, ai.score) if critical else round((base.score + ai.score) / 2)
        status = "failed" if critical else "warning" if warnings or score < 85 else "passed"
        report = QualityReport(status, score, critical, warnings, {**base.checks, **ai.checks}, ai.provider, ai.model)
    else:
        report = base
    write_json(folder / "quality" / "script-report.json", asdict(report))
    return report
