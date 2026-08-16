"""python -m rapi"""

from __future__ import annotations

import argparse
import sys

from rapi.commands import load_commands


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="rapi",
        description="HTTP mock / request simulator for testing",
    )
    parser.add_argument("--version", action="version", version="rapi 0.2.0")
    sub = parser.add_subparsers(dest="command", required=True)

    load_commands(sub)

    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)
    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\nInterrupted.", file=sys.stderr)
        sys.exit(130)
    except SystemExit:  # pragma: no cover
        raise
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":  # pragma: no cover
    main()
