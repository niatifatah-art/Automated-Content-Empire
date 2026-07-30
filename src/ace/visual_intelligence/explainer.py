from __future__ import annotations

import hashlib
import math
import shutil
import subprocess
import tempfile
import textwrap
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from PIL import Image, ImageDraw, ImageFont

from ace.utils import ensure_dir, slugify
from ace.visual_intelligence.contracts import ShotIntent, VisualFormat


@dataclass(slots=True)
class ExplainerResult:
    path: Path
    semantic_elements: list[str]
    description: str
    animated: bool
    visual_format: str = VisualFormat.ANIMATED_EXPLAINER.value


BACKGROUND = (3, 25, 37)
PANEL = (8, 44, 61)
PANEL_2 = (12, 60, 79)
ACCENT = (26, 218, 244)
ACCENT_2 = (95, 237, 181)
WARNING = (255, 93, 93)
GOLD = (255, 210, 95)
TEXT = (244, 248, 250)
MUTED = (150, 176, 190)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def _canvas(size: tuple[int, int]) -> tuple[Image.Image, ImageDraw.ImageDraw]:
    image = Image.new("RGB", size, BACKGROUND)
    draw = ImageDraw.Draw(image)
    width, height = size
    for y in range(height):
        ratio = y / max(1, height - 1)
        color = (
            int(BACKGROUND[0] + ratio * 5),
            int(BACKGROUND[1] + ratio * 25),
            int(BACKGROUND[2] + ratio * 30),
        )
        draw.line((0, y, width, y), fill=color)
    return image, draw


def _fit_text(draw: ImageDraw.ImageDraw, text: str, max_width: int, *, max_size: int, min_size: int = 18, bold: bool = True) -> ImageFont.ImageFont:
    for size in range(max_size, min_size - 1, -1):
        font = _font(size, bold=bold)
        bbox = draw.textbbox((0, 0), text, font=font)
        if bbox[2] - bbox[0] <= max_width:
            return font
    return _font(min_size, bold=bold)


def _center_text(draw: ImageDraw.ImageDraw, xy: tuple[float, float], text: str, *, fill=TEXT, font=None) -> None:
    font = font or _font(28, bold=True)
    bbox = draw.textbbox((0, 0), text, font=font)
    draw.text((xy[0] - (bbox[2] - bbox[0]) / 2, xy[1] - (bbox[3] - bbox[1]) / 2), text, fill=fill, font=font)


def _header(draw: ImageDraw.ImageDraw, size: tuple[int, int], intent: ShotIntent, label: str = "EXPLAINER") -> None:
    width, _ = size
    # Measure the badge instead of estimating from character count. Long labels
    # such as "ROGUE HOTSPOT" must remain fully visible in vertical renders.
    badge_font = _fit_text(draw, label, 270, max_size=27, min_size=17)
    label_bbox = draw.textbbox((0, 0), label, font=badge_font)
    badge_width = max(150, min(300, (label_bbox[2] - label_bbox[0]) + 42))
    draw.rounded_rectangle((48, 54, 48 + badge_width, 108), radius=17, fill=ACCENT)
    label_height = label_bbox[3] - label_bbox[1]
    draw.text((69, 81 - label_height / 2 - label_bbox[1]), label, fill=(0, 22, 32), font=badge_font)

    title = intent.subject.replace("_", " ").upper()
    if len(title) > 34:
        title = title[:31] + "…"
    title_width = max(220, width - badge_width - 150)
    font = _fit_text(draw, title, title_width, max_size=25, min_size=16)
    bbox = draw.textbbox((0, 0), title, font=font)
    draw.text((width - (bbox[2] - bbox[0]) - 48, 69), title, fill=MUTED, font=font)


def _footer(draw: ImageDraw.ImageDraw, size: tuple[int, int], intent: ShotIntent) -> None:
    """Small semantic footer, never a full sentence-sized subtitle.

    Visible captions are directed independently. The footer only anchors the
    explainer with a short idea label, and disappears when the narration is too
    long to fit cleanly.
    """
    if not bool(intent.metadata.get("show_explainer_footer", False)):
        return
    width, height = size
    text = " ".join(intent.narration.strip().split())
    if not text:
        return
    words = text.split()
    # Keep the visual clean: at most 10 words and two short lines.
    short = " ".join(words[:10]) + ("…" if len(words) > 10 else "")
    lines = textwrap.wrap(short, width=34)[:2]
    if not lines:
        return
    font = _font(25, bold=True)
    panel_top = height - (132 if len(lines) == 1 else 158)
    draw.rounded_rectangle((48, panel_top, width - 48, height - 54), radius=24, fill=PANEL)
    line_height = 33
    start_y = panel_top + 19
    for index, line in enumerate(lines):
        _center_text(draw, (width / 2, start_y + index * line_height + 13), line, font=font)


def _device(draw: ImageDraw.ImageDraw, center: tuple[float, float], label: str, *, active: bool = True) -> None:
    x, y = center
    fill = (15, 70, 91) if active else (35, 50, 59)
    outline = ACCENT if active else MUTED
    draw.rounded_rectangle((x - 75, y - 52, x + 75, y + 52), radius=18, fill=fill, outline=outline, width=4)
    draw.rectangle((x - 55, y - 30, x + 55, y + 18), fill=(5, 18, 26), outline=outline, width=2)
    draw.ellipse((x - 7, y + 29, x + 7, y + 43), fill=outline)
    _center_text(draw, (x, y + 76), label, font=_font(20, bold=True))


def _phone(draw: ImageDraw.ImageDraw, center: tuple[float, float], label: str = "PHONE", *, active: bool = True) -> None:
    x, y = center
    outline = ACCENT if active else MUTED
    draw.rounded_rectangle((x - 58, y - 96, x + 58, y + 96), radius=22, fill=(7, 26, 36), outline=outline, width=5)
    draw.rounded_rectangle((x - 43, y - 70, x + 43, y + 64), radius=10, fill=PANEL_2)
    draw.ellipse((x - 8, y + 72, x + 8, y + 88), outline=outline, width=3)
    _center_text(draw, (x, y + 124), label, font=_font(20, bold=True))


def _router(draw: ImageDraw.ImageDraw, center: tuple[float, float], *, warning: bool = False, label: str = "WI-FI ROUTER") -> None:
    x, y = center
    color = WARNING if warning else ACCENT
    draw.rounded_rectangle((x - 105, y - 55, x + 105, y + 55), radius=25, fill=(9, 42, 58), outline=color, width=5)
    draw.line((x - 72, y - 55, x - 100, y - 135), fill=color, width=5)
    draw.line((x + 72, y - 55, x + 100, y - 135), fill=color, width=5)
    for offset in (-50, 0, 50):
        draw.ellipse((x + offset - 8, y + 14, x + offset + 8, y + 30), fill=color)
    _center_text(draw, (x, y + 83), label, font=_font(22, bold=True))


def _lock(draw: ImageDraw.ImageDraw, center: tuple[float, float], *, locked: bool, scale: float = 1.0) -> None:
    x, y = center
    color = ACCENT_2 if locked else WARNING
    w, h = 68 * scale, 60 * scale
    draw.rounded_rectangle((x - w, y - h / 2, x + w, y + h), radius=15 * scale, fill=(8, 42, 52), outline=color, width=max(2, int(5 * scale)))
    if locked:
        draw.arc((x - 48 * scale, y - 82 * scale, x + 48 * scale, y + 20 * scale), start=180, end=360, fill=color, width=max(2, int(7 * scale)))
    else:
        draw.arc((x - 42 * scale, y - 82 * scale, x + 52 * scale, y + 20 * scale), start=205, end=330, fill=color, width=max(2, int(7 * scale)))
    draw.ellipse((x - 9 * scale, y + 7 * scale, x + 9 * scale, y + 25 * scale), fill=color)
    draw.rectangle((x - 4 * scale, y + 21 * scale, x + 4 * scale, y + 42 * scale), fill=color)


def _packet(draw: ImageDraw.ImageDraw, point: tuple[float, float], *, protected: bool, label: str = "DATA") -> None:
    x, y = point
    color = ACCENT_2 if protected else WARNING
    draw.rounded_rectangle((x - 43, y - 25, x + 43, y + 25), radius=11, fill=(8, 43, 56), outline=color, width=3)
    _center_text(draw, (x, y), label, fill=color, font=_font(16, bold=True))


def _line(draw: ImageDraw.ImageDraw, start: tuple[float, float], end: tuple[float, float], *, color=ACCENT, width: int = 5) -> None:
    draw.line((*start, *end), fill=color, width=width)


def _interpolate(start: tuple[float, float], end: tuple[float, float], t: float) -> tuple[float, float]:
    return start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t


def _network_frame(intent: ShotIntent, size: tuple[int, int], progress: float, *, protected: bool) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "NETWORK")
    router = (width / 2, height * 0.48)
    _router(draw, router)
    devices = [(width * 0.22, height * 0.29), (width * 0.78, height * 0.29), (width * 0.24, height * 0.69), (width * 0.76, height * 0.69)]
    for index, point in enumerate(devices):
        _line(draw, router, point, color=(50, 131, 151), width=4)
        if index in {0, 3}:
            _phone(draw, point, f"DEVICE {index + 1}")
        else:
            _device(draw, point, f"DEVICE {index + 1}")
        packet_point = _interpolate(point, router, (progress + index * 0.17) % 1.0)
        _packet(draw, packet_point, protected=protected)
    _lock(draw, (width / 2, height * 0.27), locked=protected, scale=0.75)
    label = "ENCRYPTED PACKETS" if protected else "PACKETS ARE EXPOSED"
    _center_text(draw, (width / 2, height * 0.18), label, fill=ACCENT_2 if protected else WARNING, font=_font(32, bold=True))
    _footer(draw, size, intent)
    return image


def _rogue_hotspot_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "ROGUE HOTSPOT")
    left = (width * 0.29, height * 0.41)
    right = (width * 0.71, height * 0.41)
    _router(draw, left, warning=False, label="TRUSTED")
    _router(draw, right, warning=True, label="LOOKALIKE")
    _center_text(draw, (left[0], left[1] + 126), "Cafe_WiFi", fill=ACCENT_2, font=_font(27, bold=True))
    _center_text(draw, (right[0], right[1] + 126), "Cafe_WiFi_Free", fill=WARNING, font=_font(27, bold=True))
    _phone(draw, (width / 2, height * 0.72), "YOUR PHONE")
    target = right if progress < 0.55 else left
    _line(draw, (width / 2, height * 0.62), target, color=WARNING if target == right else ACCENT_2, width=8)
    _center_text(draw, (width / 2, height * 0.19), "SAME NAME. DIFFERENT OWNER.", fill=GOLD, font=_font(29, bold=True))
    _footer(draw, size, intent)
    return image


def _vpn_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "VPN TUNNEL")
    phone = (width * 0.18, height * 0.47)
    server = (width * 0.82, height * 0.47)
    _phone(draw, phone, "DEVICE")
    _device(draw, server, "VPN SERVER")
    draw.rounded_rectangle((width * 0.29, height * 0.36, width * 0.71, height * 0.57), radius=70, outline=ACCENT_2, width=10)
    draw.rounded_rectangle((width * 0.31, height * 0.39, width * 0.69, height * 0.54), radius=55, outline=(20, 92, 105), width=4)
    _packet(draw, _interpolate((width * 0.31, height * 0.465), (width * 0.69, height * 0.465), progress), protected=True)
    _lock(draw, (width / 2, height * 0.28), locked=True, scale=0.8)
    _center_text(draw, (width / 2, height * 0.63), "ENCRYPTED TUNNEL", fill=ACCENT_2, font=_font(31, bold=True))
    _footer(draw, size, intent)
    return image


def _passkey_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "PASSKEY FLOW")
    device = (width * 0.24, height * 0.47)
    site = (width * 0.76, height * 0.47)
    _phone(draw, device, "YOUR DEVICE")
    _device(draw, site, "WEBSITE")
    _line(draw, (device[0] + 82, device[1] - 35), (site[0] - 96, site[1] - 35), color=(49, 130, 149), width=5)
    _line(draw, (site[0] - 96, site[1] + 35), (device[0] + 82, device[1] + 35), color=(49, 130, 149), width=5)
    if progress < 0.5:
        point = _interpolate((site[0] - 96, site[1] - 35), (device[0] + 82, device[1] - 35), progress * 2)
        _packet(draw, point, protected=False, label="CHALLENGE")
    else:
        point = _interpolate((device[0] + 82, device[1] + 35), (site[0] - 96, site[1] + 35), (progress - 0.5) * 2)
        _packet(draw, point, protected=True, label="SIGNATURE")
    _lock(draw, (device[0], height * 0.25), locked=True, scale=0.6)
    _center_text(draw, (device[0], height * 0.18), "PRIVATE KEY STAYS HERE", fill=ACCENT_2, font=_font(25, bold=True))
    _center_text(draw, (site[0], height * 0.18), "NO PASSWORD SENT", fill=GOLD, font=_font(25, bold=True))
    _footer(draw, size, intent)
    return image


def _partnership_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "PARTNERSHIP")
    left = (width * 0.26, height * 0.44)
    right = (width * 0.74, height * 0.44)
    draw.rounded_rectangle((left[0] - 145, left[1] - 95, left[0] + 145, left[1] + 95), radius=28, fill=PANEL, outline=ACCENT, width=6)
    draw.rounded_rectangle((right[0] - 145, right[1] - 95, right[0] + 145, right[1] + 95), radius=28, fill=PANEL, outline=ACCENT_2, width=6)
    _center_text(draw, left, "COMPANY A", font=_font(34, bold=True))
    _center_text(draw, right, "COMPANY B", font=_font(34, bold=True))
    arrow_start = (left[0] + 165, left[1])
    arrow_end = (right[0] - 165, right[1])
    visible_end = _interpolate(arrow_start, arrow_end, min(1.0, progress * 1.6))
    _line(draw, arrow_start, visible_end, color=ACCENT_2, width=11)
    if progress > 0.6:
        draw.polygon([(arrow_end[0], arrow_end[1]), (arrow_end[0] - 32, arrow_end[1] - 21), (arrow_end[0] - 32, arrow_end[1] + 21)], fill=ACCENT_2)
    _center_text(draw, (width / 2, height * 0.63), "CAPABILITY + DISTRIBUTION", fill=GOLD, font=_font(29, bold=True))
    draw.rounded_rectangle((width * 0.24, height * 0.70, width * 0.76, height * 0.79), radius=25, fill=(12, 68, 83))
    _center_text(draw, (width / 2, height * 0.745), "SHARED OUTCOME", font=_font(34, bold=True))
    _footer(draw, size, intent)
    return image


def _software_flow_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "SYSTEM FLOW")
    nodes = [
        (width * 0.18, height * 0.44, "REQUEST"),
        (width * 0.50, height * 0.32, "CLOUD"),
        (width * 0.50, height * 0.57, "FALLBACK"),
        (width * 0.82, height * 0.44, "RESULT"),
    ]
    for x, y, label in nodes:
        draw.rounded_rectangle((x - 95, y - 58, x + 95, y + 58), radius=22, fill=PANEL, outline=ACCENT if label != "FALLBACK" else ACCENT_2, width=5)
        _center_text(draw, (x, y), label, font=_font(25, bold=True))
    paths = [
        ((width * 0.28, height * 0.44), (width * 0.40, height * 0.34)),
        ((width * 0.60, height * 0.34), (width * 0.72, height * 0.44)),
        ((width * 0.28, height * 0.46), (width * 0.40, height * 0.56)),
        ((width * 0.60, height * 0.56), (width * 0.72, height * 0.46)),
    ]
    for index, (start, end) in enumerate(paths):
        _line(draw, start, end, color=(47, 118, 139), width=5)
        _packet(draw, _interpolate(start, end, (progress + index * 0.21) % 1.0), protected=True, label="API")
    _footer(draw, size, intent)
    return image


def _comparison_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "COMPARISON")
    draw.rounded_rectangle((70, 270, width / 2 - 20, 890), radius=28, fill=PANEL, outline=ACCENT, width=5)
    draw.rounded_rectangle((width / 2 + 20, 270, width - 70, 890), radius=28, fill=PANEL, outline=ACCENT_2, width=5)
    _center_text(draw, (width * 0.28, 340), "OPTION A", fill=ACCENT, font=_font(36, bold=True))
    _center_text(draw, (width * 0.72, 340), "OPTION B", fill=ACCENT_2, font=_font(36, bold=True))
    criteria = ["SPEED", "COST", "QUALITY", "CONTROL"]
    for index, criterion in enumerate(criteria):
        y = 430 + index * 105
        draw.text((104, y), criterion, fill=TEXT, font=_font(26, bold=True))
        left_bar = int((0.55 + 0.1 * math.sin(index + progress * math.pi * 2)) * 210)
        right_bar = int((0.72 + 0.08 * math.cos(index + progress * math.pi * 2)) * 210)
        draw.rounded_rectangle((100, y + 42, 100 + left_bar, y + 66), radius=10, fill=ACCENT)
        draw.rounded_rectangle((width / 2 + 55, y + 42, width / 2 + 55 + right_bar, y + 66), radius=10, fill=ACCENT_2)
    _footer(draw, size, intent)
    return image


def _terminal_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "TERMINAL DEMO")
    x1, y1, x2, y2 = 62, 225, width - 62, 930
    draw.rounded_rectangle((x1, y1, x2, y2), radius=26, fill=(4, 13, 18), outline=(60, 101, 118), width=4)
    draw.rounded_rectangle((x1, y1, x2, y1 + 65), radius=24, fill=(26, 42, 50))
    for idx, color in enumerate((WARNING, GOLD, ACCENT_2)):
        draw.ellipse((x1 + 28 + idx * 36, y1 + 23, x1 + 46 + idx * 36, y1 + 41), fill=color)
    draw.text((x1 + 30, y1 + 105), "fatah@ace:~$", fill=ACCENT_2, font=_font(29, bold=True))
    command = intent.metadata.get("command") if isinstance(intent.metadata, dict) else None
    if not command:
        match_words = intent.narration.strip().split()
        command = " ".join(match_words[:8]) if match_words else "ace visuals inspect last"
    command = str(command).strip()
    visible = command[: max(1, int(len(command) * min(1.0, progress * 1.4)))]
    font = _fit_text(draw, visible or " ", x2 - x1 - 75, max_size=31, min_size=22)
    draw.text((x1 + 30, y1 + 162), visible, fill=TEXT, font=font)
    if progress > 0.55:
        result_lines = ["✓ command completed", "✓ output verified", "exit code: 0"]
        for index, line in enumerate(result_lines):
            draw.text((x1 + 30, y1 + 275 + index * 58), line, fill=ACCENT_2 if index < 2 else MUTED, font=_font(27, bold=index < 2))
    cursor_x = x1 + 30 + draw.textlength(visible, font=font)
    if int(progress * 12) % 2 == 0:
        draw.rectangle((cursor_x + 4, y1 + 165, cursor_x + 19, y1 + 202), fill=ACCENT)
    _footer(draw, size, intent)
    return image


def _phone_hotspot_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "PHONE HOTSPOT")
    cx, cy = width / 2, height * 0.47
    draw.rounded_rectangle((cx - 215, cy - 355, cx + 215, cy + 355), radius=52, fill=(5, 17, 25), outline=ACCENT, width=7)
    draw.rounded_rectangle((cx - 178, cy - 295, cx + 178, cy + 292), radius=28, fill=PANEL_2)
    _center_text(draw, (cx, cy - 245), "PERSONAL HOTSPOT", font=_font(31, bold=True))
    rows = [("Allow Others to Join", True), ("Maximize Compatibility", False)]
    for index, (label, enabled) in enumerate(rows):
        y = cy - 135 + index * 135
        draw.text((cx - 145, y), label, fill=TEXT, font=_font(25, bold=True))
        toggle_x = cx + 105
        active = enabled and progress > 0.25
        draw.rounded_rectangle((toggle_x - 55, y - 5, toggle_x + 55, y + 45), radius=25, fill=ACCENT_2 if active else (74, 91, 101))
        knob_x = toggle_x + 31 if active else toggle_x - 31
        draw.ellipse((knob_x - 20, y, knob_x + 20, y + 40), fill=TEXT)
    _center_text(draw, (cx, cy + 135), "Wi-Fi Password", fill=MUTED, font=_font(24, bold=True))
    draw.rounded_rectangle((cx - 145, cy + 175, cx + 145, cy + 240), radius=16, fill=(4, 20, 28), outline=ACCENT_2, width=3)
    _center_text(draw, (cx, cy + 207), "••••••••••", fill=TEXT, font=_font(29, bold=True))
    if progress > 0.5:
        _device(draw, (width * 0.82, height * 0.72), "CONNECTED")
        _line(draw, (cx + 180, cy + 60), (width * 0.75, height * 0.67), color=ACCENT_2, width=6)
    _footer(draw, size, intent)
    return image


def _browser_https_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "BROWSER SECURITY")
    x1, y1, x2, y2 = 55, 245, width - 55, 900
    draw.rounded_rectangle((x1, y1, x2, y2), radius=26, fill=(247, 249, 250), outline=(70, 99, 110), width=4)
    draw.rounded_rectangle((x1, y1, x2, y1 + 78), radius=24, fill=(28, 43, 52))
    address_x1, address_x2 = x1 + 85, x2 - 30
    draw.rounded_rectangle((address_x1, y1 + 18, address_x2, y1 + 60), radius=18, fill=(237, 243, 246))
    _lock(draw, (address_x1 + 31, y1 + 31), locked=progress > 0.3, scale=0.24)
    scheme = "https://" if progress > 0.3 else "http://"
    draw.text((address_x1 + 62, y1 + 26), scheme + "example.com", fill=(17, 57, 70), font=_font(20, bold=True))
    _center_text(draw, (width / 2, y1 + 200), "BROWSER ↔ WEBSITE", fill=(18, 64, 79), font=_font(34, bold=True))
    for index in range(3):
        start = (width * 0.22, y1 + 330 + index * 70)
        end = (width * 0.78, start[1])
        draw.line((*start, *end), fill=(114, 148, 160), width=5)
        _packet(draw, _interpolate(start, end, (progress + index * 0.23) % 1.0), protected=progress > 0.3)
    label = "ENCRYPTED IN TRANSIT" if progress > 0.3 else "NOT PROTECTED"
    _center_text(draw, (width / 2, y2 - 75), label, fill=ACCENT_2 if progress > 0.3 else WARNING, font=_font(31, bold=True))
    _footer(draw, size, intent)
    return image


def _code_logic_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "CODE LOGIC")
    x1, y1, x2, y2 = 58, 235, width - 58, 930
    draw.rounded_rectangle((x1, y1, x2, y2), radius=25, fill=(7, 17, 24), outline=(49, 97, 117), width=4)
    lines = [
        ("def authenticate(user):", ACCENT),
        ("    challenge = server.create()", TEXT),
        ("    signature = device.sign(challenge)", ACCENT_2),
        ("    return server.verify(signature)", GOLD),
    ]
    reveal = max(1, int(progress * (len(lines) + 1)))
    for index, (line, color) in enumerate(lines[:reveal]):
        draw.text((x1 + 32, y1 + 75 + index * 92), line, fill=color, font=_fit_text(draw, line, x2 - x1 - 65, max_size=27, min_size=19, bold=False))
    stages = [("INPUT", width * 0.19), ("LOGIC", width * 0.5), ("RESULT", width * 0.81)]
    for index, (label, x) in enumerate(stages):
        y = y2 - 120
        draw.rounded_rectangle((x - 78, y - 45, x + 78, y + 45), radius=18, fill=PANEL, outline=ACCENT_2 if index <= progress * 3 else MUTED, width=4)
        _center_text(draw, (x, y), label, font=_font(23, bold=True))
        if index < len(stages) - 1:
            _line(draw, (x + 82, y), (stages[index + 1][1] - 82, y), color=ACCENT, width=5)
    _footer(draw, size, intent)
    return image


def _timeline_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "TIMELINE")
    x = width * 0.25
    y_start, y_end = height * 0.25, height * 0.77
    draw.line((x, y_start, x, y_end), fill=(53, 113, 132), width=8)
    labels = ["START", "CHANGE", "RESULT", "NEXT"]
    for index, label in enumerate(labels):
        y = y_start + index * ((y_end - y_start) / (len(labels) - 1))
        active = progress >= index / max(1, len(labels) - 1)
        color = ACCENT_2 if active else MUTED
        draw.ellipse((x - 23, y - 23, x + 23, y + 23), fill=PANEL, outline=color, width=6)
        draw.rounded_rectangle((x + 65, y - 48, width - 70, y + 48), radius=20, fill=PANEL, outline=color, width=4)
        draw.text((x + 96, y - 18), label, fill=TEXT, font=_font(28, bold=True))
    _footer(draw, size, intent)
    return image


def _challenge_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent, "CHALLENGE")
    day = max(1, min(7, int(progress * 7) + 1))
    _center_text(draw, (width / 2, height * 0.30), f"DAY {day} / 7", fill=GOLD, font=_font(68, bold=True))
    bar_x1, bar_x2, bar_y = 90, width - 90, height * 0.46
    draw.rounded_rectangle((bar_x1, bar_y, bar_x2, bar_y + 56), radius=28, fill=(39, 66, 78))
    fill_x = bar_x1 + (bar_x2 - bar_x1) * progress
    draw.rounded_rectangle((bar_x1, bar_y, fill_x, bar_y + 56), radius=28, fill=ACCENT_2)
    labels = [("SETUP", 0.12), ("FAIL", 0.38), ("ADAPT", 0.64), ("VERDICT", 0.9)]
    for label, p in labels:
        x = bar_x1 + (bar_x2 - bar_x1) * p
        draw.line((x, bar_y + 65, x, bar_y + 110), fill=MUTED, width=3)
        _center_text(draw, (x, bar_y + 145), label, fill=TEXT if progress >= p else MUTED, font=_font(22, bold=True))
    _center_text(draw, (width / 2, height * 0.70), "PROGRESS, FAILURES, RESULT", fill=ACCENT, font=_font(30, bold=True))
    _footer(draw, size, intent)
    return image


def _generic_frame(intent: ShotIntent, size: tuple[int, int], progress: float) -> Image.Image:
    image, draw = _canvas(size)
    width, height = size
    _header(draw, size, intent)
    cx, cy = width / 2, height * 0.47
    rings = [80, 150, 230]
    for index, radius in enumerate(rings):
        angle = progress * 360 * (1 if index % 2 == 0 else -1)
        draw.arc((cx - radius, cy - radius, cx + radius, cy + radius), start=angle, end=angle + 250, fill=ACCENT if index % 2 == 0 else ACCENT_2, width=6)
    for index, element in enumerate(intent.required_elements[:5]):
        angle = progress * math.tau + index * (math.tau / max(1, len(intent.required_elements[:5])))
        x = cx + math.cos(angle) * 230
        y = cy + math.sin(angle) * 230
        draw.ellipse((x - 25, y - 25, x + 25, y + 25), fill=PANEL, outline=ACCENT, width=4)
        _center_text(draw, (x, y + 48), element.replace("_", " ")[:14].upper(), fill=MUTED, font=_font(14, bold=True))
    title = intent.subject.replace("_", " ").upper()
    font = _fit_text(draw, title, width - 130, max_size=42, min_size=24)
    _center_text(draw, (cx, cy), title, font=font)
    _footer(draw, size, intent)
    return image


FrameFactory = Callable[[ShotIntent, tuple[int, int], float], Image.Image]


def _frame_factory(intent: ShotIntent, visual_format: str | None = None) -> tuple[FrameFactory, list[str], str, str]:
    subject = intent.subject.lower()
    required = {value.lower() for value in intent.required_elements}
    preferred = set(intent.preferred_formats)
    requested = visual_format or (intent.preferred_formats[0] if intent.preferred_formats else VisualFormat.ANIMATED_EXPLAINER.value)

    if requested == VisualFormat.TERMINAL_DEMO.value or "terminal" in required or "exact_command" in required:
        return _terminal_frame, ["terminal", "exact_command", "visible_result"], "A readable terminal demonstration shows the exact action and result.", VisualFormat.TERMINAL_DEMO.value
    if "phone_personal_hotspot" in subject or "hotspot_settings" in required:
        return _phone_hotspot_frame, ["smartphone", "hotspot_settings", "connected_device"], "A literal phone settings view demonstrates Personal Hotspot instead of generic Wi-Fi footage.", VisualFormat.APPLICATION_DEMO.value
    if requested == VisualFormat.BROWSER_DEMO.value or "https" in subject or "browser" in required:
        return _browser_https_frame, ["browser_address_bar", "https_state", "protected_connection"], "A controlled browser view shows the actual HTTPS protection state.", VisualFormat.BROWSER_DEMO.value
    if "rogue" in subject or ("fake" in subject and "wifi" in subject):
        return _rogue_hotspot_frame, ["two_similar_wifi_names", "trusted_network", "fake_network", "attacker_control"], "Trusted and lookalike Wi-Fi networks are contrasted directly.", VisualFormat.ANIMATED_EXPLAINER.value
    if "vpn" in subject or "tunnel" in subject:
        return _vpn_frame, ["device", "encrypted_tunnel", "vpn_server", "destination"], "An encrypted tunnel connects a device to a VPN server.", VisualFormat.ANIMATED_EXPLAINER.value
    if "passkey" in subject or "biometric" in subject or "authentication" in subject:
        return _passkey_frame, ["device", "biometric_confirmation", "public_private_key_flow"], "A challenge-and-signature flow explains passkey authentication.", VisualFormat.ANIMATED_EXPLAINER.value
    if "partnership" in subject or "acquisition" in subject or "deal" in subject:
        return _partnership_frame, ["company_a", "company_b", "relationship", "outcome"], "Two organizations and their shared outcome are shown without generic handshake footage.", VisualFormat.ANIMATED_EXPLAINER.value
    if requested == VisualFormat.TIMELINE.value or intent.purpose == "challenge_progress" or "timeline" in subject:
        factory = _challenge_frame if intent.purpose == "challenge_progress" else _timeline_frame
        elements = ["progress_counter", "milestones", "result"] if factory is _challenge_frame else ["ordered_events", "dates", "outcome"]
        return factory, elements, "A structured timeline makes sequence and progress visible.", VisualFormat.TIMELINE.value
    if requested == VisualFormat.COMPARISON_GRAPHIC.value or intent.purpose in {"compare", "show_data"} or "comparison" in subject:
        return _comparison_frame, ["option_a", "option_b", "comparison_criteria"], "A labeled comparison is clearer than unrelated stock footage.", VisualFormat.COMPARISON_GRAPHIC.value
    if "code" in subject or "python" in subject or "programming" in subject or "code_state" in required:
        return _code_logic_frame, ["code", "input", "logic", "result"], "A code-flow explainer makes the programming mechanism visible.", VisualFormat.APPLICATION_DEMO.value
    if "software" in subject or "api" in subject or "routing" in subject or "workflow" in subject or "architecture" in subject:
        return _software_flow_frame, ["request", "processing_nodes", "response", "directional_flow"], "A structured request route explains the software mechanism.", VisualFormat.ANIMATED_EXPLAINER.value
    if "unencrypted" in subject or "exposed" in subject:
        return lambda i, s, p: _network_frame(i, s, p, protected=False), ["shared_access_point", "multiple_devices", "data_packets", "missing_encryption_lock"], "Exposed packets move across a shared network without a closed lock.", VisualFormat.ANIMATED_EXPLAINER.value
    if "encrypted" in subject or "secure_connection" in subject:
        return lambda i, s, p: _network_frame(i, s, p, protected=True), ["shared_access_point", "multiple_devices", "data_packets", "encryption_lock"], "Protected packets and a closed lock explain encryption.", VisualFormat.ANIMATED_EXPLAINER.value
    if "wifi" in subject or "network" in subject or "router" in subject:
        return lambda i, s, p: _network_frame(i, s, p, protected="encrypted" in subject), ["wireless_router", "multiple_devices", "shared_network"], "A literal topology shows the network and its connected devices.", VisualFormat.ANIMATED_EXPLAINER.value
    if requested == VisualFormat.APPLICATION_DEMO.value and ("interface" in required or "visible_action" in required):
        return _phone_hotspot_frame, list(intent.required_elements), "A controlled UI-style demonstration shows the requested action.", VisualFormat.APPLICATION_DEMO.value
    return _generic_frame, list(intent.required_elements), "ACE generated a subject-specific motion graphic rather than unrelated stock filler.", VisualFormat.ANIMATED_EXPLAINER.value


def _phase(intent: ShotIntent) -> float:
    digest = hashlib.sha256(intent.shot_id.encode("utf-8", errors="ignore")).digest()
    return int.from_bytes(digest[:2], "big") / 65535.0


def render_explainer(
    intent: ShotIntent,
    output_dir: str | Path,
    *,
    duration: float = 3.0,
    fps: int = 8,
    size: tuple[int, int] = (720, 1280),
    animate: bool = True,
    visual_format: str | None = None,
) -> ExplainerResult:
    output_root = ensure_dir(Path(output_dir))
    factory, elements, description, resolved_format = _frame_factory(intent, visual_format)
    stem = f"{intent.shot_id}-{slugify(intent.subject, 42)}-{slugify(resolved_format, 24)}"
    ffmpeg = shutil.which("ffmpeg")
    phase = _phase(intent)
    if not animate or not ffmpeg:
        path = output_root / f"{stem}.png"
        factory(intent, size, 0.24 + phase * 0.62).save(path, quality=95)
        return ExplainerResult(path, elements, description, False, resolved_format)

    frame_count = max(12, int(max(1.5, duration) * fps))
    with tempfile.TemporaryDirectory(prefix="ace-explainer-") as temp:
        temp_dir = Path(temp)
        for index in range(frame_count):
            progress = (index / max(1, frame_count - 1) + phase) % 1.0
            frame = factory(intent, size, progress)
            frame.save(temp_dir / f"frame-{index:04d}.png")
        output = output_root / f"{stem}.mp4"
        command = [
            ffmpeg,
            "-y",
            "-framerate",
            str(fps),
            "-i",
            str(temp_dir / "frame-%04d.png"),
            "-t",
            f"{duration:.3f}",
            "-vf",
            f"fps={fps},format=yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-movflags",
            "+faststart",
            str(output),
        ]
        result = subprocess.run(command, capture_output=True, text=True, check=False)
        if result.returncode != 0 or not output.exists():
            fallback = output_root / f"{stem}.png"
            factory(intent, size, 0.24 + phase * 0.62).save(fallback, quality=95)
            return ExplainerResult(fallback, elements, description + f" FFmpeg fallback: {result.stderr[-300:]}", False, resolved_format)
    return ExplainerResult(output, elements, description, True, resolved_format)
