from __future__ import annotations

import argparse

from ace.providers import supported_provider_types


VERSION = "1.7.0"


class ACEArgumentParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        if self.prog == "ace":
            return f"""Automated Content Empire v{VERSION}

ACE is a profile-aware content production system.

Main commands:
  ace                         Open the ACE home screen
  ace new                     Create an AI-assisted account
  ace create                  Create content interactively
  ace guide                   Guided setup and troubleshooting
  ace check                   Check accounts, models, voice, resources, and rendering
  ace status last             Show every stage of a generation
  ace fix last                Repair an incomplete generation
  ace recent --open           Open the latest generation
  ace account                 Manage persistent account identities
  ace models                  Search, test, and select models
  ace voice                   Configure narration and TTS providers
  ace assets                  Manage account-owned media
  ace settings                Edit ACE settings

Creation examples:
  ace create youtube short "Why passkeys matter" --auto
  ace create instagram reel "Linux gaming" --assisted
  ace create tiktok short "Python mistake" --manual

Focused help:
  ace <command> --help
  ace voice audition --help
  ace models search --help

Advanced and compatibility commands:
  ace advanced --help
"""
        return super().format_help()


def _add_interaction_options(parser: argparse.ArgumentParser) -> None:
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--manual", dest="interaction_mode", action="store_const", const="manual", help="Ask at every meaningful step")
    group.add_argument("--assisted", dest="interaction_mode", action="store_const", const="assisted", help="Accept normal recommendations and pause at major checkpoints")
    group.add_argument("--auto", "-a", dest="interaction_mode", action="store_const", const="auto", help="Run Autopilot without routine questions")
    parser.add_argument("--dry-run", action="store_true", help="Show the plan without creating content")
    parser.add_argument("--free-only", action="store_true", help="Use free/local routes only")


def _add_model_override(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--provider", help="Override the configured provider")
    parser.add_argument("--model", help="Override the configured model or catalog alias")
    parser.add_argument("--no-fallback", action="store_true", help="Do not try configured fallback models")


def _add_language_options(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--language", help="Language code or name")
    parser.add_argument("-ar", dest="language_shortcut", action="store_const", const="ar", help="Generate/localize in Arabic")
    parser.add_argument("-fr", dest="language_shortcut", action="store_const", const="fr", help="Generate/localize in French")
    parser.add_argument("-eng", "-en", dest="language_shortcut", action="store_const", const="en", help="Generate/localize in English")


def _add_production_options(parser: argparse.ArgumentParser) -> None:
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--package", dest="production_mode", action="store_const", const="package", help="Create the editing package")
    mode.add_argument("--render", dest="production_mode", action="store_const", const="render", help="Render final media when possible")
    mode.add_argument("--both", dest="production_mode", action="store_const", const="both", help="Create package and render")
    parser.add_argument("--resources", choices=("auto", "none"), default="auto", help="Automatically collect licensed resources")
    parser.add_argument("--voice", action="store_true", help="Generate narration when a voice route is available")
    parser.add_argument("--preview", action="store_true", help="Render a low-resolution preview")


def _add_content_options(parser: argparse.ArgumentParser, *, include_output: bool = True) -> None:
    _add_language_options(parser)
    _add_interaction_options(parser)
    parser.add_argument("--audience")
    parser.add_argument("--tone")
    parser.add_argument("--instructions", default="None.", help="Extra requirements for this generation")
    review = parser.add_mutually_exclusive_group()
    review.add_argument("--review", dest="review", action="store_true")
    review.add_argument("--no-review", dest="review", action="store_false")
    parser.set_defaults(review=None)
    parser.add_argument("--variants", type=int, choices=(1, 3, 5, 10))
    parser.add_argument("--select", dest="selection_mode", choices=("manual", "auto", "hybrid"))
    parser.add_argument("--extras", help="Comma-separated supporting content types")
    parser.add_argument("--all-extras", action="store_true")
    parser.add_argument("--non-interactive", action="store_true")
    parser.add_argument("--profile", dest="profile_slug")
    parser.add_argument("--no-profile", action="store_true")
    parser.add_argument("-A", "--all-profiles", action="store_true", help="Generate separately for every eligible profile")
    if include_output:
        parser.add_argument("--output", help="Write a specific file instead of a generation folder")
    _add_model_override(parser)
    _add_production_options(parser)


def create_parser() -> argparse.ArgumentParser:
    parser = ACEArgumentParser(
        prog="ace",
        description="Automated Content Empire — profile-aware local/cloud content production CLI",
    )
    parser.add_argument("--version", action="version", version=f"ACE {VERSION}")
    parser.add_argument("--home", dest="workspace", help="Portable ACE workspace path (or set ACE_HOME)")
    parser.add_argument("--all", "-A", dest="all_profiles_home", action="store_true", help="Open ACE in all-profiles creation mode")
    sub = parser.add_subparsers(dest="command")

    guide = sub.add_parser("guide", help="Interactive setup and troubleshooting guide")
    guide.add_argument("topic", nargs="*")

    check = sub.add_parser("check", aliases=["ready"], help="Check whether ACE is ready and explain every problem")
    check_mode = check.add_mutually_exclusive_group()
    check_mode.add_argument("--live", dest="live", action="store_true", help="Contact configured providers (default)")
    check_mode.add_argument("--offline", dest="live", action="store_false", help="Do not contact local or cloud providers")
    check.set_defaults(live=True)

    status = sub.add_parser("status", help="Show stage-by-stage generation status")
    status.add_argument("generation", nargs="?", default="last")

    fix = sub.add_parser("fix", help="Repair an incomplete generation")
    fix.add_argument("generation", nargs="?", default="last")
    fix.add_argument("--preview", action="store_true")

    mode = sub.add_parser("mode", help="Read or change the default interaction mode")
    mode.add_argument("value", nargs="?", choices=("manual", "assisted", "auto"))

    create = sub.add_parser("create", help="Create content in manual, assisted, or Autopilot mode")
    create.add_argument("platform", nargs="?")
    create.add_argument("content_type", nargs="?")
    create.add_argument("topic", nargs="*")
    _add_content_options(create)

    auto = sub.add_parser("auto", help="Autopilot shortcut for ace create --auto")
    auto.add_argument("platform")
    auto.add_argument("content_type")
    auto.add_argument("topic", nargs="+")
    _add_content_options(auto)
    auto.set_defaults(interaction_mode="auto", non_interactive=True)

    plan = sub.add_parser("plan", help="Show exactly what ACE will do before execution")
    plan.add_argument("platform")
    plan.add_argument("content_type")
    plan.add_argument("topic", nargs="+")
    _add_content_options(plan)
    plan.set_defaults(dry_run=True)

    account = sub.add_parser("account", help="Manage the permanent account source of truth")
    account_sub = account.add_subparsers(dest="account_command")
    account_build = account_sub.add_parser("build", help="Use an LLM to build account.yaml")
    account_build.add_argument("description", nargs="*")
    account_build.add_argument("--name")
    account_sub.add_parser("list")
    account_use = account_sub.add_parser("use")
    account_use.add_argument("name")
    account_show = account_sub.add_parser("show")
    account_show.add_argument("name", nargs="?")
    account_edit = account_sub.add_parser("edit")
    account_edit.add_argument("name", nargs="?")
    account_check = account_sub.add_parser("check")
    account_check.add_argument("name", nargs="?")
    account_history = account_sub.add_parser("history")
    account_history.add_argument("name", nargs="?")
    account_rollback = account_sub.add_parser("rollback")
    account_rollback.add_argument("version", type=int)
    account_rollback.add_argument("--name")

    models = sub.add_parser("models", help="Search, test, recommend, and select models")
    models_sub = models.add_subparsers(dest="models_command")
    models_search = models_sub.add_parser("search")
    models_search.add_argument("query")
    models_sub.add_parser("installed")
    models_sub.add_parser("ready")
    models_sub.add_parser("recommend")
    models_discover = models_sub.add_parser("discover")
    models_discover.add_argument("provider", nargs="?", default="all")
    models_test = models_sub.add_parser("test")
    models_test.add_argument("provider", nargs="?")
    models_test.add_argument("model", nargs="?")
    models_test.add_argument("--all", action="store_true")
    models_use = models_sub.add_parser("use")
    models_use.add_argument("task")
    models_use.add_argument("model")
    models_sub.add_parser("routes")

    settings = sub.add_parser("settings", help="Show or edit normal ACE settings")
    settings.add_argument("--edit", action="store_true")

    test = sub.add_parser("test", help="Run ACE self-tests")
    test.add_argument("suite", nargs="?", default="quick", choices=("quick", "commands", "providers", "models", "voice", "resources", "render", "full"))
    test.add_argument("--report", action="store_true")

    release = sub.add_parser("release", help="Release verification")
    release_sub = release.add_subparsers(dest="release_command")
    release_verify = release_sub.add_parser("verify")
    release_verify.add_argument("--report", action="store_true")

    advanced = sub.add_parser("advanced", help="Developer and legacy command reference")
    advanced.add_argument("topic", nargs="?")

    init = sub.add_parser("init", help="Initialize ACE configuration and data directories")
    init.add_argument("path", nargs="?", help="Optional portable workspace")
    init.add_argument("--force", action="store_true", help="Replace all shipped defaults; may reset customized config")
    init.add_argument("--upgrade", action="store_true", help="Upgrade catalogs/prompts and schema while preserving user settings")

    new = sub.add_parser("new", help="Create a new account/profile")
    new.add_argument("--name")
    new.add_argument("--niche", default="")
    new.add_argument("--audience", default="General audience")
    new.add_argument("--language", default="en")
    new.add_argument("--platforms", default="tiktok,instagram,youtube")

    doctor = sub.add_parser("doctor", aliases=["capabilities"], help="Check hardware, tools, providers, and routes")
    doctor.add_argument("--live", action="store_true")

    config = sub.add_parser("config", help="Read or change ACE configuration")
    config_sub = config.add_subparsers(dest="config_command")
    config_sub.add_parser("show")
    config_sub.add_parser("path")
    config_get = config_sub.add_parser("get")
    config_get.add_argument("key")
    config_set = config_sub.add_parser("set")
    config_set.add_argument("key")
    config_set.add_argument("value")
    config_sub.add_parser("reset")

    secrets = sub.add_parser("secrets", help="Manage protected API-key storage")
    secrets_sub = secrets.add_subparsers(dest="secrets_command")
    secrets_sub.add_parser("path")
    secrets_sub.add_parser("edit")
    secrets_sub.add_parser("status")

    profile = sub.add_parser("profile", help="Manage brand/account profiles")
    profile_sub = profile.add_subparsers(dest="profile_command")
    profile_new = profile_sub.add_parser("new")
    profile_new.add_argument("--name")
    profile_sub.add_parser("list")
    profile_use = profile_sub.add_parser("use")
    profile_use.add_argument("name")
    profile_show = profile_sub.add_parser("show")
    profile_show.add_argument("name", nargs="?")
    profile_edit = profile_sub.add_parser("edit")
    profile_edit.add_argument("name", nargs="?")
    profile_validate = profile_sub.add_parser("validate")
    profile_validate.add_argument("name", nargs="?")

    language = sub.add_parser("language", help="Manage languages for the active profile")
    language_sub = language.add_subparsers(dest="language_command")
    language_sub.add_parser("status")
    language_sub.add_parser("list")
    language_set = language_sub.add_parser("set")
    language_set.add_argument("code")
    language_add = language_sub.add_parser("add")
    language_add.add_argument("code")
    language_remove = language_sub.add_parser("remove")
    language_remove.add_argument("code")

    provider = sub.add_parser("provider", help="Manage local and cloud providers")
    provider_sub = provider.add_subparsers(dest="provider_command")
    provider_sub.add_parser("list")
    provider_add = provider_sub.add_parser("add")
    provider_add.add_argument("name")
    provider_add.add_argument("type", choices=supported_provider_types())
    provider_add.add_argument("--base-url")
    provider_add.add_argument("--api-key-env")
    provider_add.add_argument("--requires-api-key", action="store_true")
    provider_add.add_argument("--api-mode", choices=("chat", "responses"), default="chat")
    provider_add.add_argument("--disabled", action="store_true")
    for action in ("remove", "enable", "disable"):
        item = provider_sub.add_parser(action)
        item.add_argument("name")
    provider_models = provider_sub.add_parser("models")
    provider_models.add_argument("name")
    provider_test = provider_sub.add_parser("test")
    provider_test.add_argument("name")
    provider_test.add_argument("model")

    model = sub.add_parser("model", help="List models and manage task routes")
    model_sub = model.add_subparsers(dest="model_command")
    model_catalog = model_sub.add_parser("catalog")
    model_catalog.add_argument("provider", nargs="?")
    model_catalog.add_argument("--kind")
    model_sub.add_parser("aliases")
    model_discover = model_sub.add_parser("discover")
    model_discover.add_argument("provider", nargs="?", default="all", help="Provider name or 'all'")
    model_sub.add_parser("edit")
    model_routes = model_sub.add_parser("routes")
    model_routes.add_argument("task", nargs="?")
    model_set = model_sub.add_parser("set")
    model_set.add_argument("task")
    model_set.add_argument("provider")
    model_set.add_argument("model")
    model_set.add_argument("--only", action="store_true")
    model_use = model_sub.add_parser("use", help="Set a task route using a named model alias")
    model_use.add_argument("task")
    model_use.add_argument("alias")
    model_use.add_argument("--only", action="store_true")
    fallback = model_sub.add_parser("fallback")
    fallback_sub = fallback.add_subparsers(dest="fallback_command")
    fallback_add = fallback_sub.add_parser("add")
    fallback_add.add_argument("task")
    fallback_add.add_argument("provider")
    fallback_add.add_argument("model")
    fallback_clear = fallback_sub.add_parser("clear")
    fallback_clear.add_argument("task")

    memory = sub.add_parser("memory", help="Manage local model RAM/VRAM lifetime")
    memory_sub = memory.add_subparsers(dest="memory_command")
    memory_sub.add_parser("status")
    memory_mode = memory_sub.add_parser("mode")
    memory_mode.add_argument("value", nargs="?", choices=("smart", "low", "performance"))
    unload = memory_sub.add_parser("unload")
    unload.add_argument("model", nargs="?")
    unload.add_argument("--provider", default="ollama")
    memory_sub.add_parser("cleanup")
    memory_sub.add_parser("plan")

    ai = sub.add_parser("ai", help="Use the AI engine directly")
    ai_sub = ai.add_subparsers(dest="ai_command")
    ai_ask = ai_sub.add_parser("ask")
    ai_ask.add_argument("prompt", nargs="+")
    ai_ask.add_argument("--task", default="default")
    _add_model_override(ai_ask)
    ai_models = ai_sub.add_parser("models")
    ai_models.add_argument("provider", nargs="?", default="ollama")

    content = sub.add_parser("content", help="Generate and inspect content")
    content_sub = content.add_subparsers(dest="content_command")
    content_list = content_sub.add_parser("list")
    content_list.add_argument("platform", nargs="?")
    content_generate = content_sub.add_parser("generate")
    content_generate.add_argument("platform")
    content_generate.add_argument("content_type")
    content_generate.add_argument("topic", nargs="+")
    _add_content_options(content_generate)
    content_pack = content_sub.add_parser("pack")
    content_pack.add_argument("platform")
    content_pack.add_argument("topic", nargs="+")
    content_pack.add_argument("--types")
    content_pack.add_argument("--output-dir")
    _add_content_options(content_pack, include_output=False)

    shortcut_aliases = {
        "youtube": ["yt"],
        "tiktok": ["tt"],
        "instagram": ["insta", "ig"],
        "facebook": ["fb"],
        "x": ["twitter"],
        "linkedin": ["li"],
    }
    for platform_name, aliases in shortcut_aliases.items():
        shortcut = sub.add_parser(platform_name, aliases=aliases, help=f"Generate {platform_name} content")
        shortcut.set_defaults(shortcut_platform=platform_name)
        shortcut.add_argument("content_type")
        shortcut.add_argument("topic", nargs="+")
        _add_content_options(shortcut)

    adapt = sub.add_parser("adapt", aliases=["translate"], help="Naturally localize existing content")
    adapt.add_argument("source")
    _add_language_options(adapt)
    adapt.add_argument("--profile", dest="profile_slug")
    adapt.add_argument("--no-profile", action="store_true")
    _add_model_override(adapt)

    dub = sub.add_parser("dub", help="Localize content and generate TTS")
    dub.add_argument("source")
    _add_language_options(dub)
    dub.add_argument("--profile", dest="profile_slug")
    dub.add_argument("--no-profile", action="store_true")
    dub.add_argument("--voice-provider")
    dub.add_argument("--voice-model")
    _add_model_override(dub)

    assets = sub.add_parser("assets", help="Manage reusable account-owned assets")
    assets_sub = assets.add_subparsers(dest="assets_command")
    assets_add = assets_sub.add_parser("add")
    assets_add.add_argument("files", nargs="+")
    assets_add.add_argument("--tags", default="")
    assets_add.add_argument("--collection")
    assets_import = assets_sub.add_parser("import")
    assets_import.add_argument("folder")
    assets_import.add_argument("--tags", default="")
    assets_import.add_argument("--collection")
    assets_list = assets_sub.add_parser("list")
    assets_list.add_argument("--type")
    assets_search = assets_sub.add_parser("search")
    assets_search.add_argument("query", nargs="+")
    assets_search.add_argument("--type")
    assets_search.add_argument("--tag")

    resources = sub.add_parser("resources", help="Find licensed resources for editing")
    resources_sub = resources.add_subparsers(dest="resources_command")
    resources_find = resources_sub.add_parser("find")
    resources_find.add_argument("generation", nargs="?", default="last")
    resources_find.add_argument("--query")
    resources_find.add_argument("--type", choices=("image", "video"))
    resources_find.add_argument("--limit", type=int)
    resources_list = resources_sub.add_parser("list")
    resources_list.add_argument("generation", nargs="?", default="last")
    resources_license = resources_sub.add_parser("license")
    resources_license.add_argument("generation", nargs="?", default="last")

    edit = sub.add_parser("edit", help="Create editing packages and renders")
    edit_sub = edit.add_subparsers(dest="edit_command")
    edit_package = edit_sub.add_parser("package")
    edit_package.add_argument("generation", nargs="?", default="last")
    edit_render = edit_sub.add_parser("render")
    edit_render.add_argument("generation", nargs="?", default="last")
    edit_render.add_argument("--preview", action="store_true")
    edit_render.add_argument("--allow-silent", action="store_true", help="Permit a silent render (normally rejected)")

    voice = sub.add_parser("voice", help="Configure and generate narration")
    voice_sub = voice.add_subparsers(dest="voice_command")
    voice_generate = voice_sub.add_parser("generate")
    voice_generate.add_argument("input")
    voice_generate.add_argument("output", nargs="?")
    voice_generate.add_argument("--provider")
    voice_generate.add_argument("--model")
    voice_list = voice_sub.add_parser("list", help="List configured or installed voices")
    voice_list.add_argument("provider", nargs="?", default="kokoro")
    voice_audition = voice_sub.add_parser("audition", help="Generate short samples and select the account voice")
    voice_audition.add_argument("--provider", default="kokoro")
    voice_audition.add_argument("--voices", help="Comma-separated voice IDs; defaults to the configured catalog")
    _add_language_options(voice_audition)
    voice_audition.add_argument("--text")
    voice_audition.add_argument("--select", type=int)
    voice_audition.add_argument("--keep-samples", action="store_true")
    voice_audition.add_argument("--non-interactive", action="store_true")
    voice_sub.add_parser("status")
    voice_sub.add_parser("providers", help="Show installed and configured TTS providers")
    voice_prepare = voice_sub.add_parser("prepare", help="Create a TTS-safe spoken script")
    voice_prepare.add_argument("generation", nargs="?", default="last")
    voice_prepare.add_argument("--no-ai", action="store_true")
    voice_test = voice_sub.add_parser("test", help="Test the configured account voice")
    voice_test.add_argument("--text")

    storage = sub.add_parser("storage", help="Inspect and clean ACE storage")
    storage_sub = storage.add_subparsers(dest="storage_command")
    storage_sub.add_parser("status")
    storage_cleanup = storage_sub.add_parser("cleanup")
    storage_cleanup.add_argument("--preview", action="store_true")
    storage_cleanup.add_argument("--days", type=int)
    storage_retention = storage_sub.add_parser("retention")
    storage_retention.add_argument("days", nargs="?", type=int)
    storage_preserve = storage_sub.add_parser("preserve")
    storage_preserve.add_argument("generation", nargs="?", default="last")

    recent = sub.add_parser("recent", help="Show the latest generation folder")
    recent.add_argument("--open", action="store_true")

    project = sub.add_parser("project", help="Legacy project workflow compatibility")
    project_sub = project.add_subparsers(dest="project_command")
    project_create = project_sub.add_parser("create")
    project_create.add_argument("title", nargs="+")
    project_create.add_argument("--platform", default="youtube")
    project_create.add_argument("--type", dest="content_type")
    project_create.add_argument("--topic")
    project_create.add_argument("--pack", action="store_true")
    project_sub.add_parser("list")
    project_status = project_sub.add_parser("status")
    project_status.add_argument("project")

    workflow = sub.add_parser("workflow", help="Run a legacy project workflow")
    workflow_sub = workflow.add_subparsers(dest="workflow_command")
    workflow_run = workflow_sub.add_parser("run")
    workflow_run.add_argument("project")
    workflow_run.add_argument("--no-review", action="store_true")
    workflow_run.add_argument("--voice", action="store_true")
    workflow_run.add_argument("--force", action="store_true")
    _add_model_override(workflow_run)

    return parser
