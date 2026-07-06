import platform
import shutil


def run():
    print("ACE Diagnostics")
    print("-" * 30)

    print(f"Python : {platform.python_version()}")

    if shutil.which("git"):
        print("Git    : Installed")
    else:
        print("Git    : Not Found")

    if shutil.which("ollama"):
        print("Ollama : Installed")
    else:
        print("Ollama : Not Found")

    if shutil.which("n8n"):
        print("n8n    : Installed")
    else:
        print("n8n    : Not Found")
