"""rapi restart - restart background server."""

from __future__ import annotations

import argparse
import time

from rapi.core.server import get_pid, run_server, stop_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("restart", help="Restart mock server")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    pid = get_pid()
    if pid:
        stop_server()
        time.sleep(0.3)
    run_server(host=args.host, port=args.port, background=True)
