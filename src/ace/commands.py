from ace.config import load, show
from ace.ai import ask, list_models
from ace.content import generate
from ace.doctor import run as doctor_run
from ace.project import create as create_project
from ace.workflow import run as workflow_run


def execute(args):
    if args.command == "doctor":
        doctor_run()
        return

    if args.command == "config":
        show()
        return

    if args.command == "project":
        if args.project_command == "create":
            create_project(
                " ".join(args.title),
            )
            return

    if args.command == "workflow":
        if args.workflow_command == "run":
            workflow_run(args.project)
            return

    if args.command == "ai":
        config = load()

        if args.ai_command == "models":
            list_models(config["ai_model"])
            return

        if args.ai_command == "ask":
            ask(
                config["ai_model"],
                args.prompt,
            )
            return

    if args.command == "content":
        if args.content_command == "linkedin":
            generate(
                "linkedin",
                topic=" ".join(args.topic),
            )
            return

        if args.content_command == "youtube":
            generate(
                "youtube",
                topic=" ".join(args.topic),
            )
            return

    print("Welcome to Automated Content Empire (ACE)")
