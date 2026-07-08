from pathlib import Path

from ace.content import generate
from ace.project import load


def run(project_path):
    print(">>> SCRIPT ENGINE <<<")

    project = Path(project_path)

    metadata = load(project_path)

    title = metadata["title"]

    output = project / "scripts" / "script.md"

    print(f"Output: {output}")

    if output.exists():
        print("Script already exists.")
        return

    print("Generating script...\n")

    generate(
        "youtube",
        output=output,
        topic=title,
    )

    print("\nScript generated.")
