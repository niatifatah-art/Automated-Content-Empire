from __future__ import annotations

import json
import math
import shutil
import tempfile
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from ace.cli import create_parser
from ace.config import initialize, load as load_config
from ace.editing import create_package, render, validate_media
from ace.models import search_models
from ace.profile import create as create_account
from ace.resources_engine import classify_license
from ace.speech import normalize_for_speech
from ace.storage import write_json


def _wave(path: Path, seconds: float = 2.0, rate: int = 24000) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        frames = bytearray()
        for index in range(int(seconds * rate)):
            value = int(6000 * math.sin(2 * math.pi * 220 * index / rate))
            frames.extend(value.to_bytes(2, "little", signed=True))
        handle.writeframes(bytes(frames))


def _generation(root: Path) -> Path:
    folder = root / "data" / "content" / "selftest" / "tiktok" / "short" / "selftest-generation"
    for relative in ("voice", "script", "quality", "licenses", "resources/generated", "exports"):
        (folder / relative).mkdir(parents=True, exist_ok=True)
    script = "Passwords are difficult to manage. Passkeys make secure sign-in simpler and resist common phishing attacks."
    (folder / "selected.md").write_text(script + "\n", encoding="utf-8")
    (folder / "script" / "tts-ready.txt").write_text(script + "\n", encoding="utf-8")
    write_json(folder / "metadata.json", {
        "platform": "tiktok", "content_type": "short", "topic": "Passkeys",
        "profile_slug": "selftest", "final_model": "selftest", "selected_candidate": 1,
        "created_at": datetime.now(timezone.utc).isoformat(),
    })
    write_json(folder / "quality" / "script-report.json", {"status": "passed", "score": 100})
    write_json(folder / "quality" / "tts-report.json", {"status": "passed"})
    write_json(folder / "licenses" / "manifest.json", {"publishable": [], "reference_only": []})
    _wave(folder / "voice" / "narration.wav", 4.0)
    return folder


def _check(name: str, fn: Callable[[], Any]) -> dict[str, str]:
    try:
        fn()
    except Exception as exc:  # self-test must report every failure
        return {"name": name, "status": "FAILED", "detail": str(exc)}
    return {"name": name, "status": "PASSED", "detail": "ok"}


def run_selftest(
    suite: str = "quick",
    *,
    workspace: str | Path | None = None,
    report: bool = False,
) -> bool:
    checks: list[dict[str, str]] = []

    def command_checks() -> None:
        parser = create_parser()
        examples = [
            ["guide"], ["check"], ["status", "last"], ["fix", "last"],
            ["create", "youtube", "short", "Topic", "--auto"],
            ["models", "search", "qwen"], ["voice", "providers"],
            ["account", "build", "A fun technology account"],
        ]
        for argv in examples:
            parser.parse_args(argv)

    def config_checks() -> None:
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            account = create_account(
                "Self Test", niche="technology", audience="general",
                primary_language="en", enabled_languages=["en"],
                enabled_platforms=["youtube", "tiktok"], workspace=directory,
            )
            assert account["slug"] == "self-test"
            assert load_config(directory)["product"]["version"] == "1.7.0"

    def model_checks() -> None:
        rows = search_models("qwen", load_config(workspace), workspace)
        assert rows, "model catalog search returned no Qwen models"

    def voice_checks() -> None:
        cleaned = normalize_for_speech('## Host\n"Use API keys." https://example.com #security')
        assert "https" not in cleaned and '"' not in cleaned and "Host" not in cleaned

    def resource_checks() -> None:
        assert classify_license("CC0")[0] == "publishable"
        assert classify_license("all rights reserved")[0] == "blocked"

    def render_checks() -> None:
        if not shutil.which("ffmpeg"):
            raise RuntimeError("FFmpeg is not installed")
        with tempfile.TemporaryDirectory() as directory:
            initialize(directory)
            folder = _generation(Path(directory))
            create_package(folder, workspace=directory)
            output = render(folder, workspace=directory, preview=True)
            media = validate_media(output, generation=folder, workspace=directory)
            assert media["status"] == "passed", media.get("problems")
            assert media.get("audio_stream") is True

    selected = {
        "quick": [("configuration", config_checks), ("commands", command_checks), ("models", model_checks)],
        "commands": [("commands", command_checks)],
        "providers": [("model/provider catalog", model_checks)],
        "models": [("models", model_checks)],
        "voice": [("TTS preparation", voice_checks)],
        "resources": [("license classifier", resource_checks)],
        "render": [("real FFmpeg render", render_checks)],
        "full": [
            ("configuration", config_checks), ("commands", command_checks),
            ("models", model_checks), ("TTS preparation", voice_checks),
            ("license classifier", resource_checks), ("real FFmpeg render", render_checks),
        ],
    }[suite]
    for name, fn in selected:
        result = _check(name, fn)
        checks.append(result)
        symbol = "✓" if result["status"] == "PASSED" else "✗"
        print(f"{symbol} {name}: {result['detail']}")
    passed = all(item["status"] == "PASSED" for item in checks)
    if report:
        target = Path.cwd() / "ACE-SELFTEST-REPORT.md"
        target.write_text(
            "# ACE Self-Test Report\n\n"
            f"Suite: `{suite}`\n\n"
            + "\n".join(f"- **{item['status']}** — {item['name']}: {item['detail']}" for item in checks)
            + f"\n\nOverall: **{'PASSED' if passed else 'FAILED'}**\n",
            encoding="utf-8",
        )
        print(f"Report: {target}")
    return passed
