import subprocess


def get_models():
    """Return a list of installed Ollama model names."""

    result = subprocess.run(
        ["ollama", "list"],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    lines = result.stdout.strip().splitlines()

    if len(lines) <= 1:
        return []

    return [line.split()[0] for line in lines[1:]]


def list_models(default_model=None):
    """Display installed Ollama models."""

    print("ACE AI Models")
    print("-" * 30)

    models = get_models()

    if not models:
        print("No models installed.")
        return

    for model in models:
        marker = "★" if model == default_model else "✓"
        print(f"{marker} {model}")


def ask(model, prompt):
    """Send a prompt to Ollama and return the response."""

    result = subprocess.run(
        ["ollama", "run", model],
        input=prompt,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        print("Failed to communicate with Ollama.")
        print(result.stderr)
        return ""

    response = result.stdout.strip()

    print(response)

    return response
