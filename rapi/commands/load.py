"""rapi load - import definitions from JSON or OpenAPI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rapi.core.openapi import load_openapi
from rapi.core.server import get_pid, stop_server
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("load", help="Import definitions from JSON or OpenAPI")
    p.add_argument("file", help="JSON or OpenAPI (YAML/JSON) file to load")
    p.add_argument(
        "--format",
        choices=("json", "openapi", "auto"),
        default="auto",
        dest="fmt",
        help="Input format (default: auto — detect from extension / content)",
    )
    p.add_argument(
        "--replace",
        action="store_true",
        help="Replace all existing definitions (default: merge)",
    )
    p.add_argument(
        "--group",
        default=None,
        help="After load, assign all imported endpoints to this group (optional)",
    )
    p.set_defaults(func=run)


def _detect_format(path: Path, text: str, fmt: str) -> str:
    if fmt != "auto":
        return fmt
    suf = path.suffix.lower()
    if suf in (".yaml", ".yml"):
        return "openapi"
    if suf == ".json":
        try:
            data = json.loads(text)
            if isinstance(data, dict) and ("openapi" in data or "swagger" in data):
                return "openapi"
            return "json"
        except json.JSONDecodeError:
            return "json"
    # no/unknown extension: peek
    if "openapi:" in text[:200] or '"openapi"' in text[:200]:
        return "openapi"
    return "json"


def run(args: argparse.Namespace) -> None:
    path = Path(args.file)
    if not path.is_file():
        raise SystemExit(f"File not found: {args.file}")

    text = path.read_text(encoding="utf-8")
    fmt = _detect_format(path, text, getattr(args, "fmt", "auto"))

    # stop any running groups that may be affected (simple: stop all known groups + default)
    store = DefinitionStore()
    groups = {ep.group for ep in store.list()} | {"default"}
    for g in sorted(groups):
        pid = get_pid(g)
        if pid:
            stop_server(g)
            print(f"Stopped server group '{g}' (pid {pid})")

    if fmt == "openapi":
        items = load_openapi(str(path))
        label = "OpenAPI"
    else:
        data = json.loads(text)
        items = data if isinstance(data, list) else data.get("endpoints", data)
        label = "JSON"

    g_override = getattr(args, "group", None)
    if g_override and isinstance(items, list):
        for it in items:
            if isinstance(it, dict):
                it["group"] = g_override

    count = store.import_from(items, merge=not args.replace)

    mode = "replaced" if args.replace else "merged"
    print(f"Loaded {count} endpoint(s) from {path} ({label}, {mode})")
    print(f"Store: {store.path}")
    for ep in store.list():
        print(f"  {ep.method:7} {ep.path}")
