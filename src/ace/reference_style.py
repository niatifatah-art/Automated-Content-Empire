from __future__ import annotations

import json
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any


def analyze(path_value: str | Path) -> dict[str, Any]:
    path = Path(path_value).expanduser().resolve()
    if not path.exists():
        raise FileNotFoundError(path)
    ffprobe = shutil.which("ffprobe")
    ffmpeg = shutil.which("ffmpeg")
    if not ffprobe or not ffmpeg:
        raise RuntimeError("FFmpeg and ffprobe are required to analyze a reference video.")

    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height", "-of", "json", str(path)],
        capture_output=True,
        text=True,
        check=False,
    )
    data = json.loads(probe.stdout or "{}")
    duration = float((data.get("format") or {}).get("duration") or 0)
    video = next((item for item in data.get("streams", []) if item.get("codec_type") == "video"), {})
    width = int(video.get("width") or 0)
    height = int(video.get("height") or 0)

    scene_run = subprocess.run(
        [ffmpeg, "-hide_banner", "-i", str(path), "-vf", "select='gt(scene,0.20)',showinfo", "-an", "-f", "null", "-"],
        capture_output=True,
        text=True,
        check=False,
    )
    cuts = sorted({float(item) for item in re.findall(r"pts_time:([0-9.]+)", scene_run.stderr) if 0 < float(item) < duration})
    boundaries = [0.0, *cuts, duration] if duration > 0 else [0.0]
    shot_lengths = [b - a for a, b in zip(boundaries, boundaries[1:]) if b > a]
    average = sum(shot_lengths) / max(1, len(shot_lengths)) if duration else 0.0
    if average and average <= 1.8:
        pace = "very_fast"
    elif average and average <= 2.6:
        pace = "fast"
    elif average and average <= 3.6:
        pace = "medium"
    else:
        pace = "controlled"
    return {
        "path": str(path),
        "duration": round(duration, 3),
        "width": width,
        "height": height,
        "orientation": "vertical" if height > width else "landscape",
        "cut_count": len(cuts),
        "average_shot_seconds": round(average, 3),
        "pace": pace,
        "scene_boundaries": [round(item, 3) for item in boundaries],
    }
