from ace.engines.script import run as script_run
from ace.engines.review import run as review_run
from ace.engines.voice import run as voice_run
from ace.project import status


STAGES = [
    {
        "name": "Script",
        "key": "script",
        "engine": script_run,
    },
    {
        "name": "Review",
        "key": None,
        "engine": review_run,
    },
    {
        "name": "Voice",
        "key": "voice",
        "engine": voice_run,
    },
    {
        "name": "Images",
        "key": "images",
        "engine": None,
    },
    {
        "name": "Video",
        "key": "video",
        "engine": None,
    },
]


def run(project_path):
    state = status(project_path)

    for stage in STAGES:
        print(f"\n{stage['name']}")

        if stage["key"] is not None:
            if state[stage["key"]]:
                print("  ✓ Already complete")
                continue

        if stage["engine"] is None:
            print("  → No engine yet")
            continue

        print("  → Running...")

        stage["engine"](project_path)

        state = status(project_path)
