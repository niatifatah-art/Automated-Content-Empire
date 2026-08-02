from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from pprint import pformat
from typing import Any

import yaml

from ace import __version__
from ace import accounts
from ace.autopilot import create_auto
from ace.captions import inspect as inspect_captions, plan as plan_captions
from ace.config import get as config_get, initialize, load as load_config, save as save_config, set_value
from ace.creative import edit_directive
from ace.creative_quality import inspect as inspect_creative
from ace.diagnostics import check as run_check, quota_status
from ace.editing import create_package, inspect as inspect_editing, render
from ace.evidence import build as build_evidence, capture_official_page
from ace.image_generation import generate as generate_image
from ace.memes import generate as generate_meme, search as search_memes, template_fit
from ace.models import ALIASES, routes as model_routes, test as test_model, use as use_model
from ace.paths import resolve_paths
from ace.providers.router import ProviderRouter
from ace.publish import approve as approve_publish, prepare as prepare_publish, schedule as schedule_publish
from ace.repair import fix as fix_generation
from ace.research import collect as collect_research, verify as verify_research
from ace.resources import collect as collect_resources, find as find_resources, list_collected
from ace.selftest import run as run_selftest
from ace.secrets import ensure_permissions, load as load_secrets
from ace.sources import add_post, add_url, inspect_url, load_sources
from ace.status import inspect as inspect_status
from ace.storage import generations, metadata, resolve_generation, update_metadata
from ace.state import approve as approve_state, event as state_event, summary as state_summary
from ace.utils import nested_get, read_json, write_json
from ace.visuals import choose_mood, collect_for_plan, inspect as inspect_visuals, plan as plan_visuals
from ace.visual_intelligence.benchmark import run as run_visual_benchmark
from ace.visual_intelligence.contracts import ShotIntent
from ace.visual_intelligence.tournament import (
    approve_decision as approve_visual_decision,
    explain as explain_visuals,
    load_candidates as load_visual_candidates,
    regenerate_shot as regenerate_visual_shot,
    replace as replace_visual,
)
from ace.voice import create_test_tone, generate as generate_voice, prepare as prepare_voice


def _workspace(args: Any) -> str | Path | None:
    return getattr(args, "workspace", None)


def _print_json(value: Any) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def _editor(path: Path) -> None:
    editor = os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vi")
    if not editor:
        print(path)
        return
    subprocess.run([editor, str(path)], check=False)


def _open(path: Path) -> None:
    opener = shutil.which("xdg-open") or shutil.which("open")
    if opener:
        subprocess.Popen([opener, str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    else:
        print(path)


def _normalize_platform(value: str) -> str:
    return {"tt": "tiktok", "ig": "instagram", "yt": "youtube"}.get(value, value)


_LOOK_ALIASES = {
    "tech": "technical_dynamic",
    "clean": "clean_documentary",
    "hype": "gaming_hype",
    "serious": "serious_technical",
    "fun": "playful_tech",
}


def _normalize_look(value: str | None) -> str | None:
    if value is None:
        return None
    return _LOOK_ALIASES.get(value, value)


def _print_status(report: dict[str, Any]) -> None:
    print(f"Generation: {Path(report['folder']).name}")
    print(f"Overall: {report['overall']}")
    print("-" * 78)
    for name, stage in report["stages"].items():
        print(f"{'✓' if stage['ok'] else '✗'} {name.replace('_', ' '):26} {stage['detail']}")
    if report.get("missing"):
        print("\nMissing: " + ", ".join(item.replace("_", " ") for item in report["missing"]))
    if report.get("warnings"):
        print("\nWarnings: " + "; ".join(report["warnings"]))


def _create(args: Any) -> int:
    topic = " ".join(args.topic).strip()
    mode = args.interaction_mode or "auto"
    if mode != "auto":
        print(f"ACE {mode} mode currently uses the same quality pipeline; interactive checkpoints are recorded in the generation package.")
    production = args.production_mode or "both"
    provider = args.provider
    result = create_auto(
        _normalize_platform(args.platform),
        args.content_type,
        topic,
        workspace=_workspace(args),
        account_slug=args.account_slug,
        provider=provider,
        model=args.model,
        no_fallback=args.no_fallback,
        allow_degraded=args.allow_degraded,
        output_mode=production,
        preview=args.preview,
        instructions=args.instructions,
        variants=args.variants,
        voice=args.voice,
        resources=args.resources == "auto",
        free_only=args.free_only,
    )
    return 0


def _simple_make(args: Any) -> int:
    variants = {"quick": 1, "balanced": 2, "best": 3}[args.quality]
    return_code = create_auto(
        args.platform,
        args.content_type,
        " ".join(args.topic).strip(),
        workspace=_workspace(args),
        account_slug=args.account_slug,
        provider=args.provider,
        model=args.model,
        no_fallback=args.no_fallback,
        allow_degraded=args.allow_degraded,
        output_mode=args.production_mode or "both",
        preview=args.preview,
        instructions=args.instructions,
        variants=variants,
        voice=args.voice,
        resources=args.media != "original",
        free_only=args.free_only,
        creative_style=_normalize_look(args.style) or "adaptive",
        media_mode="auto" if args.media == "mixed" else args.media,
        meme_mode=args.memes,
        quality_mode=args.quality,
        reference_video=args.reference,
    )
    return 0 if return_code else 1


def _review_report(generation: str, workspace: str | Path | None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    return {
        "generation": str(folder),
        "topic": metadata(folder).get("topic"),
        "status": inspect_status(folder, workspace),
        "visuals": inspect_visuals(folder, workspace),
        "captions": inspect_captions(folder, workspace),
        "editing": inspect_editing(folder, workspace),
        "creative": inspect_creative(folder, workspace),
        "state": state_summary(folder, event_limit=12),
        "final_video": str(folder / "exports" / "final.mp4") if (folder / "exports" / "final.mp4").exists() else None,
    }


def _print_review(report: dict[str, Any]) -> None:
    status = report["status"]
    visuals = report["visuals"]
    captions = report["captions"]
    editing = report["editing"]
    creative = report["creative"]
    print(f"ACE review — {report.get('topic') or Path(report['generation']).name}")
    print("-" * 72)
    print(f"Overall: {status.get('overall')}")
    print(f"Visuals: {visuals.get('status')} | shots={visuals.get('shot_count', 0)} | relevance={visuals.get('average_visual_relevance', 'n/a')}")
    print(f"Captions: {captions.get('status')} | overflow={captions.get('overflow_count', 0)}")
    print(f"Editing: {editing.get('status')} | duration={editing.get('duration', 'n/a')}s")
    print(f"Creative: {creative.get('status')} | score={creative.get('score')} | b-roll={creative.get('live_broll_ratio', 0):.0%} | static={creative.get('static_card_ratio', 0):.0%}")
    if creative.get("warnings"):
        print("Creative notes: " + "; ".join(creative["warnings"]))
    if status.get("warnings"):
        print("Warnings: " + "; ".join(status["warnings"]))
    if status.get("missing"):
        print("Missing: " + ", ".join(status["missing"]))
    print("Final: " + (report.get("final_video") or "not rendered"))


def _improve(args: Any, workspace: str | Path | None) -> int:
    generation = getattr(args, "generation", "last")
    folder = resolve_generation(generation, workspace)
    style = _normalize_look(getattr(args, "style", None))
    if style == "adaptive":
        info = metadata(folder)
        script_path = folder / "script" / "tts-ready.txt"
        if not script_path.exists():
            script_path = folder / "selected.md"
        script = script_path.read_text(encoding="utf-8") if script_path.exists() else ""
        style = choose_mood(str(info.get("topic") or ""), script)
    if style:
        update_metadata(folder, creative_style=style, editing_mood=style)
    shot_number = getattr(args, "shot", None) or getattr(args, "shot_pos", None)
    if shot_number:
        shot_id = f"shot-{shot_number:03d}"
        if style:
            rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
            for row in rows:
                current = str((row.get("metadata") or {}).get("shot_id") or f"shot-{int(row.get('index', 0)):03d}")
                if current != shot_id:
                    continue
                intent_row = dict((row.get("metadata") or {}).get("intent") or {})
                if intent_row:
                    intent = ShotIntent.from_dict(intent_row)
                    intent.mood = style
                    metadata_row = dict(row.get("metadata") or {})
                    metadata_row["creative"] = edit_directive(intent, int(row.get("index") or shot_number), style=style).to_dict()
                    metadata_row["intent"] = intent.to_dict()
                    row["metadata"] = metadata_row
                    row["mood"] = style
            write_json(folder / "visuals" / "shot-plan.json", rows)
        shot_id = f"shot-{shot_number:03d}"
        decision, _ = regenerate_visual_shot(
            folder,
            shot_id,
            workspace=workspace,
            cloud_judge=not args.no_cloud_judge,
            animate_explainers=not args.static,
        )
        state_event(folder, "visual_regenerated", stage="visual_intelligence", status=decision.status, message=decision.reason, metadata={"shot_id": shot_id})
    else:
        plan_visuals(folder, workspace, refresh_captions=False)
        collect_for_plan(folder, workspace, cloud_judge=not args.no_cloud_judge, animate_explainers=not args.static)
    create_package(folder, workspace)
    output = render(folder, workspace, preview=args.preview)
    print(output)
    return 0


def dispatch(args: Any) -> int:
    workspace = _workspace(args)
    command = args.command
    if not command:
        print(f"ACE {__version__}\nRun 'ace --help' or create your first project with:\n  ace make \"Your topic\"")
        return 0

    if command == "make":
        return _simple_make(args)

    if command in {"review", "score"}:
        report = _review_report(args.generation, workspace)
        _print_json(report) if args.json else _print_review(report)
        return 0

    if command in {"improve", "redo"}:
        return _improve(args, workspace)

    if command in {"play", "open"}:
        folder = resolve_generation(args.generation, workspace)
        output = folder / "exports" / ("preview.mp4" if args.preview else "final.mp4")
        if not output.exists():
            print(f"No {'preview' if args.preview else 'final'} video exists yet: {output}", file=sys.stderr)
            return 1
        _open(output)
        print(output)
        return 0

    if command in {"doctor", "checkup"}:
        report = run_check(workspace, live=args.live)
        print(f"ACE doctor: {report['status'].upper()}")
        for item in report["checks"]:
            print(f"{item['status'].upper():12} {item['name']:22} {item.get('detail')}")
        return 0 if report["status"] == "ready" else 1

    if command == "init":
        target_workspace = args.path or workspace
        paths = initialize(target_workspace, force=args.force, upgrade=args.upgrade)
        migrated = accounts.migrate_all(target_workspace) if args.upgrade else []
        print(f"ACE initialized at {paths.config_root}")
        if migrated:
            print("Upgraded account defaults: " + ", ".join(migrated))
        return 0

    if command == "new":
        name = args.name or input("Account name: ").strip() or "Creator"
        account = accounts.create(name, description=args.description, niche=args.niche, audience=args.audience, language=args.language, platforms=[item.strip() for item in args.platforms.split(",") if item.strip()], workspace=workspace)
        print(f"Created and activated account: {account['name']} ({account['slug']})")
        return 0

    if command == "account":
        if args.account_command == "list":
            for item in accounts.list_accounts(workspace): print(item)
        elif args.account_command == "show":
            print(yaml.safe_dump(accounts.load(args.name, workspace), sort_keys=False, allow_unicode=True))
        elif args.account_command == "use":
            print(f"Active account: {accounts.use(args.name, workspace)}")
        elif args.account_command == "edit":
            account = accounts.load(args.name, workspace)
            _editor(accounts.account_path(account["slug"], workspace))
        elif args.account_command == "check":
            account = accounts.load(args.name, workspace)
            problems = accounts.validate(account)
            print("READY" if not problems else "\n".join(f"- {item}" for item in problems))
        elif args.account_command == "upgrade":
            migrated = accounts.migrate_all(workspace)
            print("Accounts already current." if not migrated else "Upgraded: " + ", ".join(migrated))
        else:
            print("Use: ace account list|show|use|edit|check|upgrade")
        return 0

    if command == "create" or command in {"youtube", "tiktok", "instagram", "facebook", "x", "linkedin", "tt", "ig", "yt"}:
        if command != "create":
            args.platform = command
        return _create(args)

    if command in {"check", "ready"}:
        report = run_check(workspace, live=args.live)
        print(f"ACE readiness: {report['status'].upper()}")
        print("-" * 72)
        for item in report["checks"]:
            print(f"{item['status'].upper():12} {item['name']:22} {item.get('detail')}")
        return 0 if report["status"] == "ready" else 1

    if command == "status":
        _print_status(inspect_status(args.generation, workspace))
        return 0

    if command == "fix":
        _print_status(fix_generation(args.generation, workspace, preview=args.preview))
        return 0

    if command == "recent":
        recent = generations(workspace)
        if not recent:
            print("No generations yet.")
            return 1
        print(recent[0])
        if args.open:
            _open(recent[0])
        return 0

    if command == "models":
        if args.models_command == "routes":
            _print_json(model_routes(workspace))
        elif args.models_command == "use":
            provider, model = use_model(args.task, args.model, workspace)
            print(f"{args.task}: {provider}/{model}")
        elif args.models_command == "test":
            print(test_model(args.provider, args.model, workspace, allow_degraded=args.allow_degraded))
        elif args.models_command == "search":
            query = args.query.lower()
            for alias, route in ALIASES.items():
                if query in alias.lower() or query in "/".join(route).lower():
                    print(f"{alias:18} {route[0]}/{route[1]}")
        elif args.models_command == "ready":
            _print_json(ProviderRouter(workspace).credential_status())
        else:
            print("Use: ace models routes|use|test|search|ready")
        return 0

    if command == "credentials":
        router = ProviderRouter(workspace)
        if args.credentials_command == "test":
            result = router.generate("classification", "Reply with exactly: ACE credential test passed", provider=args.provider, model=args.model, temperature=0.0, max_output_tokens=512, no_fallback=True)
            print(f"{result.provider}/{result.model}/{result.credential_name}: {result.text}")
        else:
            _print_json(router.credential_status())
        return 0

    if command == "quota":
        _print_json(quota_status(workspace))
        return 0

    if command == "secrets":
        paths = resolve_paths(workspace)
        if args.secrets_command == "path": print(paths.secrets_file)
        elif args.secrets_command == "edit":
            ensure_permissions(workspace); _editor(paths.secrets_file); ensure_permissions(workspace)
        else:
            names = ["GEMINI_API_KEY_PRIMARY", "GEMINI_API_KEY_BACKUP", "GEMINI_API_KEY", "PEXELS_API_KEY", "PIXABAY_API_KEY", "OPENVERSE_ACCESS_TOKEN", "OPENAI_API_KEY", "GIPHY_API_KEY", "TENOR_API_KEY"]
            values = load_secrets(workspace)
            legacy_primary = bool(values.get("GEMINI_API_KEY")) and not bool(values.get("GEMINI_API_KEY_PRIMARY"))
            for name in names:
                status = "READY" if values.get(name) else "missing"
                note = " (legacy key is currently used as primary)" if name == "GEMINI_API_KEY_PRIMARY" and legacy_primary else ""
                print(f"{name:30} {status}{note}")
        return 0

    if command == "settings":
        path = resolve_paths(workspace).config_file
        if args.edit: _editor(path)
        else: print(path.read_text(encoding="utf-8"))
        return 0

    if command == "config":
        path = resolve_paths(workspace).config_file
        if args.config_command == "show": print(path.read_text(encoding="utf-8"))
        elif args.config_command == "path": print(path)
        elif args.config_command == "get": _print_json(config_get(args.key, workspace))
        elif args.config_command == "set": print(f"{args.key} = {set_value(args.key, args.value, workspace)!r}")
        else: print("Use: ace config show|path|get|set")
        return 0

    if command == "research":
        if args.research_command == "collect":
            rows = collect_research(args.generation, query=getattr(args, "query", None), workspace=workspace); _print_json([item.__dict__ for item in rows])
        elif args.research_command == "verify": _print_json(verify_research(args.generation, workspace).__dict__)
        elif args.research_command == "show":
            folder = resolve_generation(args.generation, workspace); _print_json({"sources": read_json(folder / "research" / "sources.json", []), "claims": read_json(folder / "research" / "claims.json", []), "contradictions": read_json(folder / "research" / "contradictions.json", [])})
        return 0

    if command == "sources":
        if args.sources_command == "add": _print_json(add_url(args.generation, args.url, workspace).__dict__)
        elif args.sources_command == "add-post": _print_json(add_post(args.generation, args.url, workspace).__dict__)
        elif args.sources_command == "list": _print_json([item.__dict__ for item in load_sources(args.generation, workspace)])
        elif args.sources_command == "inspect": _print_json(inspect_url(args.url, workspace).__dict__)
        return 0

    if command == "evidence":
        if args.evidence_command == "build": _print_json([item.__dict__ for item in build_evidence(args.generation, workspace)])
        elif args.evidence_command == "capture": _print_json(capture_official_page(args.generation, args.url, workspace, approved=args.approve).__dict__)
        elif args.evidence_command == "list":
            folder = resolve_generation(args.generation, workspace); _print_json(read_json(folder / "evidence" / "evidence-plan.json", []))
        return 0

    if command == "resources":
        if args.resources_command == "find":
            folder = resolve_generation(args.generation, workspace)
            query = args.query or str(metadata(folder).get("topic") or folder.name)
            rows = collect_resources(folder, query=query, media_type=args.type, workspace=workspace, limit=args.limit) if args.download else find_resources(query, media_type=args.type, workspace=workspace, limit=args.limit)
            _print_json([item.__dict__ for item in rows])
        elif args.resources_command == "list": _print_json([item.__dict__ for item in list_collected(args.generation, workspace)])
        return 0

    if command == "memes":
        if args.memes_command == "search": _print_json([item.__dict__ for item in search_memes(args.query, workspace, limit=args.limit)])
        elif args.memes_command == "generate": _print_json(generate_meme(args.generation, setup=args.setup, punchline=args.punchline, workspace=workspace).__dict__)
        elif args.memes_command == "fit": _print_json(template_fit(args.topic, args.mood))
        return 0

    if command == "images":
        if args.images_command == "generate": _print_json(generate_image(args.generation, " ".join(args.prompt), workspace, provider=args.provider, model=args.model, aspect_ratio=args.aspect_ratio).__dict__)
        return 0

    if command == "visuals":
        if args.visuals_command == "plan":
            _print_json([item.__dict__ for item in plan_visuals(args.generation, workspace)])
        elif args.visuals_command == "collect":
            _print_json([item.__dict__ for item in collect_for_plan(args.generation, workspace)])
        elif args.visuals_command == "inspect":
            _print_json(inspect_visuals(args.generation, workspace))
        elif args.visuals_command == "show":
            folder = resolve_generation(args.generation, workspace); _print_json(read_json(folder / "visuals" / "shot-plan.json", []))
        elif args.visuals_command == "explain":
            folder = resolve_generation(args.generation, workspace)
            shot_id = f"shot-{args.shot:03d}" if args.shot else None
            _print_json(explain_visuals(folder, shot_id))
        elif args.visuals_command == "candidates":
            folder = resolve_generation(args.generation, workspace)
            shot_id = f"shot-{args.shot:03d}"
            candidates, scores = load_visual_candidates(folder, shot_id)
            score_map = {item.candidate_id: item.to_dict() for item in scores}
            _print_json({"shot_id": shot_id, "candidates": [{"candidate": item.to_dict(), "score": score_map.get(item.candidate_id)} for item in candidates]})
        elif args.visuals_command == "regenerate":
            folder = resolve_generation(args.generation, workspace)
            shot_id = f"shot-{args.shot:03d}"
            decision, shot = regenerate_visual_shot(
                folder, shot_id, workspace=workspace, cloud_judge=not args.no_cloud_judge, animate_explainers=not args.static
            )
            state_event(folder, "visual_regenerated", stage="visual_intelligence", status=decision.status, message=decision.reason, metadata={"shot_id": shot_id})
            _print_json({"decision": decision.to_dict(), "shot": shot})
        elif args.visuals_command == "replace":
            folder = resolve_generation(args.generation, workspace)
            shot_id = f"shot-{args.shot:03d}"
            decision = replace_visual(folder, shot_id, args.candidate, approved=args.approve)
            state_event(folder, "visual_replaced", stage="visual_intelligence", status=decision.status, message=decision.reason, metadata={"shot_id": shot_id, "candidate_id": args.candidate})
            _print_json(decision.to_dict())
        elif args.visuals_command == "approve":
            folder = resolve_generation(args.generation, workspace)
            shot_id = f"shot-{args.shot:03d}"
            decision = approve_visual_decision(folder, shot_id)
            approve_state(folder, "visual_intelligence", subject_id=shot_id, metadata={"candidate_id": decision.selected_candidate_id})
            _print_json(decision.to_dict())
        elif args.visuals_command == "benchmark":
            report = run_visual_benchmark(args.fixtures)
            _print_json(report)
            return 0 if report["status"] == "passed" else 1
        else:
            print("Use: ace visuals plan|collect|show|inspect|explain|candidates|regenerate|replace|approve|benchmark")
        return 0

    if command == "captions":
        if args.captions_command == "plan": _print_json([item.__dict__ for item in plan_captions(args.generation, workspace)])
        elif args.captions_command == "inspect": _print_json(inspect_captions(args.generation, workspace))
        elif args.captions_command == "preview": print(render(args.generation, workspace, preview=True))
        return 0

    if command == "edit":
        if args.edit_command == "styles": _print_json(load_config(workspace).get("editing", {}).get("styles", {}))
        elif args.edit_command == "style" and args.style_command == "set":
            config = load_config(workspace); styles = config.get("editing", {}).get("styles", {})
            if args.name not in styles and args.name != "adaptive": raise ValueError(f"Unknown style: {args.name}")
            config.setdefault("editing", {})["default_style"] = args.name; save_config(config, workspace); print(f"Editing style: {args.name}")
        elif args.edit_command == "package": print(create_package(args.generation, workspace).plan)
        elif args.edit_command == "render": print(render(args.generation, workspace))
        elif args.edit_command == "preview": print(render(args.generation, workspace, preview=True))
        elif args.edit_command == "inspect": _print_json(inspect_editing(args.generation, workspace))
        elif args.edit_command == "rerender":
            if args.style:
                config = load_config(workspace); config.setdefault("editing", {})["default_style"] = args.style; save_config(config, workspace)
            plan_captions(args.generation, workspace); plan_visuals(args.generation, workspace); print(render(args.generation, workspace))
        elif args.edit_command == "captions" and args.edit_captions_command == "preview": print(render(args.generation, workspace, preview=True))
        return 0

    if command == "rerun":
        folder = resolve_generation(args.generation, workspace)
        state_event(folder, "rerun_started", stage=args.rerun_from, status="running", message=f"Restarting from {args.rerun_from}.")
        if args.rerun_from == "captions":
            plan_captions(folder, workspace)
            plan_visuals(folder, workspace)
            collect_for_plan(folder, workspace, cloud_judge=not args.no_cloud_judge)
            create_package(folder, workspace)
        elif args.rerun_from == "visual-plan":
            plan_visuals(folder, workspace)
            collect_for_plan(folder, workspace, cloud_judge=not args.no_cloud_judge)
            create_package(folder, workspace)
        elif args.rerun_from == "editing":
            create_package(folder, workspace)
        output = render(folder, workspace, preview=args.preview)
        state_event(folder, "rerun_finished", stage=args.rerun_from, status="passed", message=str(output))
        print(output)
        return 0

    if command == "state":
        folder = resolve_generation(args.generation, workspace)
        report = state_summary(folder, event_limit=getattr(args, "limit", 50))
        if args.state_command == "events":
            _print_json({"generation": report.get("generation"), "events": report.get("events", [])})
        else:
            _print_json(report)
        return 0

    if command == "voice":
        if args.voice_command == "prepare": print(prepare_voice(args.generation, workspace))
        elif args.voice_command == "generate": print(generate_voice(args.generation, workspace))
        elif args.voice_command == "status":
            folder = resolve_generation(args.generation, workspace); _print_json(read_json(folder / "quality" / "voice-report.json", {"status": "not run"}))
        elif args.voice_command == "test": print(create_test_tone(args.output or "/tmp/ace-voice-test.wav"))
        return 0

    if command == "assets":
        root = accounts.asset_dir(workspace=workspace)
        if args.assets_command == "add":
            source = Path(args.path).expanduser().resolve()
            if not source.exists(): raise FileNotFoundError(source)
            target = root / source.name; shutil.copy2(source, target)
            if args.tags: (target.with_suffix(target.suffix + ".tags")).write_text(args.tags + "\n", encoding="utf-8")
            print(target)
        elif args.assets_command == "list":
            for item in sorted(root.rglob("*")):
                if item.is_file(): print(item)
        return 0

    if command == "publish":
        if args.publish_command == "prepare": _print_json(prepare_publish(args.generation, workspace))
        elif args.publish_command == "approve": _print_json(approve_publish(args.generation, workspace))
        elif args.publish_command == "schedule": _print_json(schedule_publish(args.generation, args.when, workspace))
        elif args.publish_command == "status":
            folder = resolve_generation(args.generation, workspace); _print_json(read_json(folder / "publishing" / "publish-plan.json", {"status": "not prepared"}))
        return 0

    if command == "test":
        report = run_selftest(args.suite, workspace=workspace)
        _print_json(report)
        return 0 if report["passed"] else 1

    if command == "release":
        report = run_selftest("full", workspace=workspace)
        report["version"] = __version__
        report["release_ready"] = report["passed"]
        _print_json(report)
        return 0 if report["passed"] else 1

    if command == "guide":
        topic = " ".join(args.topic).lower()
        print("ACE guided setup\n" + "-" * 40)
        print("1. ace init --upgrade")
        print("2. ace secrets edit  # add Gemini primary/backup, Pexels, Pixabay")
        print("3. ace credentials test")
        print("4. ace check --live")
        print("5. ace create youtube short \"Your topic\" --auto --both")
        print("6. ace edit inspect last")
        print("7. ace status last")
        if "caption" in topic: print("Repair captions with: ace captions plan last && ace edit rerender last")
        if "resource" in topic: print("Inspect media with: ace resources find last --query \"...\" --download")
        return 0

    print(f"Unknown or incomplete command: {command}", file=sys.stderr)
    return 2
