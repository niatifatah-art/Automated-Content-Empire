import argparse


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

    subparsers = parser.add_subparsers(
        dest="command",
        help="Available commands",
    )

    subparsers.add_parser(
        "doctor",
        help="Check your development environment",
    )

    return parser
