from pathlib import Path


PROMPTS_DIR = Path("prompts")


def load_prompt(name, **variables):
    path = PROMPTS_DIR / f"{name}.txt"

    with open(path, "r", encoding="utf-8") as file:
        prompt = file.read()

    return prompt.format(**variables)


def list_prompts():
    return sorted(
        file.stem
        for file in PROMPTS_DIR.glob("*.txt")
    )
