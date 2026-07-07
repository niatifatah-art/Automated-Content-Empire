from ace.ai import ask
from ace.config import load
from ace.prompt import load_prompt
from ace.storage import save


def generate(template, **variables):
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
        return

    path = save(
        template,
        response,
    )

    print(f"\nSaved to: {path}")
