#!/usr/bin/env python3
"""Render the ACE v2.1 browser/DNS Creative Editing regression.

The fixture uses no cloud credentials and no stock provider. It verifies that
browser, DNS, encryption and request/response ideas resolve to distinct original
visual languages, that a serious explainer receives no forced meme, and that the
finished video passes technical and creative validation.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ace.accounts import create as create_account
from ace.captions import plan as plan_captions
from ace.config import initialize
from ace.creative_quality import inspect as inspect_creative
from ace.editing import create_package, render, validate_media
from ace.status import inspect as inspect_status
from ace.storage import create_generation, update_metadata
from ace.utils import write_json
from ace.visuals import collect_for_plan, inspect as inspect_visuals, plan as plan_visuals
from ace.voice import create_test_tone, prepare as prepare_voice


SCRIPT = (
    "You type a URL and press Enter. "
    "First, the browser asks DNS to translate the domain name into an IP address. "
    "Then it opens a connection to the server and negotiates TLS, which protects the HTTPS traffic. "
    "The browser sends the request, the server returns the page files, and the screen finally renders the website. "
    "All of that can happen before your finger leaves the Enter key."
)


def run(workspace: Path, *, copy_output: Path | None = None) -> dict[str, object]:
    shutil.rmtree(workspace, ignore_errors=True)
    initialize(workspace, force=True)
    account = create_account(
        "Browser Creative Regression",
        description="Technology explained with modern visual storytelling",
        workspace=workspace,
    )
    folder = create_generation(
        "youtube",
        "short",
        "What really happens when you type a URL",
        account_slug=account["slug"],
        workspace=workspace,
    )
    (folder / "selected.md").write_text(SCRIPT + "\n", encoding="utf-8")
    update_metadata(
        folder,
        final_provider="fixture",
        final_model="fixture",
        selected_candidate=1,
        creative_style="technical_dynamic",
        media_mode="original",
        meme_mode="auto",
        quality_mode="best",
    )
    write_json(folder / "evaluation.json", {"selected": 1, "candidates": [{"index": 1, "score": 98}]})
    write_json(folder / "quality" / "script-report.json", {"status": "passed", "score": 98, "critical": [], "warnings": []})
    write_json(
        folder / "quality" / "fact-report.json",
        {"status": "passed", "source_count": 3, "claim_count": 5, "verified_count": 5, "warning_count": 0, "contradictions": [], "critical": []},
    )
    write_json(
        folder / "research" / "sources.json",
        [
            {"id": "dns", "title": "DNS overview", "url": "https://example.com/dns", "official": True},
            {"id": "tls", "title": "TLS overview", "url": "https://example.com/tls", "official": True},
            {"id": "http", "title": "HTTP overview", "url": "https://example.com/http", "official": True},
        ],
    )
    write_json(folder / "evidence" / "evidence-plan.json", {"items": []})
    prepare_voice(folder, workspace)
    create_test_tone(folder / "voice" / "narration.wav", duration=27.0)
    plan_captions(folder, workspace)
    plan_visuals(folder, workspace, cloud_intents=False)
    shots = collect_for_plan(
        folder,
        workspace,
        resource_finder=lambda *args, **kwargs: [],
        cloud_judge=False,
        animate_explainers=True,
        generate_cloud_images=False,
    )
    create_package(folder, workspace)
    output = render(folder, workspace, preview=False)
    visual = inspect_visuals(folder, workspace)
    creative = inspect_creative(folder, workspace)
    media = validate_media(output, generation=folder, workspace=workspace, expect_audio=True)
    status = inspect_status(folder, workspace)
    if copy_output:
        copy_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, copy_output)
    return {
        "folder": str(folder),
        "output": str(output),
        "copied_output": str(copy_output) if copy_output else None,
        "shot_count": len(shots),
        "formats": [shot.visual_type for shot in shots],
        "visual": visual,
        "creative": creative,
        "media": media,
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/ace-browser-creative-regression"))
    parser.add_argument("--copy-output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run(
        args.workspace.expanduser().resolve(),
        copy_output=args.copy_output.expanduser().resolve() if args.copy_output else None,
    )
    if args.report:
        args.report.expanduser().resolve().write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {
        "output": result["output"],
        "copied_output": result["copied_output"],
        "shot_count": result["shot_count"],
        "formats": result["formats"],
        "visual_status": result["visual"].get("status"),
        "creative_status": result["creative"].get("status"),
        "creative_score": result["creative"].get("score"),
        "meme_count": result["creative"].get("meme_count"),
        "media_status": result["media"].get("status"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["visual_status"] == summary["creative_status"] == summary["media_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
