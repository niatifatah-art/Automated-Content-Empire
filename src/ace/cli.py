from __future__ import annotations

import argparse

from ace import __version__


class ACEParser(argparse.ArgumentParser):
    def format_help(self) -> str:
        if self.prog == "ace":
            return f"""Automated Content Empire v{__version__}

Cloud-first, evidence-aware content production with adaptive editing.

Core workflow:
  ace create youtube short "Why passkeys matter" --auto --both
  ace status last
  ace edit inspect last
  ace edit rerender last --style technical_dynamic

Main commands:
  init, new, account, create, check, status, fix, recent
  models, credentials, quota, secrets, settings
  research, sources, evidence, resources, memes, images
  visuals, captions, edit, rerun, state, voice, assets, publish
  test, release, guide

Focused help:
  ace <command> --help
  ace edit --help
  ace sources --help
"""
        return super().format_help()


def _generation(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("generation", nargs="?", default="last")


def _create_options(parser: argparse.ArgumentParser) -> None:
    modes = parser.add_mutually_exclusive_group()
    modes.add_argument("--manual", dest="interaction_mode", action="store_const", const="manual")
    modes.add_argument("--assisted", dest="interaction_mode", action="store_const", const="assisted")
    modes.add_argument("--auto", "-a", dest="interaction_mode", action="store_const", const="auto")
    output = parser.add_mutually_exclusive_group()
    output.add_argument("--package", dest="production_mode", action="store_const", const="package")
    output.add_argument("--render", dest="production_mode", action="store_const", const="render")
    output.add_argument("--both", dest="production_mode", action="store_const", const="both")
    parser.add_argument("--provider")
    parser.add_argument("--model")
    parser.add_argument("--no-fallback", action="store_true")
    parser.add_argument("--allow-degraded", action="store_true", help="Allow emergency local-model fallback with an explicit quality warning")
    parser.add_argument("--free-only", action="store_true", help="Avoid providers configured as paid; Gemini free-tier routes remain eligible")
    parser.add_argument("--preview", action="store_true")
    parser.add_argument("--voice", dest="voice", action="store_true", default=True)
    parser.add_argument("--no-voice", dest="voice", action="store_false")
    parser.add_argument("--resources", choices=("auto", "none"), default="auto")
    parser.add_argument("--instructions", default="")
    parser.add_argument("--variants", type=int, choices=(1, 3, 5, 10))
    parser.add_argument("--profile", dest="account_slug")


def create_parser() -> argparse.ArgumentParser:
    parser = ACEParser(prog="ace")
    parser.add_argument("--version", action="version", version=f"ACE {__version__}")
    parser.add_argument("--home", dest="workspace")
    sub = parser.add_subparsers(dest="command")

    init = sub.add_parser("init")
    init.add_argument("path", nargs="?")
    init.add_argument("--force", action="store_true")
    init.add_argument("--upgrade", action="store_true")

    new = sub.add_parser("new")
    new.add_argument("--name", required=False)
    new.add_argument("--description", default="")
    new.add_argument("--niche", default="technology")
    new.add_argument("--audience", default="General audience")
    new.add_argument("--language", default="en")
    new.add_argument("--platforms", default="youtube,tiktok,instagram")

    account = sub.add_parser("account")
    account_sub = account.add_subparsers(dest="account_command")
    account_sub.add_parser("list")
    account_show = account_sub.add_parser("show"); account_show.add_argument("name", nargs="?")
    account_use = account_sub.add_parser("use"); account_use.add_argument("name")
    account_edit = account_sub.add_parser("edit"); account_edit.add_argument("name", nargs="?")
    account_check = account_sub.add_parser("check"); account_check.add_argument("name", nargs="?")
    account_sub.add_parser("upgrade")

    create = sub.add_parser("create")
    create.add_argument("platform")
    create.add_argument("content_type")
    create.add_argument("topic", nargs="+")
    _create_options(create)

    for platform in ("youtube", "tiktok", "instagram", "facebook", "x", "linkedin", "tt", "ig", "yt"):
        shortcut = sub.add_parser(platform)
        shortcut.add_argument("content_type")
        shortcut.add_argument("topic", nargs="+")
        _create_options(shortcut)

    check = sub.add_parser("check", aliases=["ready"])
    check.add_argument("--live", action="store_true")
    check.add_argument("--offline", dest="live", action="store_false")
    check.set_defaults(live=False)

    status = sub.add_parser("status"); _generation(status)
    fix = sub.add_parser("fix"); _generation(fix); fix.add_argument("--preview", action="store_true")
    recent = sub.add_parser("recent"); recent.add_argument("--open", action="store_true")

    models = sub.add_parser("models")
    models_sub = models.add_subparsers(dest="models_command")
    models_sub.add_parser("routes")
    models_use = models_sub.add_parser("use"); models_use.add_argument("task"); models_use.add_argument("model")
    models_test = models_sub.add_parser("test"); models_test.add_argument("provider"); models_test.add_argument("model"); models_test.add_argument("--allow-degraded", action="store_true")
    models_search = models_sub.add_parser("search"); models_search.add_argument("query")
    models_sub.add_parser("ready")

    credentials = sub.add_parser("credentials")
    credentials_sub = credentials.add_subparsers(dest="credentials_command")
    credentials_sub.add_parser("status")
    credentials_test = credentials_sub.add_parser("test"); credentials_test.add_argument("--provider", default="gemini"); credentials_test.add_argument("--model", default="gemini-3.6-flash")

    quota = sub.add_parser("quota")
    quota_sub = quota.add_subparsers(dest="quota_command")
    quota_sub.add_parser("status")
    quota_sub.add_parser("providers")

    secrets = sub.add_parser("secrets")
    secrets_sub = secrets.add_subparsers(dest="secrets_command")
    secrets_sub.add_parser("path"); secrets_sub.add_parser("edit"); secrets_sub.add_parser("status")

    settings = sub.add_parser("settings"); settings.add_argument("--edit", action="store_true")
    config = sub.add_parser("config")
    config_sub = config.add_subparsers(dest="config_command")
    config_sub.add_parser("show"); config_sub.add_parser("path")
    config_get = config_sub.add_parser("get"); config_get.add_argument("key")
    config_set = config_sub.add_parser("set"); config_set.add_argument("key"); config_set.add_argument("value")

    research = sub.add_parser("research")
    research_sub = research.add_subparsers(dest="research_command")
    for name in ("collect", "verify", "show"):
        item = research_sub.add_parser(name); _generation(item)
    research_collect = research_sub.choices["collect"]; research_collect.add_argument("--query")

    sources = sub.add_parser("sources")
    sources_sub = sources.add_subparsers(dest="sources_command")
    sources_add = sources_sub.add_parser("add"); sources_add.add_argument("url"); sources_add.add_argument("generation", nargs="?", default="last")
    sources_post = sources_sub.add_parser("add-post"); sources_post.add_argument("url"); sources_post.add_argument("generation", nargs="?", default="last")
    sources_list = sources_sub.add_parser("list"); _generation(sources_list)
    sources_inspect = sources_sub.add_parser("inspect"); sources_inspect.add_argument("url")

    evidence = sub.add_parser("evidence")
    evidence_sub = evidence.add_subparsers(dest="evidence_command")
    evidence_build = evidence_sub.add_parser("build"); _generation(evidence_build)
    evidence_list = evidence_sub.add_parser("list"); _generation(evidence_list)
    evidence_capture = evidence_sub.add_parser("capture"); evidence_capture.add_argument("url"); evidence_capture.add_argument("generation", nargs="?", default="last"); evidence_capture.add_argument("--approve", action="store_true")

    resources = sub.add_parser("resources")
    resources_sub = resources.add_subparsers(dest="resources_command")
    resources_find = resources_sub.add_parser("find"); resources_find.add_argument("generation", nargs="?", default="last"); resources_find.add_argument("--query"); resources_find.add_argument("--type", choices=("video", "image"), default="video"); resources_find.add_argument("--limit", type=int, default=8); resources_find.add_argument("--download", action="store_true")
    resources_list = resources_sub.add_parser("list"); _generation(resources_list)

    memes = sub.add_parser("memes")
    memes_sub = memes.add_subparsers(dest="memes_command")
    memes_search = memes_sub.add_parser("search"); memes_search.add_argument("query"); memes_search.add_argument("--limit", type=int, default=10)
    memes_generate = memes_sub.add_parser("generate"); memes_generate.add_argument("generation", nargs="?", default="last"); memes_generate.add_argument("--setup", required=True); memes_generate.add_argument("--punchline", required=True)
    memes_fit = memes_sub.add_parser("fit"); memes_fit.add_argument("topic"); memes_fit.add_argument("--mood", default="playful_tech")

    images = sub.add_parser("images")
    images_sub = images.add_subparsers(dest="images_command")
    images_generate = images_sub.add_parser("generate"); images_generate.add_argument("generation", nargs="?", default="last"); images_generate.add_argument("prompt", nargs="+"); images_generate.add_argument("--provider", choices=("gemini_image", "openai_image")); images_generate.add_argument("--model"); images_generate.add_argument("--aspect-ratio")

    visuals = sub.add_parser("visuals")
    visuals_sub = visuals.add_subparsers(dest="visuals_command")
    for name in ("plan", "collect", "show", "inspect"):
        item = visuals_sub.add_parser(name); _generation(item)
    visuals_explain = visuals_sub.add_parser("explain"); _generation(visuals_explain); visuals_explain.add_argument("--shot", type=int)
    visuals_candidates = visuals_sub.add_parser("candidates"); _generation(visuals_candidates); visuals_candidates.add_argument("--shot", type=int, required=True)
    visuals_regenerate = visuals_sub.add_parser("regenerate"); _generation(visuals_regenerate); visuals_regenerate.add_argument("--shot", type=int, required=True); visuals_regenerate.add_argument("--no-cloud-judge", action="store_true"); visuals_regenerate.add_argument("--static", action="store_true")
    visuals_replace = visuals_sub.add_parser("replace"); _generation(visuals_replace); visuals_replace.add_argument("--shot", type=int, required=True); visuals_replace.add_argument("--candidate", required=True); visuals_replace.add_argument("--approve", action="store_true")
    visuals_approve = visuals_sub.add_parser("approve"); _generation(visuals_approve); visuals_approve.add_argument("--shot", type=int, required=True)
    visuals_benchmark = visuals_sub.add_parser("benchmark"); visuals_benchmark.add_argument("--fixtures")

    captions = sub.add_parser("captions")
    captions_sub = captions.add_subparsers(dest="captions_command")
    for name in ("plan", "inspect", "preview"):
        item = captions_sub.add_parser(name); _generation(item)

    edit = sub.add_parser("edit")
    edit_sub = edit.add_subparsers(dest="edit_command")
    edit_sub.add_parser("styles")
    style = edit_sub.add_parser("style")
    style_sub = style.add_subparsers(dest="style_command")
    style_set = style_sub.add_parser("set"); style_set.add_argument("name")
    for name in ("package", "render", "preview", "inspect", "rerender"):
        item = edit_sub.add_parser(name); _generation(item)
        if name == "rerender": item.add_argument("--style")
    edit_captions = edit_sub.add_parser("captions")
    edit_captions_sub = edit_captions.add_subparsers(dest="edit_captions_command")
    edit_captions_preview = edit_captions_sub.add_parser("preview"); _generation(edit_captions_preview)

    rerun = sub.add_parser("rerun")
    _generation(rerun)
    rerun.add_argument("--from", dest="rerun_from", choices=("visual-plan", "captions", "editing", "render"), required=True)
    rerun.add_argument("--preview", action="store_true")
    rerun.add_argument("--no-cloud-judge", action="store_true")

    state = sub.add_parser("state")
    state_sub = state.add_subparsers(dest="state_command")
    state_show = state_sub.add_parser("show"); _generation(state_show)
    state_events = state_sub.add_parser("events"); _generation(state_events); state_events.add_argument("--limit", type=int, default=50)

    voice = sub.add_parser("voice")
    voice_sub = voice.add_subparsers(dest="voice_command")
    for name in ("prepare", "generate", "status"):
        item = voice_sub.add_parser(name); _generation(item)
    voice_test = voice_sub.add_parser("test"); voice_test.add_argument("--output")

    assets = sub.add_parser("assets")
    assets_sub = assets.add_subparsers(dest="assets_command")
    assets_add = assets_sub.add_parser("add"); assets_add.add_argument("path"); assets_add.add_argument("--tags", default="")
    assets_sub.add_parser("list")

    publish = sub.add_parser("publish")
    publish_sub = publish.add_subparsers(dest="publish_command")
    for name in ("prepare", "approve", "status"):
        item = publish_sub.add_parser(name); _generation(item)
    publish_schedule = publish_sub.add_parser("schedule"); publish_schedule.add_argument("generation", nargs="?", default="last"); publish_schedule.add_argument("when")

    test = sub.add_parser("test"); test.add_argument("suite", nargs="?", default="quick", choices=("quick", "render", "full")); test.add_argument("--report", action="store_true")
    release = sub.add_parser("release")
    release_sub = release.add_subparsers(dest="release_command")
    release_verify = release_sub.add_parser("verify"); release_verify.add_argument("--report", action="store_true")

    guide = sub.add_parser("guide"); guide.add_argument("topic", nargs="*")
    return parser
