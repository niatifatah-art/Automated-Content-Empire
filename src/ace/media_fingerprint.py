from __future__ import annotations

import hashlib
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from ace.utils import sha256_file


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}
VIDEO_SUFFIXES = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}


def _bits_to_hex(bits: list[bool]) -> str:
    value = 0
    for bit in bits:
        value = (value << 1) | int(bit)
    width = (len(bits) + 3) // 4
    return f"{value:0{width}x}"


def image_dhash(path: str | Path, hash_size: int = 8) -> str:
    with Image.open(path) as source:
        image = ImageOps.grayscale(source).resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
        pixels = list(image.get_flattened_data()) if hasattr(image, "get_flattened_data") else list(image.getdata())
    bits: list[bool] = []
    width = hash_size + 1
    for y in range(hash_size):
        row = y * width
        for x in range(hash_size):
            bits.append(pixels[row + x] > pixels[row + x + 1])
    return _bits_to_hex(bits)


def image_ahash(path: str | Path, hash_size: int = 8) -> str:
    with Image.open(path) as source:
        image = ImageOps.grayscale(source).resize((hash_size, hash_size), Image.Resampling.LANCZOS)
        pixels = list(image.get_flattened_data()) if hasattr(image, "get_flattened_data") else list(image.getdata())
    average = sum(pixels) / max(1, len(pixels))
    return _bits_to_hex([value >= average for value in pixels])


def hamming_distance(left: str, right: str) -> int:
    if not left or not right or len(left) != len(right):
        return max(len(left), len(right), 64)
    return (int(left, 16) ^ int(right, 16)).bit_count()


def video_frame_hashes(path: str | Path, samples: int = 3) -> list[str]:
    ffmpeg = shutil.which("ffmpeg")
    ffprobe = shutil.which("ffprobe")
    if not ffmpeg or not ffprobe:
        return []
    source = Path(path)
    probe = subprocess.run(
        [ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(source)],
        capture_output=True,
        text=True,
        check=False,
    )
    try:
        duration = max(0.1, float(probe.stdout.strip()))
    except (TypeError, ValueError):
        duration = 1.0
    hashes: list[str] = []
    with tempfile.TemporaryDirectory(prefix="ace-fingerprint-") as temp:
        root = Path(temp)
        for index in range(max(1, samples)):
            timestamp = duration * (index + 1) / (samples + 1)
            frame = root / f"frame-{index}.png"
            result = subprocess.run(
                [ffmpeg, "-y", "-ss", f"{timestamp:.3f}", "-i", str(source), "-frames:v", "1", "-vf", "scale=320:-2", str(frame)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and frame.exists():
                hashes.append(image_dhash(frame))
    return hashes


def fingerprint_bundle(path: str | Path, *, include_perceptual: bool = True) -> dict[str, Any]:
    source = Path(path)
    bundle: dict[str, Any] = {"sha256": sha256_file(source), "size": source.stat().st_size}
    suffix = source.suffix.lower()
    try:
        if suffix in IMAGE_SUFFIXES:
            bundle.update({"kind": "image", "dhash": image_dhash(source), "ahash": image_ahash(source)})
        elif suffix in VIDEO_SUFFIXES:
            bundle["kind"] = "video"
            if include_perceptual:
                frames = video_frame_hashes(source, samples=2)
                bundle["frame_dhashes"] = frames
                if frames:
                    digest = hashlib.sha256("|".join(frames).encode("ascii")).hexdigest()
                    bundle["perceptual"] = digest
        else:
            bundle["kind"] = "file"
    except Exception as exc:
        bundle["fingerprint_warning"] = str(exc)
    return bundle


def tokens(bundle: dict[str, Any] | None) -> set[str]:
    bundle = bundle or {}
    output: set[str] = set()
    for key in ("sha256", "dhash", "ahash", "perceptual"):
        value = bundle.get(key)
        if value:
            output.add(f"{key}:{value}")
    for value in bundle.get("frame_dhashes") or []:
        output.add(f"frame:{value}")
    return output


def perceptual_similarity(left: dict[str, Any] | None, right: dict[str, Any] | None) -> float:
    left = left or {}
    right = right or {}
    if left.get("sha256") and left.get("sha256") == right.get("sha256"):
        return 1.0
    scores: list[float] = []
    for key in ("dhash", "ahash"):
        if left.get(key) and right.get(key):
            distance = hamming_distance(str(left[key]), str(right[key]))
            scores.append(max(0.0, 1.0 - distance / 64.0))
    left_frames = list(left.get("frame_dhashes") or [])
    right_frames = list(right.get("frame_dhashes") or [])
    if left_frames and right_frames:
        best: list[float] = []
        for value in left_frames:
            best.append(max(max(0.0, 1.0 - hamming_distance(value, other) / 64.0) for other in right_frames))
        scores.append(sum(best) / len(best))
    return max(scores, default=0.0)
