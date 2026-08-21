"""rapi status - show server and definition state."""

from __future__ import annotations

import argparse
from pathlib import Path

from rapi.core.server import get_pid, get_port, group_state_dir, log_file, state_dir
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'status',
        help='Show server status and definitions (-v for detail)',
        description='Show running state per group, store path, and registered endpoints.\nUse -v/--verbose for response bodies and list settings.',
        epilog='examples:\n  rapi status\n  rapi status -v\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--group",
        default=None,
        help="Filter by group (default: show all groups)",
    )
    p.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Show extra detail (params, list, expected body, rule bodies)",
    )
    p.set_defaults(func=run)


def _known_groups(store: DefinitionStore) -> list[str]:
    groups = {ep.group for ep in store.list()}
    root = state_dir() / "groups"
    if root.is_dir():
        for d in root.iterdir():
            if d.is_dir():
                groups.add(d.name)
    if not groups:
        groups.add("default")
    return sorted(groups)


def _fmt_params(params: dict) -> str:
    if not params:
        return ""
    parts = []
    for k, v in params.items():
        if v is None:
            parts.append(k)
        else:
            parts.append(f"{k}={v}")
    return ", ".join(parts)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()
    all_eps = store.list()
    filter_g = getattr(args, "group", None)
    verbose = bool(getattr(args, "verbose", False))

    groups = [filter_g] if filter_g else _known_groups(store)

    print("=== Server ===")
    running_n = 0
    for group in groups:
        pid = get_pid(group)
        port = get_port(group)
        g_eps = [e for e in all_eps if e.group == group]
        if pid:
            running_n += 1
            print(f"  [{group}] running")
            print(f"         pid    : {pid}")
            if port is not None:
                print(f"         listen : http://127.0.0.1:{port}")
                print(f"         port   : {port}")
            print(f"         log    : {log_file(group)}")
            print(f"         defs   : {len(g_eps)}")
        else:
            print(f"  [{group}] not running")
            if port is not None:
                print(f"         last port file : {port}  (stale?)")
            if g_eps:
                print(f"         defs   : {len(g_eps)}  (start with: rapi start --group {group})")
            elif filter_g:
                print("         defs   : 0")

    print()
    print("=== Store ===")
    print(f"  path : {store.path}")
    print(f"  total definitions : {len(all_eps)}")
    print(f"  groups with process running : {running_n}/{len(groups)}")

    eps = all_eps if not filter_g else [e for e in all_eps if e.group == filter_g]
    print()
    print("=== Definitions ===")
    if not eps:
        print("  (no definitions — use 'rapi host ...')")
        return

    # group by group name
    by_g: dict[str, list] = {}
    for ep in eps:
        by_g.setdefault(ep.group, []).append(ep)

    for group in sorted(by_g.keys()):
        print(f"  --- group: {group} ---")
        for ep in by_g[group]:
            bits = [f"status={ep.default.status}"]
            if ep.default.delay_ms:
                bits.append(f"delay={ep.default.delay_ms}ms")
            if ep.rules:
                bits.append(f"rules={len(ep.rules)}")
            if ep.params:
                bits.append("params")
            if ep.strict_params:
                bits.append("strict")
            if ep.list_key:
                bits.append(f"list={ep.list_key}x{ep.list_count}")
            if ep.expected_body is not None:
                bits.append("body-check")
            print(f"  {ep.method:7} {ep.path}")
            print(f"         name : {ep.name}")
            print(f"         {'  '.join(bits)}")
            if ep.params:
                print(f"         query: {_fmt_params(ep.params)}")
            if verbose and ep.expected_body is not None:
                body_preview = ep.expected_body if len(ep.expected_body) < 80 else ep.expected_body[:77] + "..."
                print(f"         expect body: {body_preview!r}")
            if verbose and ep.list_key:
                print(f"         list key={ep.list_key} count={ep.list_count} start={ep.list_start}")
            if verbose:
                prev = ep.default.body
                if len(prev) > 80:
                    prev = prev[:77] + "..."
                print(f"         response: {prev!r}")
            for i, rule in enumerate(ep.rules, 1):
                dly = f" delay={rule.response.delay_ms}ms" if rule.response.delay_ms else ""
                print(f"         rule[{i}] when {rule.conditions} → {rule.response.status}{dly}")
                if verbose:
                    rb = rule.response.body
                    if len(rb) > 80:
                        rb = rb[:77] + "..."
                    print(f"                body: {rb!r}")
        print()
