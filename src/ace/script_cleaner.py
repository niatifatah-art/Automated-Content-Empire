from __future__ import annotations

import re


_ANSI_ESCAPE = re.compile(r"\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])")
_PREAMBLE = re.compile(
    r"^(?:(?:sure|certainly|of course|absolutely)[!,.?:\s-]*)?"
    r"(?:here(?:'s| is)|below is|i(?:'ve| have) created)\b.*"
    r"(?:script|narration|content|post|caption|thread|outline|prompt)\b[:.!\s-]*$",
    re.IGNORECASE,
)
_CODE_FENCE = re.compile(r"^```(?:markdown|md|text)?\s*$", re.IGNORECASE)


def clean_response(text: str) -> str:
    """Remove transport noise while preserving useful Markdown structure."""

    text = _ANSI_ESCAPE.sub("", text).replace("\r\n", "\n").strip()
    lines = text.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)
    if lines and _PREAMBLE.match(lines[0].strip()):
        lines.pop(0)

    if lines and _CODE_FENCE.match(lines[0].strip()):
        lines.pop(0)
    if lines and lines[-1].strip() == "```":
        lines.pop()

    return "\n".join(lines).strip()


def clean_narration(text: str) -> str:
    """Convert generated script text into narration-friendly plain text."""

    cleaned = clean_response(text)
    output: list[str] = []

    for raw_line in cleaned.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith(("(", "[")) and line.endswith((")", "]")):
            continue
        line = re.sub(r"^#{1,6}\s*", "", line)
        line = re.sub(r"^[-*+]\s+", "", line)
        line = re.sub(r"^\d+[.)]\s+", "", line)
        line = re.sub(r"\*\*|__|`", "", line)
        if line.lower().startswith(("host:", "narrator:", "voiceover:")):
            line = line.split(":", 1)[1].strip()
        if line:
            output.append(line)

    return "\n\n".join(output)


def clean(text: str) -> str:
    """Backward-compatible alias for response cleanup."""

    return clean_response(text)
