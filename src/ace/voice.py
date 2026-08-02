from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from ace.accounts import load as load_account
from ace.secrets import get as get_secret
from ace.storage import metadata, resolve_generation
from ace.utils import ensure_dir, write_json


def prepare_text(text: str) -> str:
    value = re.sub(r"(?m)^#{1,6}\s+", "", text)
    value = re.sub(r"(?im)^\s*(?:host|narrator|scene|b-roll|music)\s*:\s*", "", value)
    value = re.sub(r"https?://\S+", "the linked source", value)
    value = value.replace("```", "")
    value = re.sub(r"\[([^\]]+)\]", r"\1", value)
    value = re.sub(r"\s+", " ", value).strip()
    return value


def prepare(generation: str | Path, workspace: str | Path | None = None) -> Path:
    folder = resolve_generation(generation, workspace)
    source = folder / "selected.md"
    if not source.exists():
        raise FileNotFoundError("selected.md is missing")
    output = ensure_dir(folder / "script") / "tts-ready.txt"
    output.write_text(prepare_text(source.read_text(encoding="utf-8")) + "\n", encoding="utf-8")
    return output


def _kokoro(text: str, output: Path, voice_id: str, language: str) -> tuple[str, str]:
    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as exc:
        raise RuntimeError("Kokoro is not installed. Install ACE with '.[voice]'.") from exc
    lang_code = {"en": "a", "fr": "f", "ar": "a"}.get(language.lower(), "a")
    pipeline = KPipeline(lang_code=lang_code)
    chunks = []
    for _graphemes, _phonemes, audio in pipeline(text, voice=voice_id):
        chunks.append(audio)
    if not chunks:
        raise RuntimeError("Kokoro produced no audio.")
    combined = np.concatenate(chunks)
    sf.write(output, combined, 24000)
    return "kokoro", voice_id


def _piper(text: str, output: Path, voice_id: str) -> tuple[str, str]:
    executable = shutil.which("piper")
    if not executable:
        raise RuntimeError("Piper is not installed.")
    result = subprocess.run([executable, "--model", voice_id, "--output_file", str(output)], input=text, text=True, capture_output=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "Piper failed")
    return "piper", voice_id


def _openai_tts(text: str, output: Path, voice_id: str, model: str, workspace: str | Path | None) -> tuple[str, str]:
    from ace.http import request
    key = get_secret("OPENAI_API_KEY", workspace)
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing.")
    response = request(
        "POST",
        "https://api.openai.com/v1/audio/speech",
        headers={"Authorization": f"Bearer {key}"},
        json_body={"model": model, "voice": voice_id, "input": text, "format": "wav"},
        timeout=120,
        retries=1,
    )
    output.write_bytes(response.body)
    return "openai", voice_id


def generate(generation: str | Path, workspace: str | Path | None = None, *, provider: str | None = None, voice_id: str | None = None) -> Path:
    folder = resolve_generation(generation, workspace)
    info = metadata(folder)
    account = load_account(str(info.get("account_slug")), workspace)
    voice = account.get("voice", {})
    provider = provider or str(voice.get("provider") or "kokoro")
    voice_id = voice_id or str(voice.get("voice_id") or "af_sarah")
    language = str(info.get("language") or account.get("languages", {}).get("primary") or "en")
    tts = folder / "script" / "tts-ready.txt"
    if not tts.exists():
        tts = prepare(folder, workspace)
    text = tts.read_text(encoding="utf-8").strip()
    output = ensure_dir(folder / "voice") / "narration.wav"
    if provider == "kokoro":
        actual_provider, actual_voice = _kokoro(text, output, voice_id, language)
    elif provider == "piper":
        actual_provider, actual_voice = _piper(text, output, voice_id)
    elif provider == "openai":
        actual_provider, actual_voice = _openai_tts(text, output, voice_id, str(voice.get("model") or "gpt-4o-mini-tts"), workspace)
    else:
        raise ValueError(f"Unsupported voice provider: {provider}")
    write_json(
        folder / "quality" / "voice-report.json",
        {
            "status": "passed",
            "requested": {"provider": provider, "voice_id": voice_id},
            "actual": {"provider": actual_provider, "voice_id": actual_voice},
            "match": provider == actual_provider and voice_id == actual_voice,
            "path": str(output),
        },
    )
    return output


def create_test_tone(output: str | Path, duration: float = 8.0) -> Path:
    target = Path(output)
    ensure_dir(target.parent)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required for the test tone.")
    result = subprocess.run(
        [ffmpeg, "-y", "-f", "lavfi", "-i", "sine=frequency=220:sample_rate=24000", "-t", str(duration), "-af", "volume=-24dB", str(target)],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-2000:])
    return target
