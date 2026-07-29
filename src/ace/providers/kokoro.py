from __future__ import annotations

from pathlib import Path

from ace.errors import ProviderRequestError, ProviderUnavailable


_pipeline = None


def generate(text: str, output: str | Path, voice: str = "af_heart") -> Path:
    """Generate speech with a lazily loaded, reusable Kokoro pipeline."""

    global _pipeline

    try:
        import numpy as np
        import soundfile as sf
        from kokoro import KPipeline
    except ImportError as exc:
        raise ProviderUnavailable(
            "Kokoro voice dependencies are not installed. Install ACE with the voice extra."
        ) from exc

    if _pipeline is None:
        _pipeline = KPipeline(lang_code="a")

    output_path = Path(output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    audio_chunks = []
    try:
        generator = _pipeline(text, voice=voice)
        for result in generator:
            audio = result.output.audio.numpy()
            audio_chunks.append(audio)
    except Exception as exc:  # third-party model errors vary
        raise ProviderRequestError(f"Kokoro generation failed: {exc}") from exc

    if not audio_chunks:
        raise ProviderRequestError("Kokoro generated no audio.")

    sf.write(output_path, np.concatenate(audio_chunks), 24000)
    return output_path


def unload() -> None:
    """Release the cached Kokoro pipeline after an audition or explicit cleanup."""

    global _pipeline
    _pipeline = None
