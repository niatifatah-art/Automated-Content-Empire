from pathlib import Path

from ace.ai import ask
from ace.config import load
from ace.prompt import load_prompt


def run(project_path):
    project = Path(project_path)

    script = project / "scripts" / "script.md"

    if not script.exists():
        print(">>> Script not found.")
        return

    print(">>> REVIEW ENGINE <<<")
    print(f">>> Reading: {script}")

    text = script.read_text(
        encoding="utf-8",
    )

    prompt = load_prompt(
        "review",
        text=text,
    )

    config = load()

    improved = ask(
        config["ai_model"],
        prompt,
    )

    if not improved:
        print(">>> Review failed.")
        return

    script.write_text(
        improved,
        encoding="utf-8",
    )

    print(">>> Review complete.")
