from __future__ import annotations

from pathlib import Path

from ace import __version__
from ace.accounts import active_slug, load as load_account
from ace.captions import plan as plan_captions
from ace.content import ContentResult, generate as generate_content, revise
from ace.creative_quality import inspect as inspect_creative
from ace.editing import create_package, render
from ace.evidence import build as build_evidence
from ace.providers import ProviderRouter
from ace.quality import run as run_quality
from ace.research import collect as collect_research, extract_claims, verify as verify_research
from ace.reference_style import analyze as analyze_reference
from ace.state import event as state_event, set_overall, stage as state_stage
from ace.status import inspect as inspect_status
from ace.storage import create_generation, update_metadata
from ace.utils import write_json
from ace.visuals import collect_for_plan, plan as plan_visuals
from ace.voice import generate as generate_voice, prepare as prepare_voice


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
    creative_style: str = "adaptive",
    media_mode: str = "auto",
    meme_mode: str = "auto",
    quality_mode: str = "balanced",
    reference_video: str | Path | None = None,
) -> ContentResult:
    slug = account_slug or active_slug(workspace)
    account = load_account(slug, workspace)
    variants = variants or int(account.get("automation", {}).get("candidates", 5))
    minimum = int(account.get("automation", {}).get("minimum_quality_score", 85))
    retries = int(account.get("automation", {}).get("maximum_retries", 2))
    folder = create_generation(platform, content_type, topic, account_slug=slug, workspace=workspace)
    reference_style = analyze_reference(reference_video) if reference_video else None
    update_metadata(
        folder,
        creative_style=creative_style,
        media_mode=media_mode,
        meme_mode=meme_mode,
        quality_mode=quality_mode,
        reference_style=reference_style,
    )
    set_overall(folder, "running", metadata={"mode": "auto", "output_mode": output_mode})
    state_event(folder, "generation_started", message=topic, metadata={"platform": platform, "content_type": content_type})
    print(f"ACE Autopilot {__version__} — {account['name']}")
    print("-" * 64)
    print(f"Platform: {platform}/{content_type}")
    print(f"Topic: {topic}")
    print(f"Candidates: {variants}; output: {output_mode}; cloud-first: yes")
    print(f"Creative: style={creative_style}; media={media_mode}; memes={meme_mode}; quality={quality_mode}")
    if reference_style:
        print(f"Reference pacing: {reference_style['pace']} ({reference_style['average_shot_seconds']}s average shot)")
    router = ProviderRouter(
        workspace,
        allow_degraded=allow_degraded,
        default_provider=provider,
        default_model=model,
        default_no_fallback=no_fallback,
        free_only=free_only,
    )

    try:
        with state_stage(folder, "research", detail="Discover and rank sources."):
            sources = collect_research(folder, query=topic, workspace=workspace)
        print(f"✓ Research discovery: {len(sources)} source(s)")

        with state_stage(folder, "script", detail="Generate, review and select script candidates."):
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

        with state_stage(folder, "script_quality", detail="Apply quality gate and revisions."):
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

        with state_stage(folder, "fact_check", detail="Map claims to sources and verify high-risk facts."):
            extract_claims(folder, workspace, router=router)
            fact = verify_research(folder, workspace, router=router)
            if fact.status == "failed":
                raise RuntimeError("Autopilot stopped at the factual quality gate. Review unverified high-risk claims.")
        print(f"✓ Claim verification: {fact.status} ({fact.verified_count}/{fact.claim_count} verified)")

        with state_stage(folder, "evidence", detail="Build article, social and official-source evidence visuals."):
            evidence = build_evidence(folder, workspace)
        print(f"✓ Evidence package: {len(evidence)} item(s)")

        with state_stage(folder, "narration", detail="Prepare and generate the account narration."):
            prepare_voice(folder, workspace)
            if voice and content_type in {"short", "reel", "story", "video_script", "long_video"}:
                generate_voice(folder, workspace)
        print("✓ TTS-safe narration and account voice")

        with state_stage(folder, "captions", detail="Direct adaptive captions independently from visual shots."):
            plan_captions(folder, workspace)
        print("✓ Adaptive Caption Director")

        with state_stage(folder, "visual_intelligence", detail="Plan intent, generate candidates, judge and select each visual."):
            plan_visuals(folder, workspace)
            if resources:
                shots = collect_for_plan(folder, workspace)
            else:
                shots = collect_for_plan(folder, workspace, resource_finder=lambda *args, **kwargs: [])
        print(f"✓ Visual Intelligence tournament: {len(shots)} shot(s)")

        with state_stage(folder, "creative_quality", detail="Check B-roll coverage, repetition, meme budget and editing rhythm."):
            creative = inspect_creative(folder, workspace)
            minimum_creative = {"quick": 52, "balanced": 64, "best": 72}.get(quality_mode, 64)
            if quality_mode == "best" and creative.get("score", 0) < minimum_creative:
                raise RuntimeError(
                    "Autopilot stopped at the creative quality gate: "
                    + "; ".join(creative.get("warnings") or [f"Creative score {creative.get('score')} is below {minimum_creative}."])
                )
        print(
            f"✓ Creative quality: {creative.get('score')}/100 "
            f"(B-roll {creative.get('live_broll_ratio', 0):.0%}, static {creative.get('static_card_ratio', 0):.0%})"
        )

        with state_stage(folder, "editing_package", detail="Build the evidence-aware editing package."):
            create_package(folder, workspace)
        print("✓ Evidence-aware editing package")

        if output_mode in {"render", "both"}:
            with state_stage(folder, "render", detail="Render and validate the final media."):
                output = render(folder, workspace, preview=preview)
            print(f"✓ Final render: {output}")
        status = inspect_status(folder, workspace)
        set_overall(folder, status["overall"], metadata={"missing": status["missing"]})
        write_json(
            folder / "autopilot-report.json",
            {
                "mode": "auto",
                "overall": status["overall"],
                "missing": status["missing"],
                "output_mode": output_mode,
                "allow_degraded": allow_degraded,
                "free_only": free_only,
                "visual_intelligence": True,
                "creative_style": creative_style,
                "media_mode": media_mode,
                "meme_mode": meme_mode,
                "quality_mode": quality_mode,
                "creative_quality": creative,
            },
        )
        state_event(folder, "generation_finished", status=status["overall"], message="Autopilot completed.")
        print(f"\nACE result: {status['overall']}")
        print(folder)
        return result
    except Exception as exc:
        set_overall(folder, "failed", metadata={"error": str(exc)})
        state_event(folder, "generation_failed", status="failed", message=str(exc))
        raise
