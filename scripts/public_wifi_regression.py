#!/usr/bin/env python3
"""Render the ACE v2.0.2 public-Wi-Fi Visual Intelligence regression.

This fixture deliberately provides no stock resources and no cloud credentials.
It proves that ACE can rebuild a meaningful seven-shot visual route from a fixed
script and narration using its original explainers and demonstrations.
"""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from ace.accounts import create as create_account
from ace.captions import plan as plan_captions
from ace.config import initialize
from ace.editing import create_package, render, validate_media
from ace.status import inspect as inspect_status
from ace.storage import create_generation, update_metadata
from ace.utils import write_json
from ace.visuals import collect_for_plan, inspect as inspect_visuals, plan as plan_visuals
from ace.voice import create_test_tone, prepare as prepare_voice


SCRIPT = (
    "Public Wi-Fi is convenient, but every device shares the same access point. "
    "If the network lacks encryption, exposed data packets can be easier to inspect. "
    "Modern HTTPS protects browser traffic by encrypting it in transit. "
    "But a rogue hotspot can copy the name of a trusted network and route your connection through a fake access point. "
    "A VPN adds an encrypted tunnel between your device and its server. "
    "For sensitive work, use your phone's personal hotspot instead. "
    "And always verify the network name before connecting."
)


def run(workspace: Path, *, copy_output: Path | None = None) -> dict[str, object]:
    shutil.rmtree(workspace, ignore_errors=True)
    initialize(workspace, force=True)
    account = create_account(
        "Fatah Visual Regression",
        description="Young adult technology creator with adaptive humor and serious cybersecurity explanations",
        workspace=workspace,
    )
    folder = create_generation(
        "youtube",
        "short",
        "Why public Wi-Fi can expose your data",
        account_slug=account["slug"],
        workspace=workspace,
    )
    (folder / "selected.md").write_text(SCRIPT + "\n", encoding="utf-8")
    update_metadata(folder, final_provider="fixture", final_model="fixture", selected_candidate=1)
    write_json(folder / "evaluation.json", {"selected": 1, "candidates": [{"index": 1, "score": 98}]})
    write_json(folder / "quality" / "script-report.json", {"status": "passed", "score": 98, "critical": [], "warnings": []})
    write_json(
        folder / "quality" / "fact-report.json",
        {
            "status": "passed",
            "source_count": 3,
            "claim_count": 5,
            "verified_count": 5,
            "warning_count": 0,
            "contradictions": [],
            "critical": [],
        },
    )
    write_json(
        folder / "research" / "sources.json",
        [
            {"id": "s1", "title": "Browser HTTPS documentation", "url": "https://example.com/https", "official": True},
            {"id": "s2", "title": "Public Wi-Fi guidance", "url": "https://example.com/wifi", "official": True},
            {"id": "s3", "title": "VPN guidance", "url": "https://example.com/vpn", "official": True},
        ],
    )
    write_json(folder / "evidence" / "evidence-plan.json", [])
    prepare_voice(folder, workspace)
    create_test_tone(folder / "voice" / "narration.wav", duration=28.0)
    plan_captions(folder, workspace)
    plan_visuals(folder, workspace, cloud_intents=False)
    shots = collect_for_plan(
        folder,
        workspace,
        resource_finder=lambda *args, **kwargs: [],
        cloud_judge=False,
        animate_explainers=True,
    )
    create_package(folder, workspace)
    output = render(folder, workspace, preview=False)
    media = validate_media(output, generation=folder, workspace=workspace, expect_audio=True)
    visual = inspect_visuals(folder, workspace)
    status = inspect_status(folder, workspace)
    if copy_output:
        copy_output.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(output, copy_output)
    return {
        "folder": str(folder),
        "output": str(output),
        "copied_output": str(copy_output) if copy_output else None,
        "shot_count": len(shots),
        "visual": visual,
        "media": media,
        "status": status,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/tmp/ace-public-wifi-regression"))
    parser.add_argument("--copy-output", type=Path)
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    result = run(args.workspace.expanduser().resolve(), copy_output=args.copy_output.expanduser().resolve() if args.copy_output else None)
    if args.report:
        args.report.expanduser().resolve().write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    summary = {
        "folder": result["folder"],
        "output": result["output"],
        "copied_output": result["copied_output"],
        "shot_count": result["shot_count"],
        "visual_status": result["visual"].get("status"),
        "average_relevance": result["visual"].get("average_visual_relevance"),
        "generic_filler_ratio": result["visual"].get("generic_filler_ratio"),
        "media_status": result["media"].get("status"),
        "completion": result["status"].get("overall"),
    }
    print(json.dumps(summary, indent=2))
    return 0 if summary["visual_status"] == "passed" and summary["media_status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
