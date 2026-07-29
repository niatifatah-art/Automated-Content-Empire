from __future__ import annotations

from pathlib import Path
from string import Formatter

from ace.errors import ConfigurationError
from ace.paths import prompts_dir, resource_text


def load_prompt(name: str, workspace: str | Path | None = None, **variables: object) -> str:
    user_path = prompts_dir(workspace) / f"{name}.txt"
    if user_path.exists():
        template = user_path.read_text(encoding="utf-8")
    else:
        try:
            template = resource_text(f"prompts/{name}.txt")
        except FileNotFoundError as exc:
            raise ConfigurationError(f"Prompt template '{name}' was not found.") from exc

    required = {
        field_name
        for _, field_name, _, _ in Formatter().parse(template)
        if field_name
    }
    missing = sorted(required.difference(variables))
    if missing:
        raise ConfigurationError(
            f"Prompt '{name}' is missing variables: {', '.join(missing)}"
        )
    return template.format(**variables)


def list_prompts(workspace: str | Path | None = None) -> list[str]:
    names = {"content", "review"}
    directory = prompts_dir(workspace)
    if directory.exists():
        names.update(path.stem for path in directory.glob("*.txt"))
    return sorted(names)
