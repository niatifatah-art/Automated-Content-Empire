from __future__ import annotations

import json
import importlib.util
import os
import shutil
import subprocess
import sys
import textwrap

from pathlib import Path
from typing import Any

from ace import assets as asset_library
from ace.ai import AIEngine
from ace.account_context import ensure_task_context
from ace.account_memory import similar_topics
from ace.autopilot import create_auto, fix_generation
from ace.catalog import content_types, load_catalog, resolve_platform
from ace.config import default_config, get_value, initialize, load, parse_cli_value, save, set_value, show, upgrade
from ace.content import available_extras, generate, generate_pack, localize
from ace.doctor import run as doctor_run
from ace.editing import create_package, render
from ace.generation_status import print_generation_status
from ace.guide import run_guide
from ace.engines.voice import audition_voice, available_voice_models, available_voice_providers, generate_voice
from ace.errors import ACEError, ConfigurationError
from ace.memory import MemoryManager, status as memory_status
from ace.models import aliases as model_aliases
from ace.models import (
    catalog_models, discover as discover_models, edit_catalog, installed_models,
    model_readiness, recommend_models, resolve_alias, search_models,
)
from ace.paths import config_home, config_path, data_home, model_catalog_path, secrets_path
from ace.readiness import print_readiness
from ace.profile import active as active_profile
from ace.profile import build_from_description, history as account_history, profile_path, rollback as account_rollback
from ace.profile import active_slug, create as create_profile
from ace.profile import edit as edit_profile
from ace.profile import list_profiles, load as load_profile, save as save_profile
from ace.profile import use as use_profile
from ace.profile import validate as validate_profile
from ace.profile import wizard as profile_wizard
from ace.project import create as create_project
from ace.project import list_projects, status as project_status
from ace.providers import supported_provider_types
from ace.resources_engine import collect_for_generation
from ace.secrets import edit as edit_secrets
from ace.secrets import masked_status
from ace.speech import prepare_tts_script
from ace.storage import cleanup as storage_cleanup
from ace.storage import last_generation, preserve, resolve_generation, usage
from ace.workflow import run as workflow_run
from ace.yaml_compat import dump_data
from ace.selftest import run_selftest


def _workspace(args) -> str | Path | None:
    return getattr(args, "workspace", None)


def _topic(args) -> str:
    return " ".join(args.topic).strip()


def _language(args) -> str | None:
    return getattr(args, "language_shortcut", None) or getattr(args, "language", None)


def _model_override(args, workspace: str | Path | None) -> tuple[str | None, str | None]:
    provider = getattr(args, "provider", None)
    model = getattr(args, "model", None)
    if model and not provider:
        alias = resolve_alias(model, workspace)
        if alias:
            return alias
    return provider, model


def _content_kwargs(args) -> dict[str, Any]:
    workspace = _workspace(args)
    provider, model = _model_override(args, workspace)
    extras = None
    if getattr(args, "extras", None):
        extras = [item.strip() for item in args.extras.split(",") if item.strip()]
    return {
        "language": _language(args),
        "audience": getattr(args, "audience", None),
        "tone": getattr(args, "tone", None),
        "extra_instructions": getattr(args, "instructions", "None."),
        "provider": provider,
        "model": model,
        "no_fallback": getattr(args, "no_fallback", False),
        "review": getattr(args, "review", None),
        "variants": getattr(args, "variants", None),
        "selection_mode": getattr(args, "selection_mode", None),
        "extras": extras,
        "interactive": sys.stdin.isatty() and not getattr(args, "non_interactive", False),
        "profile_slug": getattr(args, "profile_slug", None),
        "no_profile": getattr(args, "no_profile", False),
        "workspace": workspace,
    }


def _show_routes(config: dict[str, Any], task: str | None = None) -> None:
    routes = config.get("routes", {})
    selected = {task: routes.get(task)} if task else routes
    for route_task, route in selected.items():
        if not route:
            print(f"{route_task}: not configured")
            continue
        chain = " -> ".join(
            f"{item.get('provider')}/{item.get('model')}"
            for item in route
            if isinstance(item, dict)
        )
        print(f"{route_task}: {chain}")


def _provider_defaults(provider_type: str) -> dict[str, Any]:
    defaults: dict[str, dict[str, Any]] = {
        "ollama": {"base_url": "http://127.0.0.1:11434", "timeout_seconds": 600, "paid": False},
        "gemini": {"base_url": "https://generativelanguage.googleapis.com/v1beta", "api_key_env": "GEMINI_API_KEY", "requires_api_key": True, "timeout_seconds": 180, "paid": True},
        "anthropic": {"base_url": "https://api.anthropic.com/v1", "api_key_env": "ANTHROPIC_API_KEY", "requires_api_key": True, "timeout_seconds": 180, "paid": True},
        "openai_compatible": {"requires_api_key": False, "api_mode": "chat", "timeout_seconds": 180, "paid": False},
    }
    return dict(defaults.get(provider_type, {}))


def _home(workspace: str | Path | None, all_profiles: bool = False) -> int:
    config = load(workspace)
    profile_name = "None"
    slug = config.get("active_profile")
    if slug:
        try:
            profile_name = str(load_profile(str(slug), workspace).get("name", slug))
        except ACEError:
            profile_name = f"Missing ({slug})"
    route = config.get("routes", {}).get("script", [])
    route_text = " -> ".join(f"{item.get('provider')}/{item.get('model')}" for item in route if isinstance(item, dict))
    print("Automated Content Empire — ACE")
    print("ACE is ready")
    print("-" * 56)
    print(f"Active profile : {profile_name}")
    print(f"Model route    : {route_text or 'Not configured'}")
    print(f"Memory mode    : {config.get('memory', {}).get('mode', 'smart')}")
    print(f"Config         : {config_path(workspace)}")
    print(f"Data           : {data_home(workspace)}")
    if all_profiles:
        print("Mode           : all eligible profiles")
    print("\nStart with:")
    print("  ace new")
    print('  ace create tiktok short "Your topic"')
    print("  ace guide")
    print("  ace models ready")
    print("  ace --help")
    return 0


def _ask_production_mode(args, workspace: str | Path | None) -> str:
    explicit = getattr(args, "production_mode", None)
    if explicit:
        return explicit
    default = str(load(workspace).get("render", {}).get("default_mode", "package"))
    if not (sys.stdin.isatty() and not getattr(args, "non_interactive", False)):
        return default
    print("\nWhat should ACE produce?")
    print("  1. Editing package")
    print("  2. Final rendered media")
    print("  3. Both")
    print("  0. Content only")
    answer = input(f"Choose [default: {default}]: ").strip().lower()
    return {"1": "package", "2": "render", "3": "both", "0": "content", "": default}.get(answer, default)


def _voice_for_result(result, args, workspace: str | Path | None) -> Path | None:
    should_generate = bool(getattr(args, "voice", False))
    profile = None
    metadata: dict[str, Any] = {}
    try:
        metadata = json.loads((result.folder / "metadata.json").read_text(encoding="utf-8"))
        profile = load_profile(str(metadata.get("profile_slug")), workspace)
    except Exception:
        pass
    voice_config = (profile or {}).get("voice", {})
    if voice_config.get("configured"):
        should_generate = True
    if not should_generate:
        return None
    language_code = str(metadata.get("language_code") or "")
    language_route = voice_config.get("language_overrides", {}).get(language_code, {}) if voice_config.get("configured") else {}
    provider = language_route.get("provider") or (voice_config.get("provider") if voice_config.get("configured") else None)
    model = language_route.get("voice_id") or (voice_config.get("voice_id") if voice_config.get("configured") else None)
    tts_path = prepare_tts_script(result.folder, workspace=workspace, use_ai=True)
    output = result.folder / "voice" / "narration.wav"
    try:
        path, used_provider, used_model = generate_voice(
            tts_path.read_text(encoding="utf-8"),
            output,
            workspace=workspace,
            provider=provider,
            model=model,
            language=language_code or None,
            instructions=str(voice_config.get("energy") or "natural"),
        )
    except ACEError as exc:
        print(f"Voice skipped: {exc}")
        return None
    if provider and model and (used_provider != provider or used_model != model):
        raise ConfigurationError(
            f"Voice mismatch: requested {provider}/{model}, got {used_provider}/{used_model}."
        )
    print(f"Voice: {path} ({used_provider}/{used_model})")
    return path


def _production(result, args) -> None:
    workspace = _workspace(args)
    mode = _ask_production_mode(args, workspace)
    if mode == "content":
        return
    if getattr(args, "resources", "auto") == "auto":
        try:
            resources = collect_for_generation(result.folder, workspace=workspace)
        except Exception as exc:
            print(f"Resources skipped: {exc}")
        else:
            print(f"Resources: {len(resources)} publishable asset(s) selected")
    _voice_for_result(result, args, workspace)
    if mode in {"package", "both", "render"}:
        package = create_package(result.folder, workspace=workspace)
        print(f"Editing package: {package.plan}")
    if mode in {"render", "both"}:
        try:
            output = render(result.folder, workspace=workspace, preview=getattr(args, "preview", False))
        except ACEError as exc:
            print(f"Render skipped: {exc}")
        else:
            print(f"Rendered: {output}")


def _print_result(result) -> None:
    print(result.text)
    print(f"\nSaved: {result.folder}")
    print(f"Selected: candidate {result.selected_index + 1}/{len(result.candidates) or 1}")
    print(f"Model: {result.provider}/{result.model}")
    if result.reviewed:
        print("Review: completed")
    if result.extras:
        print(f"Extras: {', '.join(path.parent.name for path in result.extras)}")


def _generate_for_args(platform: str, content_type: str, args) -> int:
    workspace = _workspace(args)
    kwargs = _content_kwargs(args)
    if getattr(args, "all_extras", False):
        kwargs["extras"] = available_extras(platform, content_type, workspace)
    if getattr(args, "all_profiles", False):
        profiles = [
            item for item in list_profiles(workspace)
            if item.get("platforms", {}).get(platform, {}).get("enabled", False)
        ]
        if not profiles:
            raise ConfigurationError(f"No profile has {platform} enabled.")
        print(f"Generating separately for {len(profiles)} profile(s).")
        for profile in profiles:
            local_kwargs = {**kwargs, "profile_slug": profile["slug"], "no_profile": False, "interactive": False}
            result = generate(platform, content_type, topic=_topic(args), output=getattr(args, "output", None), **local_kwargs)
            print(f"\n[{profile['name']}] {result.folder}")
            _production(result, args)
        return 0
    result = generate(platform, content_type, topic=_topic(args), output=getattr(args, "output", None), **kwargs)
    _print_result(result)
    if getattr(args, "output", None) is None:
        _production(result, args)
    return 0



def _run_free_only(enabled: bool, callback):
    previous = os.environ.get("ACE_FREE_ONLY")
    if enabled:
        os.environ["ACE_FREE_ONLY"] = "1"
    try:
        return callback()
    finally:
        if previous is None:
            os.environ.pop("ACE_FREE_ONLY", None)
        else:
            os.environ["ACE_FREE_ONLY"] = previous


def _resolve_interaction_mode(args, workspace: str | Path | None) -> str:
    explicit = getattr(args, "interaction_mode", None)
    if explicit:
        return str(explicit)
    account = active_profile(workspace, required=False)
    if account:
        configured = account.get("automation", {}).get("default_mode")
        if configured:
            return str(configured)
    return str(load(workspace).get("interaction", {}).get("default_mode", "assisted"))


def _print_plan(platform: str, content_type: str, topic: str, args) -> None:
    workspace = _workspace(args)
    config = load(workspace)
    account = active_profile(workspace, required=False)
    mode = _resolve_interaction_mode(args, workspace)
    route = config.get("routes", {}).get("script", [])
    voice = (account or {}).get("voice", {})
    print("ACE creation plan")
    print("-" * 64)
    print(f"Account        : {(account or {}).get('name', 'No account')}")
    print(f"Request        : {platform}/{content_type}")
    print(f"Topic          : {topic}")
    print(f"Mode           : {mode}")
    print(f"Language       : {_language(args) or (account or {}).get('languages', {}).get('primary', 'en')}")
    print("Model route    : " + " -> ".join(
        f"{item.get('provider')}/{item.get('model')}" for item in route if isinstance(item, dict)
    ))
    if voice.get("configured"):
        print(f"Voice          : {voice.get('provider')}/{voice.get('voice_id')}")
    else:
        print("Voice          : not configured")
    print(f"Production     : {getattr(args, 'production_mode', None) or (account or {}).get('automation', {}).get('output', 'both')}")
    print("Stages         : account → research → candidates → quality → TTS → voice → resources → edit → validate")
    print(f"Cloud policy   : {'free/local only' if getattr(args, 'free_only', False) else 'configured routes with fallbacks'}")


def _model_target_from_value(value: str, workspace: str | Path | None) -> tuple[str, str]:
    alias = resolve_alias(value, workspace)
    if alias:
        return alias
    if "/" in value:
        provider, model = value.split("/", 1)
        return provider, model
    config = load(workspace)
    exact = [item for item in catalog_models(workspace=workspace) if item.get("id") == value]
    if len(exact) == 1:
        return str(exact[0]["provider"]), value
    if value in {item.get("name") for item in config.get("providers", {}).values() if isinstance(item, dict)}:
        raise ConfigurationError("Use provider/model or a named alias.")
    raise ConfigurationError(
        f"Unknown model or alias '{value}'. Try 'ace models search {value}' or 'ace models recommend'."
    )


def _create_command(args, *, force_auto: bool = False, plan_only: bool = False) -> int:
    workspace = _workspace(args)
    platform = getattr(args, "platform", None)
    content_type = getattr(args, "content_type", None)
    topic = _topic(args)
    if not platform:
        platforms = list(load_catalog(workspace).get("platforms", {}))
        print("Choose a platform:")
        for index, name in enumerate(platforms, 1):
            print(f"  {index}. {name}")
        answer = input("Number: ").strip()
        try:
            platform = platforms[int(answer) - 1]
        except (ValueError, IndexError):
            raise ConfigurationError("Invalid platform selection.")
    if not content_type:
        types = content_types(platform, workspace)
        print(f"Choose a {platform} content type:")
        for index, name in enumerate(types, 1):
            print(f"  {index}. {name}")
        answer = input("Number: ").strip()
        try:
            content_type = types[int(answer) - 1]
        except (ValueError, IndexError):
            raise ConfigurationError("Invalid content-type selection.")
    if not topic:
        topic = input("Topic: ").strip()
    if not topic:
        raise ConfigurationError("A topic is required.")
    mode = "auto" if force_auto else _resolve_interaction_mode(args, workspace)
    account = None
    if not getattr(args, "all_profiles", False):
        account = ensure_task_context(
            platform, content_type, workspace=workspace,
            account_slug=getattr(args, "profile_slug", None), mode=mode,
            no_profile=getattr(args, "no_profile", False),
        )
    if account:
        matches = similar_topics(topic, str(account["slug"]), workspace)
        if matches:
            print(f"⚠ Similar previous topic: {matches[0].get('topic')} ({matches[0].get('similarity', 0):.0%} match)")
    if plan_only or getattr(args, "dry_run", False):
        _print_plan(platform, content_type, topic, args)
        return 0
    if mode == "auto":
        output_mode = getattr(args, "production_mode", None) or "both"
        provider_name, model_name = _model_override(args, workspace)

        def run_one(profile_slug: str | None):
            return create_auto(
                platform, content_type, topic,
                workspace=workspace,
                profile_slug=profile_slug,
                language=_language(args),
                provider=provider_name,
                model=model_name,
                free_only=getattr(args, "free_only", False),
                output_mode=output_mode,
                preview=getattr(args, "preview", False),
            )

        if getattr(args, "all_profiles", False):
            profiles = [
                item for item in list_profiles(workspace)
                if item.get("platforms", {}).get(platform, {}).get("enabled", False)
            ]
            if not profiles:
                raise ConfigurationError(f"No account has {platform} enabled.")
            print(f"ACE Autopilot will create separate results for {len(profiles)} account(s).")
            failures: list[str] = []
            for profile in profiles:
                try:
                    result = _run_free_only(
                        getattr(args, "free_only", False),
                        lambda slug=str(profile["slug"]): run_one(slug),
                    )
                except ACEError as exc:
                    failures.append(f"{profile['name']}: {exc}")
                    print(f"✗ [{profile['name']}] {exc}")
                    continue
                print(f"✓ [{profile['name']}] {result.folder}")
            if failures:
                print("\nSome accounts could not complete:")
                for failure in failures:
                    print(f"  - {failure}")
                return 1
            return 0

        result = _run_free_only(
            getattr(args, "free_only", False),
            lambda: run_one(getattr(args, "profile_slug", None)),
        )
        print(f"Finished: {result.folder}")
        return 0
    # Assisted accepts routine recommendations but pauses for production.
    if mode == "assisted":
        args.non_interactive = True
        args.selection_mode = args.selection_mode or "auto"
        if not getattr(args, "extras", None) and not getattr(args, "all_extras", False):
            args.extras = ",".join(available_extras(platform, content_type, workspace)[:4])
    return _run_free_only(
        getattr(args, "free_only", False),
        lambda: _generate_for_args(platform, content_type, args),
    )


def execute(args) -> int:
    workspace = _workspace(args)

    if not args.command:
        if getattr(args, "all_profiles_home", False) and sys.stdin.isatty():
            args.platform = None
            args.content_type = None
            args.topic = []
            args.all_profiles = True
            args.profile_slug = None
            args.no_profile = False
            args.interaction_mode = "assisted"
            args.non_interactive = False
            args.free_only = False
            args.production_mode = None
            args.preview = False
            args.resources = "auto"
            args.voice = False
            args.output = None
            args.extras = None
            args.all_extras = False
            args.review = None
            args.variants = None
            args.selection_mode = None
            args.provider = None
            args.model = None
            args.no_fallback = False
            args.language = None
            args.language_shortcut = None
            args.audience = None
            args.tone = None
            args.instructions = "None."
            args.dry_run = False
            return _create_command(args)
        return _home(workspace, getattr(args, "all_profiles_home", False))

    if args.command == "guide":
        return run_guide(workspace, " ".join(args.topic).strip() or None)

    if args.command in {"check", "ready"}:
        return 0 if print_readiness(workspace, live=args.live) else 1

    if args.command == "status":
        return 0 if print_generation_status(args.generation, workspace) else 1

    if args.command == "fix":
        report = fix_generation(args.generation, workspace=workspace, preview=args.preview)
        print(f"Repair result: {report['overall']}")
        return 0 if report["overall"] in {"COMPLETE", "COMPLETE_WITH_WARNINGS"} else 1

    if args.command == "mode":
        config = load(workspace)
        if args.value:
            config.setdefault("interaction", {})["default_mode"] = args.value
            save(config, workspace)
            account = active_profile(workspace, required=False)
            if account:
                account.setdefault("automation", {})["default_mode"] = args.value
                save_profile(account, workspace)
        print(config.get("interaction", {}).get("default_mode", "assisted"))
        return 0

    if args.command in {"create", "auto", "plan"}:
        return _create_command(args, force_auto=args.command == "auto", plan_only=args.command == "plan")

    if args.command == "account":
        command = args.account_command or "list"
        if command == "build":
            description = " ".join(args.description).strip()
            if not description:
                description = input("Describe the account you want ACE to build: ").strip()
            if not description:
                raise ConfigurationError("An account description is required.")
            account_name = args.name or input("Account name: ").strip()
            if not account_name:
                raise ConfigurationError("An account name is required.")
            account = build_from_description(account_name, description, workspace=workspace)
            print(f"Active account: {account['name']} ({account['slug']})")
            print(profile_path(str(account['slug']), workspace))
        elif command == "list":
            active_name = active_slug(workspace)
            for item in list_profiles(workspace):
                marker = "★" if item.get("slug") == active_name else " "
                print(f"{marker} {item.get('slug'):24} {item.get('name')}")
        elif command == "use":
            item = use_profile(args.name, workspace)
            print(f"Active account: {item['name']}")
        elif command == "show":
            item = load_profile(args.name, workspace) if args.name else active_profile(workspace)
            print(dump_data(item))
        elif command == "edit":
            print(edit_profile(args.name, workspace))
        elif command == "check":
            item = load_profile(args.name, workspace) if args.name else active_profile(workspace)
            problems = validate_profile(item)
            if problems:
                for problem in problems:
                    print(f"ERROR: {problem}")
                return 1
            print("Account source of truth is valid.")
        elif command == "history":
            for path in account_history(args.name, workspace):
                print(path.name)
        elif command == "rollback":
            print(account_rollback(args.version, args.name, workspace))
        return 0

    if args.command == "models":
        command = args.models_command or "ready"
        config = load(workspace)
        if command == "search":
            rows = search_models(args.query, config, workspace)
            if not rows:
                print("No catalog matches. Try live discovery: ace models discover all")
            for item in rows:
                status, detail = model_readiness(str(item['provider']), str(item['id']), config)
                print(f"{item['provider']:12} {item['id']:38} {status:14} {detail}")
        elif command == "installed":
            rows = installed_models(config)
            if not rows:
                print("No installed local models reported.")
            for item in rows:
                print(f"{item['provider']:12} {item['model']:38} READY")
        elif command == "ready":
            for task, route in config.get("routes", {}).items():
                if not route:
                    continue
                target = route[0]
                status, detail = model_readiness(str(target.get('provider')), str(target.get('model')), config)
                print(f"{task:14} {target.get('provider')}/{target.get('model'):34} {status:14} {detail}")
        elif command == "recommend":
            print(dump_data(recommend_models(config, workspace)))
        elif command == "discover":
            names = list(config.get("providers", {})) if args.provider == "all" else [args.provider]
            for name in names:
                print(f"[{name}]")
                try:
                    rows = discover_models(name, config)
                except ACEError as exc:
                    print(f"  unavailable: {exc}")
                    continue
                for model_name in rows:
                    print(f"  {model_name}")
        elif command == "test":
            targets: list[tuple[str, str]] = []
            if args.all:
                for route in config.get("routes", {}).values():
                    if route and isinstance(route[0], dict):
                        target = (str(route[0].get("provider")), str(route[0].get("model")))
                        if target not in targets:
                            targets.append(target)
            elif args.provider and args.model:
                targets = [(args.provider, args.model)]
            elif args.provider:
                for model_name in discover_models(args.provider, config):
                    targets.append((args.provider, model_name))
            else:
                route = config.get("routes", {}).get("script", [])
                if route:
                    targets = [(str(route[0].get("provider")), str(route[0].get("model")))]
            failed = False
            for provider_name, model_name in targets:
                try:
                    with AIEngine(config) as engine:
                        result = engine.generate("default", "Reply with exactly: ACE_MODEL_OK", provider=provider_name, model=model_name, no_fallback=True, max_output_tokens=24)
                    print(f"READY {provider_name}/{result.model}: {result.text[:80]}")
                except ACEError as exc:
                    failed = True
                    print(f"FAILED {provider_name}/{model_name}: {exc}")
            return 1 if failed else 0
        elif command == "use":
            provider_name, model_name = _model_target_from_value(args.model, workspace)
            routes = config.setdefault("routes", {})
            selected = {"provider": provider_name, "model": model_name}
            existing = list(routes.get(args.task, []))
            routes[args.task] = [selected, *(item for item in existing if item != selected)]
            save(config, workspace)
            _show_routes(config, args.task)
        elif command == "routes":
            _show_routes(config)
        return 0

    if args.command == "settings":
        if args.edit:
            editor = os.environ.get("EDITOR") or shutil.which("nano") or shutil.which("vi")
            if not editor:
                raise ConfigurationError("No text editor found. Set $EDITOR.")
            subprocess.run([editor, str(config_path(workspace))], check=False)
        else:
            print(f"Settings: {config_path(workspace)}")
            print(f"Secrets : {secrets_path(workspace)}")
            print(f"Accounts: {config_home(workspace) / 'accounts'}")
        return 0

    if args.command == "test":
        return 0 if run_selftest(args.suite, workspace=workspace, report=args.report) else 1

    if args.command == "release":
        if args.release_command != "verify":
            raise ConfigurationError("Use 'ace release verify'.")
        return 0 if run_selftest("full", workspace=workspace, report=args.report) else 1

    if args.command == "advanced":
        print("Advanced and compatibility commands:")
        print("  ace config, secrets, provider, model, memory, ai")
        print("  ace content, project, workflow, storage")
        print("Use ace <command> --help for focused details.")
        return 0

    if args.command == "init":
        target = args.path or workspace
        if args.upgrade:
            result = upgrade(target)
            root = result["root"]
            print(f"ACE upgraded safely: {root}")
            print(f"Previous editable system files: {result['backup']}")
        else:
            root = initialize(target, force=args.force)
            print(f"ACE is ready: {root}")
        print(f"Configuration: {config_path(target)}")
        print(f"Secrets: {secrets_path(target)}")
        print(f"Data: {data_home(target)}")
        return 0

    if args.command == "new":
        initialize(workspace)
        if args.name:
            profile = create_profile(
                args.name,
                niche=args.niche,
                audience=args.audience,
                primary_language=args.language,
                enabled_languages=[args.language],
                enabled_platforms=[item.strip() for item in args.platforms.split(",") if item.strip()],
                workspace=workspace,
            )
        else:
            profile = profile_wizard(workspace)
        print(f"Active profile: {profile['name']} ({profile['slug']})")
        return 0

    if args.command in {"doctor", "capabilities"}:
        return 0 if doctor_run(workspace, live=args.live) else 1

    if args.command == "config":
        command = args.config_command or "show"
        if command == "show":
            show(workspace)
        elif command == "path":
            print(config_path(workspace))
        elif command == "get":
            print(json.dumps(get_value(load(workspace), args.key), ensure_ascii=False))
        elif command == "set":
            config = load(workspace)
            set_value(config, args.key, parse_cli_value(args.value))
            print(f"Updated {args.key} in {save(config, workspace)}")
        elif command == "reset":
            print(f"Reset configuration: {save(default_config(), workspace)}")
        return 0

    if args.command == "secrets":
        command = args.secrets_command or "status"
        if command == "path":
            print(secrets_path(workspace))
        elif command == "edit":
            print(edit_secrets(workspace))
        elif command == "status":
            for key, value in masked_status(workspace).items():
                print(f"{key:26} {value}")
        return 0

    if args.command == "profile":
        command = args.profile_command or "list"
        if command == "new":
            profile = create_profile(args.name, workspace=workspace) if args.name else profile_wizard(workspace)
            print(f"Active profile: {profile['name']}")
        elif command == "list":
            active_name = active_slug(workspace)
            for item in list_profiles(workspace):
                marker = "★" if item.get("slug") == active_name else " "
                enabled = [name for name, value in item.get("platforms", {}).items() if value.get("enabled")]
                print(f"{marker} {item.get('slug'):24} {item.get('name')} — {', '.join(enabled) or 'no platforms'}")
        elif command == "use":
            profile = use_profile(args.name, workspace)
            print(f"Active profile: {profile['name']}")
        elif command == "show":
            profile = load_profile(args.name, workspace) if args.name else active_profile(workspace)
            print(json.dumps(profile, indent=2, ensure_ascii=False))
        elif command == "edit":
            print(edit_profile(args.name, workspace))
        elif command == "validate":
            profile = load_profile(args.name, workspace) if args.name else active_profile(workspace)
            problems = validate_profile(profile)
            if problems:
                for problem in problems:
                    print(f"ERROR: {problem}")
                return 1
            print("Profile is valid.")
        return 0

    if args.command == "language":
        profile = active_profile(workspace)
        languages = profile.setdefault("languages", {})
        enabled = languages.setdefault("enabled", [languages.get("primary", "en")])
        command = args.language_command or "status"
        if command == "status":
            print(f"Primary: {languages.get('primary', 'en')}")
            print(f"Enabled: {', '.join(enabled)}")
        elif command == "list":
            for code in enabled:
                marker = "★" if code == languages.get("primary") else "✓"
                print(f"{marker} {code}")
        elif command == "set":
            if args.code not in enabled:
                enabled.append(args.code)
            languages["primary"] = args.code
            save_profile(profile, workspace)
            print(f"Primary language: {args.code}")
        elif command == "add":
            if args.code not in enabled:
                enabled.append(args.code)
                save_profile(profile, workspace)
            print(f"Enabled language: {args.code}")
        elif command == "remove":
            if args.code == languages.get("primary"):
                raise ConfigurationError("Set another primary language before removing this one.")
            languages["enabled"] = [code for code in enabled if code != args.code]
            save_profile(profile, workspace)
            print(f"Removed language: {args.code}")
        return 0

    if args.command == "provider":
        config = load(workspace)
        providers = config.setdefault("providers", {})
        command = args.provider_command or "list"
        if command == "list":
            for name, provider in providers.items():
                enabled = "enabled" if provider.get("enabled", True) else "disabled"
                cost = "paid" if provider.get("paid", False) else "free/local"
                print(f"{name:12} {provider.get('type', 'unknown'):20} {enabled:8} {cost:10} {provider.get('base_url', '')}")
        elif command == "add":
            if args.type not in supported_provider_types():
                raise ConfigurationError(f"Unsupported provider type: {args.type}")
            provider = _provider_defaults(args.type)
            provider.update({"type": args.type, "enabled": not args.disabled})
            if args.base_url:
                provider["base_url"] = args.base_url
            if args.api_key_env:
                provider["api_key_env"] = args.api_key_env
            if args.requires_api_key:
                provider["requires_api_key"] = True
            if args.type == "openai_compatible":
                provider["api_mode"] = args.api_mode
                if "base_url" not in provider:
                    raise ConfigurationError("OpenAI-compatible providers require --base-url.")
            providers[args.name] = provider
            save(config, workspace)
            print(f"Provider saved: {args.name}")
        elif command == "remove":
            if args.name not in providers:
                raise ConfigurationError(f"Unknown provider: {args.name}")
            del providers[args.name]
            save(config, workspace)
            print(f"Provider removed: {args.name}")
        elif command in {"enable", "disable"}:
            if args.name not in providers:
                raise ConfigurationError(f"Unknown provider: {args.name}")
            providers[args.name]["enabled"] = command == "enable"
            save(config, workspace)
            print(f"Provider {command}d: {args.name}")
        elif command == "models":
            with AIEngine(config) as engine:
                models = engine.list_models(args.name)
            for model in models:
                print(model)
        elif command == "test":
            result = AIEngine(config).test_provider(args.name, args.model)
            print(result.text)
            print(f"Provider test passed: {result.provider}/{result.model}")
        return 0

    if args.command == "model":
        config = load(workspace)
        routes = config.setdefault("routes", {})
        command = args.model_command or "catalog"
        if command == "catalog":
            for item in catalog_models(args.provider, kind=args.kind, workspace=workspace):
                ram = f" RAM≥{item['minimum_ram_gb']}GB" if item.get("minimum_ram_gb") else ""
                print(f"{item['provider']:12} {item['id']:36} {item.get('name', '')} [{item.get('status', '')}/{item.get('tier', '')}]{ram}")
        elif command == "aliases":
            for name, target in model_aliases(workspace).items():
                print(f"{name:20} {target['provider']}/{target['model']}")
        elif command == "discover":
            provider_names = [args.provider]
            if args.provider == "all":
                provider_names = [
                    name for name, item in config.get("providers", {}).items()
                    if isinstance(item, dict) and item.get("enabled", True)
                ]
            for provider_name in provider_names:
                print(f"[{provider_name}]")
                try:
                    discovered = discover_models(provider_name, config)
                except ACEError as exc:
                    print(f"  unavailable: {exc}")
                    continue
                if not discovered:
                    print("  no models reported")
                for discovered_model in discovered:
                    print(f"  {discovered_model}")
        elif command == "edit":
            print(edit_catalog(workspace))
        elif command == "routes":
            _show_routes(config, args.task)
        elif command in {"set", "use"}:
            if command == "use":
                alias = resolve_alias(args.alias, workspace)
                if not alias:
                    known = ", ".join(sorted(model_aliases(workspace)))
                    raise ConfigurationError(f"Unknown model alias '{args.alias}'. Available: {known}")
                provider, selected_model = alias
                task = args.task
                only = args.only
            else:
                alias = resolve_alias(args.model, workspace)
                provider, selected_model = alias if alias and args.provider in {"alias", "auto"} else (args.provider, args.model)
                task = args.task
                only = args.only
            selected = {"provider": provider, "model": selected_model}
            existing = list(routes.get(task, []))
            routes[task] = [selected]
            if not only:
                routes[task].extend(item for item in existing if item != selected)
            save(config, workspace)
            _show_routes(config, task)
        elif command == "fallback":
            if args.fallback_command == "add":
                route = routes.setdefault(args.task, [])
                selected = {"provider": args.provider, "model": args.model}
                if selected not in route:
                    route.append(selected)
                save(config, workspace)
                _show_routes(config, args.task)
            elif args.fallback_command == "clear":
                routes[args.task] = list(routes.get(args.task, []))[:1]
                save(config, workspace)
                _show_routes(config, args.task)
            else:
                raise ConfigurationError("Choose 'model fallback add' or 'clear'.")
        return 0

    if args.command == "memory":
        config = load(workspace)
        command = args.memory_command or "status"
        if command == "status":
            state = memory_status(config)
            print(f"Mode: {state['mode']}")
            print(f"Unload at pipeline end: {state['unload_at_pipeline_end']}")
            for provider, details in state["providers"].items():
                print(f"{provider}: {details['status']}")
                for model in details.get("models", []):
                    print(f"  {model.get('name') or model.get('model')} — {model.get('size_vram', 0)} VRAM bytes")
        elif command == "mode":
            if args.value:
                config.setdefault("memory", {})["mode"] = args.value
                save(config, workspace)
            print(config.get("memory", {}).get("mode", "smart"))
        elif command in {"unload", "cleanup"}:
            manager = MemoryManager(config)
            if args.model if command == "unload" else False:
                manager.unload(args.provider, args.model)
                print(f"Unloaded: {args.provider}/{args.model}")
            else:
                unloaded = manager.unload_all(ignore_errors=False)
                print("Unloaded: " + (", ".join(unloaded) if unloaded else "no loaded Ollama models"))
        elif command == "plan":
            print(f"Mode: {config.get('memory', {}).get('mode', 'smart')}")
            print(f"Maximum loaded local models: {config.get('memory', {}).get('maximum_loaded_local_models', 1)}")
            _show_routes(config)
        return 0

    if args.command == "ai":
        config = load(workspace)
        if args.ai_command == "ask":
            provider, model = _model_override(args, workspace)
            with AIEngine(config) as engine:
                result = engine.generate(args.task, " ".join(args.prompt), provider=provider, model=model, no_fallback=args.no_fallback)
            print(result.text)
            print(f"\nModel: {result.provider}/{result.model}")
        elif args.ai_command == "models":
            with AIEngine(config) as engine:
                for model in engine.list_models(args.provider):
                    print(model)
        else:
            raise ConfigurationError("Choose 'ai ask' or 'ai models'.")
        return 0

    if args.command == "content":
        command = args.content_command
        if command == "list":
            catalog = load_catalog(workspace)
            if args.platform:
                key, platform = resolve_platform(args.platform, workspace)
                print(f"{platform.get('name', key)} ({key})")
                for type_name, spec in platform.get("types", {}).items():
                    aliases = ", ".join(spec.get("aliases", []))
                    print(f"  {type_name:20} {spec.get('label', '')}{f' [{aliases}]' if aliases else ''}")
            else:
                for key, platform in catalog["platforms"].items():
                    print(f"{key:12} {platform.get('name', key)}")
                    print(f"  {', '.join(content_types(key, workspace))}")
        elif command == "generate":
            return _create_command(args)
        elif command == "pack":
            selected = [item.strip() for item in args.types.split(",") if item.strip()] if args.types else None
            kwargs = _content_kwargs(args)
            for key in ("variants", "selection_mode", "extras", "interactive"):
                kwargs.pop(key, None)
            results = generate_pack(args.platform, topic=_topic(args), types=selected, output_dir=args.output_dir, **kwargs)
            print(f"Generated {len(results)} deliverables:")
            for result in results:
                print(f"  {result.content_type:18} {result.path} ({result.provider}/{result.model})")
        else:
            raise ConfigurationError("Choose a content command.")
        return 0

    if hasattr(args, "shortcut_platform"):
        args.platform = args.shortcut_platform
        return _create_command(args)

    if args.command in {"adapt", "translate"}:
        target = _language(args)
        if not target:
            raise ConfigurationError("Choose a target language, for example -ar, -fr, or -eng.")
        provider, model = _model_override(args, workspace)
        output = localize(args.source, target, workspace=workspace, profile_slug=args.profile_slug, no_profile=args.no_profile, provider=provider, model=model)
        print(f"Localized content: {output}")
        return 0

    if args.command == "dub":
        target = _language(args)
        if not target:
            raise ConfigurationError("Choose a target language, for example -ar, -fr, or -eng.")
        provider, model = _model_override(args, workspace)
        localized = localize(args.source, target, workspace=workspace, profile_slug=args.profile_slug, no_profile=args.no_profile, provider=provider, model=model)
        voice_output = localized.parent / "voice" / f"narration-{target}.wav"
        path, voice_provider, voice_model = generate_voice(localized.read_text(encoding="utf-8"), voice_output, workspace=workspace, provider=args.voice_provider, model=args.voice_model)
        print(f"Localized: {localized}")
        print(f"Voice: {path} ({voice_provider}/{voice_model})")
        return 0

    if args.command == "assets":
        profile = active_profile(workspace)
        slug = str(profile["slug"])
        command = args.assets_command or "list"
        if command == "add":
            tags = [item.strip() for item in args.tags.split(",") if item.strip()]
            for filename in args.files:
                item = asset_library.add(filename, slug, tags=tags, collection=args.collection, workspace=workspace)
                print(f"{item['id']} {item['path']}")
        elif command == "import":
            tags = [item.strip() for item in args.tags.split(",") if item.strip()]
            items = asset_library.import_folder(args.folder, slug, tags=tags, collection=args.collection, workspace=workspace)
            print(f"Imported {len(items)} asset(s).")
        elif command == "list":
            rows = asset_library.search("", slug, asset_type=args.type, workspace=workspace)
            for item in rows:
                print(f"{item['id']:20} {item.get('type'):8} {item.get('filename')} [{', '.join(item.get('tags', []))}]")
        elif command == "search":
            rows = asset_library.search(" ".join(args.query), slug, asset_type=args.type, tag=args.tag, workspace=workspace)
            for item in rows:
                print(f"{item['id']:20} {item.get('type'):8} {item.get('filename')}")
        return 0

    if args.command == "resources":
        command = args.resources_command or "list"
        folder = resolve_generation(getattr(args, "generation", "last"), workspace)
        if command == "find":
            metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
            resources = collect_for_generation(folder, query=args.query, profile_slug=metadata.get("profile_slug"), media_type=args.type, limit=args.limit, workspace=workspace)
            for item in resources:
                print(f"{item.id:24} {item.type:8} {item.license:18} {item.local_path}")
        elif command == "list":
            manifest = folder / "licenses" / "manifest.json"
            if not manifest.exists():
                print("No resource manifest. Run 'ace resources find last'.")
            else:
                data = json.loads(manifest.read_text(encoding="utf-8"))
                for item in data.get("publishable", []):
                    print(f"PUBLISHABLE {item.get('license'):18} {item.get('title')} — {item.get('local_path')}")
                for item in data.get("reference_only", []):
                    print(f"REFERENCE   {item.get('title')} — {item.get('source_url')}")
        elif command == "license":
            path = folder / "licenses" / "ATTRIBUTION.md"
            print(path.read_text(encoding="utf-8") if path.exists() else "No attribution file.")
        return 0

    if args.command == "edit":
        if args.edit_command == "package":
            package = create_package(args.generation, workspace=workspace)
            print(package.plan)
            print(package.subtitles)
        elif args.edit_command == "render":
            print(render(args.generation, workspace=workspace, preview=args.preview, allow_silent=args.allow_silent))
        else:
            raise ConfigurationError("Choose 'edit package' or 'edit render'.")
        return 0

    if args.command == "voice":
        command = args.voice_command or "status"
        if command == "generate":
            input_path = Path(args.input).expanduser()
            language_code = None
            if str(args.input).lower() == "last":
                folder = last_generation(workspace)
                metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
                language_code = str(metadata.get("language_code") or "en")
                tts_path = folder / "script" / "tts-ready.txt"
                if not tts_path.exists():
                    tts_path = prepare_tts_script(folder, workspace=workspace, use_ai=True)
                input_path = tts_path
                output = Path(args.output) if args.output else folder / "voice" / "narration.wav"
            else:
                output = Path(args.output) if args.output else Path.cwd() / "voice.wav"
            text = input_path.read_text(encoding="utf-8") if input_path.exists() else args.input
            path, provider_name, model_name = generate_voice(
                text, output, workspace=workspace, provider=args.provider, model=args.model,
                language=language_code,
            )
            print(f"Voice generated: {path} ({provider_name}/{model_name})")
        elif command == "list":
            voices = available_voice_models(args.provider, workspace=workspace)
            if not voices:
                print(f"No {args.provider} voices found.")
            for voice in voices:
                print(voice)
        elif command == "providers":
            config = load(workspace)
            account = active_profile(workspace, required=False)
            selected = (account or {}).get("voice", {})
            for name in available_voice_providers(workspace):
                models = available_voice_models(name, workspace=workspace)
                installed = True
                detail = f"{len(models)} catalog voice(s)" if models else "no voices configured"
                if name == "kokoro":
                    installed = importlib.util.find_spec("kokoro") is not None
                    if not installed:
                        detail = "install: python -m pip install -e '.[voice]'"
                elif name == "pocket_tts":
                    installed = importlib.util.find_spec("pocket_tts") is not None
                    if not installed:
                        detail = "install: python -m pip install -e '.[pocket-tts]'"
                elif name == "piper":
                    installed = shutil.which("piper") is not None and bool(models)
                    if not installed:
                        detail = "install Piper and at least one .onnx voice"
                elif name == "openai_tts":
                    installed = bool(os.environ.get("OPENAI_API_KEY", "").strip())
                    if not installed:
                        detail = "add OPENAI_API_KEY with ace guide"
                state = "CONFIGURED" if installed and selected.get("provider") == name else "READY" if installed else "NOT READY"
                print(f"{name:14} {state:24} {detail}")
        elif command == "prepare":
            path = prepare_tts_script(args.generation, workspace=workspace, use_ai=not args.no_ai)
            print(path)
        elif command == "test":
            account = active_profile(workspace)
            voice_config = account.get("voice", {})
            if not voice_config.get("configured"):
                raise ConfigurationError("No account voice is configured. Run 'ace voice audition'.")
            text = args.text or "ACE voice check. This account voice is configured and ready for natural narration."
            output = profile_path(str(account["slug"]), workspace).parent / "voice-test.wav"
            path, provider_name, model_name = generate_voice(
                text, output, workspace=workspace,
                provider=str(voice_config.get("provider")), model=str(voice_config.get("voice_id")),
                language=str(account.get("languages", {}).get("primary", "en")),
            )
            print(f"Voice test passed: {path} ({provider_name}/{model_name})")
        elif command == "audition":
            voices = [item.strip() for item in args.voices.split(",") if item.strip()] if args.voices else None
            manifest = audition_voice(
                workspace=workspace,
                provider=args.provider,
                voices=voices,
                language=_language(args),
                text=args.text,
                select=args.select,
                keep_samples=args.keep_samples,
                interactive=not args.non_interactive,
            )
            print(f"Selected voice: {manifest['provider']}/{manifest['selected_voice']}")
            print(f"Sample: {manifest['selected_sample']}")
        elif command == "status":
            account = active_profile(workspace, required=False)
            print(dump_data((account or {}).get("voice", load(workspace).get("voice", {}))))
        else:
            raise ConfigurationError("Choose voice generate, audition, list, providers, prepare, test, or status.")
        return 0

    if args.command == "storage":
        config = load(workspace)
        command = args.storage_command or "status"
        if command == "status":
            sizes = usage(workspace)
            for name, value in sizes.items():
                print(f"{name:10}: {value / (1024 ** 3):.2f} GB")
            print(f"Retention: {config.get('storage', {}).get('temporary_retention_days', 7)} days")
        elif command == "cleanup":
            days = args.days or int(config.get("storage", {}).get("temporary_retention_days", 7))
            paths = storage_cleanup(workspace, retention_days=days, preview=args.preview)
            print(("Would remove" if args.preview else "Removed") + f" {len(paths)} path(s).")
            for path in paths:
                print(path)
        elif command == "retention":
            if args.days is not None:
                config.setdefault("storage", {})["temporary_retention_days"] = args.days
                config["storage"]["rejected_candidates_retention_days"] = args.days
                save(config, workspace)
            print(config.get("storage", {}).get("temporary_retention_days", 7))
        elif command == "preserve":
            print(preserve(args.generation, workspace))
        return 0

    if args.command == "recent":
        folder = last_generation(workspace)
        print(folder)
        if args.open:
            opener = shutil.which("xdg-open")
            if opener:
                subprocess.Popen([opener, str(folder)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return 0

    if args.command == "project":
        command = args.project_command
        if command == "create":
            path = create_project(" ".join(args.title), platform=args.platform, content_type=args.content_type, topic=args.topic, pack=args.pack, workspace=workspace)
            print(f"Project created: {path}")
        elif command == "list":
            projects = list_projects(workspace)
            if not projects:
                print("No projects found.")
            for path, metadata in projects:
                print(f"{path.name:24} {metadata.get('platform', 'youtube')}/{metadata.get('content_type', 'long_video')} — {metadata.get('title', path.name)}")
        elif command == "status":
            for key, complete in project_status(args.project, workspace).items():
                print(f"{key:10}: {'complete' if complete else 'missing'}")
        else:
            raise ConfigurationError("Choose a project command.")
        return 0

    if args.command == "workflow":
        if args.workflow_command != "run":
            raise ConfigurationError("Choose 'workflow run'.")
        provider, model = _model_override(args, workspace)
        outputs = workflow_run(args.project, review=not args.no_review, voice=args.voice, force=args.force, provider=provider, model=model, no_fallback=args.no_fallback, workspace=workspace)
        for path in outputs:
            print(path)
        return 0

    return _home(workspace)
