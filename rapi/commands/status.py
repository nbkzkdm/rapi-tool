"""rapi status - show server and definition state."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, get_port, log_file
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="Show server status and definitions")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    pid = get_pid()
    if pid:
        port = get_port()
        port_info = f"  port={port}" if port is not None else ""
        print(f"Server : running (pid {pid}{port_info})")
        if port is not None:
            print(f"Listen : http://127.0.0.1:{port}")
        print(f"Log    : {log_file()}")
    else:
        print("Server : not running")

    store = DefinitionStore()
    eps = store.list()
    print(f"Store  : {store.path}")
    print(f"Defs   : {len(eps)}")
    if not eps:
        print("  (no definitions — use 'rapi host ...')")
        return
    print()
    for ep in eps:
        rules_info = f", {len(ep.rules)} rules" if ep.rules else ""
        print(f"  {ep.method:7} {ep.path}  [{ep.name}]  status={ep.default.status}{rules_info}")
        for i, rule in enumerate(ep.rules, 1):
            print(f"           rule[{i}] when {rule.conditions} → {rule.response.status}")
