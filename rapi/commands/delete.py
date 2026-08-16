"""rapi delete - remove a definition; stop server if it was running."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, stop_server
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("delete", help="Delete a definition (stops server if running)")
    p.add_argument("name", nargs="?", default=None,
                   help="Definition name or path (omit with --all to clear all)")
    p.add_argument("--all", action="store_true", help="Delete all definitions")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()

    # stop server first if running (definitions changed)
    pid = get_pid()
    if pid:
        stop_server()
        print(f"Stopped server (pid {pid})")

    if args.all:
        n = len(store.list())
        store.clear()
        print(f"Deleted all definitions ({n})")
        return

    if not args.name:
        raise SystemExit("Specify a name/path or use --all")

    if store.delete(args.name):
        print(f"Deleted: {args.name}")
    else:
        print(f"Not found: {args.name}")
        print("Current definitions:")
        for ep in store.list():
            print(f"  {ep.name}  ({ep.method} {ep.path})")
