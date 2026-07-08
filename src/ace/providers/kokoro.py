from pathlib import Path

import numpy as np
import soundfile as sf
from kokoro import KPipeline


_pipeline = KPipeline(
    lang_code="a",
)


def generate(text, output, voice="af_heart"):
    output = Path(output)

    output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    generator = _pipeline(
        text,
        voice=voice,
    )

    audio_chunks = []

    for result in generator:
        audio = result.output.audio.numpy()
        audio_chunks.append(audio)

    if not audio_chunks:
        raise RuntimeError("No audio was generated.")

    audio = np.concatenate(audio_chunks)

    sf.write(
        output,
        audio,
        24000,
    )

    return output
