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
        'host',
        help='Register a REST mock definition (path + method + response)',
        description="Register (or replace) a mock endpoint definition.\nPort is NOT set here — use 'rapi start --port' when listening.\nOptional: --group, query/body validation, rules, list generation, delay.",
        epilog='examples:\n  rapi host /sample get -r \'{"ok":true}\'\n  rapi host \'/users/{id}\' get -r \'{"id":"{INPUT.path.id}"}\'\n  rapi host /slow get -r \'{"ok":true}\' --delay 1500\n',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("path", help="Endpoint path (e.g. sample or /api/users)")
    p.add_argument("method", help="HTTP method (get, post, put, delete, patch, query, ...)")
    p.add_argument("-r", "--response", default="OK", help="Default response body")
    p.add_argument("-f", "--response-file", help="Default response body from file")
    p.add_argument("-s", "--status", type=int, default=200, help="Default status code")
    p.add_argument("--delay", type=int, default=0, metavar="MS",
                   help="Delay default response by MS milliseconds (timeout tests)")
    p.add_argument("-t", "--content-type", default=None, help="Content-Type")
    p.add_argument("-b", "--body", help="Expected request body (exact or ~regex)")
    p.add_argument("--body-file", help="Expected request body from file")
    p.add_argument("-p", "--param", action="append", default=[], metavar="KEY[=VALUE]",
                   help="Required query param (KEY, KEY=val, KEY=~regex)")
    p.add_argument("--strict", action="store_true", help="Reject extra query params")
    p.add_argument("--name", default=None, help="Definition name (default: METHOD:path)")
    p.add_argument("--group", default="default",
                   help="Definition group (default: default). Used to split processes")
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
    p.add_argument("--rule-delay", action="append", default=[], type=int, dest="rule_delay",
                   help="Delay (ms) for the corresponding --when (order matched)")
    p.add_argument("--list-key", default=None,
                   help="Envelope field path to fill with a generated list (e.g. results)")
    p.add_argument("--list-item", default=None,
                   help="JSON template for one list element ({INDEX}, {INDEX:05}, {DATE}, {DATE:%Y/%m/%d})")
    p.add_argument("--list-item-file", default=None,
                   help="Load list item template from file")
    p.add_argument("--list-count", type=int, default=None,
                   help="Number of list items to generate")
    p.add_argument("--list-start", type=int, default=1,
                   help="Start index for {INDEX} (default: 1)")
    p.add_argument("--list-date-start", default=None,
                   help="Start datetime for {DATE} (e.g. 2026/09/01 or 2026-09-01 10:00)")
    p.add_argument("--list-date-increment-type", default=None,
                   metavar="TYPE",
                   help="Date step: month, day, hour, minute (alias: minite)")
    p.add_argument("--list-date-increment-unit", type=int, default=1,
                   help="Add this many TYPE units per list item (default: 1)")
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

    delay_ms = max(0, int(getattr(args, "delay", 0) or 0))
    default = ResponseSpec(status=args.status, body=body, content_type=ct, delay_ms=delay_ms)

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
    rule_delays = getattr(args, "rule_delay", None) or []

    for i, w in enumerate(whens):
        cond = _parse_when(w)
        st = statuses[i] if i < len(statuses) else 400
        rb = responses[i] if i < len(responses) else '{"error":"condition matched"}'
        if i < len(resp_files) and resp_files[i]:
            rfp = Path(resp_files[i])
            if rfp.is_file():
                rb = rfp.read_text(encoding="utf-8")
        rd = rule_delays[i] if i < len(rule_delays) else 0
        rules.append(Rule(
            conditions=cond,
            response=ResponseSpec(
                status=st,
                body=rb,
                content_type="application/json" if _looks_like_json(rb) else None,
                delay_ms=max(0, int(rd or 0)),
            ),
        ))

    list_item = getattr(args, "list_item", None)
    if getattr(args, "list_item_file", None):
        lip = Path(args.list_item_file)
        if not lip.is_file():
            raise SystemExit(f"list item file not found: {args.list_item_file}")
        list_item = lip.read_text(encoding="utf-8")

    list_key = getattr(args, "list_key", None)
    list_count = getattr(args, "list_count", None)
    list_start = getattr(args, "list_start", 1)
    list_date_start = getattr(args, "list_date_start", None)
    list_date_increment_type = getattr(args, "list_date_increment_type", None)
    list_date_increment_unit = int(getattr(args, "list_date_increment_unit", 1) or 1)
    if list_key and list_item is None:
        raise SystemExit("--list-key requires --list-item or --list-item-file")
    if list_key and list_count is None:
        raise SystemExit("--list-key requires --list-count")

    name = args.name or f"{method}:{path}"
    ep = Endpoint(
        name=name,
        path=path,
        method=method,
        group=getattr(args, "group", "default") or "default",
        default=default,
        rules=rules,
        params=params,
        strict_params=args.strict,
        expected_body=expected_body,
        list_key=list_key,
        list_item=list_item,
        list_count=list_count,
        list_start=list_start,
        list_date_start=list_date_start,
        list_date_increment_type=list_date_increment_type,
        list_date_increment_unit=list_date_increment_unit,
    )

    store = DefinitionStore()
    store.upsert(ep)

    print(f"Registered: {ep.method} {ep.path}")
    print(f"  group    : {ep.group}")
    print(f"  name     : {ep.name}")
    print(f"  status   : {ep.default.status}")
    if ep.default.delay_ms:
        print(f"  delay    : {ep.default.delay_ms} ms")
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
