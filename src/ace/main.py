from ace.cli import create_parser
from ace.commands import execute


def main():
    parser = create_parser()
    args = parser.parse_args()

    execute(args)


if __name__ == "__main__":
    main()
