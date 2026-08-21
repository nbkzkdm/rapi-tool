"""rapi call - send a request to a running mock server (connectivity check)."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from rapi.core.server import get_pid, get_port


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        'call',
        help='Call a running mock (connectivity check; --curl for curl sample)',
        description='Send an HTTP request to a running rapi server.\nIf --port is omitted, uses the port of the running --group.',
        epilog='examples:\n  rapi call /sample get\n  rapi call /api post --body \'{"id":"001"}\' --curl\n  rapi call /slow get --timeout 10\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("path", help="Request path (e.g. /slow or /users/42)")
    p.add_argument("method", help="HTTP method (get, post, ...)")
    p.add_argument("--group", default="default", help="Server group (default: default)")
    p.add_argument("--host", default="127.0.0.1", help="Host (default: 127.0.0.1)")
    p.add_argument("--port", type=int, default=None, help="Port (default: from running group)")
    p.add_argument(
        "-q",
        "--query",
        action="append",
        default=[],
        metavar="KEY=VAL",
        help="Query parameter (repeatable)",
    )
    p.add_argument("-b", "--body", default=None, help="Request body string")
    p.add_argument("--body-file", default=None, help="Request body from file")
    p.add_argument(
        "-H",
        "--header",
        action="append",
        default=[],
        metavar="Name: value",
        help="Request header (repeatable)",
    )
    p.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Timeout seconds (default: 30; useful with --delay mocks)",
    )
    p.add_argument("-v", "--verbose", action="store_true", help="Show request details")
    p.add_argument(
        "--curl",
        action="store_true",
        dest="show_curl",
        help="After the call, print an equivalent curl command",
    )
    p.set_defaults(func=run)


def _parse_headers(items: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for raw in items or []:
        if ":" not in raw:
            raise SystemExit(f"Invalid header (use 'Name: value'): {raw}")
        name, value = raw.split(":", 1)
        headers[name.strip()] = value.strip()
    return headers


def _parse_query(items: list[str]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for raw in items or []:
        if "=" in raw:
            k, v = raw.split("=", 1)
            pairs.append((k, v))
        else:
            pairs.append((raw, ""))
    return pairs


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    if not (
        (s.startswith("{") and s.endswith("}"))
        or (s.startswith("[") and s.endswith("]"))
    ):
        return False
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def _build_url(host: str, port: int, path: str, query_pairs: list[tuple[str, str]]) -> str:
    if not path.startswith("/"):
        path = "/" + path
    qs = urllib.parse.urlencode(query_pairs)
    base = f"http://{host}:{port}{path}"
    return f"{base}?{qs}" if qs else base


def _format_curl(
    method: str,
    url: str,
    headers: dict[str, str],
    body: str | None,
) -> str:
    parts = ["curl"]
    m = method.upper()
    if m != "GET":
        parts.extend(["-X", m])
    for name, value in headers.items():
        parts.extend(["-H", f"{name}: {value}"])
    if body is not None and m not in ("GET", "HEAD"):
        parts.extend(["-d", body])
    parts.append(url)
    return " ".join(shlex.quote(p) for p in parts)


def run(args: argparse.Namespace) -> None:
    group = getattr(args, "group", "default") or "default"
    host = getattr(args, "host", "127.0.0.1") or "127.0.0.1"
    port = getattr(args, "port", None)
    method = args.method.upper()
    path = args.path if args.path.startswith("/") else f"/{args.path}"

    if port is None:
        pid = get_pid(group)
        port = get_port(group)
        if not pid or port is None:
            print(
                f"Group '{group}' is not running (or port unknown).",
                file=sys.stderr,
            )
            print(f"  Start with: rapi start --group {group} --port 8000", file=sys.stderr)
            raise SystemExit(1)

    body = getattr(args, "body", None)
    if getattr(args, "body_file", None):
        bf = Path(args.body_file)
        if not bf.is_file():
            raise SystemExit(f"body file not found: {args.body_file}")
        body = bf.read_text(encoding="utf-8")

    headers = _parse_headers(getattr(args, "header", None) or [])
    query_pairs = _parse_query(getattr(args, "query", None) or [])
    url = _build_url(host, port, path, query_pairs)

    data: bytes | None = None
    if body is not None and method not in ("GET", "HEAD"):
        data = body.encode("utf-8")
        if "Content-Type" not in headers and "content-type" not in {k.lower() for k in headers}:
            if _looks_like_json(body):
                headers["Content-Type"] = "application/json"
            else:
                headers["Content-Type"] = "text/plain; charset=utf-8"

    timeout = float(getattr(args, "timeout", 30.0) or 30.0)
    verbose = bool(getattr(args, "verbose", False))
    show_curl = bool(getattr(args, "show_curl", False))

    if verbose:
        print(f"→ {method} {url}")
        for k, v in headers.items():
            print(f"  {k}: {v}")
        if body is not None and method not in ("GET", "HEAD"):
            preview = body if len(body) < 200 else body[:197] + "..."
            print(f"  body: {preview}")
    else:
        print(f"→ {method} {url}")

    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            raw = resp.read()
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = None
    except urllib.error.HTTPError as e:
        status = e.code
        raw = e.read() if e.fp is not None else b""
        try:
            text = raw.decode("utf-8")
        except UnicodeDecodeError:
            text = None
    except urllib.error.URLError as e:
        elapsed = (time.monotonic() - t0) * 1000
        print(f"← connection error ({elapsed:.0f} ms): {e}", file=sys.stderr)
        if show_curl:
            print()
            print("# equivalent curl")
            print(_format_curl(method, url, headers, body))
        raise SystemExit(1) from e

    elapsed = (time.monotonic() - t0) * 1000
    print(f"← {status}  ({elapsed:.0f} ms)")
    if text is not None:
        print(text)
    else:
        print(f"<binary {len(raw)} bytes>")

    if show_curl:
        print()
        print("# equivalent curl")
        print(_format_curl(method, url, headers, body))
