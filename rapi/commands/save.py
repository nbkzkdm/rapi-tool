"""rapi save - export current definitions to JSON or OpenAPI."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rapi.core.openapi import dump_openapi
from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'save',
        help='Export definitions to JSON or OpenAPI',
        description='Write current definitions to a file (JSON or OpenAPI 3 YAML/JSON).',
        epilog='examples:\n  rapi save my.json\n  rapi save openapi.yaml --format openapi\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "file",
        nargs="?",
        default=None,
        help="Output file (default: rapi-definitions.json or openapi.yaml)",
    )
    p.add_argument(
        "--format",
        choices=("json", "openapi"),
        default="json",
        dest="fmt",
        help="Export format (default: json). openapi writes OpenAPI 3 YAML/JSON",
    )
    p.add_argument(
        "--no-x-rapi",
        action="store_true",
        help="When --format openapi: omit x-rapi-* extensions (standard OpenAPI only)",
    )
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()
    endpoints = store.list()
    fmt = getattr(args, "fmt", "json")

    if args.file:
        path = Path(args.file)
    else:
        path = Path("openapi.yaml" if fmt == "openapi" else "rapi-definitions.json")

    if fmt == "openapi":
        include_ext = not getattr(args, "no_x_rapi", False)
        dump_openapi(endpoints, str(path), include_extensions=include_ext)
        mode = "standard" if not include_ext else "with x-rapi-*"
        print(f"Saved OpenAPI ({len(endpoints)} path operation(s), {mode}) → {path.resolve()}")
    else:
        data = store.export()
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"Saved {len(data.get('endpoints', []))} endpoint(s) → {path.resolve()}")
