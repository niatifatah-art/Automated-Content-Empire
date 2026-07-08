import argparse

from ace.prompt import list_prompts


def create_parser():
    parser = argparse.ArgumentParser(
        prog="ace",
        description="Automated Content Empire",
    )

    parser.add_argument(
        "--version",
        action="version",
        version="ACE 0.1.0",
    )

    sub = parser.add_subparsers(dest="command")

    # ------------------------------------------------------------------
    # project
    # ------------------------------------------------------------------

    project = sub.add_parser(
        "project",
        help="Manage projects",
    )

    project_sub = project.add_subparsers(
        dest="project_command",
    )

    create = project_sub.add_parser(
        "create",
        help="Create a new project",
    )

    create.add_argument(
        "title",
        nargs="+",
    )

    # ------------------------------------------------------------------
    # workflow
    # ------------------------------------------------------------------

    workflow = sub.add_parser(
        "workflow",
        help="Run project workflows",
    )

    workflow_sub = workflow.add_subparsers(
        dest="workflow_command",
    )

    run = workflow_sub.add_parser(
        "run",
        help="Run a project workflow",
    )

    run.add_argument(
        "project",
    )

    # ------------------------------------------------------------------
    # doctor
    # ------------------------------------------------------------------

    sub.add_parser(
        "doctor",
        help="Check your development environment",
    )

    # ------------------------------------------------------------------
    # config
    # ------------------------------------------------------------------

    sub.add_parser(
        "config",
        help="Show ACE configuration",
    )

    # ------------------------------------------------------------------
    # ai
    # ------------------------------------------------------------------

    ai = sub.add_parser(
        "ai",
        help="AI tools",
    )

    ai_sub = ai.add_subparsers(
        dest="ai_command",
    )

    ai_sub.add_parser(
        "models",
        help="List installed Ollama models",
    )

    ask = ai_sub.add_parser(
        "ask",
        help="Ask the configured AI model",
    )

    ask.add_argument(
        "prompt",
        nargs="+",
    )

    # ------------------------------------------------------------------
    # content
    # ------------------------------------------------------------------

    content = sub.add_parser(
        "content",
        help="Generate content",
    )

    content_sub = content.add_subparsers(
        dest="content_command",
    )

    for prompt_name in list_prompts():
        command = content_sub.add_parser(
            prompt_name,
            help=f"Generate {prompt_name} content",
        )

        command.add_argument(
            "topic",
            nargs="+",
        )

    return parser
