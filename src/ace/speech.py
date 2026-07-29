from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ace.ai import AIEngine
from ace.config import load as load_config
from ace.errors import ACEError
from ace.profile import load as load_profile
from ace.script_cleaner import clean_narration
from ace.storage import resolve_generation, write_json

DEFAULT_PRONUNCIATIONS = {
    "API": "A P I",
    "APIs": "A P I's",
    "SQL": "S Q L",
    "GPU": "G P U",
    "CPU": "C P U",
    "RAM": "ram",
    "URL": "U R L",
    "URLs": "U R Ls",
    "HTTP": "H T T P",
    "HTTPS": "H T T P S",
    "CVE": "C V E",
    "CVEs": "C V Es",
    "AI": "A I",
    "TTS": "text to speech",
    "FFmpeg": "F F m peg",
    "NVIDIA": "en vid ee uh",
}


def _profile_for_folder(folder: Path, workspace: str | Path | None) -> dict[str, Any] | None:
    try:
        metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
        slug = metadata.get("profile_slug")
        return load_profile(str(slug), workspace) if slug else None
    except Exception:
        return None


def normalize_for_speech(text: str, profile: dict[str, Any] | None = None) -> str:
    value = clean_narration(text)
    value = re.sub(r"https?://\S+|www\.\S+", "", value)
    value = re.sub(r"(?m)^\s*#+\s*", "", value)
    value = re.sub(r"(?m)^\s*[-*•]\s+", "", value)
    value = re.sub(r"(?im)^\s*(?:host|narrator|speaker|voiceover|script|hook|intro|outro)\s*:?[ \t]*$", "", value)
    value = re.sub(r"(?m)^\s*(?:CTA|CALL TO ACTION)\s*:\s*", "", value, flags=re.IGNORECASE)
    value = re.sub(r"(?im)^\s*\[(?:intro|outro|hook|scene|cut|b-roll|music|pause)[^\]]*\]\s*$", "", value)
    value = value.replace("“", "").replace("”", "").replace('"', "")
    value = value.replace("‘", "'").replace("’", "'")
    value = re.sub(r"#([\w-]+)", r"\1", value)
    # Most emoji are visual instructions, not narration.
    value = re.sub(r"[\U0001F000-\U0001FAFF\u2600-\u27BF]", "", value)
    pronunciations = dict(DEFAULT_PRONUNCIATIONS)
    pronunciations.update((profile or {}).get("voice", {}).get("pronunciations", {}))
    for source, spoken in sorted(pronunciations.items(), key=lambda item: -len(str(item[0]))):
        value = re.sub(rf"\b{re.escape(str(source))}\b", str(spoken), value)
    value = re.sub(r"\s+([,.;!?؟])", r"\1", value)
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value).strip()
    return value


def _ai_spoken_rewrite(text: str, profile: dict[str, Any] | None, workspace: str | Path | None, engine: AIEngine | None = None) -> tuple[str, str | None, str | None]:
    prompt = (
        "Rewrite the following approved social-media script for natural speech synthesis.\n"
        "Return only the spoken words. No headings, labels, markdown, quotation marks, emojis, URLs, hashtags, "
        "stage directions, or explanations. Preserve factual meaning and account personality. Use short, natural "
        "sentences and conversational pauses. Do not add new claims.\n\n"
        f"ACCOUNT VOICE:\n{json.dumps((profile or {}).get('identity', {}), ensure_ascii=False)}\n\n"
        f"SCRIPT:\n{text}"
    )
    try:
        if engine is None:
            with AIEngine.from_workspace(workspace) as owned:
                result = owned.generate("tts", prompt, temperature=0.2, max_output_tokens=3500)
        else:
            result = engine.generate("tts", prompt, temperature=0.2, max_output_tokens=3500)
        return normalize_for_speech(result.text, profile), result.provider, result.model
    except ACEError:
        return normalize_for_speech(text, profile), None, None


def prepare_tts_script(
    generation: str | Path,
    *,
    workspace: str | Path | None = None,
    use_ai: bool = True,
    engine: AIEngine | None = None,
) -> Path:
    folder = resolve_generation(generation, workspace)
    selected = folder / "selected.md"
    if not selected.exists():
        raise FileNotFoundError(f"Selected script not found: {selected}")
    profile = _profile_for_folder(folder, workspace)
    original = selected.read_text(encoding="utf-8")
    if use_ai:
        spoken, provider, model = _ai_spoken_rewrite(original, profile, workspace, engine)
    else:
        spoken, provider, model = normalize_for_speech(original, profile), None, None
    if not spoken:
        raise ValueError("No TTS-ready text remains after speech preparation.")
    script_dir = folder / "script"
    script_dir.mkdir(parents=True, exist_ok=True)
    output = script_dir / "tts-ready.txt"
    output.write_text(spoken.rstrip() + "\n", encoding="utf-8")
    report = {
        "status": "ready",
        "source": str(selected),
        "output": str(output),
        "ai_rewrite": bool(provider),
        "provider": provider,
        "model": model,
        "characters": len(spoken),
        "forbidden_artifacts": {
            "markdown_heading": bool(re.search(r"(?m)^#", spoken)),
            "stage_direction": bool(re.search(r"\[[^\]]+\]", spoken)),
            "url": bool(re.search(r"https?://", spoken)),
            "double_quote": '"' in spoken,
        },
    }
    write_json(folder / "quality" / "tts-report.json", report)
    return output
