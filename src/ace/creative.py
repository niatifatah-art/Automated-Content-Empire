from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any

from ace.visual_intelligence.contracts import ShotIntent, VisualFormat, VisualPurpose


@dataclass(frozen=True, slots=True)
class CreativeProfile:
    name: str
    pace: str
    broll_density: float
    humor_budget: float
    max_memes_per_minute: float
    motion_palette: tuple[str, ...]
    transition_palette: tuple[str, ...]
    overlay_palette: tuple[str, ...]
    sfx_density: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class BrollQuery:
    query: str
    role: str
    camera: str
    subject: str
    action: str
    setting: str
    negative_terms: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class MemeBeat:
    allowed: bool
    setup: str
    punchline: str
    reason: str
    placement: float = 0.68

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class EditDirective:
    motion: str
    transition: str
    overlay: str
    emphasis: str
    speed: float
    sfx: str | None
    start_hint: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


_PROFILES: dict[str, CreativeProfile] = {
    "technical_dynamic": CreativeProfile(
        "technical_dynamic", "fast", 0.58, 0.20, 0.8,
        ("slow_push", "punch_in", "pan_right", "steady"),
        ("cut", "quick_fade", "push"),
        ("keyword", "callout", "none"), 0.32,
    ),
    "clean_documentary": CreativeProfile(
        "clean_documentary", "medium", 0.44, 0.05, 0.0,
        ("steady", "slow_push", "slow_pan"),
        ("cut", "fade"),
        ("source", "lower_third", "none"), 0.08,
    ),
    "gaming_hype": CreativeProfile(
        "gaming_hype", "very_fast", 0.72, 0.62, 1.8,
        ("punch_in", "snap_zoom", "pan_left", "pan_right"),
        ("cut", "flash", "push", "quick_fade"),
        ("keyword", "reaction", "counter"), 0.72,
    ),
    "challenge": CreativeProfile(
        "challenge", "fast", 0.65, 0.50, 1.4,
        ("handheld", "punch_in", "slow_push", "steady"),
        ("cut", "push", "quick_fade"),
        ("counter", "reaction", "keyword"), 0.58,
    ),
    "serious_technical": CreativeProfile(
        "serious_technical", "controlled", 0.35, 0.0, 0.0,
        ("steady", "slow_push"),
        ("cut", "fade"),
        ("source", "callout", "none"), 0.04,
    ),
    "playful_tech": CreativeProfile(
        "playful_tech", "fast", 0.66, 0.54, 1.5,
        ("punch_in", "slow_push", "pan_left", "pan_right"),
        ("cut", "push", "quick_fade"),
        ("keyword", "reaction", "callout"), 0.62,
    ),
}


def profile_for(name: str | None) -> CreativeProfile:
    return _PROFILES.get(str(name or "").strip(), _PROFILES["technical_dynamic"])


def _words(value: str) -> list[str]:
    return [item.lower() for item in re.findall(r"[A-Za-z0-9+#.-]{2,}", value)]


def _first_match(text: str, values: list[tuple[tuple[str, ...], str]], default: str) -> str:
    lower = text.lower()
    for terms, value in values:
        if any(term in lower for term in terms):
            return value
    return default


def build_broll_queries(intent: ShotIntent, *, limit: int = 6) -> list[BrollQuery]:
    """Build diverse literal B-roll searches instead of repeating one broad query.

    Abstract mechanisms still receive a small real-world context set, but the
    explainer/demo remains primary. Literal scenes receive action, object,
    environment, close-up and over-the-shoulder variants.
    """

    narration = intent.narration.strip()
    subject = intent.subject.replace("_", " ").strip() or "technology"
    action = _first_match(
        narration,
        [
            (("type", "address bar", "url"), "typing a web address"),
            (("press enter", "enter key", "hit enter"), "pressing the Enter key"),
            (("scroll", "browse", "website", "browser"), "browsing a website"),
            (("tap", "toggle", "settings", "phone"), "using phone settings"),
            (("install", "terminal", "command", "sudo", "git ", "pip "), "running a computer command"),
            (("game", "gaming", "fps", "gpu"), "playing a PC game"),
            (("connect", "wifi", "wi-fi", "network"), "connecting a device to Wi-Fi"),
            (("server", "data center", "cloud"), "working with servers"),
        ],
        "using a digital device",
    )
    setting = _first_match(
        narration,
        [
            (("airport",), "airport lounge"),
            (("cafe", "coffee shop", "public wi-fi", "public wifi"), "modern cafe"),
            (("gaming", "gpu", "console"), "gaming setup"),
            (("office", "company", "business"), "modern office"),
            (("phone", "mobile", "hotspot"), "everyday indoor setting"),
            (("server", "data center"), "data center"),
        ],
        "clean modern workspace",
    )
    object_name = _first_match(
        narration,
        [
            (("enter key", "keyboard"), "computer keyboard"),
            (("browser", "website", "url", "dns", "https", "tls"), "laptop browser"),
            (("phone", "mobile", "hotspot", "face id", "fingerprint"), "smartphone"),
            (("gpu", "graphics card"), "graphics card"),
            (("terminal", "command", "linux", "code"), "computer screen"),
            (("router", "wifi", "wi-fi", "network"), "wireless router"),
        ],
        subject,
    )
    negatives = tuple(dict.fromkeys([*intent.forbidden_elements, "logo", "watermark", "text overlay"]))

    abstract = intent.literalness in {"abstract_mechanism", "data", "evidence"}
    templates = [
        (f"{action} {object_name} {setting} vertical video", "literal_action", "medium close-up"),
        (f"close up {object_name} screen hands vertical", "object_detail", "macro close-up"),
        (f"over shoulder {action} {object_name}", "human_context", "over-the-shoulder"),
        (f"{object_name} {setting} cinematic b roll", "environment", "wide establishing"),
        (f"hands using {object_name} realistic vertical", "interaction", "detail shot"),
        (f"{subject} real world technology footage", "context", "documentary"),
    ]
    if abstract:
        templates = templates[:3]
    output: list[BrollQuery] = []
    seen: set[str] = set()
    for query, role, camera in templates:
        normalized = " ".join(query.split())
        if normalized.lower() in seen:
            continue
        seen.add(normalized.lower())
        output.append(BrollQuery(normalized, role, camera, subject, action, setting, negatives))
        if len(output) >= limit:
            break
    return output


def choose_meme_beat(intent: ShotIntent, *, mode: str = "auto") -> MemeBeat:
    mode = str(mode or "auto").lower()
    serious = intent.mood == "serious_technical" or intent.evidence_required or intent.purpose in {
        VisualPurpose.SHOW_EVIDENCE.value,
        VisualPurpose.SHOW_DATA.value,
    }
    if mode == "off" or serious:
        return MemeBeat(False, "", "", "Memes are disabled or inappropriate for this factual/serious beat.")

    lower = intent.narration.lower()
    triggers = (
        "somehow", "of course", "weird", "ridiculous", "crash", "bug", "again", "finally",
        "because linux", "developer", "plot twist", "except", "until", "but then", "nope",
    )
    natural = any(term in lower for term in triggers)
    # "on" means actively consider a meme, not force one into every sentence.
    # It broadens the signal to mild contrast/punchline structures but still
    # requires a genuine comedic turn and a style that permits humor.
    contrast = bool(re.search(r"\b(?:but|except|until|then|apparently|turns out)\b", lower))
    comedic_signal = natural or (mode == "on" and contrast)
    allowed = bool(intent.humor_allowed and comedic_signal)
    if not allowed:
        return MemeBeat(False, "", "", "No natural comedy beat was detected.")

    cleaned = " ".join(intent.narration.strip().split())
    setup = cleaned[:110].rstrip(" .,!?")
    punchline = _first_match(
        lower,
        [
            (("linux",), "Linux: one command away from character development"),
            (("bug", "crash"), "The fix created two new side quests"),
            (("again",), "Yes, we are doing this again"),
            (("finally",), "Narrator: it was not final"),
            (("developer",), "Works on my machine intensifies"),
        ],
        "That escalated quickly",
    )
    return MemeBeat(True, setup or "Tech explained", punchline, "A brief original reaction card supports a genuine punchline.")


def edit_directive(intent: ShotIntent, index: int, *, style: str | None = None) -> EditDirective:
    profile = profile_for(style or intent.mood)
    preferred = intent.preferred_formats[0] if intent.preferred_formats else VisualFormat.MINIMAL_SCREEN.value

    if intent.purpose == VisualPurpose.HOOK.value:
        motion, emphasis, overlay = "punch_in", "strong", "keyword"
        transition = "cut"
        sfx = "impact" if profile.sfx_density >= 0.4 else None
    elif preferred in {VisualFormat.OFFICIAL_EVIDENCE.value, VisualFormat.ARTICLE_CARD.value, VisualFormat.SOCIAL_POST_CARD.value}:
        motion, emphasis, overlay = "slow_push", "source", "source"
        transition = "cut" if profile.pace in {"fast", "very_fast"} else "fade"
        sfx = None
    elif preferred in {VisualFormat.BROWSER_DEMO.value, VisualFormat.APPLICATION_DEMO.value, VisualFormat.TERMINAL_DEMO.value}:
        demo_motions = ("punch_in", "steady", "slow_push")
        motion, emphasis, overlay = demo_motions[index % len(demo_motions)], "demonstrate", "callout"
        transition = "cut" if index % 3 else "quick_fade"
        sfx = "soft_tick" if profile.sfx_density >= 0.55 and index % 2 == 0 else None
    elif preferred in {VisualFormat.ANIMATED_EXPLAINER.value, VisualFormat.COMPARISON_GRAPHIC.value, VisualFormat.DATA_CHART.value, VisualFormat.TIMELINE.value}:
        explainer_motions = ("steady", "slow_push", "pan_right")
        motion, emphasis, overlay = explainer_motions[index % len(explainer_motions)], "explain", "callout"
        transition = "cut" if index % 2 == 0 else "quick_fade"
        sfx = "soft_tick" if profile.sfx_density >= 0.55 and index % 2 == 0 else None
    elif preferred == VisualFormat.MEME.value:
        motion, emphasis, overlay = "snap_zoom", "reaction", "reaction"
        transition = "cut"
        sfx = "pop"
    else:
        motion = profile.motion_palette[index % len(profile.motion_palette)]
        transition = profile.transition_palette[index % len(profile.transition_palette)]
        overlay = profile.overlay_palette[index % len(profile.overlay_palette)]
        emphasis = "support"
        sfx = "whoosh" if profile.sfx_density >= 0.7 and index % 3 == 0 else None

    speed = 1.0
    if profile.pace == "very_fast":
        speed = 1.04
    elif profile.pace == "controlled":
        speed = 0.98
    start_hint = (0.12, 0.34, 0.56)[index % 3]
    return EditDirective(motion, transition, overlay, emphasis, speed, sfx, start_hint)
