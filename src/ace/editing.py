from __future__ import annotations

import json
import re
import shutil
import subprocess
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ace.config import load as load_config
from ace.errors import ConfigurationError, ProviderUnavailable
from ace.storage import resolve_generation, write_json


@dataclass(frozen=True)
class EditPackage:
    folder: Path
    plan: Path
    subtitles: Path
    final_video: Path | None = None


def _sentences(text: str) -> list[str]:
    compact = re.sub(r"\s+", " ", text).strip()
    if not compact:
        return []
    parts = re.split(r"(?<=[.!?؟])\s+", compact)
    return [part.strip() for part in parts if part.strip()]


def _audio_duration(path: Path) -> float | None:
    if not path.exists():
        return None
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                return handle.getnframes() / float(handle.getframerate())
        except (wave.Error, OSError, ZeroDivisionError):
            pass
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    result = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def _resource_paths(folder: Path) -> list[Path]:
    paths: list[Path] = []
    for relative in ("resources/publishable", "resources/attribution-required", "resources/generated"):
        root = folder / relative
        if root.exists():
            paths.extend(path for path in sorted(root.iterdir()) if path.is_file() or path.is_symlink())
    return paths


def _format_srt_time(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def _voice_path(folder: Path) -> Path | None:
    preferred = folder / "voice" / "narration.wav"
    if preferred.exists():
        return preferred
    candidates = sorted((folder / "voice").glob("*")) if (folder / "voice").exists() else []
    return candidates[0] if candidates else None


def create_package(generation: str | Path, *, workspace: str | Path | None = None) -> EditPackage:
    folder = resolve_generation(generation, workspace)
    tts_path = folder / "script" / "tts-ready.txt"
    script_path = tts_path if tts_path.exists() else folder / "selected.md"
    if not script_path.exists():
        raise FileNotFoundError(f"Selected content not found: {script_path}")
    text = script_path.read_text(encoding="utf-8")
    sentences = _sentences(text)
    if not sentences:
        raise ConfigurationError("The selected content is empty.")
    resources = _resource_paths(folder)
    voice = _voice_path(folder)
    total_duration = _audio_duration(voice) if voice else None
    if not total_duration:
        total_duration = max(6.0, sum(max(1.8, len(sentence.split()) / 2.6) for sentence in sentences))
    weights = [max(1.0, len(sentence.split())) for sentence in sentences]
    weight_total = sum(weights)
    start = 0.0
    timeline: list[dict[str, Any]] = []
    srt: list[str] = []
    for index, (sentence, weight) in enumerate(zip(sentences, weights), 1):
        duration = total_duration * (weight / weight_total)
        end = total_duration if index == len(sentences) else start + duration
        resource = resources[(index - 1) % len(resources)] if resources else None
        timeline.append(
            {
                "segment": index,
                "start": round(start, 3),
                "end": round(end, 3),
                "duration": round(end - start, 3),
                "narration": sentence,
                "resource": str(resource) if resource else None,
                "action": "crop_to_fill_and_add_subtle_motion" if resource else "branded_motion_text_fallback",
                "text_overlay": sentence,
            }
        )
        srt.extend([str(index), f"{_format_srt_time(start)} --> {_format_srt_time(end)}", sentence, ""])
        start = end
    editing_dir = folder / "editing"
    subtitles_dir = folder / "subtitles"
    editing_dir.mkdir(parents=True, exist_ok=True)
    subtitles_dir.mkdir(parents=True, exist_ok=True)
    metadata = json.loads((folder / "metadata.json").read_text(encoding="utf-8")) if (folder / "metadata.json").exists() else {}
    platform = str(metadata.get("platform", "tiktok"))
    content_type = str(metadata.get("content_type", "short"))
    vertical = platform in {"tiktok", "instagram"} or content_type in {"short", "reel", "story", "video_script"}
    plan_data = {
        "schema_version": 2,
        "platform": platform,
        "content_type": content_type,
        "orientation": "vertical" if vertical else "landscape",
        "resolution": "1080x1920" if vertical else "1920x1080",
        "duration": round(total_duration, 3),
        "voice": str(voice) if voice else None,
        "resources": [str(path) for path in resources],
        "fallback_visuals": not bool(resources),
        "subtitles": str(subtitles_dir / "subtitles.srt"),
        "timeline": timeline,
    }
    plan = write_json(editing_dir / "edit-plan.json", plan_data)
    subtitles = subtitles_dir / "subtitles.srt"
    subtitles.write_text("\n".join(srt).rstrip() + "\n", encoding="utf-8")
    (editing_dir / "README.md").write_text(
        "# ACE editing package\n\n"
        "- `edit-plan.json` contains the timeline and asset mapping.\n"
        "- `../subtitles/subtitles.srt` contains timed subtitles.\n"
        "- Resources are under `../resources/`.\n"
        "- The license manifest is under `../licenses/`.\n"
        "- When no reusable media exists, ACE uses a branded animated text fallback.\n",
        encoding="utf-8",
    )
    return EditPackage(folder=folder, plan=plan, subtitles=subtitles)


def _is_video(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _is_image(path: Path) -> bool:
    return path.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}


def _run(command: list[str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise ProviderUnavailable(f"FFmpeg failed: {result.stderr.strip()[-1600:]}")
    return result


def _escape_filter_path(path: Path) -> str:
    return str(path.resolve()).replace("\\", "\\\\").replace(":", "\\:").replace("'", "\\'")


def validate_media(
    output: str | Path,
    *,
    generation: str | Path | None = None,
    workspace: str | Path | None = None,
    expect_audio: bool = True,
) -> dict[str, Any]:
    path = Path(output)
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    report: dict[str, Any] = {"status": "failed", "path": str(path), "problems": []}
    if not path.exists() or path.stat().st_size < 1000:
        report["problems"].append("Output file is missing or too small.")
    if ffprobe and path.exists():
        probe = _run([
            ffprobe, "-v", "error", "-show_entries", "stream=codec_type,width,height,duration:format=duration",
            "-of", "json", str(path),
        ])
        try:
            data = json.loads(probe.stdout)
        except json.JSONDecodeError:
            data = {}
        streams = data.get("streams", [])
        video = next((item for item in streams if item.get("codec_type") == "video"), None)
        audio = next((item for item in streams if item.get("codec_type") == "audio"), None)
        report.update({
            "video_stream": bool(video), "audio_stream": bool(audio),
            "width": (video or {}).get("width"), "height": (video or {}).get("height"),
            "duration": float(data.get("format", {}).get("duration") or 0),
        })
        if not video:
            report["problems"].append("No video stream was found.")
        if expect_audio and not audio:
            report["problems"].append("Narration was expected but no audio stream was found.")
    if ffmpeg and path.exists():
        black = subprocess.run(
            [ffmpeg, "-hide_banner", "-i", str(path), "-vf", "blackdetect=d=0.4:pix_th=0.10", "-an", "-f", "null", "-"],
            capture_output=True, text=True, check=False,
        )
        durations = [float(value) for value in re.findall(r"black_duration:([0-9.]+)", black.stderr)]
        total = float(report.get("duration") or 0)
        ratio = (sum(durations) / total) if total > 0 else 0
        report["black_frame_ratio"] = round(min(1.0, ratio), 4)
        if ratio > 0.92:
            report["problems"].append("The video is almost entirely black.")
        if expect_audio and report.get("audio_stream"):
            silence = subprocess.run(
                [ffmpeg, "-hide_banner", "-i", str(path), "-af", "silencedetect=n=-48dB:d=1", "-vn", "-f", "null", "-"],
                capture_output=True, text=True, check=False,
            )
            silence_durations = [float(value) for value in re.findall(r"silence_duration: ([0-9.]+)", silence.stderr)]
            silence_ratio = (sum(silence_durations) / total) if total > 0 else 0
            report["silence_ratio"] = round(min(1.0, silence_ratio), 4)
            if silence_ratio > 0.9:
                report["problems"].append("The narration track is almost entirely silent.")
    report["status"] = "passed" if not report["problems"] else "failed"
    if generation is not None:
        folder = resolve_generation(generation, workspace)
        write_json(folder / "quality" / "media-report.json", report)
    return report


def render(
    generation: str | Path,
    *,
    workspace: str | Path | None = None,
    preview: bool = False,
    allow_silent: bool = False,
) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise ProviderUnavailable("FFmpeg is not installed. The editing package is still available.")
    package = create_package(generation, workspace=workspace)
    folder = package.folder
    plan = json.loads(package.plan.read_text(encoding="utf-8"))
    config = load_config(workspace)
    voice_value = plan.get("voice")
    voice = Path(voice_value) if voice_value else None
    if not (allow_silent or preview) and not (voice and voice.exists()):
        raise ConfigurationError(
            "Final rendering is not ready: narration is missing. Run 'ace voice generate last' or use --allow-silent."
        )
    vertical = plan.get("orientation") == "vertical"
    width, height = ((360, 640) if vertical else (640, 360)) if preview else ((1080, 1920) if vertical else (1920, 1080))
    fps = 30
    temp = folder / "temp" / "render"
    temp.mkdir(parents=True, exist_ok=True)
    segments: list[Path] = []
    for item in plan.get("timeline", []):
        duration = max(0.5, float(item.get("duration", 2.0)))
        resource_value = item.get("resource")
        resource = Path(resource_value) if resource_value else None
        output = temp / f"segment-{int(item['segment']):03d}.mp4"
        video_filter = (
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},fps={fps},format=yuv420p"
        )
        if resource and resource.exists() and _is_video(resource):
            command = [ffmpeg, "-y", "-stream_loop", "-1", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", video_filter, "-c:v", "libx264", "-preset", "veryfast", str(output)]
        elif resource and resource.exists() and _is_image(resource):
            command = [ffmpeg, "-y", "-loop", "1", "-i", str(resource), "-t", f"{duration:.3f}", "-an", "-vf", video_filter, "-c:v", "libx264", "-preset", "veryfast", str(output)]
        else:
            # A visible, animated technical background; never silently pretend a pure black frame is final media.
            fallback_filter = (
                f"drawgrid=width={max(40, width//12)}:height={max(40, height//20)}:thickness=1:color=white@0.10,"
                f"noise=alls=4:allf=t+u,"
                f"eq=brightness='0.02*sin(2*PI*t/{max(duration,1):.3f})',format=yuv420p"
            )
            command = [ffmpeg, "-y", "-f", "lavfi", "-i", f"color=c=0x101827:s={width}x{height}:r={fps}", "-t", f"{duration:.3f}", "-an", "-vf", fallback_filter, "-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p", str(output)]
        _run(command)
        segments.append(output)
    if not segments:
        raise ConfigurationError("The edit plan contains no renderable segments.")
    concat_file = temp / "concat.txt"
    concat_file.write_text("\n".join(f"file '{path.as_posix()}'" for path in segments) + "\n", encoding="utf-8")
    video_only = temp / "video-only.mp4"
    _run([ffmpeg, "-y", "-f", "concat", "-safe", "0", "-i", str(concat_file), "-c", "copy", str(video_only)])
    exports = folder / "exports"
    exports.mkdir(parents=True, exist_ok=True)
    output = exports / ("preview.mp4" if preview else "final.mp4")
    burn = bool(config.get("render", {}).get("burn_subtitles", True)) and package.subtitles.exists()
    video_codec_args = ["-c:v", "libx264", "-preset", "veryfast", "-pix_fmt", "yuv420p"]
    vf = []
    if burn:
        subtitle_path = _escape_filter_path(package.subtitles)
        font_size = 20 if preview else (48 if vertical else 42)
        vf.append(
            f"subtitles='{subtitle_path}':force_style='FontName=DejaVu Sans,FontSize={font_size},"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,BorderStyle=1,Outline=3,Shadow=1,"
            "Alignment=2,MarginV=90'"
        )
    command = [ffmpeg, "-y", "-i", str(video_only)]
    if voice and voice.exists():
        command += ["-i", str(voice)]
    if vf:
        command += ["-vf", ",".join(vf)]
    command += video_codec_args
    if voice and voice.exists():
        command += ["-c:a", "aac", "-b:a", "192k", "-shortest"]
    else:
        command += ["-an"]
    command += ["-movflags", "+faststart", str(output)]
    _run(command)
    report = validate_media(output, generation=folder, workspace=workspace, expect_audio=bool(voice and voice.exists()))
    if config.get("render", {}).get("reject_empty_renders", True) and report["status"] != "passed":
        raise ProviderUnavailable("Final media validation failed: " + "; ".join(report["problems"]))
    return output
