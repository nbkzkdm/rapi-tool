from __future__ import annotations

import json
import re
from typing import Any


_PLACEHOLDER_RE = re.compile(r"\{INPUT\.([^}]+)\}")


def _dig(obj: Any, path: str) -> Any:
    """Walk dotted path into dict/list. Returns None if missing."""
    cur = obj
    for part in path.split("."):
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(part)
        elif isinstance(cur, list):
            try:
                cur = cur[int(part)]
            except (ValueError, IndexError):
                return None
        else:
            return None
    return cur


def build_input_context(
    method: str,
    path: str,
    query: dict[str, list[str]],
    headers: dict[str, str],
    body_text: str | None,
) -> dict[str, Any]:
    """Build a nested dict that placeholders can resolve against."""
    qflat = {k: (v[0] if v else "") for k, v in query.items()}
    body_obj: Any = None
    if body_text:
        try:
            body_obj = json.loads(body_text)
        except (json.JSONDecodeError, TypeError):
            body_obj = None

    return {
        "method": method,
        "path": path,
        "query": qflat,
        "header": {k.lower(): v for k, v in headers.items()},
        "body": body_obj if body_obj is not None else (body_text or ""),
        "_body_raw": body_text or "",
    }


def apply_placeholders(template: str, ctx: dict[str, Any]) -> str:
    """Replace {INPUT.xxx} placeholders in template using ctx.

    Missing values become empty string.
    Surrounding text is preserved (e.g. "Test{INPUT.body.id}" -> "Test004").
    """

    def repl(m: re.Match[str]) -> str:
        key = m.group(1).strip()
        # special: body alone when it's the raw string
        if key == "body":
            val = ctx.get("_body_raw", "")
            if val == "" and isinstance(ctx.get("body"), (dict, list)):
                val = json.dumps(ctx["body"], ensure_ascii=False)
            return "" if val is None else str(val)

        # header.X-Request-Id etc. (case-insensitive)
        if key.lower().startswith("header."):
            hname = key.split(".", 1)[1].lower()
            headers = ctx.get("header") or {}
            return str(headers.get(hname, ""))

        val = _dig(ctx, key)
        if val is None:
            return ""
        if isinstance(val, (dict, list)):
            return json.dumps(val, ensure_ascii=False)
        return str(val)

    return _PLACEHOLDER_RE.sub(repl, template)
