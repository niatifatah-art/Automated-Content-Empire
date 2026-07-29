from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.accounts import active_slug, load as load_account
from ace.content import ContentResult, generate as generate_content, revise
from ace.editing import create_package, render
from ace.evidence import build as build_evidence
from ace.providers import ProviderRouter
from ace.quality import run as run_quality
from ace.research import collect as collect_research, extract_claims, verify as verify_research
from ace.status import inspect as inspect_status
from ace.storage import create_generation
from ace.utils import write_json
from ace.voice import generate as generate_voice, prepare as prepare_voice
from ace.visuals import collect_for_plan, plan as plan_visuals
from ace.captions import plan as plan_captions


def create_auto(
    platform: str,
    content_type: str,
    topic: str,
    *,
    workspace: str | Path | None = None,
    account_slug: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    no_fallback: bool = False,
    allow_degraded: bool = False,
    output_mode: str = "both",
    preview: bool = False,
    instructions: str = "",
    variants: int | None = None,
    voice: bool = True,
    resources: bool = True,
    free_only: bool = False,
) -> ContentResult:
    slug = account_slug or active_slug(workspace)
    account = load_account(slug, workspace)
    variants = variants or int(account.get("automation", {}).get("candidates", 5))
    minimum = int(account.get("automation", {}).get("minimum_quality_score", 85))
    retries = int(account.get("automation", {}).get("maximum_retries", 2))
    folder = create_generation(platform, content_type, topic, account_slug=slug, workspace=workspace)
    print(f"ACE Autopilot 2.0 — {account['name']}")
    print("-" * 64)
    print(f"Platform: {platform}/{content_type}")
    print(f"Topic: {topic}")
    print(f"Candidates: {variants}; output: {output_mode}; cloud-first: yes")
    router = ProviderRouter(
        workspace,
        allow_degraded=allow_degraded,
        default_provider=provider,
        default_model=model,
        default_no_fallback=no_fallback,
        free_only=free_only,
    )

    sources = collect_research(folder, query=topic, workspace=workspace)
    print(f"✓ Research discovery: {len(sources)} source(s)")

    result = generate_content(
        platform,
        content_type,
        topic,
        instructions=instructions,
        variants=variants,
        account_slug=slug,
        workspace=workspace,
        router=router,
        provider=provider,
        model=model,
        no_fallback=no_fallback,
        existing_folder=folder,
    )
    print(f"✓ Script candidates and selection: {result.provider}/{result.model}")

    quality = run_quality(folder, workspace, router=router)
    for _ in range(retries):
        if quality.status in {"passed", "warning"} and quality.score >= minimum and not quality.critical:
            break
        problems = [*quality.critical, *quality.warnings, f"Quality score must reach {minimum}; current score is {quality.score}."]
        result = revise(result, problems, router)
        quality = run_quality(folder, workspace, router=router)
    if quality.critical or quality.score < minimum:
        raise RuntimeError("Autopilot stopped at the script quality gate: " + "; ".join([*quality.critical, *quality.warnings]))
    print(f"✓ Script quality: {quality.score}/100 ({quality.status})")

    extract_claims(folder, workspace, router=router)
    fact = verify_research(folder, workspace, router=router)
    if fact.status == "failed":
        raise RuntimeError("Autopilot stopped at the factual quality gate. Review unverified high-risk claims.")
    print(f"✓ Claim verification: {fact.status} ({fact.verified_count}/{fact.claim_count} verified)")

    evidence = build_evidence(folder, workspace)
    print(f"✓ Evidence package: {len(evidence)} item(s)")

    prepare_voice(folder, workspace)
    print("✓ TTS-safe narration script")
    if voice and content_type in {"short", "reel", "story", "video_script", "long_video"}:
        generate_voice(folder, workspace)
        print("✓ Narration with the account voice")

    plan_captions(folder, workspace)
    print("✓ Adaptive Caption Director")
    plan_visuals(folder, workspace)
    if resources:
        shots = collect_for_plan(folder, workspace)
    else:
        shots = plan_visuals(folder, workspace)
    print(f"✓ Semantic Visual Director: {len(shots)} shot(s)")

    create_package(folder, workspace)
    print("✓ Evidence-aware editing package")
    if output_mode in {"render", "both"}:
        output = render(folder, workspace, preview=preview)
        print(f"✓ Final render: {output}")
    status = inspect_status(folder, workspace)
    write_json(folder / "autopilot-report.json", {"mode": "auto", "overall": status["overall"], "missing": status["missing"], "output_mode": output_mode, "allow_degraded": allow_degraded, "free_only": free_only})
    print(f"\nACE result: {status['overall']}")
    print(folder)
    return result
