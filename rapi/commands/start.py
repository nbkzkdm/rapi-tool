"""rapi start - start background mock server from registered definitions."""

from __future__ import annotations

import argparse

from rapi.core.server import run_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("start", help="Start mock server (background)")
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
