"""rapi host - register / update a REST endpoint definition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.store import DefinitionStore


def _looks_like_json(text: str) -> bool:
    s = text.strip()
    if not ((s.startswith("{") and s.endswith("}")) or (s.startswith("[") and s.endswith("]"))):
        return False  # non-JSON shaped text
    try:
        json.loads(s)
        return True
    except json.JSONDecodeError:
        return False


def register(subparsers: argparse._SubParsersAction) -> None:
    p = subparsers.add_parser(
        "host",
        help="Define (register) a mock REST endpoint",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
examples:
  rapi host /sample get -r '{"ok":true}'
  rapi host /sample post -r '{"id":"{INPUT.body.id}"}' \\
    --when 'body.id=004' --status 400 --response '{"error":"invalid","id":"{INPUT.body.id}"}'
  rapi host /search query -r '{"results":[]}' --body '~"filter"'
        """,
    )
    p.add_argument("path", help="Endpoint path (e.g. sample or /api/users)")
    p.add_argument("method", help="HTTP method (get, post, put, delete, patch, query, ...)")
    p.add_argument("-r", "--response", default="OK", help="Default response body")
    p.add_argument("-f", "--response-file", help="Default response body from file")
    p.add_argument("-s", "--status", type=int, default=200, help="Default status code")
    p.add_argument("-t", "--content-type", default=None, help="Content-Type")
    p.add_argument("-b", "--body", help="Expected request body (exact or ~regex)")
    p.add_argument("--body-file", help="Expected request body from file")
    p.add_argument("-p", "--param", action="append", default=[], metavar="KEY[=VALUE]",
                   help="Required query param (KEY, KEY=val, KEY=~regex)")
    p.add_argument("--strict", action="store_true", help="Reject extra query params")
    p.add_argument("--name", default=None, help="Definition name (default: METHOD:path)")
    # conditional rules via repeated --when / --status / --response groups is awkward;
    # we collect --when and pair with following --rule-status / --rule-response
    p.add_argument("--when", action="append", default=[], metavar="COND",
                   help="Rule condition(s), AND via comma. e.g. body.id=004 or body.id=~^9,query.x=1")
    p.add_argument("--rule-status", action="append", default=[], type=int, dest="rule_status",
                   help="Status for the corresponding --when (order matched)")
    p.add_argument("--rule-response", action="append", default=[], dest="rule_response",
                   help="Body for the corresponding --when (order matched)")
    p.add_argument("--rule-response-file", action="append", default=[], dest="rule_response_file",
                   help="Body file for the corresponding --when")
    p.set_defaults(func=run)


def _parse_when(s: str) -> dict[str, str]:
    """'body.id=004,query.x=1' → dict AND conditions."""
    cond: dict[str, str] = {}
    for part in s.split(","):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            cond[k.strip()] = v.strip()
        else:
            # existence-only not fully supported in rules; treat as non-empty match
            cond[part] = "~.+"
    return cond


def run(args: argparse.Namespace) -> None:
    path = args.path if args.path.startswith("/") else f"/{args.path}"
    method = args.method.upper()

    # default response body
    body = args.response
    if args.response_file:
        rf = Path(args.response_file)
        if not rf.is_file():
            raise SystemExit(f"response file not found: {args.response_file}")
        body = rf.read_text(encoding="utf-8")

    ct = args.content_type
    if ct is None and _looks_like_json(body):
        ct = "application/json"

    default = ResponseSpec(status=args.status, body=body, content_type=ct)

    # params
    params: dict[str, str | None] = {}
    for p in args.param or []:
        if "=" in p:
            k, v = p.split("=", 1)
            params[k] = v
        else:
            params[p] = None

    expected_body = args.body
    if args.body_file:
        bf = Path(args.body_file)
        if not bf.is_file():
            raise SystemExit(f"body file not found: {args.body_file}")
        expected_body = bf.read_text(encoding="utf-8")

    # rules
    rules: list[Rule] = []
    whens = args.when or []
    statuses = args.rule_status or []
    responses = args.rule_response or []
    resp_files = args.rule_response_file or []

    for i, w in enumerate(whens):
        cond = _parse_when(w)
        st = statuses[i] if i < len(statuses) else 400
        rb = responses[i] if i < len(responses) else '{"error":"condition matched"}'
        if i < len(resp_files) and resp_files[i]:
            rfp = Path(resp_files[i])
            if rfp.is_file():
                rb = rfp.read_text(encoding="utf-8")
        rules.append(Rule(
            conditions=cond,
            response=ResponseSpec(status=st, body=rb, content_type="application/json" if _looks_like_json(rb) else None),
        ))

    name = args.name or f"{method}:{path}"
    ep = Endpoint(
        name=name,
        path=path,
        method=method,
        default=default,
        rules=rules,
        params=params,
        strict_params=args.strict,
        expected_body=expected_body,
    )

    store = DefinitionStore()
    store.upsert(ep)

    print(f"Registered: {ep.method} {ep.path}")
    print(f"  name     : {ep.name}")
    print(f"  status   : {ep.default.status}")
    prev = ep.default.body if len(ep.default.body) < 60 else ep.default.body[:57] + "..."
    print(f"  response : {prev!r}")
    if ep.rules:
        print(f"  rules    : {len(ep.rules)}")
        for i, rule in enumerate(ep.rules, 1):
            print(f"    [{i}] when {rule.conditions} → {rule.response.status}")
    if ep.params:
        print(f"  params   : {ep.params}")
    print(f"  store    : {store.path}")
    print()
    print("Run 'rapi start' to listen.")
