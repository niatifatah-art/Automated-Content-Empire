from pathlib import Path
from datetime import datetime


CONTENT_DIR = Path("data/content")


def save(content_type, text):
    folder = CONTENT_DIR / content_type
    folder.mkdir(parents=True, exist_ok=True)

    filename = datetime.now().strftime("%Y-%m-%d_%H-%M-%S.md")

    path = folder / filename

    path.write_text(
        text,
        encoding="utf-8",
    )

    return path
