from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.providers import ProviderFailure, ProviderRouter
from ace.sources import SourceRecord, discover_news_rss, load_sources, save_sources
from ace.storage import metadata, resolve_generation
from ace.utils import read_json, sha256_bytes, write_json


@dataclass
class ClaimRecord:
    id: str
    text: str
    importance: str = "normal"
    factual_risk: str = "medium"
    source_ids: list[str] = field(default_factory=list)
    status: str = "unverified"
    confidence: float = 0.0
    visual_options: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


@dataclass
class ResearchReport:
    source_count: int
    claim_count: int
    verified_count: int
    warning_count: int
    contradictions: list[dict[str, Any]]
    status: str


def collect(generation: str | Path, *, query: str | None = None, workspace: str | Path | None = None) -> list[SourceRecord]:
    folder = resolve_generation(generation, workspace)
    query = query or str(metadata(folder).get("topic") or folder.name)
    current = load_sources(folder, workspace)
    config = load_config(workspace)
    discovered: list[SourceRecord] = []
    if config.get("research", {}).get("rss_fallback", True):
        try:
            discovered = discover_news_rss(query, workspace, limit=int(config.get("research", {}).get("maximum_sources", 12)))
        except Exception:
            discovered = []
    combined = [*current, *discovered]
    combined.sort(key=lambda item: (not item.official, -item.credibility_score, item.title))
    limit = int(config.get("research", {}).get("maximum_sources", 12))
    save_sources(folder, combined[:limit], workspace)
    return combined[:limit]


def _fallback_claims(script: str) -> list[ClaimRecord]:
    sentences = [part.strip() for part in re.split(r"(?<=[.!?])\s+", re.sub(r"\s+", " ", script)) if len(part.split()) >= 4]
    claims: list[ClaimRecord] = []
    for sentence in sentences:
        risky = bool(re.search(r"\b\d+(?:\.\d+)?%?\b|\bannounced\b|\bdeal\b|\bfirst\b|\bbest\b|\bnever\b|\balways\b", sentence, re.I))
        claims.append(
            ClaimRecord(
                id=sha256_bytes(sentence.encode("utf-8"))[:12],
                text=sentence,
                importance="high" if risky else "normal",
                factual_risk="high" if risky else "medium",
                visual_options=["evidence_card", "semantic_broll", "generated_diagram"],
            )
        )
    return claims


def extract_claims(generation: str | Path, workspace: str | Path | None = None, *, router: ProviderRouter | None = None) -> list[ClaimRecord]:
    folder = resolve_generation(generation, workspace)
    script_path = folder / "selected.md"
    script = script_path.read_text(encoding="utf-8")
    owned = router or ProviderRouter(workspace)
    prompt = (
        "Extract factual claims from this social-media script. Return JSON only as an array. Each item must contain "
        "text, importance (low|normal|high), factual_risk (low|medium|high), and visual_options (array chosen from "
        "evidence_card, official_page, social_post, semantic_broll, generated_diagram, meme_reaction). Do not invent claims.\n\n"
        + script
    )
    try:
        result = owned.generate("fact_check", prompt, json_mode=True, temperature=0.1, max_output_tokens=2400)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.I | re.S)
        start, end = raw.find("["), raw.rfind("]")
        rows = json.loads(raw[start : end + 1])
        claims = [
            ClaimRecord(
                id=sha256_bytes(str(row.get("text", "")).encode("utf-8"))[:12],
                text=str(row.get("text", "")).strip(),
                importance=str(row.get("importance", "normal")),
                factual_risk=str(row.get("factual_risk", "medium")),
                visual_options=[str(item) for item in row.get("visual_options", [])],
            )
            for row in rows
            if isinstance(row, dict) and str(row.get("text", "")).strip()
        ]
    except (ProviderFailure, ValueError, json.JSONDecodeError):
        claims = _fallback_claims(script)
    write_json(folder / "research" / "claims.json", [asdict(item) for item in claims])
    return claims


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-zA-Z0-9_]{3,}", value.lower()) if token not in {"this", "that", "with", "from", "have", "your", "they", "will"}}


def map_claims_to_sources(claims: list[ClaimRecord], sources: list[SourceRecord]) -> list[ClaimRecord]:
    for claim in claims:
        claim_tokens = _tokens(claim.text)
        ranked: list[tuple[float, SourceRecord]] = []
        for source in sources:
            source_tokens = _tokens(" ".join(filter(None, [source.title, source.description, source.text_excerpt])))
            overlap = len(claim_tokens & source_tokens) / max(1, len(claim_tokens))
            score = overlap * 0.7 + source.credibility_score * 0.3
            if overlap > 0 or source.official:
                ranked.append((score, source))
        ranked.sort(key=lambda item: item[0], reverse=True)
        selected = [item for score, item in ranked[:3] if score >= 0.18]
        claim.source_ids = [item.id for item in selected]
        if selected:
            primary = any(item.official or item.credibility_score >= 0.9 for item in selected)
            independent = len({item.domain for item in selected}) >= 2
            claim.confidence = round(min(0.98, 0.55 + max(item.credibility_score for item in selected) * 0.3 + (0.12 if independent else 0)), 2)
            if claim.factual_risk == "high" and not (primary or independent):
                claim.status = "warning"
                claim.notes.append("High-risk claim needs one primary source or two independent credible sources.")
            else:
                claim.status = "verified"
        else:
            claim.status = "unverified"
            claim.notes.append("No sufficiently relevant source was mapped.")
    return claims


def detect_contradictions(claims: list[ClaimRecord], sources: list[SourceRecord]) -> list[dict[str, Any]]:
    contradictions: list[dict[str, Any]] = []
    opposing = [("finalized", "negotiating"), ("confirmed", "rumor"), ("approved", "rejected"), ("available", "delayed")]
    for claim in claims:
        mapped = [source for source in sources if source.id in claim.source_ids]
        combined = " ".join(" ".join(filter(None, [source.title, source.description])) for source in mapped).lower()
        for positive, negative in opposing:
            if positive in combined and negative in combined:
                contradictions.append({"claim_id": claim.id, "claim": claim.text, "terms": [positive, negative], "status": "review_required"})
    return contradictions


def verify(generation: str | Path, workspace: str | Path | None = None, *, router: ProviderRouter | None = None) -> ResearchReport:
    folder = resolve_generation(generation, workspace)
    sources = load_sources(folder, workspace)
    claims_path = folder / "research" / "claims.json"
    if claims_path.exists():
        claims = [ClaimRecord(**row) for row in read_json(claims_path, [])]
    else:
        claims = extract_claims(folder, workspace, router=router)
    claims = map_claims_to_sources(claims, sources)
    contradictions = detect_contradictions(claims, sources)
    write_json(claims_path, [asdict(item) for item in claims])
    write_json(folder / "research" / "contradictions.json", contradictions)
    warning_count = sum(item.status != "verified" for item in claims) + len(contradictions)
    report = ResearchReport(
        source_count=len(sources),
        claim_count=len(claims),
        verified_count=sum(item.status == "verified" for item in claims),
        warning_count=warning_count,
        contradictions=contradictions,
        status="failed" if any(item.status == "unverified" and item.factual_risk == "high" for item in claims) else "warning" if warning_count else "passed",
    )
    write_json(folder / "quality" / "fact-report.json", asdict(report))
    return report
