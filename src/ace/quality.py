from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.ai import AIEngine
from ace.errors import ACEError
from ace.storage import resolve_generation, write_json


@dataclass(frozen=True)
class QualityReport:
    status: str
    score: int
    critical: tuple[str, ...]
    warnings: tuple[str, ...]
    checks: dict[str, Any]
    provider: str | None = None
    model: str | None = None


def _sources_count(folder: Path) -> int:
    paths = [folder / "research" / "sources.json", folder / "licenses" / "manifest.json"]
    count = 0
    for path in paths:
        if not path.exists():
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(data, list):
            count += len(data)
        elif isinstance(data, dict):
            count += len(data.get("reference_only", [])) + len(data.get("sources", []))
    return count


def _heuristic(text: str, folder: Path | None = None) -> QualityReport:
    critical: list[str] = []
    warnings: list[str] = []
    words = text.split()
    stage = re.findall(r"(?im)^\s*(?:\[[^\]]+\]|(?:host|narrator|scene|b-roll|music)\s*:)", text)
    headings = re.findall(r"(?m)^\s*#{1,6}\s+", text)
    urls = re.findall(r"https?://\S+", text)
    unsupported_numbers = re.findall(r"\b(?:\d{2,}(?:\.\d+)?%?|\d+(?:\.\d+)?\s*(?:million|billion|trillion))\b", text, re.I)
    repeated = len(words) - len(set(word.lower().strip(".,!?;:") for word in words))
    if not text.strip():
        critical.append("Script is empty.")
    if len(words) < 8:
        critical.append("Script is too short to be a finished deliverable.")
    if stage:
        warnings.append("Script contains stage directions or speaker labels; TTS must use the cleaned version.")
    if headings:
        warnings.append("Script contains Markdown headings.")
    if urls:
        warnings.append("Script contains URLs that should not be spoken.")
    source_count = _sources_count(folder) if folder else 0
    if unsupported_numbers and source_count == 0:
        warnings.append("Numeric/statistical claims exist but no research sources are stored.")
    if repeated > max(20, len(words) * 0.55):
        warnings.append("The script may be repetitive.")
    score = 100 - len(critical) * 35 - len(warnings) * 7
    score = max(0, min(100, score))
    status = "failed" if critical else "warning" if warnings else "passed"
    return QualityReport(
        status=status,
        score=score,
        critical=tuple(critical),
        warnings=tuple(warnings),
        checks={
            "word_count": len(words),
            "stage_direction_count": len(stage),
            "markdown_heading_count": len(headings),
            "url_count": len(urls),
            "numeric_claim_count": len(unsupported_numbers),
            "stored_source_count": source_count,
        },
    )


def _ai_check(text: str, folder: Path, workspace: str | Path | None, engine: AIEngine | None = None) -> QualityReport | None:
    prompt = f"""Review this social-media script. Return valid JSON only with:
status (passed, warning, or failed), score (0-100), critical (array), warnings (array),
and checks (object with brand_match, clarity, hook, platform_fit, factual_risk, tts_compatibility).
Do not factually verify claims you cannot verify. Mark them as needing sources. Reject invented quotes,
unsupported precise statistics, stage directions in narration, and text that sounds like an AI preamble.

SCRIPT:
{text}
"""
    try:
        if engine is None:
            with AIEngine.from_workspace(workspace) as owned:
                result = owned.generate("quality", prompt, temperature=0.1, max_output_tokens=1600)
        else:
            result = engine.generate("quality", prompt, temperature=0.1, max_output_tokens=1600)
        raw = result.text.strip()
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw, flags=re.I | re.S)
        start, end = raw.find("{"), raw.rfind("}")
        data = json.loads(raw[start : end + 1])
        if not isinstance(data, dict):
            return None
        return QualityReport(
            status=str(data.get("status", "warning")),
            score=max(0, min(100, int(data.get("score", 0)))),
            critical=tuple(str(item) for item in data.get("critical", [])),
            warnings=tuple(str(item) for item in data.get("warnings", [])),
            checks=data.get("checks", {}) if isinstance(data.get("checks"), dict) else {},
            provider=result.provider,
            model=result.model,
        )
    except (ACEError, ValueError, json.JSONDecodeError):
        return None


def run_script_quality(
    generation: str | Path,
    *,
    workspace: str | Path | None = None,
    use_ai: bool = True,
    engine: AIEngine | None = None,
) -> QualityReport:
    folder = resolve_generation(generation, workspace)
    path = folder / "selected.md"
    text = path.read_text(encoding="utf-8")
    heuristic = _heuristic(text, folder)
    ai = _ai_check(text, folder, workspace, engine) if use_ai else None
    if ai:
        critical = tuple(dict.fromkeys([*heuristic.critical, *ai.critical]))
        warnings = tuple(dict.fromkeys([*heuristic.warnings, *ai.warnings]))
        score = min(heuristic.score, ai.score) if critical else round((heuristic.score + ai.score) / 2)
        status = "failed" if critical else "warning" if warnings or score < 85 else "passed"
        report = QualityReport(status, score, critical, warnings, {**heuristic.checks, **ai.checks}, ai.provider, ai.model)
    else:
        report = heuristic
    write_json(folder / "quality" / "script-report.json", asdict(report))
    return report


def ensure_quality(report: QualityReport, minimum_score: int = 85) -> None:
    if report.critical or report.score < minimum_score:
        details = "; ".join([*report.critical, *report.warnings]) or f"score {report.score}"
        raise ValueError(f"Script quality gate failed: {details}")
