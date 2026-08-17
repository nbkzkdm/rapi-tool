"""rapi delete - remove a definition; stop server if it was running."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, stop_server
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("delete", help="Delete a definition (stops server if running)")
    p.add_argument("name", nargs="?", default=None,
                   help="Definition name or path (omit with --all to clear)")
    p.add_argument("--all", action="store_true", help="Delete all definitions in the group")
    p.add_argument("--group", default="default", help="Group scope (default: default)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()
    group = getattr(args, "group", "default") or "default"

    pid = get_pid(group)
    if pid:
        stop_server(group)
        print(f"Stopped server group '{group}' (pid {pid})")

    if args.all:
        targets = [ep for ep in store.list() if ep.group == group]
        for ep in targets:
            store.delete(ep.name, group=group)
        print(f"Deleted all definitions in group '{group}' ({len(targets)})")
        return

    if not args.name:
        raise SystemExit("Specify a name/path or use --all")

    if store.delete(args.name, group=group):
        print(f"Deleted: {args.name} (group={group})")
    else:
        print(f"Not found: {args.name} (group={group})")
        print("Current definitions:")
        for ep in store.list():
            if ep.group == group:
                print(f"  {ep.name}  ({ep.method} {ep.path})")
