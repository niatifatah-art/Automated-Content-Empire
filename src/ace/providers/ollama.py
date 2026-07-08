import subprocess


def generate(model, prompt):
    result = subprocess.run(
        [
            "ollama",
            "run",
            model,
            prompt,
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(result.stderr)

    return result.stdout.strip()


def list_models():
    result = subprocess.run(
        [
            "ollama",
            "list",
        ],
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        return []

    lines = result.stdout.splitlines()

    if len(lines) <= 1:
        return []

    return [
        line.split()[0]
        for line in lines[1:]
    ]
