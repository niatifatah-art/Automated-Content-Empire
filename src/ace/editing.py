from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.audio import mix as mix_audio, normalize_narration
from ace.captions import inspect as inspect_captions, plan as plan_captions
from ace.config import load as load_config
from ace.storage import metadata, resolve_generation
from ace.utils import ensure_dir, read_json, sha256_file, write_json
from ace.visuals import Shot, collect_for_plan, inspect as inspect_visuals, plan as plan_visuals


VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif"}


@dataclass(frozen=True)
class EditPackage:
    folder: Path
    plan: Path
    accessibility_subtitles: Path
    styled_captions: Path
    final_video: Path | None = None


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError((result.stderr.strip() or result.stdout.strip())[-5000:])
    return result


def _ffprobe(path: Path) -> dict[str, Any]:
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return {}
    result = _run([ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration", "-of", "json", str(path)])
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError:
        return {}


def _duration(path: Path) -> float:
    data = _ffprobe(path)
    try:
        return float(data.get("format", {}).get("duration") or 0)
    except (TypeError, ValueError):
        return 0.0


def _dimensions(vertical: bool, preview: bool) -> tuple[int, int]:
    if preview:
        return (360, 640) if vertical else (640, 360)
    return (1080, 1920) if vertical else (1920, 1080)


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def create_package(generation: str | Path, workspace: str | Path | None = None) -> EditPackage:
    folder = resolve_generation(generation, workspace)
    if not (folder / "captions" / "caption-plan.json").exists():
        plan_captions(folder, workspace)
    if not (folder / "visuals" / "shot-plan.json").exists():
        plan_visuals(folder, workspace)
    shot_rows = read_json(folder / "visuals" / "shot-plan.json", []) or []
    shots = [Shot(**row) for row in shot_rows]
    if not shots or any(not shot.resource_path or not Path(shot.resource_path).exists() for shot in shots):
        shots = collect_for_plan(folder, workspace)
    info = metadata(folder)
    vertical = str(info.get("content_type")) in {"short", "reel", "story", "video_script"} or str(info.get("platform")) in {"tiktok", "instagram"}
    plan_data = {
        "schema_version": 4,
        "orientation": "vertical" if vertical else "landscape",
        "resolution": "1080x1920" if vertical else "1920x1080",
        "mood": info.get("editing_mood", "technical_dynamic"),
        "voice": str(folder / "voice" / "narration.wav") if (folder / "voice" / "narration.wav").exists() else None,
        "accessibility_subtitles": str(folder / "subtitles" / "accessibility.srt"),
        "styled_captions": str(folder / "captions" / "styled-captions.ass"),
        "shots": [asdict(item) for item in shots],
    }
    plan_path = write_json(folder / "editing" / "edit-plan.json", plan_data)
    (folder / "editing" / "README.md").write_text(
        "# ACE editing package\n\n"
        "- `edit-plan.json`: shot-by-shot semantic timeline.\n"
        "- `../captions/styled-captions.ass`: adaptive visible captions.\n"
        "- `../subtitles/accessibility.srt`: complete accessibility subtitle track.\n"
        "- `../evidence/`: source cards and approved captures.\n"
        "- `../licenses/`: license and attribution metadata.\n",
        encoding="utf-8",
    )
    return EditPackage(folder, plan_path, folder / "subtitles" / "accessibility.srt", folder / "captions" / "styled-captions.ass")


def _media_filter(width: int, height: int, *, vertical: bool, is_image: bool, duration: float, transition: float, crop_focus: str) -> str:
    fade_out = max(0.0, duration - transition)
    if vertical:
        # Keep the complete foreground visible and use a blurred background instead of destructive center cropping.
        base = (
            f"split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=24:2[blur];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
            f"[blur][front]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        base = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"
    if is_image:
        zoom = "zoompan=z='min(zoom+0.0007,1.06)':d=1:s={}x{}:fps=30".format(width, height)
        base = base + "," + zoom
    fade = f",fade=t=in:st=0:d={transition:.3f},fade=t=out:st={fade_out:.3f}:d={transition:.3f}"
    return base + fade + ",fps=30,format=yuv420p"


def _render_shot(ffmpeg: str, shot: Shot, output: Path, width: int, height: int, vertical: bool, preview: bool, transition: float) -> None:
    resource = Path(str(shot.resource_path))
    duration = max(0.55, float(shot.duration))
    suffix = resource.suffix.lower()
    if suffix in VIDEO_EXTENSIONS:
        source_duration = _duration(resource)
        available = max(0.0, source_duration - duration - 0.15)
        start_offset = (int(sha256_file(resource)[:8], 16) % 1000) / 1000 * available if available > 0 else 0.0
        vf = _media_filter(width, height, vertical=vertical, is_image=False, duration=duration, transition=transition, crop_focus=shot.crop_focus)
        command = [ffmpeg, "-y", "-ss", f"{start_offset:.3f}", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-pix_fmt", "yuv420p", str(output)]
    elif suffix in IMAGE_EXTENSIONS:
        vf = _media_filter(width, height, vertical=vertical, is_image=True, duration=duration, transition=transition, crop_focus=shot.crop_focus)
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-pix_fmt", "yuv420p", str(output)]
    else:
        raise ValueError(f"Unsupported visual file: {resource}")
    _run(command)


def render(generation: str | Path, workspace: str | Path | None = None, *, preview: bool = False) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is not installed.")
    package = create_package(generation, workspace)
    folder = package.folder
    plan_data = read_json(package.plan, {}) or {}
    shots = [Shot(**row) for row in plan_data.get("shots", [])]
    if not shots:
        raise RuntimeError("The edit plan contains no shots.")
    vertical = plan_data.get("orientation") == "vertical"
    width, height = _dimensions(vertical, preview)
    config = load_config(workspace)
    transition = float(config.get("editing", {}).get("transition_seconds", 0.16))
    render_dir = ensure_dir(folder / "temp" / "render")
    segment_paths: list[Path] = []
    for shot in shots:
        if not shot.resource_path or not Path(shot.resource_path).exists():
            raise FileNotFoundError(f"Missing visual for shot {shot.index}: {shot.resource_path}")
        output = render_dir / f"shot-{shot.index:03d}.mp4"
        _render_shot(ffmpeg, shot, output, width, height, vertical, preview, transition)
        segment_paths.append(output)
    concat = render_dir / "concat.txt"
    concat.write_text("\n".join(f"file '{path.as_posix()}'" for path in segment_paths) + "\n", encoding="utf-8")
    video_only = render_dir / "video-only.mp4"
    _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat), "-c", "copy", str(video_only)])
    voice = folder / "voice" / "narration.wav"
    if voice.exists() and config.get("audio", {}).get("normalize_narration", True):
        normalize_narration(folder, workspace)
    with_audio = mix_audio(folder, video_only, workspace, mood=str(plan_data.get("mood") or "")) if voice.exists() else video_only
    output = ensure_dir(folder / "exports") / ("preview.mp4" if preview else "final.mp4")
    captions = folder / "captions" / "styled-captions.ass"
    if captions.exists() and config.get("render", {}).get("burn_visible_captions", True):
        escaped = _escape_filter_path(captions)
        command = [ffmpeg, "-y", "-i", str(with_audio), "-vf", f"ass='{escaped}'", "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-pix_fmt", "yuv420p"]
        if voice.exists():
            command += ["-c:a", "copy"]
        else:
            command += ["-an"]
        command += ["-movflags", "+faststart", str(output)]
        _run(command)
    else:
        shutil.copy2(with_audio, output)
    report = validate_media(output, generation=folder, workspace=workspace, expect_audio=voice.exists())
    if config.get("render", {}).get("reject_empty_renders", True) and report["status"] == "failed":
        raise RuntimeError("Final media validation failed: " + "; ".join(report["problems"]))
    return output


def validate_media(
    output: str | Path,
    *,
    generation: str | Path | None = None,
    workspace: str | Path | None = None,
    expect_audio: bool = True,
) -> dict[str, Any]:
    path = Path(output)
    report: dict[str, Any] = {"status": "failed", "path": str(path), "problems": [], "warnings": []}
    if not path.exists() or path.stat().st_size < 1000:
        report["problems"].append("Output file is missing or too small.")
    data = _ffprobe(path) if path.exists() else {}
    streams = data.get("streams", []) if isinstance(data, dict) else []
    video = next((item for item in streams if item.get("codec_type") == "video"), None)
    audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
    report.update(
        {
            "video_stream": bool(video),
            "audio_stream": bool(audio),
            "width": (video or {}).get("width"),
            "height": (video or {}).get("height"),
            "duration": float((data.get("format") or {}).get("duration") or 0),
        }
    )
    if not video:
        report["problems"].append("No video stream was found.")
    if expect_audio and not audio:
        report["problems"].append("Narration was expected but no audio stream was found.")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg and path.exists():
        black = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.45:pix_th=0.10", "-an", "-f", "null", "-"], capture_output=True, text=True, check=False)
        durations = [float(value) for value in re.findall(r"black_duration:([0-9.]+)", black.stderr)]
        total = float(report.get("duration") or 0)
        ratio = sum(durations) / total if total > 0 else 0
        report["black_frame_ratio"] = round(min(1.0, ratio), 4)
        if ratio > 0.55:
            report["problems"].append("The video contains too much black footage.")
        elif ratio > 0.15:
            report["warnings"].append("The video contains noticeable black footage.")
        if expect_audio and audio:
            silence = subprocess.run([ffmpeg, "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-48dB:d=1", "-vn", "-f", "null", "-"], capture_output=True, text=True, check=False)
            silence_durations = [float(value) for value in re.findall(r"silence_duration: ([0-9.]+)", silence.stderr)]
            silence_ratio = sum(silence_durations) / total if total > 0 else 0
            report["silence_ratio"] = round(min(1.0, silence_ratio), 4)
            if silence_ratio > 0.9:
                report["problems"].append("The narration track is almost entirely silent.")
    if generation is not None:
        folder = resolve_generation(generation, workspace)
        caption_report = inspect_captions(folder, workspace)
        visual_report = inspect_visuals(folder, workspace)
        report["caption_report"] = caption_report
        report["visual_report"] = visual_report
        if caption_report.get("status") == "failed":
            report["problems"].append("Visible caption layout contains overflow.")
        if visual_report.get("missing_visuals"):
            report["problems"].append("One or more shots has no visual.")
        intelligence = visual_report.get("visual_intelligence") or {}
        if intelligence.get("status") == "failed":
            report["problems"].append("Visual Intelligence validation failed: " + "; ".join(intelligence.get("problems", [])))
        elif intelligence.get("status") == "warning":
            report["warnings"].append("Visual Intelligence completed with warnings.")
        write_json(folder / "quality" / "media-report.json", report)
    report["status"] = "failed" if report["problems"] else "warning" if report["warnings"] else "passed"
    if generation is not None:
        write_json(resolve_generation(generation, workspace) / "quality" / "media-report.json", report)
    return report


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    caption_report = inspect_captions(folder, workspace)
    visual_report = inspect_visuals(folder, workspace)
    media_report = read_json(folder / "quality" / "media-report.json", {}) or {}
    component_statuses = {caption_report.get("status"), visual_report.get("status"), media_report.get("status", "not_run")}
    report = {
        "status": "not_run" if "not_run" in component_statuses else "failed" if "failed" in component_statuses else "warning" if "warning" in component_statuses else "passed",
        "caption_overflow": caption_report.get("overflow_count", 0),
        "caption_visible": caption_report.get("visible_count", 0),
        "caption_hidden": caption_report.get("hidden_count", 0),
        "missing_visuals": visual_report.get("missing_visuals", 0),
        "repeated_visuals": visual_report.get("repeated_external_visuals", {}),
        "average_shot_seconds": visual_report.get("average_shot_seconds"),
        "final_resolution": [media_report.get("width"), media_report.get("height")],
        "audio_stream": media_report.get("audio_stream"),
        "black_frame_ratio": media_report.get("black_frame_ratio"),
        "silence_ratio": media_report.get("silence_ratio"),
    }
    write_json(folder / "quality" / "editing-report.json", report)
    return report
