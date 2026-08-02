from __future__ import annotations

import base64
import json
import mimetypes
import re
import shutil
import subprocess
import tempfile
import urllib.parse
import time
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from ace.config import load as load_config
from ace.http import HTTPError, request
from ace.secrets import load as load_secrets
from ace.tracing import emit as emit_trace, new_trace_id
from ace.visual_intelligence.contracts import DecisionStatus, ShotIntent, VisualCandidate, VisualScore


def _extract_json(text: str) -> dict[str, Any]:
    value = text.strip()
    value = re.sub(r"^```(?:json)?\s*", "", value, flags=re.I)
    value = re.sub(r"\s*```$", "", value)
    try:
        row = json.loads(value)
    except json.JSONDecodeError:
        start, end = value.find("{"), value.rfind("}")
        if start < 0 or end <= start:
            raise
        row = json.loads(value[start : end + 1])
    return row if isinstance(row, dict) else {}


def _sample_images(path: Path, *, limit: int = 3) -> list[Path]:
    suffix = path.suffix.lower()
    if suffix in {".png", ".jpg", ".jpeg", ".webp"}:
        return [path]
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return []
    duration_run = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = float(duration_run.stdout.strip())
    except ValueError:
        duration = 0.0
    times = [duration * ratio for ratio in (0.2, 0.5, 0.8)] if duration > 0 else [0.0]
    temp_root = Path(tempfile.mkdtemp(prefix="ace-vision-samples-"))
    output: list[Path] = []
    for index, when in enumerate(times[:limit], 1):
        target = temp_root / f"frame-{index}.jpg"
        run = subprocess.run(
            [ffmpeg, "-y", "-ss", f"{when:.3f}", "-i", str(path), "-frames:v", "1", "-vf", "scale='min(768,iw)':-2", "-q:v", "3", str(target)],
            capture_output=True,
            text=True,
            check=False,
        )
        if run.returncode == 0 and target.exists():
            output.append(target)
    return output


def _image_part(path: Path) -> dict[str, Any]:
    mime = mimetypes.guess_type(path.name)[0] or "image/jpeg"
    if mime == "image/webp":
        # Gemini accepts WebP, but JPEG is more predictable across providers.
        converted = path.with_suffix(".judge.jpg")
        Image.open(path).convert("RGB").save(converted, quality=86)
        path = converted
        mime = "image/jpeg"
    return {"inlineData": {"mimeType": mime, "data": base64.b64encode(path.read_bytes()).decode("ascii")}}


def _credentials(workspace: str | Path | None) -> list[tuple[str, str]]:
    values = load_secrets(workspace)
    rows: list[tuple[str, str]] = []
    for name in ("GEMINI_API_KEY_PRIMARY", "GEMINI_API_KEY_BACKUP", "GEMINI_API_KEY"):
        key = values.get(name)
        if key and all(existing != key for _, existing in rows):
            rows.append((name, key))
    return rows


def _merge(base: VisualScore, row: dict[str, Any], *, model: str, credential_name: str) -> VisualScore:
    def number(name: str, fallback: float) -> float:
        try:
            return max(0.0, min(100.0, float(row.get(name, fallback))))
        except (TypeError, ValueError):
            return fallback

    relevance = number("semantic_relevance", base.semantic_relevance)
    clarity = number("clarity", base.clarity)
    vertical = number("vertical_fit", base.vertical_fit)
    truth = number("truthfulness", base.truthfulness)
    quality = number("visual_quality", base.visual_quality)
    style = number("style_match", base.style_match)
    required = number("required_element_coverage", base.required_element_coverage)
    duplicate = number("duplicate_risk", base.duplicate_risk)
    overall = (
        relevance * 0.35
        + clarity * 0.17
        + required * 0.12
        + vertical * 0.09
        + style * 0.08
        + truth * 0.11
        + quality * 0.08
        - duplicate * 0.10
    )
    violations = [str(item) for item in row.get("forbidden_violations", []) if str(item).strip()]
    misleading = bool(row.get("misleading", False))
    accepted = bool(row.get("accepted", False)) and not violations and not misleading
    decision = DecisionStatus.ACCEPTED.value if accepted else DecisionStatus.REJECTED.value
    reasoning = list(base.reasoning)
    cloud_reason = str(row.get("reason") or "Cloud vision judge completed.")
    reasoning.append(cloud_reason)
    if misleading:
        reasoning.append("Cloud judge marked the visual as potentially misleading.")
    return VisualScore(
        candidate_id=base.candidate_id,
        shot_id=base.shot_id,
        semantic_relevance=relevance,
        clarity=clarity,
        required_element_coverage=required,
        vertical_fit=vertical,
        style_match=style,
        truthfulness=truth,
        visual_quality=quality,
        provenance_confidence=base.provenance_confidence,
        duplicate_risk=duplicate,
        overall=round(max(0.0, min(100.0, overall)), 2),
        decision=decision,
        forbidden_violations=list(dict.fromkeys([*base.forbidden_violations, *violations])),
        warnings=[*base.warnings, *[str(item) for item in row.get("warnings", [])]],
        reasoning=reasoning,
        judge=f"gemini_vision:{model}:{credential_name}",
    )


def _enforce_thresholds(score: VisualScore, settings: dict[str, Any]) -> VisualScore:
    thresholds = settings.get("acceptance", {})
    checks = [
        (score.semantic_relevance, float(thresholds.get("minimum_relevance", 78)), "semantic relevance"),
        (score.clarity, float(thresholds.get("minimum_clarity", 72)), "clarity"),
        (score.vertical_fit, float(thresholds.get("minimum_vertical_fit", 70)), "vertical fit"),
        (score.truthfulness, float(thresholds.get("minimum_truthfulness", 95)), "truthfulness"),
    ]
    failures = [f"{label} {value:.1f} < {minimum:.1f}" for value, minimum, label in checks if value < minimum]
    maximum_duplicate = float(thresholds.get("maximum_duplicate_risk", 25))
    if score.duplicate_risk > maximum_duplicate:
        failures.append(f"duplicate risk {score.duplicate_risk:.1f} > {maximum_duplicate:.1f}")
    if score.forbidden_violations:
        failures.append("forbidden visual elements detected")
    if failures:
        score.decision = DecisionStatus.REJECTED.value
        score.reasoning.append("Strict acceptance gate rejected the candidate: " + "; ".join(failures) + ".")
    return score


def judge_candidate(
    intent: ShotIntent,
    candidate: VisualCandidate,
    base_score: VisualScore,
    workspace: str | Path | None = None,
    *,
    requester: Callable[..., Any] = request,
    enabled: bool | None = None,
) -> VisualScore:
    """Inspect sampled frames with Gemini when credentials and local media exist.

    The deterministic score is always retained as a fallback. Cloud vision never
    turns a reference-only, simulated or placeholder asset into publishable media.
    """

    config = load_config(workspace)
    settings = config.get("visual_intelligence", {})
    trace_id = new_trace_id("vision")
    trace_metadata = {"shot_id": intent.shot_id, "candidate_id": candidate.candidate_id, "subject": intent.subject}
    if enabled is None:
        enabled = bool(settings.get("cloud_vision_judge", True))
    if not enabled or not candidate.path:
        return base_score
    path = Path(candidate.path).expanduser()
    if not path.exists():
        return base_score
    samples = _sample_images(path, limit=int(settings.get("judge_frame_count", 3)))
    if not samples:
        return base_score
    credentials = _credentials(workspace)
    if not credentials:
        base_score.warnings.append("Cloud vision judge skipped because no Gemini credential is configured.")
        return base_score

    model = str(settings.get("vision_model") or "gemini-3.5-flash")
    emit_trace(
        "visual_judge.start",
        workspace=workspace,
        trace_id=trace_id,
        metadata=trace_metadata,
        model=model,
        frame_count=len(samples),
        deterministic_score=base_score.overall,
    )
    prompt = (
        "You are ACE's strict Visual Judge. Inspect the attached sampled frames and compare them with the exact narration and intent. "
        "Do not reward a clip merely because it looks technological. Reject visual metaphors triggered by one word, generic stock filler, "
        "financial charts for networking topics, generic hackers, office interviews, accidental logos, watermarks, unreadable text, and visuals "
        "that become misleading after vertical cropping. Answer as JSON only.\n\n"
        f"NARRATION: {intent.narration}\n"
        f"PURPOSE: {intent.purpose}\nSUBJECT: {intent.subject}\nMOOD: {intent.mood}\n"
        f"REQUIRED ELEMENTS: {json.dumps(intent.required_elements)}\n"
        f"FORBIDDEN ELEMENTS: {json.dumps(intent.forbidden_elements)}\n"
        f"CANDIDATE FORMAT: {candidate.format}\nCANDIDATE DESCRIPTION: {candidate.description}\n"
        "Return keys: accepted (boolean), semantic_relevance, clarity, required_element_coverage, vertical_fit, style_match, "
        "truthfulness, visual_quality, duplicate_risk, forbidden_violations (array), warnings (array), misleading (boolean), reason. "
        "Scores are 0-100. Evidence must be completely truthful."
    )
    parts: list[dict[str, Any]] = [{"text": prompt}]
    parts.extend(_image_part(sample) for sample in samples)
    body = {
        "contents": [{"role": "user", "parts": parts}],
        "generationConfig": {"maxOutputTokens": 1400, "responseMimeType": "application/json"},
    }
    errors: list[str] = []
    for credential_name, key in credentials:
        url = (
            f"{str(config.get('providers', {}).get('gemini', {}).get('base_url') or 'https://generativelanguage.googleapis.com/v1beta').rstrip('/')}"
            f"/models/{urllib.parse.quote(model, safe='')}:generateContent?key={urllib.parse.quote(key)}"
        )
        started = time.monotonic()
        try:
            emit_trace(
                "visual_judge.attempt.start",
                workspace=workspace,
                trace_id=trace_id,
                metadata=trace_metadata,
                model=model,
                credential=credential_name,
            )
            response = requester("POST", url, json_body=body, timeout=90, retries=0)
            data = response.json()
            candidates = data.get("candidates") or []
            text_parts = candidates[0].get("content", {}).get("parts", []) if candidates else []
            text = "".join(str(item.get("text", "")) for item in text_parts if isinstance(item, dict)).strip()
            if not text:
                raise RuntimeError("Gemini vision judge returned no text.")
            merged = _enforce_thresholds(_merge(base_score, _extract_json(text), model=model, credential_name=credential_name), settings)
            emit_trace(
                "visual_judge.attempt.success",
                workspace=workspace,
                trace_id=trace_id,
                metadata=trace_metadata,
                model=model,
                credential=credential_name,
                elapsed_seconds=round(time.monotonic() - started, 4),
                score=merged.overall,
                decision=merged.decision,
            )
            return merged
        except (HTTPError, RuntimeError, ValueError, KeyError, json.JSONDecodeError) as exc:
            emit_trace(
                "visual_judge.attempt.failure",
                workspace=workspace,
                trace_id=trace_id,
                metadata=trace_metadata,
                model=model,
                credential=credential_name,
                elapsed_seconds=round(time.monotonic() - started, 4),
                error=str(exc),
            )
            errors.append(f"{credential_name}: {exc}")
    emit_trace(
        "visual_judge.failure",
        workspace=workspace,
        trace_id=trace_id,
        metadata=trace_metadata,
        model=model,
        errors=errors,
    )
    base_score.warnings.append("Cloud vision judge failed; deterministic score retained: " + "; ".join(errors))
    return base_score
