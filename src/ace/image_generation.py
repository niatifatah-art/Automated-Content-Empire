from __future__ import annotations

import base64
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.http import request
from ace.providers.router import ProviderRouter
from ace.secrets import load as load_secrets
from ace.storage import resolve_generation
from ace.utils import ensure_dir, sha256_file, slugify, utc_now_iso, write_json


@dataclass
class GeneratedImage:
    path: str
    provider: str
    model: str
    prompt: str
    created_at: str
    content_hash: str
    aspect_ratio: str
    label: str = "AI-generated illustration"
    used_as_evidence: bool = False


def _save_manifest(folder: Path, item: GeneratedImage) -> None:
    path = ensure_dir(folder / "visuals" / "generated") / "image-generation-manifest.json"
    rows: list[dict[str, Any]] = []
    if path.exists():
        try:
            rows = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            rows = []
    rows.append(asdict(item))
    write_json(path, rows)


def _gemini_keys(workspace: str | Path | None = None) -> list[tuple[str, str]]:
    router = ProviderRouter(workspace)
    return [(item.name, item.value) for item in router.credentials_for("gemini") if item.value]


def _find_image_data(value: Any) -> str | None:
    if isinstance(value, dict):
        data = value.get("data")
        kind = str(value.get("type") or "").lower()
        mime = str(value.get("mime_type") or value.get("mimeType") or "").lower()
        if isinstance(data, str) and (kind == "image" or mime.startswith("image/")):
            return data
        output_image = value.get("output_image")
        if isinstance(output_image, dict) and isinstance(output_image.get("data"), str):
            return str(output_image["data"])
        for child in value.values():
            found = _find_image_data(child)
            if found:
                return found
    elif isinstance(value, list):
        for child in value:
            found = _find_image_data(child)
            if found:
                return found
    return None


def _generate_gemini(prompt: str, output: Path, workspace: str | Path | None, model: str, aspect_ratio: str) -> GeneratedImage:
    failures: list[str] = []
    body = {
        "model": model,
        "input": prompt,
        "response_format": {
            "type": "image",
            "mime_type": "image/png",
            "aspect_ratio": aspect_ratio,
            "image_size": "1K",
        },
    }
    for credential_name, key in _gemini_keys(workspace):
        try:
            data = request(
                "POST",
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                headers={"x-goog-api-key": key},
                json_body=body,
                timeout=180,
                retries=1,
            ).json()
            encoded = _find_image_data(data)
            if not encoded:
                raise RuntimeError("Gemini image response contained no image data.")
            output.write_bytes(base64.b64decode(encoded))
            return GeneratedImage(str(output), f"gemini_image:{credential_name}", model, prompt, utc_now_iso(), sha256_file(output), aspect_ratio)
        except Exception as exc:
            failures.append(f"{credential_name}: {exc}")
    raise RuntimeError("Gemini image generation failed: " + "; ".join(failures))


def _generate_openai(prompt: str, output: Path, workspace: str | Path | None, model: str, aspect_ratio: str) -> GeneratedImage:
    secrets = load_secrets(workspace)
    key = secrets.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("OPENAI_API_KEY is missing.")
    size = "1024x1536" if aspect_ratio in {"9:16", "2:3"} else "1536x1024" if aspect_ratio in {"16:9", "3:2"} else "1024x1024"
    data = request(
        "POST",
        "https://api.openai.com/v1/images/generations",
        headers={"Authorization": f"Bearer {key}"},
        json_body={"model": model, "prompt": prompt, "size": size, "quality": "medium", "output_format": "png"},
        timeout=180,
        retries=1,
    ).json()
    rows = data.get("data") or []
    if not rows:
        raise RuntimeError("OpenAI image response contained no image.")
    row = rows[0]
    if row.get("b64_json"):
        output.write_bytes(base64.b64decode(row["b64_json"]))
    elif row.get("url"):
        output.write_bytes(request("GET", str(row["url"]), timeout=120, retries=1).body)
    else:
        raise RuntimeError("OpenAI image response contained neither b64_json nor URL.")
    return GeneratedImage(str(output), "openai_image", model, prompt, utc_now_iso(), sha256_file(output), aspect_ratio)


def generate(
    generation: str | Path,
    prompt: str,
    workspace: str | Path | None = None,
    *,
    provider: str | None = None,
    model: str | None = None,
    aspect_ratio: str | None = None,
) -> GeneratedImage:
    folder = resolve_generation(generation, workspace)
    config = load_config(workspace)
    settings = config.get("generated_images", {})
    meta = json.loads((folder / "metadata.json").read_text(encoding="utf-8"))
    vertical = str(meta.get("content_type")) in {"short", "reel", "story", "video_script"} or str(meta.get("platform")) in {"tiktok", "instagram"}
    aspect_ratio = aspect_ratio or str(settings.get("aspect_ratio_vertical" if vertical else "aspect_ratio_landscape", "9:16" if vertical else "16:9"))
    providers = [provider] if provider else list(settings.get("provider_order", ["gemini_image", "openai_image"]))
    output = ensure_dir(folder / "visuals" / "generated") / f"ai-{slugify(prompt, 50)}.png"
    failures: list[str] = []
    safe_prompt = (
        prompt
        + "\nCreate an original illustrative visual. Do not imitate a real webpage, social post, quotation, news screenshot, or evidence document. "
        "Do not include logos unless explicitly requested and permitted. No visible watermark text."
    )
    for selected in providers:
        try:
            if selected == "gemini_image":
                item = _generate_gemini(safe_prompt, output, workspace, model or str(settings.get("gemini_model", "gemini-3.1-flash-image")), aspect_ratio)
            elif selected == "openai_image":
                item = _generate_openai(safe_prompt, output, workspace, model or str(settings.get("openai_model", "gpt-image-1-mini")), aspect_ratio)
            else:
                failures.append(f"unknown provider {selected}")
                continue
            _save_manifest(folder, item)
            return item
        except Exception as exc:
            failures.append(f"{selected}: {exc}")
    raise RuntimeError("No cloud image provider succeeded: " + "; ".join(failures))
