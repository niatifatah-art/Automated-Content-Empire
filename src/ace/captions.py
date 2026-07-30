from __future__ import annotations

import json
import re
import shutil
import wave
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

from ace.config import load as load_config
from ace.graphics import fit_text, font_path
from ace.storage import metadata, resolve_generation
from ace.utils import read_json, write_json


VISIBLE_MODES = {
    "none",
    "accessibility_only",
    "short_phrase",
    "keyword",
    "full_title",
    "quote_card",
    "article_headline",
    "social_post",
    "command",
    "code_panel",
    "statistic",
    "challenge_counter",
    "cta",
}


@dataclass
class CaptionCue:
    index: int
    start: float
    end: float
    spoken_text: str
    visible_text: str
    mode: str
    position: str
    font_size: int
    lines: list[str]
    reason: str
    overflow: bool = False
    sentence_index: int = 0


def audio_duration(path: Path | None) -> float | None:
    if not path or not path.exists():
        return None
    if path.suffix.lower() == ".wav":
        try:
            with wave.open(str(path), "rb") as handle:
                return handle.getnframes() / float(handle.getframerate())
        except Exception:
            pass
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return None
    import subprocess
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


def _sentences(text: str) -> list[str]:
    text = re.sub(r"(?m)^#{1,6}\s+", "", text)
    text = re.sub(r"\s+", " ", text).strip()
    return [part.strip() for part in re.split(r"(?<=[.!?؟])\s+", text) if part.strip()]


def _chunks(sentence: str, minimum: int, maximum: int) -> list[str]:
    words = sentence.split()
    if len(words) <= maximum:
        return [sentence]
    chunks: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        punctuation_break = word.rstrip().endswith((",", ";", ":", "—"))
        if len(current) >= maximum or (len(current) >= minimum and punctuation_break):
            chunks.append(" ".join(current).strip())
            current = []
    if current:
        if chunks and len(current) < minimum:
            chunks[-1] += " " + " ".join(current)
        else:
            chunks.append(" ".join(current))
    return chunks


def _clean_visible(text: str) -> str:
    return text.strip().strip('"“”').rstrip(".")


def _director(text: str, index: int, total: int, mood: str, topic: str, *, has_evidence: bool) -> tuple[str, str, str]:
    lower = text.lower()
    if has_evidence and any(term in lower for term in ("announced", "deal", "partnership", "report", "confirmed", "official")):
        return "article_headline", _clean_visible(text), "The sentence references a source-worthy announcement."
    if index == 1:
        return "full_title", _clean_visible(text), "Opening hook/title deserves deliberate full-screen emphasis."
    if re.search(r"(^|\s)(sudo|pip|npm|git|python|curl)\s", lower) or "```" in text:
        return "code_panel", _clean_visible(text), "Command or code should remain exact and readable."
    if re.search(r"\b\d+(?:\.\d+)?(?:%|x|gb|tb|million|billion)?\b", lower):
        match = re.search(r".{0,28}\b\d+(?:\.\d+)?(?:%|x|gb|tb|million|billion)?\b.{0,28}", text, re.I)
        return "statistic", _clean_visible(match.group(0) if match else text), "Important number/statistic needs a focused visual treatment."
    if any(term in lower for term in ("challenge", "day one", "day 1", "can i", "let's see if")):
        return "challenge_counter", _clean_visible(text), "Challenge structure benefits from explicit progress text."
    if index == total or any(term in lower for term in ("follow", "subscribe", "comment", "try it", "what do you think")):
        return "cta", _clean_visible(text), "Closing action should be concise and visible."
    serious = mood in {"serious_technical", "breaking_news", "security_incident"}
    if serious and index % 3 == 0:
        return "none", "", "Serious pacing leaves selected moments visually clean."
    if not serious and index % 5 == 0:
        return "none", "", "The visual can carry this moment without repetitive captions."
    words = text.split()
    if len(words) <= 5:
        return "keyword", _clean_visible(text), "Short phrase already behaves like a useful emphasis caption."
    return "short_phrase", _clean_visible(text), "Adaptive phrase caption supports comprehension without reproducing the whole sentence."


def _format_srt(seconds: float) -> str:
    millis = max(0, round(seconds * 1000))
    hours, remainder = divmod(millis, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, ms = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{ms:03d}"


def _format_ass(seconds: float) -> str:
    centis = max(0, round(seconds * 100))
    hours, remainder = divmod(centis, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    secs, cs = divmod(remainder, 100)
    return f"{hours}:{minutes:02d}:{secs:02d}.{cs:02d}"


def _ass_escape(text: str) -> str:
    return text.replace("\\", r"\\").replace("{", r"\{").replace("}", r"\}").replace("\n", r"\N")


def plan(generation: str | Path, workspace: str | Path | None = None, *, mood: str | None = None) -> list[CaptionCue]:
    folder = resolve_generation(generation, workspace)
    config = load_config(workspace)
    settings = config.get("captions", {})
    meta = metadata(folder)
    topic = str(meta.get("topic") or "")
    mood = mood or str(meta.get("editing_mood") or "technical_dynamic")
    script_path = folder / "script" / "tts-ready.txt"
    if not script_path.exists():
        script_path = folder / "selected.md"
    text = script_path.read_text(encoding="utf-8")
    sentences = _sentences(text)
    minimum = int(settings.get("words_per_chunk_min", 3))
    maximum = int(settings.get("words_per_chunk_max", 6))
    spoken_chunks: list[tuple[str, int]] = []
    for sentence_index, sentence in enumerate(sentences, 1):
        spoken_chunks.extend((chunk, sentence_index) for chunk in _chunks(sentence, minimum, maximum))
    voice = folder / "voice" / "narration.wav"
    duration = audio_duration(voice)
    if not duration:
        duration = max(6.0, sum(max(1.4, len(chunk.split()) / 2.7) for chunk, _ in spoken_chunks))
    weights = [max(1.0, len(chunk.split())) for chunk, _ in spoken_chunks]
    total_weight = sum(weights) or 1.0
    has_evidence = bool(read_json(folder / "evidence" / "evidence-plan.json", []))
    vertical = str(meta.get("content_type")) in {"short", "reel", "story", "video_script"} or str(meta.get("platform")) in {"tiktok", "instagram"}
    canvas = (1080, 1920) if vertical else (1920, 1080)
    image = Image.new("RGB", canvas)
    draw = ImageDraw.Draw(image)
    max_width = int(canvas[0] * float(settings.get("safe_width_ratio", 0.82)))
    max_height = int(canvas[1] * 0.20)
    start_size = int(settings.get("font_size_vertical" if vertical else "font_size_landscape", 68 if vertical else 48))
    minimum_size = int(settings.get("minimum_font_size", 34))
    max_lines = int(settings.get("maximum_lines", 2))
    cues: list[CaptionCue] = []
    current = 0.0
    for index, ((chunk, sentence_index), weight) in enumerate(zip(spoken_chunks, weights), 1):
        cue_duration = duration * weight / total_weight
        end = duration if index == len(spoken_chunks) else current + cue_duration
        mode, visible, reason = _director(chunk, index, len(spoken_chunks), mood, topic, has_evidence=has_evidence)
        if mode in {"none", "accessibility_only"}:
            selected_size, lines, overflow = start_size, [], False
        else:
            if mode == "short_phrase" and len(visible.split()) > maximum:
                visible = " ".join(visible.split()[:maximum])
            selected_font, lines = fit_text(visible, draw, max_width, max_height, start_size=start_size, min_size=minimum_size, max_lines=max_lines)
            selected_size = selected_font.size
            overflow = len(lines) > max_lines or any(draw.textbbox((0, 0), line, font=selected_font)[2] > max_width for line in lines)
        position = "top" if mode in {"full_title", "article_headline", "social_post"} else "center" if mode in {"statistic", "code_panel", "challenge_counter"} else "bottom"
        cues.append(
            CaptionCue(
                index=index,
                start=round(current, 3),
                end=round(end, 3),
                spoken_text=chunk,
                visible_text=visible,
                mode=mode,
                position=position,
                font_size=selected_size,
                lines=lines,
                reason=reason,
                overflow=overflow,
                sentence_index=sentence_index,
            )
        )
        current = end
    write_json(folder / "captions" / "caption-plan.json", [asdict(item) for item in cues])
    _write_srt(folder, cues)
    _write_ass(folder, cues, canvas, settings)
    return cues


def _write_srt(folder: Path, cues: list[CaptionCue]) -> Path:
    lines: list[str] = []
    for cue in cues:
        lines.extend([str(cue.index), f"{_format_srt(cue.start)} --> {_format_srt(cue.end)}", cue.spoken_text, ""])
    path = folder / "subtitles" / "accessibility.srt"
    path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
    # Compatibility with ACE 1.x.
    (folder / "subtitles" / "subtitles.srt").write_text(path.read_text(encoding="utf-8"), encoding="utf-8")
    return path


def _write_ass(folder: Path, cues: list[CaptionCue], canvas: tuple[int, int], settings: dict[str, Any]) -> Path:
    width, height = canvas
    margin_v = int(height * float(settings.get("safe_bottom_ratio", 0.13)))
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{settings.get('font_name', 'DejaVu Sans')},{settings.get('font_size_vertical', 68)},&H00FFFFFF,&H0000E5FF,&H00101010,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,90,90,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events: list[str] = []
    for cue in cues:
        if cue.mode in {"none", "accessibility_only", "article_headline", "social_post"} or not cue.visible_text:
            # Evidence/social cards already contain the exact visible text; accessibility remains in SRT.
            continue
        alignment = 8 if cue.position == "top" else 5 if cue.position == "center" else 2
        text = r"\N".join(_ass_escape(line) for line in cue.lines)
        if cue.mode in {"article_headline", "social_post"}:
            color = "&H00FFD048&"
        elif cue.mode in {"statistic", "challenge_counter"}:
            color = "&H0048D0FF&"
        else:
            color = "&H00FFFFFF&"
        override = rf"{{\an{alignment}\fs{cue.font_size}\c{color}\bord4\shad1}}"
        events.append(f"Dialogue: 0,{_format_ass(cue.start)},{_format_ass(cue.end)},Default,,0,0,0,,{override}{text}")
    path = folder / "captions" / "styled-captions.ass"
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
    return path


def inspect(generation: str | Path, workspace: str | Path | None = None) -> dict[str, Any]:
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "captions" / "caption-plan.json", []) or []
    overflows = [row for row in rows if row.get("overflow")]
    visible = [row for row in rows if row.get("mode") not in {"none", "accessibility_only", "article_headline", "social_post"}]
    card_text = [row for row in rows if row.get("mode") in {"article_headline", "social_post"}]
    modes: dict[str, int] = {}
    for row in rows:
        modes[str(row.get("mode"))] = modes.get(str(row.get("mode")), 0) + 1
    report = {
        "status": "not_run" if not rows else "failed" if overflows else "passed",
        "cue_count": len(rows),
        "visible_count": len(visible),
        "hidden_count": len(rows) - len(visible) - len(card_text),
        "card_text_count": len(card_text),
        "overflow_count": len(overflows),
        "modes": modes,
        "font_path": font_path(),
    }
    write_json(folder / "quality" / "caption-report.json", report)
    return report


def adapt_to_visuals(generation: str | Path, workspace: str | Path | None = None) -> list[CaptionCue]:
    """Direct visible captions after the actual visual format is selected.

    Caption planning happens before resource selection, so this second pass
    prevents titles from covering explainer headers, browser address bars,
    terminal commands, evidence cards, or text-heavy typography cards.
    Accessibility SRT always keeps the complete spoken text.
    """
    folder = resolve_generation(generation, workspace)
    rows = read_json(folder / "captions" / "caption-plan.json", []) or []
    if not rows:
        return []
    cues = [CaptionCue(**row) for row in rows]
    shots = read_json(folder / "visuals" / "shot-plan.json", []) or []
    config = load_config(workspace)
    settings = config.get("captions", {})
    meta = metadata(folder)
    vertical = str(meta.get("content_type")) in {"short", "reel", "story", "video_script"} or str(meta.get("platform")) in {"tiktok", "instagram"}
    canvas = (1080, 1920) if vertical else (1920, 1080)
    draw = ImageDraw.Draw(Image.new("RGB", canvas))
    max_width = int(canvas[0] * float(settings.get("safe_width_ratio", 0.82)))
    max_height = int(canvas[1] * 0.20)
    start_size = int(settings.get("font_size_vertical" if vertical else "font_size_landscape", 68 if vertical else 48))
    minimum_size = int(settings.get("minimum_font_size", 34))
    max_lines = int(settings.get("maximum_lines", 2))

    by_index = {cue.index: cue for cue in cues}
    text_heavy = {
        "official_evidence", "article_card", "social_post_card", "kinetic_typography", "minimal_screen",
    }
    top_ui = {
        "animated_explainer", "browser_demo", "terminal_demo", "application_demo", "comparison_graphic", "data_chart", "timeline",
    }
    for shot in shots:
        visual_format = str(shot.get("visual_type") or "")
        indices = list((shot.get("metadata") or {}).get("caption_cue_indices") or [])
        for index in indices:
            cue = by_index.get(int(index))
            if not cue:
                continue
            if visual_format in text_heavy:
                cue.mode = "accessibility_only"
                cue.visible_text = ""
                cue.lines = []
                cue.position = "bottom"
                cue.reason += " Hidden because the selected visual already carries deliberate readable text."
                cue.overflow = False
                continue
            if visual_format in top_ui:
                cue.position = "bottom"
                if cue.mode == "full_title":
                    cue.mode = "short_phrase"
                    cue.visible_text = " ".join(_clean_visible(cue.spoken_text).split()[:6])
                    cue.reason += " Converted from a top title to a bottom phrase to protect the explainer header."
                elif cue.mode in {"code_panel", "article_headline", "social_post"}:
                    cue.mode = "accessibility_only"
                    cue.visible_text = ""
                    cue.lines = []
                    cue.reason += " Hidden because the selected visual contains the exact technical or source text."
                    cue.overflow = False
                    continue
                if cue.visible_text:
                    selected_font, lines = fit_text(
                        cue.visible_text,
                        draw,
                        max_width,
                        max_height,
                        start_size=min(start_size, cue.font_size or start_size),
                        min_size=minimum_size,
                        max_lines=max_lines,
                    )
                    cue.font_size = selected_font.size
                    cue.lines = lines
                    cue.overflow = len(lines) > max_lines or any(
                        draw.textbbox((0, 0), line, font=selected_font)[2] > max_width for line in lines
                    )

    ordered = [by_index[index] for index in sorted(by_index)]
    write_json(folder / "captions" / "caption-plan.json", [asdict(item) for item in ordered])
    _write_srt(folder, ordered)
    _write_ass(folder, ordered, canvas, settings)
    return ordered
