from pathlib import Path
from datetime import datetime
import json
import re


PROJECTS_DIR = Path("projects")


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-")


def create(title):
    slug = slugify(title)

    timestamp = datetime.now().strftime("%Y-%m-%d")

    folder = PROJECTS_DIR / f"{timestamp}-{slug}"

    folder.mkdir(parents=True, exist_ok=True)

    for name in (
        "images",
        "audio",
        "video",
        "exports",
    ):
        (folder / name).mkdir(exist_ok=True)

    metadata = {
        "title": title,
        "slug": slug,
        "created": datetime.now().isoformat(),
        "status": "draft",
    }

    with open(folder / "project.json", "w") as file:
        json.dump(
            metadata,
            file,
            indent=4,
        )

    return folder
