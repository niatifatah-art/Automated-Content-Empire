from ace.cli import create_parser
from ace.doctor import run


def main():
    parser = create_parser()
    args = parser.parse_args()

    if args.command == "doctor":
        run()
        return

    print("Welcome to Automated Content Empire (ACE)")


if __name__ == "__main__":
    main()
