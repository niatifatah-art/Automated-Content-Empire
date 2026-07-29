from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ace.ai import AIEngine
from ace.catalog import resolve_content_type
from ace.config import load as load_config
from ace.content import ContentResult, generate
from ace.editing import create_package, render
from ace.engines.voice import generate_voice
from ace.errors import ACEError, ConfigurationError
from ace.generation_status import inspect_generation
from ace.fact_check import run_fact_check
from ace.profile import active as active_account, load as load_account
from ace.quality import run_script_quality
from ace.research import collect_research
from ace.resources_engine import collect_for_generation
from ace.speech import prepare_tts_script
from ace.storage import write_json

VIDEO_TYPES = {"short", "long_video", "reel", "story", "video_script"}


def required_extras(platform: str, content_type: str, config: dict[str, Any]) -> list[str]:
    key = f"{platform}.{content_type}"
    return [str(item) for item in config.get("automation", {}).get("required_extras_by_type", {}).get(key, [])]


def _account_for_result(result: ContentResult, workspace: str | Path | None) -> dict[str, Any] | None:
    metadata = json.loads((result.folder / "metadata.json").read_text(encoding="utf-8"))
    slug = metadata.get("profile_slug")
    try:
        return load_account(str(slug), workspace) if slug and slug != "no-profile" else None
    except Exception:
        return None


def _revise_for_quality(result: ContentResult, problems: list[str], workspace: str | Path | None, engine: AIEngine | None = None) -> None:
    prompt = (
        "Revise this approved social-media script to fix the listed quality problems. Return only the finished script. "
        "Do not add headings, stage directions, quotation marks around the whole script, citations inside narration, "
        "or new factual claims.\n\nPROBLEMS:\n- " + "\n- ".join(problems) + "\n\nSCRIPT:\n" + result.path.read_text(encoding="utf-8")
    )
    if engine is None:
        with AIEngine.from_workspace(workspace) as owned:
            improved = owned.generate("review", prompt, temperature=0.2, max_output_tokens=4096)
    else:
        improved = engine.generate("review", prompt, temperature=0.2, max_output_tokens=4096)
    revisions = result.folder / "revisions"
    revisions.mkdir(exist_ok=True)
    current = result.path.read_text(encoding="utf-8")
    (revisions / f"v{len(list(revisions.glob('v*.md'))) + 1:03d}-before-quality-fix.md").write_text(current, encoding="utf-8")
    result.path.write_text(improved.text.strip() + "\n", encoding="utf-8")


def _generate_narration(result: ContentResult, workspace: str | Path | None) -> Path:
    metadata = json.loads((result.folder / "metadata.json").read_text(encoding="utf-8"))
    account = _account_for_result(result, workspace)
    voice = (account or {}).get("voice", {})
    language = str(metadata.get("language_code") or (account or {}).get("languages", {}).get("primary") or "en")
    override = voice.get("language_overrides", {}).get(language, {}) if voice else {}
    requested_provider = override.get("provider") or voice.get("provider")
    requested_model = override.get("voice_id") or voice.get("voice_id")
    if not voice.get("configured"):
        raise ConfigurationError("Account voice is not configured. Run 'ace voice audition'.")
    tts = result.folder / "script" / "tts-ready.txt"
    output = result.folder / "voice" / "narration.wav"
    path, actual_provider, actual_model = generate_voice(
        tts.read_text(encoding="utf-8"),
        output,
        workspace=workspace,
        provider=str(requested_provider),
        model=str(requested_model),
        language=language,
        instructions=str(voice.get("energy") or "natural"),
    )
    voice_report = {
        "requested": {"provider": requested_provider, "model": requested_model},
        "actual": {"provider": actual_provider, "model": actual_model},
        "match": actual_provider == requested_provider and actual_model == requested_model,
        "path": str(path),
    }
    write_json(result.folder / "quality" / "voice-report.json", voice_report)
    if not voice_report["match"]:
        raise ConfigurationError(
            f"Voice mismatch: requested {requested_provider}/{requested_model}, got {actual_provider}/{actual_model}."
        )
    return path


def create_auto(
    platform: str,
    content_type: str,
    topic: str,
    *,
    workspace: str | Path | None = None,
    profile_slug: str | None = None,
    language: str | None = None,
    provider: str | None = None,
    model: str | None = None,
    free_only: bool = False,
    output_mode: str = "both",
    preview: bool = False,
) -> ContentResult:
    config = load_config(workspace)
    account = load_account(profile_slug, workspace) if profile_slug else active_account(workspace)
    platform_key, type_key, _, _ = resolve_content_type(platform, content_type, workspace)
    auto = account.get("automation", {})
    variants = int(auto.get("candidates", config.get("automation", {}).get("candidates", 5)))
    extras = required_extras(platform_key, type_key, config)
    print(f"ACE Autopilot — {account['name']}")
    print("-" * 56)
    print(f"Platform: {platform_key}/{type_key}")
    print(f"Topic: {topic}")
    print(f"Candidates: {variants}; output: {output_mode}")

    with AIEngine.from_workspace(workspace) as engine:
        result = generate(
            platform_key,
            type_key,
            topic=topic,
            language=language,
            provider=provider,
            model=model,
            variants=variants,
            selection_mode="auto",
            review=True,
            extras=extras,
            ask_extras=False,
            interactive=False,
            profile_slug=str(account["slug"]),
            workspace=workspace,
            engine=engine,
        )
        print("✓ Script and supporting content")

        collect_research(result.folder, query=topic, workspace=workspace)
        print("✓ Research references stored")
        fact_report = run_fact_check(result.folder, workspace=workspace, use_ai=True, engine=engine)
        if fact_report.critical:
            raise ConfigurationError("Autopilot stopped at the factual quality gate: " + "; ".join(fact_report.critical))
        print(f"✓ Fact check: {fact_report.status} ({fact_report.source_count} source(s))")

        minimum = int(auto.get("minimum_quality_score", config.get("quality", {}).get("minimum_score", 85)))
        retries = int(auto.get("maximum_retries", config.get("automation", {}).get("maximum_retries", 3)))
        report = run_script_quality(result.folder, workspace=workspace, engine=engine)
        for _ in range(retries):
            if report.status == "passed" and report.score >= minimum:
                break
            problems = [*report.critical, *report.warnings, f"Quality score must reach {minimum}; current score is {report.score}."]
            try:
                _revise_for_quality(result, problems, workspace, engine)
            except ACEError:
                break
            report = run_script_quality(result.folder, workspace=workspace, engine=engine)
        if report.critical:
            raise ConfigurationError("Autopilot stopped at the script quality gate: " + "; ".join(report.critical))
        print(f"✓ Script quality {report.score}/100")

        prepare_tts_script(result.folder, workspace=workspace, use_ai=True, engine=engine)
        print("✓ TTS-ready script")

    if type_key in VIDEO_TYPES:
        _generate_narration(result, workspace)
        print("✓ Narration with the account voice")
        try:
            resources = collect_for_generation(result.folder, query=topic, profile_slug=str(account["slug"]), workspace=workspace)
        except Exception as exc:
            resources = []
            print(f"⚠ External resources unavailable: {exc}")
        print(f"✓ Visual route: {len(resources)} reusable asset(s); branded fallback available")
        create_package(result.folder, workspace=workspace)
        print("✓ Editing package and subtitles")
        if output_mode in {"render", "both"}:
            output = render(result.folder, workspace=workspace, preview=preview)
            print(f"✓ Final render: {output}")
    status = inspect_generation(result.folder, workspace)
    write_json(result.folder / "autopilot-report.json", {
        "mode": "auto", "overall": status["overall"], "missing": status["missing"],
        "free_only": free_only, "output_mode": output_mode,
    })
    print(f"\nACE result: {status['overall']}")
    print(result.folder)
    return result


def fix_generation(generation: str | Path, *, workspace: str | Path | None = None, preview: bool = False) -> dict[str, Any]:
    from ace.storage import resolve_generation

    folder = resolve_generation(generation, workspace)
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    account = load_account(str(metadata.get("profile_slug")), workspace)
    status = inspect_generation(folder, workspace)
    if not status["stages"]["research"]["ok"]:
        collect_research(folder, query=str(metadata.get("topic", "")), workspace=workspace)
    report = run_script_quality(folder, workspace=workspace)
    if report.critical:
        raise ConfigurationError("Cannot automatically repair critical script problems: " + "; ".join(report.critical))
    run_fact_check(folder, workspace=workspace, use_ai=True)
    if not status["stages"]["tts_preparation"]["ok"]:
        prepare_tts_script(folder, workspace=workspace)
    if not status["stages"]["narration"]["ok"]:
        fake_result = ContentResult(
            platform=str(metadata.get("platform")), content_type=str(metadata.get("content_type")), topic=str(metadata.get("topic")),
            text=(folder / "selected.md").read_text(encoding="utf-8"), path=folder / "selected.md", folder=folder,
            provider=str(metadata.get("final_provider", "")), model=str(metadata.get("final_model", "")), reviewed=bool(metadata.get("reviewed")),
        )
        _generate_narration(fake_result, workspace)
    try:
        collect_for_generation(folder, query=str(metadata.get("topic", "")), profile_slug=str(account["slug"]), workspace=workspace)
    except Exception:
        pass
    create_package(folder, workspace=workspace)
    render(folder, workspace=workspace, preview=preview)
    return inspect_generation(folder, workspace)
