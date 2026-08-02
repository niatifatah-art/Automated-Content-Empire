from __future__ import annotations

import math
from pathlib import Path
from typing import Iterable

from PIL import Image, ImageDraw, ImageFont

from ace.utils import ensure_dir


FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]
REGULAR_FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
]


def font_path(*, bold: bool = True) -> str:
    for candidate in (FONT_CANDIDATES if bold else REGULAR_FONT_CANDIDATES):
        if Path(candidate).exists():
            return candidate
    raise FileNotFoundError("No suitable system font found. Install DejaVu Sans.")


def font(size: int, *, bold: bool = True) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(font_path(bold=bold), max(8, int(size)))


def wrap_text(text: str, draw: ImageDraw.ImageDraw, selected_font: ImageFont.FreeTypeFont, max_width: int, *, max_lines: int | None = None) -> list[str]:
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for index, word in enumerate(words[1:], start=1):
        candidate = f"{current} {word}"
        if draw.textbbox((0, 0), candidate, font=selected_font)[2] <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
            if max_lines and len(lines) >= max_lines - 1:
                current = " ".join(words[index:])
                break
    lines.append(current)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines


def fit_text(text: str, draw: ImageDraw.ImageDraw, max_width: int, max_height: int, *, start_size: int, min_size: int = 24, max_lines: int = 3, bold: bool = True) -> tuple[ImageFont.FreeTypeFont, list[str]]:
    for size in range(start_size, min_size - 1, -2):
        selected = font(size, bold=bold)
        lines = wrap_text(text, draw, selected, max_width, max_lines=max_lines)
        line_height = int(size * 1.18)
        width = max((draw.textbbox((0, 0), line, font=selected)[2] for line in lines), default=0)
        height = line_height * len(lines)
        if width <= max_width and height <= max_height:
            return selected, lines
    selected = font(min_size, bold=bold)
    return selected, wrap_text(text, draw, selected, max_width, max_lines=max_lines)


def _gradient(size: tuple[int, int], start=(14, 23, 42), end=(31, 52, 88)) -> Image.Image:
    width, height = size
    image = Image.new("RGB", size)
    pixels = image.load()
    for y in range(height):
        ratio = y / max(1, height - 1)
        row = tuple(round(start[i] * (1 - ratio) + end[i] * ratio) for i in range(3))
        for x in range(width):
            pixels[x, y] = row
    return image


def create_card(
    output: str | Path,
    *,
    title: str,
    kicker: str | None = None,
    footer: str | None = None,
    label: str | None = None,
    size: tuple[int, int] = (1080, 1920),
    accent: tuple[int, int, int] = (72, 208, 255),
) -> Path:
    target = Path(output)
    ensure_dir(target.parent)
    image = _gradient(size)
    draw = ImageDraw.Draw(image)
    width, height = size
    margin = int(width * 0.085)
    safe_width = width - margin * 2
    draw.rounded_rectangle((margin, int(height * 0.13), width - margin, int(height * 0.86)), radius=40, fill=(10, 17, 31), outline=accent, width=4)
    y = int(height * 0.19)
    if label:
        label_font = font(int(width * 0.034), bold=True)
        box = draw.textbbox((0, 0), label.upper(), font=label_font)
        pad_x, pad_y = 22, 12
        draw.rounded_rectangle((margin + 44, y, margin + 44 + box[2] + pad_x * 2, y + box[3] + pad_y * 2), radius=18, fill=accent)
        draw.text((margin + 44 + pad_x, y + pad_y - 2), label.upper(), font=label_font, fill=(7, 14, 27))
        y += box[3] + pad_y * 2 + 68
    if kicker:
        kicker_font = font(int(width * 0.036), bold=False)
        lines = wrap_text(kicker, draw, kicker_font, safe_width - 88, max_lines=2)
        for line in lines:
            draw.text((margin + 44, y), line, font=kicker_font, fill=(180, 196, 220))
            y += int(kicker_font.size * 1.3)
        y += 24
    title_font, lines = fit_text(title, draw, safe_width - 88, int(height * 0.40), start_size=int(width * 0.085), min_size=int(width * 0.045), max_lines=5, bold=True)
    for line in lines:
        draw.text((margin + 44, y), line, font=title_font, fill=(246, 249, 255))
        y += int(title_font.size * 1.18)
    if footer:
        footer_font = font(int(width * 0.033), bold=False)
        footer_y = int(height * 0.79)
        draw.line((margin + 44, footer_y - 34, width - margin - 44, footer_y - 34), fill=(76, 94, 123), width=2)
        footer_lines = wrap_text(footer, draw, footer_font, safe_width - 88, max_lines=3)
        for line in footer_lines:
            draw.text((margin + 44, footer_y), line, font=footer_font, fill=(174, 190, 215))
            footer_y += int(footer_font.size * 1.35)
    image.save(target, quality=95)
    return target


def create_meme_card(output: str | Path, *, setup: str, punchline: str, size: tuple[int, int] = (1080, 1920)) -> Path:
    target = Path(output)
    ensure_dir(target.parent)
    image = _gradient(size, start=(34, 19, 48), end=(11, 34, 48))
    draw = ImageDraw.Draw(image)
    width, height = size
    margin = int(width * 0.08)
    setup_font, setup_lines = fit_text(setup, draw, width - margin * 2, int(height * 0.25), start_size=66, min_size=38, max_lines=4)
    punch_font, punch_lines = fit_text(punchline, draw, width - margin * 2, int(height * 0.34), start_size=92, min_size=48, max_lines=5)
    y = int(height * 0.18)
    for line in setup_lines:
        draw.text((margin, y), line, font=setup_font, fill=(205, 214, 232))
        y += int(setup_font.size * 1.2)
    y = int(height * 0.52)
    for line in punch_lines:
        bbox = draw.textbbox((0, 0), line, font=punch_font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x + 4, y + 5), line, font=punch_font, fill=(0, 0, 0))
        draw.text((x, y), line, font=punch_font, fill=(255, 255, 255), stroke_width=2, stroke_fill=(30, 10, 45))
        y += int(punch_font.size * 1.14)
    image.save(target, quality=95)
    return target


def create_abstract_visual(
    output: str | Path,
    *,
    concept: str,
    label: str = "ACE VISUAL",
    size: tuple[int, int] = (1080, 1920),
    show_concept: bool = True,
) -> Path:
    """Create a text-light original visual so subtitles do not duplicate a full card."""
    target = Path(output)
    ensure_dir(target.parent)
    image = _gradient(size, start=(9, 18, 35), end=(22, 50, 80))
    draw = ImageDraw.Draw(image)
    width, height = size
    cx, cy = width // 2, int(height * 0.45)
    for radius, outline_width in ((330, 8), (240, 6), (150, 5)):
        box = (cx - radius, cy - radius, cx + radius, cy + radius)
        draw.ellipse(box, outline=(72, 208, 255), width=outline_width)
    for angle in range(0, 360, 45):
        radians = math.radians(angle)
        x1 = cx + int(math.cos(radians) * 150)
        y1 = cy + int(math.sin(radians) * 150)
        x2 = cx + int(math.cos(radians) * 330)
        y2 = cy + int(math.sin(radians) * 330)
        draw.line((x1, y1, x2, y2), fill=(80, 133, 184), width=4)
    label_font = font(34, bold=True)
    draw.rounded_rectangle((70, 85, 330, 145), radius=18, fill=(72, 208, 255))
    draw.text((91, 98), label, font=label_font, fill=(7, 14, 27))
    if show_concept:
        keywords = " ".join(concept.strip().split()[:3]).upper() or "TECH"
        selected, lines = fit_text(keywords, draw, width - 150, int(height * 0.16), start_size=72, min_size=38, max_lines=2)
        y = int(height * 0.75)
        for line in lines:
            bbox = draw.textbbox((0, 0), line, font=selected)
            x = (width - (bbox[2] - bbox[0])) // 2
            draw.text((x, y), line, font=selected, fill=(214, 230, 247))
            y += int(selected.size * 1.18)
    image.save(target, quality=95)
    return target
