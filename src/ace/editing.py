from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from functools import lru_cache
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from ace.audio import generate_sfx_track, mix as mix_audio, normalize_narration
from ace.captions import inspect as inspect_captions, plan as plan_captions
from ace.config import load as load_config
from ace.creative_quality import inspect as inspect_creative
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


@lru_cache(maxsize=256)
def _scene_starts(path_value: str) -> tuple[float, ...]:
    """Return useful local scene-change timestamps for B-roll trimming."""
    ffmpeg = shutil.which("ffmpeg")
    path = Path(path_value)
    if not ffmpeg or not path.exists() or path.suffix.lower() not in VIDEO_EXTENSIONS:
        return ()
    run = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-vf", "select='gt(scene,0.18)',showinfo", "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    values = [float(item) for item in re.findall(r"pts_time:([0-9.]+)", run.stderr)]
    return tuple(dict.fromkeys(round(item, 3) for item in values if item >= 0))


def _best_start_offset(resource: Path, *, available: float, hint: float) -> float:
    if available <= 0:
        return 0.0
    target = max(0.0, min(available, hint * available))
    candidates = [item for item in _scene_starts(str(resource.resolve())) if 0 <= item <= available]
    if not candidates:
        return target
    return min(candidates, key=lambda item: abs(item - target))


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
        "creative_style": info.get("creative_style", "adaptive"),
        "media_mode": info.get("media_mode", "auto"),
        "meme_mode": info.get("meme_mode", "auto"),
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


def _media_filter(
    width: int,
    height: int,
    *,
    vertical: bool,
    is_image: bool,
    duration: float,
    transition: float,
    crop_focus: str,
    shot: Shot,
) -> str:
    creative = dict((shot.metadata or {}).get("creative") or {})
    motion = str(creative.get("motion") or "steady")
    transition_name = str(creative.get("transition") or shot.transition or "cut")
    emphasis = str(creative.get("emphasis") or "support")

    if vertical:
        # Preserve the foreground and fill the vertical frame without destructive cropping.
        base = (
            f"split=2[bg][fg];"
            f"[bg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=24:2[blur];"
            f"[fg]scale={width}:{height}:force_original_aspect_ratio=decrease[front];"
            f"[blur][front]overlay=(W-w)/2:(H-h)/2"
        )
    else:
        base = f"scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height}"

    # Apply motion to the composed frame. This creates actual shot variation instead
    # of rendering every image/video as the same static card.
    if motion in {"slow_push", "punch_in", "snap_zoom", "pan_left", "pan_right", "slow_pan", "handheld"}:
        max_zoom = {
            "slow_push": 1.045,
            "punch_in": 1.075,
            "snap_zoom": 1.11,
            "pan_left": 1.06,
            "pan_right": 1.06,
            "slow_pan": 1.045,
            "handheld": 1.035,
        }[motion]
        increment = max(0.00025, (max_zoom - 1.0) / max(1.0, duration * 30.0))
        if motion in {"pan_left", "slow_pan"}:
            x_expr = "(iw-iw/zoom)*(1-on/(duration*30))".replace("duration", f"{duration:.4f}")
        elif motion == "pan_right":
            x_expr = "(iw-iw/zoom)*(on/(duration*30))".replace("duration", f"{duration:.4f}")
        elif motion == "handheld":
            x_expr = "(iw-iw/zoom)/2+sin(on/5)*5"
        else:
            x_expr = "iw/2-(iw/zoom/2)"
        y_expr = "ih/2-(ih/zoom/2)" if motion != "handheld" else "ih/2-(ih/zoom/2)+cos(on/7)*4"
        base += (
            f",zoompan=z='min(zoom+{increment:.7f},{max_zoom:.4f})':"
            f"x='{x_expr}':y='{y_expr}':d=1:s={width}x{height}:fps=30"
        )
    elif is_image:
        base += f",zoompan=z='min(zoom+0.00035,1.035)':d=1:s={width}x{height}:fps=30"

    # Slight finishing pass. Stronger styles get a little more contrast, while
    # evidence/serious shots stay restrained.
    if shot.mood in {"gaming_hype", "playful_tech", "challenge"}:
        base += ",eq=contrast=1.055:saturation=1.08:brightness=0.005,unsharp=3:3:0.30"
    elif shot.mood == "serious_technical":
        base += ",eq=contrast=1.025:saturation=0.98,unsharp=3:3:0.18"
    else:
        base += ",eq=contrast=1.035:saturation=1.035,unsharp=3:3:0.22"

    # Avoid the old fade-to-black between every segment. Hard cuts are the default;
    # soft transitions only fade in briefly and therefore preserve energy and sync.
    if transition_name in {"fade", "quick_fade"}:
        fade_duration = min(0.16 if transition_name == "fade" else 0.08, max(0.04, transition))
        base += f",fade=t=in:st=0:d={fade_duration:.3f}"
    elif transition_name == "flash":
        base += ",eq=brightness='if(lt(t,0.06),0.18*(1-t/0.06),0)':eval=frame"

    if emphasis == "strong":
        base += f",drawbox=x=0:y=0:w={width}:h=8:color=white@0.35:t=fill"

    return base + ",fps=30,format=yuv420p"


def _secondary_details(shot: Shot) -> tuple[Path | None, dict[str, Any]]:
    row = dict((shot.metadata or {}).get("secondary_visual") or {})
    usage = dict((shot.metadata or {}).get("secondary_usage") or {})
    value = row.get("path")
    if not value or str(usage.get("mode") or "none") == "none":
        return None, usage
    path = Path(str(value)).expanduser()
    return (path if path.exists() else None), usage


def _compose_secondary(
    ffmpeg: str,
    primary: Path,
    secondary: Path,
    output: Path,
    *,
    width: int,
    height: int,
    duration: float,
    preview: bool,
    usage: dict[str, Any],
) -> None:
    """Add a deliberate cutaway or PIP, never an arbitrary text-card overlay."""
    mode = str(usage.get("mode") or "none")
    start = max(0.0, min(duration - 0.25, float(usage.get("start") or duration * 0.34)))
    insert_duration = max(0.45, min(duration - start, float(usage.get("duration") or 0.9)))
    end = min(duration, start + insert_duration)
    is_image = secondary.suffix.lower() in IMAGE_EXTENSIONS
    secondary_args = ["-loop", "1", "-i", str(secondary)] if is_image else ["-stream_loop", "-1", "-i", str(secondary)]

    if mode == "cutaway":
        # Full-screen B-roll inserts are more natural than covering an explainer
        # with another card. Keep the whole foreground visible over a blurred fill.
        sec = (
            f"[1:v]split=2[sbg][sfg];"
            f"[sbg]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},boxblur=20:2[sblur];"
            f"[sfg]scale={width}:{height}:force_original_aspect_ratio=decrease[sfront];"
            f"[sblur][sfront]overlay=(W-w)/2:(H-h)/2,eq=contrast=1.04:saturation=1.06,format=yuv420p[sec];"
            f"[0:v][sec]overlay=x=0:y=0:enable='between(t,{start:.3f},{end:.3f})':eof_action=repeat[v]"
        )
    else:
        overlay_w = max(120, int(width * 0.38))
        overlay_h = max(160, int(height * 0.29))
        margin = max(12, int(width * 0.04))
        sec = (
            f"[1:v]scale={overlay_w}:{overlay_h}:force_original_aspect_ratio=increase,"
            f"crop={overlay_w}:{overlay_h},"
            f"drawbox=x=0:y=0:w=iw:h=ih:color=white@0.30:t=4,format=yuv420p[sec];"
            f"[0:v][sec]overlay=x=W-w-{margin}:y={margin + 54}:"
            f"enable='between(t,{start:.3f},{end:.3f})':eof_action=repeat[v]"
        )

    command = [
        ffmpeg, "-y", "-i", str(primary), *secondary_args, "-t", f"{duration:.3f}",
        "-filter_complex", sec, "-map", "[v]", "-an",
        "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast",
        "-pix_fmt", "yuv420p", str(output),
    ]
    _run(command)


def _render_shot(ffmpeg: str, shot: Shot, output: Path, width: int, height: int, vertical: bool, preview: bool, transition: float) -> None:
    resource = Path(str(shot.resource_path))
    duration = max(0.55, float(shot.duration))
    suffix = resource.suffix.lower()
    secondary, secondary_usage = _secondary_details(shot)
    creative = dict((shot.metadata or {}).get("creative") or {})
    use_secondary = bool(secondary and duration >= 2.6 and str(secondary_usage.get("mode") or "none") in {"cutaway", "pip"} and shot.visual_type != "meme")
    primary_output = output.with_name(output.stem + "-primary.mp4") if use_secondary else output

    if suffix in VIDEO_EXTENSIONS:
        source_duration = _duration(resource)
        available = max(0.0, source_duration - duration - 0.15)
        start_hint = max(0.0, min(1.0, float(creative.get("start_hint", 0.33))))
        start_offset = _best_start_offset(resource, available=available, hint=start_hint)
        vf = _media_filter(width, height, vertical=vertical, is_image=False, duration=duration, transition=transition, crop_focus=shot.crop_focus, shot=shot)
        command = [ffmpeg, "-y", "-ss", f"{start_offset:.3f}", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-pix_fmt", "yuv420p", str(primary_output)]
    elif suffix in IMAGE_EXTENSIONS:
        vf = _media_filter(width, height, vertical=vertical, is_image=True, duration=duration, transition=transition, crop_focus=shot.crop_focus, shot=shot)
        command = [ffmpeg, "-y", "-loop", "1", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", vf, "-c:v", "libx264", "-preset", "ultrafast" if preview else "veryfast", "-pix_fmt", "yuv420p", str(primary_output)]
    else:
        raise ValueError(f"Unsupported visual file: {resource}")
    _run(command)
    if use_secondary and secondary is not None:
        _compose_secondary(
            ffmpeg, primary_output, secondary, output,
            width=width, height=height, duration=duration, preview=preview, usage=secondary_usage,
        )



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
    generate_sfx_track(folder, plan_data.get("shots", []), workspace)
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
        creative_report = inspect_creative(folder, workspace)
        report["caption_report"] = caption_report
        report["visual_report"] = visual_report
        report["creative_report"] = creative_report
        if caption_report.get("status") == "failed":
            report["problems"].append("Visible caption layout contains overflow.")
        if visual_report.get("missing_visuals"):
            report["problems"].append("One or more shots has no visual.")
        intelligence = visual_report.get("visual_intelligence") or {}
        if intelligence.get("status") == "failed":
            report["problems"].append("Visual Intelligence validation failed: " + "; ".join(intelligence.get("problems", [])))
        elif intelligence.get("status") == "warning":
            report["warnings"].append("Visual Intelligence completed with warnings.")
        if creative_report.get("status") == "warning":
            report["warnings"].append("Creative quality needs review: " + "; ".join(creative_report.get("warnings", [])[:3]))
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
        "creative_score": (media_report.get("creative_report") or {}).get("score"),
        "live_broll_ratio": (media_report.get("creative_report") or {}).get("live_broll_ratio"),
        "static_card_ratio": (media_report.get("creative_report") or {}).get("static_card_ratio"),
    }
    write_json(folder / "quality" / "editing-report.json", report)
    return report
