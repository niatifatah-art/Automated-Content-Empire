from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from ace.accounts import asset_dir
from ace.config import load as load_config
from ace.storage import resolve_generation
from ace.utils import ensure_dir, write_json


def normalize_narration(generation: str | Path, workspace: str | Path | None = None) -> Path:
    folder = resolve_generation(generation, workspace)
    source = folder / "voice" / "narration.wav"
    if not source.exists():
        raise FileNotFoundError("Narration is missing.")
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required.")
    settings = load_config(workspace).get("audio", {})
    target = ensure_dir(folder / "audio") / "narration-normalized.wav"
    lufs = float(settings.get("target_lufs", -16))
    peak = float(settings.get("true_peak_db", -1))
    filters = f"highpass=f=70,acompressor=threshold=-18dB:ratio=2.5:attack=15:release=180,loudnorm=I={lufs}:TP={peak}:LRA=11"
    result = subprocess.run([ffmpeg, "-y", "-i", str(source), "-af", filters, str(target)], capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-3000:])
    write_json(folder / "quality" / "audio-report.json", {"status": "passed", "normalized": True, "target_lufs": lufs, "true_peak_db": peak, "path": str(target)})
    return target


def find_music(workspace: str | Path | None = None, mood: str = "") -> Path | None:
    root = asset_dir(workspace=workspace)
    candidates = []
    for suffix in ("*.mp3", "*.wav", "*.m4a", "*.flac", "*.ogg"):
        candidates.extend(root.rglob(suffix))
    if not candidates:
        return None
    mood_tokens = set(mood.replace("_", " ").lower().split())
    candidates.sort(key=lambda path: sum(token in path.stem.lower() for token in mood_tokens), reverse=True)
    return candidates[0]


def mix(generation: str | Path, video_path: str | Path, workspace: str | Path | None = None, *, mood: str = "") -> Path:
    folder = resolve_generation(generation, workspace)
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise RuntimeError("FFmpeg is required.")
    narration = folder / "audio" / "narration-normalized.wav"
    if not narration.exists():
        narration = folder / "voice" / "narration.wav"
    if not narration.exists():
        raise FileNotFoundError("Narration is missing.")
    config = load_config(workspace)
    music_mode = str(config.get("audio", {}).get("background_music", "adaptive"))
    music = find_music(workspace, mood) if music_mode != "never" else None
    output = folder / "temp" / "render" / "with-audio.mp4"
    ensure_dir(output.parent)
    if music:
        filter_complex = (
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[voice];"
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.10[music];"
            "[music][voice]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=400[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
        command = [ffmpeg, "-y", "-i", str(video_path), "-i", str(narration), "-stream_loop", "-1", "-i", str(music), "-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)]
    else:
        command = [ffmpeg, "-y", "-i", str(video_path), "-i", str(narration), "-map", "0:v", "-map", "1:a", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])
    return output
