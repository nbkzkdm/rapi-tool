"""rapi status - show server and definition state."""

from __future__ import annotations

import argparse

from rapi.core.server import get_pid, get_port, log_file
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("status", help="Show server status and definitions")
    p.add_argument("--group", default=None,
                   help="Filter by group (default: show all groups)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()
    all_eps = store.list()
    groups = sorted({ep.group for ep in all_eps}) or ["default"]
    filter_g = getattr(args, "group", None)

    if filter_g:
        groups = [filter_g]

    for group in groups:
        pid = get_pid(group)
        if pid:
            port = get_port(group)
            port_info = f"  port={port}" if port is not None else ""
            print(f"[{group}] Server : running (pid {pid}{port_info})")
            if port is not None:
                print(f"[{group}] Listen : http://127.0.0.1:{port}")
            print(f"[{group}] Log    : {log_file(group)}")
        else:
            print(f"[{group}] Server : not running")

    print(f"Store  : {store.path}")
    eps = all_eps if not filter_g else [e for e in all_eps if e.group == filter_g]
    print(f"Defs   : {len(eps)}")
    if not eps:
        print("  (no definitions — use 'rapi host ...')")
        return
    print()
    for ep in eps:
        rules_info = f", {len(ep.rules)} rules" if ep.rules else ""
        print(f"  [{ep.group}] {ep.method:7} {ep.path}  [{ep.name}]  status={ep.default.status}{rules_info}")
        for i, rule in enumerate(ep.rules, 1):
            print(f"           rule[{i}] when {rule.conditions} → {rule.response.status}")
