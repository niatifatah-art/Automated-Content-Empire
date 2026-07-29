from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.providers import ProviderRouter
from ace.storage import resolve_generation
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


def heuristic(text: str) -> QualityReport:
    critical: list[str] = []
    warnings: list[str] = []
    words = text.split()
    stage = re.findall(r"(?im)^\s*(?:\[[^\]]+\]|(?:host|narrator|scene|b-roll|music)\s*:)", text)
    headings = re.findall(r"(?m)^\s*#{1,6}\s+", text)
    urls = re.findall(r"https?://\S+", text)
    invented_quote_risk = re.findall(r"[“\"]([^”\"]{8,})[”\"]", text)
    precise = re.findall(r"\b(?:\d{2,}(?:\.\d+)?%|\d+(?:\.\d+)?\s*(?:million|billion|trillion))\b", text, re.I)
    if not text.strip():
        critical.append("Script is empty.")
    if len(words) < 8:
        critical.append("Script is too short to be a finished deliverable.")
    if stage:
        warnings.append("Script contains stage directions or speaker labels.")
    if headings:
        warnings.append("Script contains Markdown headings.")
    if urls:
        warnings.append("Script contains URLs that should not be spoken.")
    if invented_quote_risk:
        warnings.append("Quotation marks require exact source verification.")
    if precise:
        warnings.append("Precise statistics must be mapped to strong sources.")
    score = max(0, min(100, 100 - len(critical) * 35 - len(warnings) * 5))
    status = "failed" if critical else "warning" if warnings else "passed"
    return QualityReport(status, score, tuple(critical), tuple(warnings), {"word_count": len(words), "stage_direction_count": len(stage), "heading_count": len(headings), "url_count": len(urls), "quotation_count": len(invented_quote_risk), "precise_claim_count": len(precise)})


def ai_check(text: str, router: ProviderRouter) -> QualityReport | None:
    prompt = f"""Review this social-media script. Return JSON only with:
status (passed, warning, failed), score (0-100), critical (array), warnings (array), and checks (object).
Judge brand match, clarity, hook, platform fit, factual risk, natural speech, age-appropriate humor, and TTS compatibility.
Reject invented quotes, unsupported precise claims, misleading certainty, stage directions, and AI preambles.
Do not factually verify anything yourself; flag claims needing sources.

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
    base = heuristic(text)
    ai = ai_check(text, router or ProviderRouter(workspace)) if use_ai else None
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
