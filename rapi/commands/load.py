"""rapi load - import definitions from a JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rapi.core.server import get_pid, stop_server
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("load", help="Import definitions from JSON file")
    p.add_argument("file", help="JSON file to load")
    p.add_argument("--replace", action="store_true",
                   help="Replace all existing definitions (default: merge)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"File not found: {args.file}")

    data = json.loads(path.read_text(encoding="utf-8"))

    # definitions changed → stop running server
    pid = get_pid()
    if pid:
        stop_server()
        print(f"Stopped server (pid {pid})")

    store = DefinitionStore()
    count = store.import_from(data, merge=not args.replace)
    mode = "replaced" if args.replace else "merged"
    print(f"Loaded {count} endpoint(s) from {path} ({mode})")
    print(f"Store: {store.path}")
    for ep in store.list():
        print(f"  {ep.method:7} {ep.path}")
