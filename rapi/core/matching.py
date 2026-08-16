from __future__ import annotations

import json
import re
from typing import Any

from .placeholders import _dig


def match_value(actual: str, expected: str) -> bool:
    """Match a single value.

    - starts with '~' → fullmatch regex on the rest
    - contains N/A/X/* → simple pattern language
    - otherwise exact string match
    """
    if expected.startswith("~"):
        try:
            return re.fullmatch(expected[1:], actual) is not None
        except re.error:
            return False

    pattern_chars = set("NAX*")
    if any(c in pattern_chars for c in expected):
        parts: list[str] = []
        for c in expected:
            if c == "N":
                parts.append(r"\d")
            elif c == "A":
                parts.append(r"[A-Za-z]")
            elif c == "X":
                parts.append(r"[A-Za-z0-9]")
            elif c == "*":
                parts.append(r".")
            else:
                parts.append(re.escape(c))
        try:
            return re.fullmatch("^" + "".join(parts) + "$", actual) is not None
        except re.error:  # pragma: no cover
            return False

    return actual == expected


def match_body_pattern(actual: str, expected: str) -> bool:
    """Body validation.

    - expected starts with '~' → regex search on the rest
    - otherwise:
      1. strip trailing whitespace and compare strings
      2. if both are valid JSON, compare parsed values (key order / spacing ignored)
    """
    if expected.startswith("~"):
        try:
            return re.search(expected[1:], actual) is not None
        except re.error:
            return False

    a = actual.strip()
    e = expected.strip()
    if a == e:
        return True

    # JSON structural equality (handles trailing newline, spacing, key order)
    try:
        return json.loads(actual) == json.loads(expected)
    except (json.JSONDecodeError, TypeError):
        return False


def _resolve_actual(
    key: str,
    method: str,
    path: str,
    query: dict[str, list[str]],
    headers: dict[str, str],
    body_text: str | None,
    body_json: Any,
) -> str | None:
    """Resolve a condition key to the actual string value from the request."""
    key = key.strip()
    low = key.lower()

    if low == "method":
        return method
    if low == "path":
        return path

    if low.startswith("query."):
        qname = key.split(".", 1)[1]
        vals = query.get(qname) or query.get(qname.lower())
        if not vals:
            return None
        return vals[0]

    if low.startswith("header."):
        hname = key.split(".", 1)[1].lower()
        # headers dict should already be lowercased keys ideally
        for hk, hv in headers.items():
            if hk.lower() == hname:
                return hv
        return None

    if low == "body":
        return body_text or ""

    if low.startswith("body."):
        if body_json is None:
            return None
        path_in_body = key.split(".", 1)[1]
        val = _dig(body_json, path_in_body)
        if val is None:
            return None
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return None


def match_conditions(
    conditions: dict[str, str],
    method: str,
    path: str,
    query: dict[str, list[str]],
    headers: dict[str, str],
    body_text: str | None,
) -> bool:
    """AND-match all conditions against the request. Empty conditions → True."""
    if not conditions:
        return True

    body_json: Any = None
    if body_text:
        try:
            body_json = json.loads(body_text)
        except (json.JSONDecodeError, TypeError):
            body_json = None

    for key, expected in conditions.items():
        actual = _resolve_actual(key, method, path, query, headers, body_text, body_json)
        if actual is None:
            return False
        # rules: ~regex uses search (so ~^9 matches 999); other patterns use match_value
        if expected.startswith("~"):
            try:
                if re.search(expected[1:], actual) is None:
                    return False
            except re.error:
                return False
        elif not match_value(actual, expected):
            return False
    return True
