import re


def clean(text):
    lines = []

    for line in text.splitlines():
        line = line.strip()

        if not line:
            continue

        if line.startswith("#"):
            continue

        if line.startswith("**"):
            continue

        if line.startswith("("):
            continue

        if line.startswith("["):
            continue

        if line.lower().startswith("host:"):
            line = line[5:].strip()

        line = re.sub(r"\*\*", "", line)

        lines.append(line)

    return "\n\n".join(lines)
