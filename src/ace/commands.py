from ace.doctor import run as doctor_run
from ace.config import load, show
from ace.ai import ask, list_models
from ace.content import generate

def execute(args):
    if args.command == "doctor":
        doctor_run()
        return

    if args.command == "config":
        show()
        return

    if args.command == "ai":
        config = load()

        if args.ai_command == "models":
            list_models(config["ai_model"])
            return

        if args.ai_command == "ask":
            ask(config["ai_model"], args.prompt)
            return

    if args.command == "content":
        if args.content_command == "linkedin":
            generate(
                "linkedin",
                topic=" ".join(args.topic),
            )
            return

    print("Welcome to Automated Content Empire (ACE)")
