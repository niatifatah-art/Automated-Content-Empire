from pathlib import Path

from ace.ai import ask
from ace.config import load
from ace.prompt import load_prompt
from ace.storage import save


def generate(template, output=None, **variables):
    config = load()

    prompt = load_prompt(
        template,
        **variables,
    )

    response = ask(
        config["ai_model"],
        prompt,
    )

    if not response:
        return None

    if output is None:
        path = save(
            template,
            response,
        )
    else:
        path = Path(output)

        path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        path.write_text(
            response,
            encoding="utf-8",
        )

    print(f"\nSaved to: {path}")

    return response
