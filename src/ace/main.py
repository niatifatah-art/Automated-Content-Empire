import argparse


def main():
    parser = argparse.ArgumentParser(
        prog="ace",
        description="Automated Content Empire"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="ACE 0.1.0"
    )

    args = parser.parse_args()

    print("Welcome to Automated Content Empire (ACE)")


if __name__ == "__main__":
    main()
