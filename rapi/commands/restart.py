"""rapi restart - restart background server."""

from __future__ import annotations

import argparse
import time

from rapi.core.server import get_pid, run_server, stop_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'restart',
        help='Restart mock server',
        description='Stop then start the server for a group.',
        epilog='examples:\n  rapi restart --port 8000\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--group", default="default", help="Group to restart (default: default)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    group = getattr(args, "group", "default") or "default"
    pid = get_pid(group)
    if pid:
        stop_server(group)
        time.sleep(0.3)
    run_server(host=args.host, port=args.port, background=True, group=group)
