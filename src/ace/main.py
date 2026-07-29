from __future__ import annotations

import sys

from ace.cli import create_parser
from ace.commands import execute
from ace.env import load_env
from ace.errors import ACEError


def main() -> int:
    parser = create_parser()
    args = parser.parse_args()
    load_env(getattr(args, "workspace", None))

    try:
        return execute(args)
    except (ACEError, FileNotFoundError, ValueError) as exc:
        print(f"ACE error: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
