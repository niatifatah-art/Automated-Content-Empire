from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from ace.errors import ProviderUnavailable, ProviderRequestError


def generate(
    text: str,
    output: str | Path,
    *,
    model: str = "gpt-4o-mini-tts",
    voice: str = "coral",
    instructions: str | None = None,
    base_url: str = "https://api.openai.com/v1",
) -> Path:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise ProviderUnavailable("OPENAI_API_KEY is not set. Run 'ace guide' and choose Configure API keys.")
    payload: dict[str, object] = {
        "model": model,
        "voice": voice,
        "input": text,
        "response_format": "wav",
    }
    if instructions and model.startswith("gpt-4o"):
        payload["instructions"] = instructions
    request = urllib.request.Request(
        f"{base_url.rstrip('/')}/audio/speech",
        data=json.dumps(payload).encode("utf-8"),
        method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            audio = response.read()
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ProviderRequestError(f"OpenAI TTS HTTP {exc.code}: {body[:800]}") from exc
    except OSError as exc:
        raise ProviderUnavailable(f"OpenAI TTS request failed: {exc}") from exc
    path = Path(output)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(audio)
    return path
