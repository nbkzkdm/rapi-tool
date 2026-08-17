"""Expand list placeholders in response envelopes."""

from __future__ import annotations

import json
import re
from typing import Any


_INDEX_RE = re.compile(r"\{INDEX(?::(\d+))?\}")


def format_index(n: int, width: int | None = None) -> str:
    if width is None or width <= 0:
        return str(n)
    return f"{n:0{width}d}"


def apply_index_placeholders(template: str, index: int) -> str:
    def repl(m: re.Match[str]) -> str:
        width_s = m.group(1)
        width = int(width_s) if width_s else None
        return format_index(index, width)

    return _INDEX_RE.sub(repl, template)


def _apply_index_in_obj(obj: Any, index: int) -> Any:
    if isinstance(obj, str):
        return apply_index_placeholders(obj, index)
    if isinstance(obj, list):
        return [_apply_index_in_obj(x, index) for x in obj]
    if isinstance(obj, dict):
        return {k: _apply_index_in_obj(v, index) for k, v in obj.items()}
    return obj


def expand_list_in_body(
    body: str,
    *,
    list_key: str | None,
    list_item: str | None,
    list_count: int | None,
    list_start: int = 1,
) -> str:
    """If list_* is configured, fill envelope[list_key] with generated items.

    - body: envelope JSON string (may contain {LIST_COUNT} before/after)
    - list_item: JSON string for one item (supports {INDEX} / {INDEX:05})
    - list_key: dotted path under the envelope root, e.g. "results" or "data.items"
    """
    if not list_key or list_item is None or list_count is None:
        return body

    count = max(0, int(list_count))
    start = int(list_start)

    try:
        item_template = json.loads(list_item)
    except json.JSONDecodeError:
        # treat as string template for each element
        item_template = list_item

    items: list[Any] = []
    for i in range(count):
        idx = start + i
        if isinstance(item_template, str):
            items.append(apply_index_placeholders(item_template, idx))
        else:
            items.append(_apply_index_in_obj(json.loads(json.dumps(item_template)), idx))

    # inject into envelope
    try:
        envelope: Any = json.loads(body)
    except json.JSONDecodeError:
        return body

    if not isinstance(envelope, dict):
        return body

    _set_by_path(envelope, list_key, items)

    # optional {LIST_COUNT} in string leaves of envelope (after structure set)
    text = json.dumps(envelope, ensure_ascii=False)
    text = text.replace("{LIST_COUNT}", str(count))
    # also support in original body if dump changed quoting — re-parse path already used dump
    return text


def _set_by_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Any = root
    for p in parts[:-1]:
        if not isinstance(cur, dict):  # pragma: no cover - defensive
            return
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    if isinstance(cur, dict) and parts:
        cur[parts[-1]] = value
