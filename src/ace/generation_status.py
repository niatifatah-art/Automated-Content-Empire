from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ace.storage import resolve_generation, write_json


def _json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return value if isinstance(value, dict) else {}


def inspect_generation(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    metadata = _json(folder / "metadata.json")
    script_report = _json(folder / "quality" / "script-report.json")
    tts_report = _json(folder / "quality" / "tts-report.json")
    media_report = _json(folder / "quality" / "media-report.json")
    fact_report = _json(folder / "quality" / "fact-report.json")
    manifest = _json(folder / "licenses" / "manifest.json")
    stages = {
        "research": {"ok": bool((folder / "research" / "sources.json").exists()), "detail": "sources stored" if (folder / "research" / "sources.json").exists() else "not run"},
        "script_generation": {"ok": (folder / "selected.md").exists(), "detail": metadata.get("final_model", "missing")},
        "candidate_selection": {"ok": (folder / "evaluation.json").exists(), "detail": f"candidate {metadata.get('selected_candidate', '?')}"},
        "script_quality": {"ok": script_report.get("status") == "passed", "detail": f"{script_report.get('status', 'not run')} {script_report.get('score', '')}".strip()},
        "fact_verification": {"ok": fact_report.get("status") in {"passed", "warning"} and not fact_report.get("critical"), "detail": f"{fact_report.get('status', 'not run')} — {fact_report.get('source_count', 0)} source(s)"},
        "tts_preparation": {"ok": (folder / "script" / "tts-ready.txt").exists(), "detail": tts_report.get("status", "not run")},
        "narration": {"ok": (folder / "voice" / "narration.wav").exists(), "detail": "ready" if (folder / "voice" / "narration.wav").exists() else "missing"},
        "publishable_resources": {"ok": bool(manifest.get("publishable")) or bool(_json(folder / "editing" / "edit-plan.json").get("fallback_visuals")), "detail": f"{len(manifest.get('publishable', []))} external; branded fallback allowed"},
        "subtitles": {"ok": (folder / "subtitles" / "subtitles.srt").exists(), "detail": "ready" if (folder / "subtitles" / "subtitles.srt").exists() else "missing"},
        "editing_plan": {"ok": (folder / "editing" / "edit-plan.json").exists(), "detail": "ready" if (folder / "editing" / "edit-plan.json").exists() else "missing"},
        "final_render": {"ok": (folder / "exports" / "final.mp4").exists(), "detail": "exists" if (folder / "exports" / "final.mp4").exists() else "missing"},
        "final_validation": {"ok": media_report.get("status") == "passed", "detail": media_report.get("status", "not run")},
    }
    required = ["script_generation", "script_quality", "fact_verification"]
    content_type = str(metadata.get("content_type", ""))
    if content_type in {"short", "long_video", "reel", "story", "video_script"}:
        required += ["tts_preparation", "narration", "publishable_resources", "subtitles", "editing_plan", "final_render", "final_validation"]
    missing = [name for name in required if not stages[name]["ok"]]
    warnings: list[str] = []
    if not missing:
        if fact_report.get("status") == "warning":
            warnings.append("fact verification completed with warnings")
        if script_report.get("warnings"):
            warnings.append("script quality report contains warnings")
        if media_report.get("warnings"):
            warnings.append("media validation report contains warnings")
    if missing:
        overall = "INCOMPLETE"
    elif warnings:
        overall = "COMPLETE_WITH_WARNINGS"
    else:
        overall = "COMPLETE"
    report = {
        "folder": str(folder), "overall": overall, "required": required,
        "missing": missing, "warnings": warnings, "stages": stages,
    }
    write_json(folder / "status.json", report)
    return report


def print_generation_status(generation: str | Path, workspace: str | Path | None = None) -> bool:
    report = inspect_generation(generation, workspace)
    print(f"Generation: {Path(report['folder']).name}")
    print(f"Overall: {report['overall']}")
    print("-" * 72)
    for name, stage in report["stages"].items():
        print(f"{'✓' if stage['ok'] else '✗'} {name.replace('_', ' '):26} {stage['detail']}")
    if report["missing"]:
        print("\nMissing: " + ", ".join(item.replace("_", " ") for item in report["missing"]))
    if report.get("warnings"):
        print("\nWarnings: " + "; ".join(report["warnings"]))
    return report["overall"] in {"COMPLETE", "COMPLETE_WITH_WARNINGS"}
