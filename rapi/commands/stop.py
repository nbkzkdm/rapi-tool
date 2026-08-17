"""rapi stop - stop background server."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, stop_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("stop", help="Stop mock server")
    p.add_argument("--group", default="default", help="Group to stop (default: default)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    group = getattr(args, "group", "default") or "default"
    pid = get_pid(group)
    if not pid:
        print(f"Group '{group}' is not running.")
        return
    if stop_server(group):
        print(f"Stopped group '{group}' (pid {pid})")
    else:
        print(f"Failed to stop group '{group}'.")
