"""rapi start - start background mock server from registered definitions."""

from __future__ import annotations

import argparse

from rapi.core.server import run_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'start',
        help='Start mock server in the background',
        description='Start the HTTP mock server for a definition group.\nLoads endpoints for --group and listens on --host/--port.',
        epilog='examples:\n  rapi start --port 8000\n  rapi start --group api-a --port 8001\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--host", default="127.0.0.1", help="Bind address")
    p.add_argument("--port", type=int, default=8000, help="Port")
    p.add_argument("-f", "--foreground", action="store_true", help="Run in foreground")
    p.add_argument("--group", default="default", help="Group to serve (default: default)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    run_server(
        host=args.host,
        port=args.port,
        background=not args.foreground,
        group=getattr(args, "group", "default") or "default",
    )
