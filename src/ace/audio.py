from __future__ import annotations

import math
import random
import shutil
import struct
import subprocess
import wave
from array import array
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


def generate_sfx_track(
    generation: str | Path,
    shots: list[dict] | list[object],
    workspace: str | Path | None = None,
) -> Path | None:
    """Generate a restrained, license-free SFX track from edit directives."""
    folder = resolve_generation(generation, workspace)
    mode = str(load_config(workspace).get("audio", {}).get("sound_effects", "minimal"))
    if mode in {"none", "never", "off"}:
        return None
    events: list[tuple[float, str]] = []
    total = 0.0
    for row in shots:
        if isinstance(row, dict):
            start = float(row.get("start") or 0)
            end = float(row.get("end") or start + float(row.get("duration") or 0))
            creative = dict((row.get("metadata") or {}).get("creative") or {})
        else:
            start = float(getattr(row, "start", 0))
            end = float(getattr(row, "end", start + float(getattr(row, "duration", 0))))
            creative = dict((getattr(row, "metadata", {}) or {}).get("creative") or {})
        total = max(total, end)
        kind = str(creative.get("sfx") or "")
        if kind:
            events.append((start + 0.02, kind))
    if not events or total <= 0:
        return None

    rate = 48000
    samples = array("f", [0.0]) * int((total + 0.4) * rate)
    rng = random.Random(210)

    def add_event(when: float, kind: str) -> None:
        start_index = int(max(0.0, when) * rate)
        lengths = {"impact": 0.22, "pop": 0.13, "soft_tick": 0.08, "whoosh": 0.26}
        length = lengths.get(kind, 0.10)
        count = int(length * rate)
        for index in range(count):
            position = start_index + index
            if position >= len(samples):
                break
            t = index / rate
            progress = index / max(1, count - 1)
            envelope = math.exp(-6.5 * progress)
            if kind == "impact":
                frequency = 115 - 55 * progress
                value = math.sin(2 * math.pi * frequency * t) * envelope * 0.34
            elif kind == "pop":
                frequency = 720 - 220 * progress
                value = math.sin(2 * math.pi * frequency * t) * envelope * 0.20
            elif kind == "whoosh":
                frequency = 240 + 900 * progress
                value = (math.sin(2 * math.pi * frequency * t) * 0.10 + (rng.random() * 2 - 1) * 0.035) * math.sin(math.pi * progress)
            else:
                value = math.sin(2 * math.pi * 1200 * t) * envelope * 0.10
            samples[position] = max(-1.0, min(1.0, samples[position] + value))

    for event in events:
        add_event(*event)

    output = ensure_dir(folder / "audio") / "creative-sfx.wav"
    with wave.open(str(output), "wb") as handle:
        handle.setnchannels(2)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for value in samples:
            sample = int(max(-1.0, min(1.0, value)) * 32767)
            frames.extend(struct.pack("<hh", sample, sample))
        handle.writeframes(frames)
    write_json(folder / "quality" / "sfx-report.json", {"status": "passed", "event_count": len(events), "events": [{"time": item[0], "type": item[1]} for item in events], "path": str(output)})
    return output


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
    sfx = folder / "audio" / "creative-sfx.wav"
    if not sfx.exists():
        sfx = None
    output = folder / "temp" / "render" / "with-audio.mp4"
    ensure_dir(output.parent)

    command = [ffmpeg, "-y", "-i", str(video_path), "-i", str(narration)]
    if music:
        command += ["-stream_loop", "-1", "-i", str(music)]
    if sfx:
        command += ["-i", str(sfx)]

    if music and sfx:
        filter_complex = (
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[voice];"
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.10[music];"
            "[music][voice]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=400[ducked];"
            "[3:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.42[sfx];"
            "[voice][ducked][sfx]amix=inputs=3:duration=first:normalize=0[aout]"
        )
    elif music:
        filter_complex = (
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[voice];"
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.10[music];"
            "[music][voice]sidechaincompress=threshold=0.025:ratio=10:attack=20:release=400[ducked];"
            "[voice][ducked]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    elif sfx:
        filter_complex = (
            "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[voice];"
            "[2:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=0.42[sfx];"
            "[voice][sfx]amix=inputs=2:duration=first:normalize=0[aout]"
        )
    else:
        filter_complex = "[1:a]aformat=sample_rates=48000:channel_layouts=stereo,volume=1.0[aout]"

    command += ["-filter_complex", filter_complex, "-map", "0:v", "-map", "[aout]", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest", str(output)]
    result = subprocess.run(command, capture_output=True, text=True, check=False)
    if result.returncode != 0:
        raise RuntimeError(result.stderr[-4000:])
    return output

