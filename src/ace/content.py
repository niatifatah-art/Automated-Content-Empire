from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.accounts import load as load_account
from ace.providers import ProviderRouter
from ace.sources import load_sources
from ace.storage import create_generation, metadata, update_metadata
from ace.utils import write_json


@dataclass
class Candidate:
    index: int
    text: str
    provider: str
    model: str
    credential: str | None
    score: float = 0.0
    reasons: list[str] | None = None


@dataclass
class ContentResult:
    folder: Path
    path: Path
    text: str
    provider: str
    model: str
    selected_candidate: int


def _account_prompt(account: dict[str, Any]) -> str:
    identity = account.get("identity", {})
    humor = identity.get("humor", {})
    return (
        f"Creator identity: {account.get('name')}.\n"
        f"Description: {account.get('description')}.\n"
        f"Personality: {', '.join(identity.get('personality', []))}.\n"
        f"Audience: {account.get('audience', {}).get('description')}; knowledge level {account.get('audience', {}).get('knowledge_level')}.\n"
        f"Humor: adaptive, {humor.get('default_level', 'moderate')}; light self-aware cringe is allowed, forced jokes are not.\n"
        f"Avoid: {', '.join(account.get('content', {}).get('avoid', []))}.\n"
    )


def _format_prompt(platform: str, content_type: str) -> str:
    if content_type in {"short", "reel", "story", "video_script"}:
        return (
            "Write a spoken social video script of roughly 35-60 seconds. Start with a strong natural hook, explain one clear idea, "
            "and end cleanly. Do not include headings, scene directions, citations inside narration, or a generic AI preamble."
        )
    if content_type in {"long_video", "youtube_video"}:
        return "Write a structured spoken video script with a hook, clear sections, examples, and conclusion. Do not include production directions unless asked."
    if content_type in {"post", "thread", "linkedin_post"}:
        return "Write platform-native social copy with a natural opening, useful substance, and restrained call to action."
    return f"Write a finished {platform} {content_type} deliverable."


def _source_context(folder: Path) -> str:
    sources = load_sources(folder)
    if not sources:
        return "No external sources are currently available. Avoid precise claims that require verification."
    lines = []
    for source in sources[:10]:
        lines.append(f"- [{source.credibility}] {source.title} — {source.publisher or source.domain} — {source.url}")
    return "Available research references:\n" + "\n".join(lines)


def _candidate_prompt(
    account: dict[str, Any],
    platform: str,
    content_type: str,
    topic: str,
    instructions: str,
    folder: Path,
    variant: int,
) -> str:
    angles = [
        "clear explanatory angle",
        "curiosity-driven angle",
        "young-adult playful tech angle",
        "serious evidence-first angle",
        "challenge or surprising-comparison angle",
    ]
    angle = angles[(variant - 1) % len(angles)]
    return f"""{_account_prompt(account)}
Task: {_format_prompt(platform, content_type)}
Topic: {topic}
Candidate angle: {angle}
Extra instructions: {instructions or 'None'}

Safety and quality rules:
- Use only conservative, well-established claims supported by the supplied sources.
- Never invent quotations, percentages, dates, studies, benchmark results, or deal terms.
- Do not use quotation marks unless the quotation appears in a source.
- Clearly frame rumors, reactions, jokes, and opinions as such.
- Match the seriousness of the topic; do not joke about victims or harm.
- Sound like a smart 20-year-old technology creator: human, current, lightly funny when appropriate, never corporate or childish.

{_source_context(folder)}

Return only the final spoken script.
"""


def _heuristic_score(text: str, topic: str) -> tuple[float, list[str]]:
    words = text.split()
    score = 50.0
    reasons: list[str] = []
    if 70 <= len(words) <= 180:
        score += 15
        reasons.append("appropriate short-form length")
    elif len(words) < 35:
        score -= 20
        reasons.append("too short")
    if any(token in text.lower()[:180] for token in ("why", "here's", "this", "imagine", "stop", "just")):
        score += 8
        reasons.append("direct hook")
    if topic.lower().split()[0] in text.lower():
        score += 6
        reasons.append("topic relevance")
    if re.search(r"(?im)^\s*(?:scene|host|narrator|b-roll|music)\s*:", text):
        score -= 25
        reasons.append("contains stage directions")
    if re.search(r"\b\d{2,}(?:\.\d+)?%\b", text):
        score -= 8
        reasons.append("precise statistic needs strong sourcing")
    if text.lower().count("in conclusion"):
        score -= 5
        reasons.append("generic conclusion")
    return max(0.0, min(100.0, score)), reasons


def _select_with_ai(candidates: list[Candidate], topic: str, router: ProviderRouter) -> int:
    payload = "\n\n".join(f"CANDIDATE {item.index}:\n{item.text}" for item in candidates)
    prompt = f"""Choose the best social-video script for: {topic}
Score clarity, hook, factual restraint, brand fit, natural speech, and platform fit. Return JSON only:
{{"selected": 1, "scores": {{"1": 90}}, "reason": "..."}}

{payload}
"""
    try:
        result = router.generate("review", prompt, json_mode=True, temperature=0.1, max_output_tokens=800)
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", result.text.strip(), flags=re.I | re.S)
        data = json.loads(raw[raw.find("{") : raw.rfind("}") + 1])
        selected = int(data.get("selected", 0))
        if 1 <= selected <= len(candidates):
            scores = data.get("scores", {})
            for candidate in candidates:
                if str(candidate.index) in scores:
                    candidate.score = float(scores[str(candidate.index)])
            return selected
    except Exception:
        pass
    return max(candidates, key=lambda item: item.score).index


def generate(
    platform: str,
    content_type: str,
    topic: str,
    *,
    instructions: str = "",
    variants: int = 5,
    account_slug: str | None = None,
    workspace: str | Path | None = None,
    router: ProviderRouter | None = None,
    provider: str | None = None,
    model: str | None = None,
    no_fallback: bool = False,
    existing_folder: Path | None = None,
) -> ContentResult:
    account = load_account(account_slug, workspace)
    folder = existing_folder or create_generation(platform, content_type, topic, account_slug=account["slug"], workspace=workspace)
    owned = router or ProviderRouter(workspace)
    candidates: list[Candidate] = []
    candidates_dir = folder / "script" / "candidates"
    candidates_dir.mkdir(parents=True, exist_ok=True)
    for index in range(1, max(1, variants) + 1):
        prompt = _candidate_prompt(account, platform, content_type, topic, instructions, folder, index)
        result = owned.generate("script", prompt, provider=provider, model=model, temperature=0.55, max_output_tokens=3000, no_fallback=no_fallback)
        text = result.text.strip()
        score, reasons = _heuristic_score(text, topic)
        candidate = Candidate(index, text, result.provider, result.model, result.credential_name, score, reasons)
        candidates.append(candidate)
        (candidates_dir / f"candidate-{index:02d}.md").write_text(text + "\n", encoding="utf-8")
    selected_index = _select_with_ai(candidates, topic, owned) if len(candidates) > 1 else 1
    selected = next(item for item in candidates if item.index == selected_index)
    selected_path = folder / "selected.md"
    selected_path.write_text(selected.text + "\n", encoding="utf-8")
    write_json(folder / "evaluation.json", {"selected": selected_index, "candidates": [asdict(item) for item in candidates]})
    update_metadata(
        folder,
        final_provider=selected.provider,
        final_model=selected.model,
        final_credential=selected.credential,
        selected_candidate=selected.index,
        instructions=instructions,
    )
    return ContentResult(folder, selected_path, selected.text, selected.provider, selected.model, selected.index)


def revise(result: ContentResult, problems: list[str], router: ProviderRouter) -> ContentResult:
    prompt = (
        "Revise this approved social-media script to fix the listed problems. Return only the finished spoken script. "
        "Do not add headings, stage directions, invented quotes, citations inside narration, or new unsupported claims.\n\n"
        "PROBLEMS:\n- " + "\n- ".join(problems) + "\n\nSCRIPT:\n" + result.path.read_text(encoding="utf-8")
    )
    improved = router.generate("review", prompt, temperature=0.2, max_output_tokens=3000)
    revisions = result.folder / "script" / "revisions"
    revisions.mkdir(parents=True, exist_ok=True)
    current = result.path.read_text(encoding="utf-8")
    (revisions / f"v{len(list(revisions.glob('v*.md'))) + 1:03d}-before.md").write_text(current, encoding="utf-8")
    result.path.write_text(improved.text.strip() + "\n", encoding="utf-8")
    return ContentResult(result.folder, result.path, improved.text.strip(), improved.provider, improved.model, result.selected_candidate)
