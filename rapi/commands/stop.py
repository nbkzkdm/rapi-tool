"""rapi stop - stop background server."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, stop_server


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("stop", help="Stop mock server")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    pid = get_pid()
    if not pid:
        print("Not running.")
        return
    if stop_server():
        print(f"Stopped (pid {pid})")
    else:
        print("Failed to stop.")
