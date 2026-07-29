from __future__ import annotations

import gc
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ace.config import load
from ace.errors import ACEError, ConfigurationError, ProviderRequestError
from ace.paths import cache_home, data_home, workspace_root
from ace.profile import active as active_profile
from ace.profile import profile_path
from ace.profile import save as save_profile
from ace.providers.kokoro import generate as kokoro_generate
from ace.providers.kokoro import unload as kokoro_unload
from ace.providers.piper import generate as piper_generate
from ace.providers.pocket_tts import generate as pocket_generate
from ace.providers.pocket_tts import unload as pocket_unload
from ace.providers.openai_tts import generate as openai_tts_generate
from ace.script_cleaner import clean_narration
from ace.speech import normalize_for_speech


DEFAULT_AUDITION_TEXT = {
    "en": (
        "Welcome. Today I will show you a simple idea that can change the way you work. "
        "Are you ready? Follow the steps, stay focused, and let us begin."
    ),
    "fr": (
        "Bienvenue. Aujourd'hui, je vais vous montrer une idée simple qui peut changer votre façon de travailler. "
        "Vous êtes prêt ? Suivez les étapes, restez concentré, et commençons."
    ),
    "ar": (
        "أهلاً وسهلاً. اليوم سأشارك معكم فكرة بسيطة يمكن أن تغيّر طريقة عملكم. "
        "هل أنتم مستعدون؟ ركّزوا معي، واتبعوا الخطوات، ولنبدأ."
    ),
}


def generate_voice(
    text: str,
    output: str | Path,
    *,
    workspace: str | Path | None = None,
    provider: str | None = None,
    model: str | None = None,
    language: str | None = None,
    instructions: str | None = None,
) -> tuple[Path, str, str]:
    root = data_home(workspace)
    config = load(workspace)
    routes: list[dict[str, Any]] = list(config.get("voice", {}).get("routes", []))
    language_code = (language or "en").lower()
    if not provider and not model:
        try:
            account = active_profile(workspace, required=False)
        except Exception:
            account = None
        if account and account.get("voice", {}).get("configured"):
            voice_config = account["voice"]
            override = voice_config.get("language_overrides", {}).get(language_code, {})
            selected_provider = override.get("provider") or voice_config.get("provider")
            selected_model = override.get("voice_id") or voice_config.get("voice_id")
            if selected_provider and selected_model:
                selected = {"provider": selected_provider, "model": selected_model}
                routes = [selected, *(route for route in routes if route != selected)]

    if provider or model:
        if not provider or not model:
            raise ProviderRequestError("Voice provider and model must be supplied together.")
        selected = {"provider": provider, "model": model}
        routes = [selected, *(route for route in routes if route != selected)]

    narration = normalize_for_speech(clean_narration(text))
    if not narration:
        raise ProviderRequestError("No narration text remains after cleanup.")

    attempts: list[str] = []
    for route in routes:
        route_provider = str(route.get("provider", ""))
        route_model = str(route.get("model", ""))
        label = f"{route_provider}/{route_model}"
        try:
            if route_provider == "piper":
                path = piper_generate(
                    narration,
                    output,
                    model=route_model,
                    workspace=root,
                )
            elif route_provider == "kokoro":
                path = kokoro_generate(narration, output, voice=route_model)
            elif route_provider == "pocket_tts":
                path = pocket_generate(narration, output, voice=route_model, language=language_code)
            elif route_provider == "openai_tts":
                if ":" in route_model:
                    tts_model, voice_id = route_model.split(":", 1)
                else:
                    tts_model, voice_id = "gpt-4o-mini-tts", route_model
                path = openai_tts_generate(narration, output, model=tts_model, voice=voice_id, instructions=instructions)
            else:
                attempts.append(f"{label}: unsupported voice provider")
                continue
        except ACEError as exc:
            attempts.append(f"{label}: {exc}")
            continue
        return path, route_provider, route_model

    details = "\n".join(f"  - {attempt}" for attempt in attempts)
    raise ProviderRequestError(f"All voice providers failed.\n{details}")


def available_voice_models(
    provider: str,
    *,
    workspace: str | Path | None = None,
) -> list[str]:
    config = load(workspace)
    voice_config = config.get("voice", {})
    if provider == "kokoro":
        configured = voice_config.get("catalog", {}).get("kokoro", [])
        return [str(item) for item in configured if str(item).strip()]
    if provider == "pocket_tts":
        configured = voice_config.get("catalog", {}).get("pocket_tts", [])
        return [str(item) for item in configured if str(item).strip()]
    if provider == "openai_tts":
        configured = voice_config.get("catalog", {}).get("openai_tts", [])
        return [str(item) for item in configured if str(item).strip()]
    if provider == "piper":
        root = data_home(workspace) / "models" / "piper"
        return [str(path.relative_to(root)) for path in sorted(root.rglob("*.onnx"))] if root.exists() else []
    return []


def _play(path: Path) -> bool:
    candidates = [
        ("ffplay", ["-nodisp", "-autoexit", "-loglevel", "error"]),
        ("paplay", []),
        ("aplay", []),
    ]
    for executable, flags in candidates:
        program = shutil.which(executable)
        if not program:
            continue
        subprocess.run([program, *flags, str(path)], check=False)
        return True
    return False


def audition_voice(
    *,
    workspace: str | Path | None = None,
    provider: str | None = None,
    voices: list[str] | None = None,
    language: str | None = None,
    text: str | None = None,
    select: int | None = None,
    keep_samples: bool = False,
    interactive: bool = True,
) -> dict[str, Any]:
    profile = active_profile(workspace)
    language_code = (language or profile.get("languages", {}).get("primary") or "en").lower()
    provider = provider or str(load(workspace).get("voice", {}).get("routes", [{}])[0].get("provider", "kokoro"))
    voices = voices or available_voice_models(provider, workspace=workspace)
    if not voices:
        raise ConfigurationError(
            f"No {provider} voices were found. Install/configure a voice model or pass --voices."
        )
    script = text or DEFAULT_AUDITION_TEXT.get(language_code, DEFAULT_AUDITION_TEXT["en"])
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    audition_dir = cache_home(workspace) / "voice-auditions" / str(profile["slug"]) / timestamp
    audition_dir.mkdir(parents=True, exist_ok=True)
    (audition_dir / "test-script.txt").write_text(script.rstrip() + "\n", encoding="utf-8")

    generated: list[tuple[str, Path]] = []
    failures: list[str] = []
    try:
        for index, voice in enumerate(voices, 1):
            output = audition_dir / f"{index:02d}-{voice.replace('/', '_')}.wav"
            try:
                path, _, _ = generate_voice(
                    script,
                    output,
                    workspace=workspace,
                    provider=provider,
                    model=voice,
                    language=language_code,
                )
            except ACEError as exc:
                failures.append(f"{voice}: {exc}")
                continue
            generated.append((voice, path))

        if not generated:
            details = "\n".join(f"  - {failure}" for failure in failures)
            raise ProviderRequestError(f"No audition sample could be generated.\n{details}")

        selected_index = select
        if selected_index is None and interactive and sys.stdin.isatty():
            print("\nVoice audition samples:")
            for index, (voice, path) in enumerate(generated, 1):
                print(f"  {index}. {voice}")
                _play(path)
            raw = input(f"Choose a voice [1-{len(generated)}, default 1]: ").strip()
            try:
                selected_index = int(raw) if raw else 1
            except ValueError:
                selected_index = 1
        selected_index = selected_index or 1
        if not 1 <= selected_index <= len(generated):
            raise ConfigurationError(f"Voice selection must be between 1 and {len(generated)}.")

        selected_voice, selected_path = generated[selected_index - 1]
        profile_dir = profile_path(str(profile["slug"]), workspace).parent
        final_sample = profile_dir / "voice-sample.wav"
        final_sample.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(selected_path, final_sample)
        profile["voice"].update(
            {
                "configured": True,
                "provider": provider,
                "voice_id": selected_voice,
                "sample": str(final_sample),
            }
        )
        profile["voice"].setdefault("language_overrides", {})
        profile["voice"]["language_overrides"][language_code] = {
            "provider": provider,
            "voice_id": selected_voice,
        }
        save_profile(profile, workspace)

        manifest = {
            "profile": profile["slug"],
            "provider": provider,
            "language": language_code,
            "selected_voice": selected_voice,
            "selected_sample": str(final_sample),
            "tested_voices": [voice for voice, _ in generated],
            "failures": failures,
        }
        (profile_dir / "voice-audition.json").write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        if keep_samples:
            kept = profile_dir / "voice-auditions" / timestamp
            kept.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(audition_dir), str(kept))
            manifest["audition_folder"] = str(kept)
        else:
            shutil.rmtree(audition_dir, ignore_errors=True)
        return manifest
    finally:
        if provider == "kokoro":
            kokoro_unload()
        elif provider == "pocket_tts":
            pocket_unload()
        gc.collect()


def available_voice_providers(workspace: str | Path | None = None) -> list[str]:
    providers: list[str] = []
    config = load(workspace)
    for route in config.get("voice", {}).get("routes", []):
        if isinstance(route, dict) and route.get("provider"):
            name = str(route["provider"])
            if name not in providers:
                providers.append(name)
    for name in ("pocket_tts", "kokoro", "piper", "openai_tts"):
        if name not in providers:
            providers.append(name)
    return providers


def run(project_path: str | Path, workspace: str | Path | None = None) -> Path | None:
    project = Path(project_path)
    candidates = [project / "content" / "main.md", project / "scripts" / "script.md"]
    script = next((path for path in candidates if path.exists()), None)
    if script is None:
        print("Script/content file not found.")
        return None

    output = project / "voice" / "voice.wav"
    path, provider, model = generate_voice(
        script.read_text(encoding="utf-8"),
        output,
        workspace=workspace,
    )
    print(f"Voice generated with {provider}/{model}: {path}")
    return path
