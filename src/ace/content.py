from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ace.ai import AIEngine, GenerationResult
from ace.catalog import default_pack, resolve_content_type, resolve_platform
from ace.config import load as load_config
from ace.errors import ACEError, ConfigurationError
from ace.profile import active as active_profile
from ace.profile import context_text, load as load_profile
from ace.prompt import load_prompt
from ace.script_cleaner import clean_response
from ace.storage import create_generation_dir, create_pack_dir, save_generation, write_json


LANGUAGE_NAMES = {
    "en": "English",
    "eng": "English",
    "fr": "French",
    "fra": "French",
    "ar": "Arabic",
}


@dataclass(frozen=True)
class ContentResult:
    platform: str
    content_type: str
    topic: str
    text: str
    path: Path
    folder: Path
    provider: str
    model: str
    reviewed: bool
    candidates: tuple[str, ...] = ()
    selected_index: int = 0
    extras: tuple[Path, ...] = ()


def normalize_language(value: str | None, profile: dict[str, Any] | None, config: dict[str, Any]) -> tuple[str, str]:
    raw = value or (profile or {}).get("languages", {}).get("primary") or config.get("languages", {}).get("default") or "en"
    code = str(raw).strip().lower()
    code = {"english": "en", "french": "fr", "arabic": "ar"}.get(code, code)
    return code, LANGUAGE_NAMES.get(code, str(raw))


def language_instruction(code: str, profile: dict[str, Any] | None, config: dict[str, Any]) -> str:
    if code == "ar":
        language_config = (profile or {}).get("languages", {}) or config.get("languages", {})
        style = language_config.get("arabic_style", "neutral_mashriqi_social")
        fallback = language_config.get("arabic_fallback", "spoken_modern_standard")
        return (
            "Write natural, widely understood Arabic for social media. Prefer a neutral Mashriqi conversational "
            f"register ({style}) with minimal region-specific slang. If the model cannot do that reliably, use "
            f"natural spoken Modern Standard Arabic ({fallback}), never stiff textbook or newsreader language."
        )
    if code == "fr":
        return "Write idiomatic natural French, not translated English. Preserve the account's established level of formality."
    if code == "en":
        return "Write natural contemporary English suitable for the account and audience."
    return f"Write directly and naturally in {LANGUAGE_NAMES.get(code, code)}; do not produce a literal translation."


def _constraints(specification: dict[str, Any]) -> str:
    constraints = specification.get("constraints", [])
    return "\n".join(f"- {item}" for item in constraints) if constraints else "- Follow the platform's normal conventions."


def _resolve_profile(
    workspace: str | Path | None,
    *,
    profile_slug: str | None,
    no_profile: bool,
) -> dict[str, Any] | None:
    if no_profile:
        return None
    if profile_slug:
        return load_profile(profile_slug, workspace)
    return active_profile(workspace, required=True)


def _base_prompt(
    *,
    workspace: str | Path | None,
    profile: dict[str, Any] | None,
    platform_key: str,
    platform_spec: dict[str, Any],
    type_key: str,
    specification: dict[str, Any],
    topic: str,
    language_code: str,
    language_name: str,
    audience: str,
    tone: str,
    extra_instructions: str,
) -> str:
    adaptation = (profile or {}).get("platforms", {}).get(platform_key, {}).get("adaptation", {})
    adaptation_text = json.dumps(adaptation, ensure_ascii=False) if adaptation else "Use normal platform conventions."
    constraints = f"{_constraints(specification)}\n- Platform adaptation settings: {adaptation_text}"
    return load_prompt(
        "content",
        workspace,
        profile_context=context_text(profile),
        platform_name=platform_spec.get("name", platform_key),
        content_label=specification.get("label", type_key),
        topic=topic,
        language=language_name,
        language_instruction=language_instruction(language_code, profile, load_config(workspace)),
        audience=audience,
        tone=tone,
        goal=specification.get("goal", "Create useful content."),
        output_format=specification.get("format", "A finished deliverable."),
        constraints=constraints,
        extra_instructions=extra_instructions or "None.",
    )


def _parse_candidates(text: str, expected: int) -> list[str]:
    cleaned = clean_response(text)
    pattern = re.compile(r"(?m)^\s*===\s*CANDIDATE\s+\d+\s*===\s*$", re.IGNORECASE)
    parts = [part.strip() for part in pattern.split(cleaned) if part.strip()]
    if not parts:
        return [cleaned] if cleaned else []
    return parts[:expected]


def _extract_json(text: str) -> dict[str, Any] | None:
    cleaned = clean_response(text).strip()
    cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        value = json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _heuristic_evaluation(candidates: list[str]) -> dict[str, Any]:
    scores: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates, 1):
        length = len(candidate.split())
        clarity = max(55, min(92, 88 - abs(length - 140) // 8))
        hook = 80 if candidate.strip().splitlines() and len(candidate.strip().splitlines()[0]) < 140 else 70
        overall = round((clarity + hook + 78 + 76 + 74) / 5)
        scores.append(
            {
                "candidate": index,
                "brand_consistency": 78,
                "platform_fit": 76,
                "hook": hook,
                "clarity": clarity,
                "originality": 74,
                "overall": overall,
                "reason": "Fallback local scoring; AI evaluation was unavailable or invalid.",
            }
        )
    recommended = max(scores, key=lambda item: item["overall"])["candidate"] if scores else 1
    return {"recommended": recommended, "scores": scores, "method": "heuristic_fallback"}


def _evaluate(
    candidates: list[str],
    *,
    engine: AIEngine,
    profile: dict[str, Any] | None,
    platform_name: str,
    content_label: str,
    topic: str,
    language: str,
    workspace: str | Path | None,
) -> dict[str, Any]:
    rendered = "\n\n".join(f"=== CANDIDATE {index} ===\n{candidate}" for index, candidate in enumerate(candidates, 1))
    prompt = load_prompt(
        "selection",
        workspace,
        profile_context=context_text(profile),
        platform_name=platform_name,
        content_label=content_label,
        topic=topic,
        language=language,
        candidates=rendered,
    )
    try:
        result = engine.generate("selection", prompt, temperature=0.1, max_output_tokens=2000)
    except ACEError:
        return _heuristic_evaluation(candidates)
    evaluation = _extract_json(result.text)
    if not evaluation or not isinstance(evaluation.get("recommended"), int):
        return _heuristic_evaluation(candidates)
    recommended = int(evaluation["recommended"])
    if not 1 <= recommended <= len(candidates):
        return _heuristic_evaluation(candidates)
    evaluation["method"] = "ai"
    evaluation["provider"] = result.provider
    evaluation["model"] = result.model
    return evaluation


def _choose_interactively(candidates: list[str], evaluation: dict[str, Any], mode: str) -> int:
    recommended = max(1, min(len(candidates), int(evaluation.get("recommended", 1))))
    print(f"\nGenerated {len(candidates)} candidates. Recommended: {recommended}\n")
    for index, candidate in enumerate(candidates, 1):
        first_line = next((line.strip() for line in candidate.splitlines() if line.strip()), "")
        marker = " ★" if index == recommended else ""
        print(f"  {index}. {first_line[:110]}{marker}")
    if mode == "auto":
        return recommended - 1
    answer = input(f"Choose 1-{len(candidates)} [Enter accepts {recommended}]: ").strip()
    if not answer:
        return recommended - 1
    try:
        selected = int(answer)
    except ValueError:
        return recommended - 1
    return selected - 1 if 1 <= selected <= len(candidates) else recommended - 1


def _review(
    text: str,
    *,
    engine: AIEngine,
    profile: dict[str, Any] | None,
    platform_name: str,
    content_label: str,
    language: str,
    audience: str,
    tone: str,
    provider: str | None,
    model: str | None,
    no_fallback: bool,
    workspace: str | Path | None,
) -> tuple[str, GenerationResult]:
    prompt = load_prompt(
        "review",
        workspace,
        profile_context=context_text(profile),
        platform_name=platform_name,
        content_label=content_label,
        language=language,
        audience=audience,
        tone=tone,
        content=text,
    )
    result = engine.generate("review", prompt, provider=provider, model=model, no_fallback=no_fallback)
    return clean_response(result.text), result


def available_extras(platform: str, primary_type: str, workspace: str | Path | None = None) -> list[str]:
    _, platform_spec = resolve_platform(platform, workspace)
    preferred = ["caption", "hashtags", "title", "hook", "thumbnail", "shot_list", "on_screen_text", "cta", "story", "description", "tags"]
    types = list(platform_spec.get("types", {}))
    ordered = [item for item in preferred if item in types and item != primary_type]
    ordered.extend(item for item in types if item != primary_type and item not in ordered)
    return ordered


def _choose_extras(platform: str, primary_type: str, workspace: str | Path | None = None) -> list[str]:
    extras = available_extras(platform, primary_type, workspace)
    if not extras:
        return []
    print("\nGenerate supporting content?")
    for index, item in enumerate(extras, 1):
        print(f"  {index}. {item.replace('_', ' ').title()}")
    print("  A. Generate all")
    print("  0. Finish")
    raw = input("Choose numbers, ranges, or A: ").strip().lower()
    if raw in {"", "0", "none"}:
        return []
    if raw in {"a", "all"}:
        return extras
    selected: set[int] = set()
    for part in raw.split(","):
        part = part.strip()
        if "-" in part:
            try:
                start, end = (int(value) for value in part.split("-", 1))
            except ValueError:
                continue
            selected.update(range(start, end + 1))
        else:
            try:
                selected.add(int(part))
            except ValueError:
                continue
    return [item for index, item in enumerate(extras, 1) if index in selected]


def _generate_one(
    platform: str,
    content_type: str,
    *,
    topic: str,
    engine: AIEngine,
    profile: dict[str, Any] | None,
    config: dict[str, Any],
    language_code: str,
    language_name: str,
    audience: str,
    tone: str,
    extra_instructions: str,
    provider: str | None,
    model: str | None,
    no_fallback: bool,
    variants: int,
    selection_mode: str,
    review: bool,
    interactive: bool,
    workspace: str | Path | None,
) -> tuple[str, list[str], int, dict[str, Any], GenerationResult, GenerationResult | None, str, str, dict[str, Any], dict[str, Any]]:
    platform_key, type_key, platform_spec, specification = resolve_content_type(platform, content_type, workspace)
    base_prompt = _base_prompt(
        workspace=workspace,
        profile=profile,
        platform_key=platform_key,
        platform_spec=platform_spec,
        type_key=type_key,
        specification=specification,
        topic=topic,
        language_code=language_code,
        language_name=language_name,
        audience=audience,
        tone=tone,
        extra_instructions=extra_instructions,
    )
    task = str(specification.get("task", "writing"))
    if variants > 1:
        prompt = load_prompt("variants", workspace, count=variants, base_prompt=base_prompt)
        generated = engine.generate(task, prompt, provider=provider, model=model, no_fallback=no_fallback)
        candidates = _parse_candidates(generated.text, variants)
    else:
        prompt = base_prompt
        generated = engine.generate(task, prompt, provider=provider, model=model, no_fallback=no_fallback)
        candidates = [clean_response(generated.text)]
    candidates = [clean_response(item) for item in candidates if clean_response(item)]
    if not candidates:
        raise ConfigurationError("The model returned no usable content candidates.")
    evaluation = _evaluate(
        candidates,
        engine=engine,
        profile=profile,
        platform_name=str(platform_spec.get("name", platform_key)),
        content_label=str(specification.get("label", type_key)),
        topic=topic,
        language=language_name,
        workspace=workspace,
    ) if len(candidates) > 1 else {"recommended": 1, "scores": [], "method": "single_candidate"}
    selected_index = _choose_interactively(candidates, evaluation, selection_mode) if interactive and len(candidates) > 1 else max(0, min(len(candidates) - 1, int(evaluation.get("recommended", 1)) - 1))
    text = candidates[selected_index]
    review_result: GenerationResult | None = None
    if review:
        text, review_result = _review(
            text,
            engine=engine,
            profile=profile,
            platform_name=str(platform_spec.get("name", platform_key)),
            content_label=str(specification.get("label", type_key)),
            language=language_name,
            audience=audience,
            tone=tone,
            provider=provider,
            model=model,
            no_fallback=no_fallback,
            workspace=workspace,
        )
    return text, candidates, selected_index, evaluation, generated, review_result, platform_key, type_key, platform_spec, specification


def generate(
    platform: str,
    content_type: str | None = None,
    *,
    topic: str,
    language: str | None = None,
    audience: str | None = None,
    tone: str | None = None,
    extra_instructions: str = "None.",
    provider: str | None = None,
    model: str | None = None,
    no_fallback: bool = False,
    review: bool | None = None,
    variants: int | None = None,
    selection_mode: str | None = None,
    extras: list[str] | None = None,
    ask_extras: bool | None = None,
    interactive: bool = False,
    profile_slug: str | None = None,
    no_profile: bool = False,
    output: str | Path | None = None,
    workspace: str | Path | None = None,
    engine: AIEngine | None = None,
) -> ContentResult:
    config = load_config(workspace)
    profile = _resolve_profile(workspace, profile_slug=profile_slug, no_profile=no_profile)
    if content_type is None:
        _, platform_spec = resolve_platform(platform, workspace)
        content_type = str(platform_spec.get("default_type", "post"))
    platform_key, type_key, _, _ = resolve_content_type(platform, content_type, workspace)
    language_code, language_name = normalize_language(language, profile, config)
    audience = audience or str((profile or {}).get("audience", {}).get("description") or config.get("default_audience", "General audience"))
    identity = (profile or {}).get("identity", {})
    personality = ", ".join(identity.get("personality", []))
    tone = tone or personality or str(config.get("default_tone", "Clear, engaging, and natural"))
    profile_content = (profile or {}).get("content", {})
    variants = int(variants if variants is not None else profile_content.get("variants", config.get("generation", {}).get("variants", 5)))
    if variants not in {1, 3, 5, 10}:
        raise ConfigurationError("Variants must be one of: 1, 3, 5, 10.")
    selection_mode = str(selection_mode or profile_content.get("selection_mode") or config.get("generation", {}).get("selection_mode", "hybrid"))
    if selection_mode not in {"manual", "auto", "hybrid"}:
        raise ConfigurationError("Selection mode must be manual, auto, or hybrid.")
    review = bool(profile_content.get("review", config.get("generation", {}).get("review_by_default", True))) if review is None else review
    ask_extras = bool(profile_content.get("ask_for_extras", config.get("generation", {}).get("ask_for_extras", True))) if ask_extras is None else ask_extras

    profile_slug_value = str((profile or {}).get("slug") or "no-profile")
    folder = create_generation_dir(profile_slug_value, platform_key, type_key, topic, workspace) if output is None else Path(output).expanduser().parent

    owned_engine = engine is None
    engine = engine or AIEngine(config)
    failed = True
    try:
        (
            text,
            candidates,
            selected_index,
            evaluation,
            generated,
            review_result,
            platform_key,
            type_key,
            platform_spec,
            specification,
        ) = _generate_one(
            platform_key,
            type_key,
            topic=topic,
            engine=engine,
            profile=profile,
            config=config,
            language_code=language_code,
            language_name=language_name,
            audience=audience,
            tone=tone,
            extra_instructions=extra_instructions,
            provider=provider,
            model=model,
            no_fallback=no_fallback,
            variants=variants,
            selection_mode=selection_mode,
            review=review,
            interactive=interactive,
            workspace=workspace,
        )
        chosen_extras = list(extras or [])
        if interactive and extras is None and ask_extras:
            chosen_extras = _choose_extras(platform_key, type_key, workspace)
        extra_paths: list[Path] = []
        if output is None:
            for extra_type in chosen_extras:
                if extra_type == type_key:
                    continue
                (
                    extra_text,
                    extra_candidates,
                    extra_selected_index,
                    extra_evaluation,
                    extra_generated,
                    extra_review,
                    _,
                    resolved_extra,
                    _,
                    _,
                ) = _generate_one(
                    platform_key,
                    extra_type,
                    topic=topic,
                    engine=engine,
                    profile=profile,
                    config=config,
                    language_code=language_code,
                    language_name=language_name,
                    audience=audience,
                    tone=tone,
                    extra_instructions=f"Support the selected primary {type_key}.\n\nPRIMARY CONTENT:\n{text}",
                    provider=provider,
                    model=model,
                    no_fallback=no_fallback,
                    variants=variants,
                    selection_mode=selection_mode,
                    review=review,
                    interactive=interactive,
                    workspace=workspace,
                )
                extra_folder = folder / "extras" / resolved_extra
                extra_path = save_generation(
                    extra_folder,
                    extra_text,
                    metadata={
                        "schema_version": 3,
                        "profile_slug": profile_slug_value,
                        "platform": platform_key,
                        "content_type": resolved_extra,
                        "topic": topic,
                        "supporting": type_key,
                        "generation_provider": extra_generated.provider,
                        "generation_model": extra_generated.model,
                        "review_provider": extra_review.provider if extra_review else None,
                        "review_model": extra_review.model if extra_review else None,
                    },
                    candidates=extra_candidates,
                    selected_index=extra_selected_index,
                    evaluation=extra_evaluation,
                    profile_snapshot=profile,
                )
                extra_paths.append(extra_path)

        final_generation = review_result or generated
        metadata = {
            "schema_version": 3,
            "profile": (profile or {}).get("name"),
            "profile_slug": profile_slug_value,
            "platform": platform_key,
            "content_type": type_key,
            "topic": topic,
            "task": specification.get("task", "writing"),
            "generation_provider": generated.provider,
            "generation_model": generated.model,
            "generation_fallback_attempts": list(generated.attempts),
            "review_provider": review_result.provider if review_result else None,
            "review_model": review_result.model if review_result else None,
            "final_provider": final_generation.provider,
            "final_model": final_generation.model,
            "reviewed": review,
            "language_code": language_code,
            "language": language_name,
            "audience": audience,
            "tone": tone,
            "variants_requested": variants,
            "variants_generated": len(candidates),
            "selection_mode": selection_mode,
            "extras": [path.parent.name for path in extra_paths],
        }
        if output is None:
            path = save_generation(
                folder,
                text,
                metadata=metadata,
                candidates=candidates,
                selected_index=selected_index,
                evaluation=evaluation,
                profile_snapshot=profile,
                prompt=_base_prompt(
                    workspace=workspace,
                    profile=profile,
                    platform_key=platform_key,
                    platform_spec=platform_spec,
                    type_key=type_key,
                    specification=specification,
                    topic=topic,
                    language_code=language_code,
                    language_name=language_name,
                    audience=audience,
                    tone=tone,
                    extra_instructions=extra_instructions,
                ),
            )
        else:
            path = Path(output).expanduser()
            if not path.is_absolute():
                path = Path.cwd() / path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text.rstrip() + "\n", encoding="utf-8")
            write_json(path.with_suffix(".json"), metadata)
            folder = path.parent
        # Every generated script is checked immediately. The report is stored
        # even in manual mode so a later `ace status` can explain failures.
        if output is None:
            try:
                from ace.quality import run_script_quality
                quality_report = run_script_quality(folder, workspace=workspace, use_ai=bool(review), engine=engine)
                metadata_path = folder / "metadata.json"
                stored_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
                stored_metadata["quality_status"] = quality_report.status
                stored_metadata["quality_score"] = quality_report.score
                write_json(metadata_path, stored_metadata)
            except Exception as exc:
                write_json(folder / "quality" / "script-report.json", {
                    "status": "warning", "score": 0, "critical": [],
                    "warnings": [f"Quality checker could not complete: {exc}"], "checks": {},
                })
        if output is None:
            try:
                from ace.account_memory import record_generation
                record_generation(folder, workspace)
            except Exception:
                pass
        failed = False
        return ContentResult(
            platform=platform_key,
            content_type=type_key,
            topic=topic,
            text=text,
            path=path,
            folder=folder,
            provider=final_generation.provider,
            model=final_generation.model,
            reviewed=review,
            candidates=tuple(candidates),
            selected_index=selected_index,
            extras=tuple(extra_paths),
        )
    finally:
        if owned_engine:
            engine.close(failed=failed)


def generate_pack(
    platform: str,
    *,
    topic: str,
    types: list[str] | None = None,
    language: str | None = None,
    audience: str | None = None,
    tone: str | None = None,
    extra_instructions: str = "None.",
    provider: str | None = None,
    model: str | None = None,
    no_fallback: bool = False,
    review: bool | None = None,
    workspace: str | Path | None = None,
    output_dir: str | Path | None = None,
    profile_slug: str | None = None,
    no_profile: bool = False,
) -> list[ContentResult]:
    selected_types = types or default_pack(platform, workspace)
    if not selected_types:
        raise ConfigurationError(f"No content types are configured for platform '{platform}'.")
    profile = _resolve_profile(workspace, profile_slug=profile_slug, no_profile=no_profile)
    platform_key, _, _, _ = resolve_content_type(platform, selected_types[0], workspace)
    folder = Path(output_dir) if output_dir else create_pack_dir(platform_key, topic, workspace, str((profile or {}).get("slug") or "no-profile"))
    folder.mkdir(parents=True, exist_ok=True)
    results: list[ContentResult] = []
    for selected_type in selected_types:
        result = generate(
            platform_key,
            selected_type,
            topic=topic,
            language=language,
            audience=audience,
            tone=tone,
            extra_instructions=extra_instructions,
            provider=provider,
            model=model,
            no_fallback=no_fallback,
            review=review,
            variants=1,
            ask_extras=False,
            interactive=False,
            profile_slug=(profile or {}).get("slug"),
            no_profile=profile is None,
            output=folder / f"{selected_type}.md",
            workspace=workspace,
        )
        results.append(result)
    return results


def localize(
    source: str | Path,
    target_language: str,
    *,
    workspace: str | Path | None = None,
    profile_slug: str | None = None,
    no_profile: bool = False,
    provider: str | None = None,
    model: str | None = None,
) -> Path:
    from ace.storage import resolve_generation

    profile = _resolve_profile(workspace, profile_slug=profile_slug, no_profile=no_profile)
    config = load_config(workspace)
    language_code, language_name = normalize_language(target_language, profile, config)
    source_path = Path(source).expanduser()
    if str(source).lower() == "last" or not source_path.exists():
        folder = resolve_generation(source, workspace)
        source_path = folder / "selected.md"
    else:
        folder = source_path.parent
    content = source_path.read_text(encoding="utf-8")
    prompt = load_prompt(
        "localize",
        workspace,
        target_language=language_name,
        profile_context=context_text(profile),
        language_instruction=language_instruction(language_code, profile, config),
        content=content,
    )
    with AIEngine(config) as engine:
        result = engine.generate("translation", prompt, provider=provider, model=model)
    text = clean_response(result.text)
    output = folder / f"localized-{language_code}.md"
    output.write_text(text.rstrip() + "\n", encoding="utf-8")
    return output
