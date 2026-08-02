from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from ace.accounts import create as create_account
from ace.captions import inspect as inspect_captions, plan as plan_captions
from ace.config import initialize
from ace.editing import create_package, render, validate_media
from ace.evidence import build_article_cards
from ace.research import ClaimRecord
from ace.sources import SourceRecord, save_sources
from ace.status import inspect as inspect_status
from ace.storage import create_generation, update_metadata
from ace.utils import write_json
from ace.voice import create_test_tone, prepare as prepare_voice
from ace.visuals import collect_for_plan, inspect as inspect_visuals, plan as plan_visuals
from ace.visual_intelligence.benchmark import run as run_visual_benchmark


def run(suite: str = "quick", *, workspace: str | Path | None = None) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    with tempfile.TemporaryDirectory(prefix="ace-selftest-") as temp:
        home = Path(temp)
        initialize(home, force=True)
        account = create_account("Self Test", description="Technology explained clearly and playfully", workspace=home)
        folder = create_generation("youtube", "short", "Why passkeys are safer", account_slug=account["slug"], workspace=home)
        script = (
            "Passwords can be stolen by a fake login page. Passkeys change that by keeping the secret on your device. "
            "Your phone confirms you with Face ID or a fingerprint. The website receives proof, not your reusable password. "
            "That makes ordinary phishing much harder. Try passkeys on an account that supports them."
        )
        (folder / "selected.md").write_text(script + "\n", encoding="utf-8")
        update_metadata(folder, final_provider="selftest", final_model="fixture", selected_candidate=1)
        write_json(folder / "evaluation.json", {"selected": 1, "candidates": [{"index": 1, "score": 98}]})
        write_json(folder / "quality" / "script-report.json", {"status": "warning", "score": 98, "critical": [], "warnings": ["fixture warning"]})
        source = SourceRecord(
            id="official-passkeys",
            url="https://example.com/passkeys",
            title="Official passkey overview",
            publisher="Example Security",
            official=True,
            credibility="primary",
            credibility_score=0.95,
            description="Passkeys use device-bound credentials designed to resist phishing.",
        )
        save_sources(folder, [source], home)
        write_json(folder / "research" / "claims.json", [{"id": "c1", "text": "Passkeys resist phishing", "importance": "high", "factual_risk": "high", "source_ids": [source.id], "status": "verified", "confidence": 0.95, "visual_options": ["evidence_card"], "notes": []}])
        write_json(folder / "quality" / "fact-report.json", {"status": "warning", "source_count": 1, "claim_count": 1, "verified_count": 1, "warning_count": 1, "contradictions": [], "critical": []})
        build_article_cards(folder, home)
        prepare_voice(folder, home)
        create_test_tone(folder / "voice" / "narration.wav", duration=13.0)
        cues = plan_captions(folder, home)
        checks.append({"name": "caption_plan", "passed": bool(cues) and not any(item.overflow for item in cues), "detail": inspect_captions(folder, home)})
        benchmark = run_visual_benchmark()
        checks.append({"name": "visual_benchmark", "passed": benchmark.get("status") == "passed", "detail": {"average_score": benchmark.get("average_score"), "case_count": benchmark.get("case_count")}})
        plan_visuals(folder, home, cloud_intents=False)
        shots = collect_for_plan(
            folder,
            home,
            resource_finder=lambda *args, **kwargs: [],
            cloud_judge=False,
            animate_explainers=suite == "full",
        )
        visual_report = inspect_visuals(folder, home)
        checks.append({"name": "visual_intelligence", "passed": bool(shots) and not visual_report.get("missing_visuals") and visual_report.get("status") in {"passed", "warning"}, "detail": visual_report})
        create_package(folder, home)
        if suite in {"render", "full", "quick"}:
            full_render = suite == "full"
            output = render(folder, home, preview=not full_render)
            media = validate_media(output, generation=folder, workspace=home, expect_audio=True)
            checks.append({"name": "final_render" if full_render else "preview_render", "passed": media.get("status") in {"passed", "warning"}, "detail": media})
        if suite == "full":
            status = inspect_status(folder, home)
            checks.append({"name": "warning_completion_logic", "passed": status["overall"] == "COMPLETE_WITH_WARNINGS", "detail": status["overall"]})
        return {"suite": suite, "passed": all(item["passed"] for item in checks), "checks": checks}
