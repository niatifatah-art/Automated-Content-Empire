from __future__ import annotations

import gc
from pathlib import Path
from typing import Any

from ace.errors import ProviderUnavailable, ProviderRequestError

_models: dict[str, Any] = {}
_voice_states: dict[tuple[str, str], Any] = {}

LANGUAGE_MAP = {
    "en": "english",
    "eng": "english",
    "fr": "french",
    "de": "german",
    "pt": "portuguese",
    "it": "italian",
    "es": "spanish",
}


def generate(
    text: str,
    output: str | Path,
    *,
    voice: str = "alba",
    language: str = "en",
) -> Path:
    try:
        from pocket_tts import TTSModel
        import scipy.io.wavfile
    except ImportError as exc:
        raise ProviderUnavailable(
            "Pocket TTS is not installed. Run: python -m pip install -e '.[pocket-tts]'"
        ) from exc

    language_name = LANGUAGE_MAP.get(language.lower(), language.lower())
    if language_name not in set(LANGUAGE_MAP.values()):
        raise ProviderUnavailable(f"Pocket TTS does not support language '{language}'.")
    try:
        model = _models.get(language_name)
        if model is None:
            try:
                model = TTSModel.load_model(language=language_name)
            except TypeError:
                model = TTSModel.load_model()
            _models[language_name] = model
        key = (language_name, voice)
        state = _voice_states.get(key)
        if state is None:
            state = model.get_state_for_audio_prompt(voice)
            _voice_states[key] = state
        audio = model.generate_audio(state, text)
        path = Path(output)
        path.parent.mkdir(parents=True, exist_ok=True)
        array = audio.detach().cpu().numpy() if hasattr(audio, "detach") else audio.numpy()
        scipy.io.wavfile.write(str(path), int(model.sample_rate), array)
        return path
    except ProviderUnavailable:
        raise
    except Exception as exc:
        raise ProviderRequestError(f"Pocket TTS generation failed: {exc}") from exc


def unload() -> None:
    _models.clear()
    _voice_states.clear()
    gc.collect()
