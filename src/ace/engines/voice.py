from pathlib import Path

from ace.providers.kokoro import generate


def run(project_path):
    project = Path(project_path)

    script = project / "scripts" / "script.md"
    voice = project / "voice" / "voice.wav"

    print(">>> VOICE ENGINE <<<")

    if not script.exists():
        print("Script not found.")
        return

    if voice.exists():
        print("Voice already exists.")
        return

    print(f"Reading: {script}")
    print(f"Output : {voice}")

    text = script.read_text(
        encoding="utf-8",
    )

    generate(
        text=text,
        output=voice,
    )

    print("Voice generated.")
