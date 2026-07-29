from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Any

from ace.ai import AIEngine
from ace.errors import ACEError
from ace.storage import resolve_generation, write_json


@dataclass(frozen=True)
class FactReport:
    status: str
    critical: tuple[str, ...]
    warnings: tuple[str, ...]
    claims: tuple[dict[str, Any], ...]
    source_count: int
    provider: str | None = None
    model: str | None = None


def _load_sources(folder: Path) -> list[dict[str, Any]]:
    path = folder / "research" / "sources.json"
    if not path.exists():
        return []
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(value, dict):
        value = value.get("sources", [])
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _heuristic(text: str, sources: list[dict[str, Any]]) -> FactReport:
    claims: list[dict[str, Any]] = []
    critical: list[str] = []
    warnings: list[str] = []
    precise = re.findall(r"[^.!?\n]*(?:\b\d+(?:\.\d+)?%|\b\d{4}\b|\b\d+(?:\.\d+)?\s*(?:million|billion|trillion))[^.!?\n]*[.!?]?", text, re.I)
    quoted = re.findall(r'[“\"]([^”\"]{8,})[”\"]', text)
    for value in precise:
        claims.append({"text": value.strip(), "status": "needs_source", "reason": "precise numeric or dated claim"})
    for value in quoted:
        claims.append({"text": value.strip(), "status": "needs_source", "reason": "direct quotation"})
    if claims and not sources:
        critical.append("Precise claims or quotations exist but no research sources are stored.")
    elif claims:
        warnings.append("Precise claims or quotations require explicit source matching before publication.")
    if not sources:
        warnings.append("No research sources are stored; factual confidence is limited.")
    return FactReport(
        status="failed" if critical else "warning" if warnings else "passed",
        critical=tuple(critical), warnings=tuple(warnings), claims=tuple(claims), source_count=len(sources),
    )


def _ai_fact_check(text: str, sources: list[dict[str, Any]], workspace: str | Path | None, engine: AIEngine | None = None) -> FactReport | None:
    source_view = [
        {"title": item.get("title"), "url": item.get("source_url") or item.get("url"), "provider": item.get("source_provider")}
        for item in sources[:20]
    ]
    prompt = f"""Audit the script only against the supplied source metadata. Return valid JSON only with:
status (passed, warning, failed), critical (array), warnings (array), claims (array of objects with text,
status, source_indexes, reason). Status values for claims: verified, unsupported, contradicted, time_sensitive,
or needs_full_source. Never use your memory as evidence. A title alone is not enough to verify a precise claim.
Reject invented quotations and unsupported precise statistics.

SOURCES:
{json.dumps(source_view, ensure_ascii=False)}

SCRIPT:
{text}
"""
    try:
        if engine is None:
            with AIEngine.from_workspace(workspace) as owned:
                result = owned.generate("fact_check", prompt, temperature=0.0, max_output_tokens=2400)
        else:
            result = engine.generate("fact_check", prompt, temperature=0.0, max_output_tokens=2400)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.I | re.S)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        if not isinstance(data, dict):
            return None
        return FactReport(
            status=str(data.get("status", "warning")),
            critical=tuple(str(item) for item in data.get("critical", [])),
            warnings=tuple(str(item) for item in data.get("warnings", [])),
            claims=tuple(item for item in data.get("claims", []) if isinstance(item, dict)),
            source_count=len(sources), provider=result.provider, model=result.model,
        )
    except (ACEError, ValueError, json.JSONDecodeError):
        return None


def run_fact_check(
    generation: str | Path,
    *, workspace: str | Path | None = None, use_ai: bool = True, engine: AIEngine | None = None,
) -> FactReport:
    folder = resolve_generation(generation, workspace)
    text = (folder / "selected.md").read_text(encoding="utf-8")
    sources = _load_sources(folder)
    heuristic = _heuristic(text, sources)
    ai = _ai_fact_check(text, sources, workspace, engine) if use_ai and sources else None
    if ai:
        critical = tuple(dict.fromkeys([*heuristic.critical, *ai.critical]))
        warnings = tuple(dict.fromkeys([*heuristic.warnings, *ai.warnings]))
        claims = ai.claims or heuristic.claims
        status = "failed" if critical else "warning" if warnings or ai.status != "passed" else "passed"
        report = FactReport(status, critical, warnings, claims, len(sources), ai.provider, ai.model)
    else:
        report = heuristic
    write_json(folder / "quality" / "fact-report.json", asdict(report))
    return report
