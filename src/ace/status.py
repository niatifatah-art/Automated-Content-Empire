from __future__ import annotations

from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.storage import resolve_generation
from ace.utils import read_json, write_json


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    config = load_config(workspace)
    minimum = int(config.get("execution", {}).get("minimum_quality_score", 85))
    metadata = read_json(folder / "metadata.json", {}) or {}
    script = read_json(folder / "quality" / "script-report.json", {}) or {}
    fact = read_json(folder / "quality" / "fact-report.json", {}) or {}
    media = read_json(folder / "quality" / "media-report.json", {}) or {}
    captions = read_json(folder / "quality" / "caption-report.json", {}) or {}
    visuals = read_json(folder / "quality" / "visual-report.json", {}) or {}
    manifest = read_json(folder / "licenses" / "manifest.json", {}) or {}
    sources = read_json(folder / "research" / "sources.json", []) or []
    script_ok = (
        script.get("status") in {"passed", "warning"}
        and not script.get("critical")
        and int(script.get("score", 0)) >= minimum
    )
    fact_ok = fact.get("status") in {"passed", "warning"} and not fact.get("critical")
    media_ok = media.get("status") in {"passed", "warning"} and not media.get("problems")
    stages = {
        "research": {"ok": (folder / "research" / "sources.json").exists(), "detail": f"{len(sources) if isinstance(sources, list) else fact.get('source_count', 0)} source(s)"},
        "script_generation": {"ok": (folder / "selected.md").exists(), "detail": str(metadata.get("final_model", "missing"))},
        "candidate_selection": {"ok": (folder / "evaluation.json").exists(), "detail": f"candidate {metadata.get('selected_candidate', '?')}"},
        "script_quality": {"ok": script_ok, "detail": f"{script.get('status', 'not run')} {script.get('score', '')}".strip()},
        "fact_verification": {"ok": fact_ok, "detail": f"{fact.get('status', 'not run')} — {fact.get('verified_count', 0)}/{fact.get('claim_count', 0)} claims"},
        "evidence": {"ok": (folder / "evidence" / "evidence-plan.json").exists(), "detail": "ready" if (folder / "evidence" / "evidence-plan.json").exists() else "not built"},
        "tts_preparation": {"ok": (folder / "script" / "tts-ready.txt").exists(), "detail": "ready" if (folder / "script" / "tts-ready.txt").exists() else "missing"},
        "narration": {"ok": (folder / "voice" / "narration.wav").exists(), "detail": "ready" if (folder / "voice" / "narration.wav").exists() else "missing"},
        "visual_plan": {"ok": (folder / "visuals" / "shot-plan.json").exists() and visuals.get("status") in {"passed", "warning"} and int(visuals.get("shot_count", 0)) > 0 and not visuals.get("missing_visuals"), "detail": f"{visuals.get('shot_count', 0)} shots"},
        "captions": {"ok": (folder / "captions" / "styled-captions.ass").exists() and captions.get("status") in {"passed", "warning"} and int(captions.get("cue_count", 0)) > 0, "detail": f"{captions.get('visible_count', 0)} visible; {captions.get('hidden_count', 0)} clean moments"},
        "editing_plan": {"ok": (folder / "editing" / "edit-plan.json").exists(), "detail": "ready" if (folder / "editing" / "edit-plan.json").exists() else "missing"},
        "final_render": {"ok": (folder / "exports" / "final.mp4").exists(), "detail": "exists" if (folder / "exports" / "final.mp4").exists() else "missing"},
        "final_validation": {"ok": media_ok, "detail": media.get("status", "not run")},
    }
    content_type = str(metadata.get("content_type", ""))
    required = ["script_generation", "script_quality", "fact_verification"]
    if content_type in {"short", "long_video", "reel", "story", "video_script"}:
        required += ["tts_preparation", "narration", "visual_plan", "captions", "editing_plan", "final_render", "final_validation"]
    missing = [name for name in required if not stages[name]["ok"]]
    warnings: list[str] = []
    if script.get("status") == "warning":
        warnings.append("script quality passed the score gate with noncritical warnings")
    if fact.get("status") == "warning":
        warnings.append("fact verification completed with warnings")
    if media.get("status") == "warning":
        warnings.append("media validation completed with warnings")
    overall = "INCOMPLETE" if missing else "COMPLETE_WITH_WARNINGS" if warnings else "COMPLETE"
    report = {"folder": str(folder), "overall": overall, "required": required, "missing": missing, "warnings": warnings, "stages": stages}
    write_json(folder / "status.json", report)
    return report
