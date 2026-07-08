import json
from pathlib import Path


PROJECTS_DIR = Path("projects")


def slugify(title):
    return (
        title.lower()
        .strip()
        .replace(" ", "-")
    )


def create(title):
    slug = slugify(title)

    project = PROJECTS_DIR / slug

    project.mkdir(parents=True, exist_ok=True)

    for folder in (
        "ideas",
        "prompts",
        "scripts",
        "voice",
        "images",
        "videos",
        "exports",
        "logs",
    ):
        (project / folder).mkdir(exist_ok=True)

    metadata = {
        "title": title,
        "slug": slug,
        "status": "created",
    }

    with open(project / "project.json", "w") as file:
        json.dump(
            metadata,
            file,
            indent=4,
        )

    print(f"Project created: {project}")


def load(project_path):
    project = Path(project_path)

    metadata = project / "project.json"

    if not metadata.exists():
        raise FileNotFoundError("project.json not found.")

    with open(metadata) as file:
        return json.load(file)


def status(project_path):
    project = Path(project_path)

    return {
        "script": any((project / "scripts").glob("*")),
        "voice": any((project / "voice").glob("*")),
        "images": any((project / "images").glob("*")),
        "video": any((project / "videos").glob("*")),
    }
