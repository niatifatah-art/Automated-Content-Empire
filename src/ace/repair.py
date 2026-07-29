from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.captions import plan as plan_captions
from ace.editing import create_package, render
from ace.evidence import build as build_evidence
from ace.quality import run as run_quality
from ace.research import collect as collect_research, extract_claims, verify as verify_research
from ace.status import inspect as inspect_status
from ace.storage import metadata, resolve_generation
from ace.voice import generate as generate_voice, prepare as prepare_voice
from ace.visuals import collect_for_plan, plan as plan_visuals


def fix(generation: str | Path, workspace: str | Path | None = None, *, preview: bool = False, allow_degraded: bool = False) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    status = inspect_status(folder, workspace)
    topic = str(metadata(folder).get("topic") or "")
    if not status["stages"]["research"]["ok"]:
        collect_research(folder, query=topic, workspace=workspace)
    if not (folder / "quality" / "script-report.json").exists():
        run_quality(folder, workspace)
    if not (folder / "research" / "claims.json").exists():
        extract_claims(folder, workspace)
    verify_research(folder, workspace)
    if not (folder / "evidence" / "evidence-plan.json").exists():
        build_evidence(folder, workspace)
    if not (folder / "script" / "tts-ready.txt").exists():
        prepare_voice(folder, workspace)
    if not (folder / "voice" / "narration.wav").exists():
        generate_voice(folder, workspace)
    plan_captions(folder, workspace)
    plan_visuals(folder, workspace)
    collect_for_plan(folder, workspace)
    create_package(folder, workspace)
    render(folder, workspace, preview=preview)
    return inspect_status(folder, workspace)
