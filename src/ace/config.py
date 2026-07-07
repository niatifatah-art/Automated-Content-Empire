import json
from pathlib import Path


CONFIG_FILE = Path("config/config.json")


def load():
    with open(CONFIG_FILE, "r") as file:
        return json.load(file)


def show():
    config = load()

    print("ACE Configuration")
    print("-" * 30)

    for key, value in config.items():
        print(f"{key:20}: {value}")
