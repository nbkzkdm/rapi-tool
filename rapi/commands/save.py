"""rapi save - export current definitions to a JSON file."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rapi.core.store import DefinitionStore


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser("save", help="Export definitions to JSON file")
    p.add_argument("file", nargs="?", default="rapi-definitions.json",
                   help="Output file (default: rapi-definitions.json)")
    p.set_defaults(func=run)


def run(args: argparse.Namespace) -> None:
    store = DefinitionStore()
    data = store.export()
    path = Path(args.file)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(data.get('endpoints', []))} endpoint(s) → {path.resolve()}")
