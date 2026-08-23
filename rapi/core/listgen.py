"""Expand list placeholders in response envelopes."""

from __future__ import annotations

import json
import re
from calendar import monthrange
from datetime import datetime, timedelta
from typing import Any


_INDEX_RE = re.compile(r"\{INDEX(?::(\d+))?\}")
# {DATE} or {DATE:%Y/%m/%d} (strftime after the colon)
_DATE_RE = re.compile(r"\{DATE(?::([^}]+))?\}")

_DATE_START_FORMATS = (
    "%Y/%m/%d %H:%M:%S",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d",
)

_INCREMENT_ALIASES = {
    "month": "month",
    "months": "month",
    "day": "day",
    "days": "day",
    "hour": "hour",
    "hours": "hour",
    "minute": "minute",
    "minutes": "minute",
    "minite": "minute",  # common typo accepted
    "minites": "minute",
}


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


def parse_date_start(text: str) -> datetime:
    s = text.strip()
    for fmt in _DATE_START_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(
        f"Cannot parse list date start: {text!r} "
        f"(try YYYY/MM/DD or YYYY-MM-DD[ HH:MM[:SS]])"
    )


def normalize_increment_type(raw: str | None) -> str | None:
    if raw is None or not str(raw).strip():
        return None
    key = str(raw).strip().lower()
    if key not in _INCREMENT_ALIASES:
        raise ValueError(
            f"Invalid increment type: {raw!r} "
            f"(use month, day, hour, minute)"
        )
    return _INCREMENT_ALIASES[key]


def add_date_offset(dt: datetime, *, inc_type: str, unit: int, steps: int) -> datetime:
    """Apply (unit * steps) of inc_type to dt."""
    n = int(unit) * int(steps)
    if n == 0:
        return dt
    if inc_type == "day":
        return dt + timedelta(days=n)
    if inc_type == "hour":
        return dt + timedelta(hours=n)
    if inc_type == "minute":
        return dt + timedelta(minutes=n)
    if inc_type == "month":
        return _add_months(dt, n)
    raise ValueError(f"Unknown increment type: {inc_type}")


def _add_months(dt: datetime, months: int) -> datetime:
    y = dt.year + (dt.month - 1 + months) // 12
    m = (dt.month - 1 + months) % 12 + 1
    last = monthrange(y, m)[1]
    d = min(dt.day, last)
    return dt.replace(year=y, month=m, day=d)


def format_date(dt: datetime, fmt: str | None = None) -> str:
    if not fmt:
        fmt = "%Y/%m/%d"
    # allow YYYY/MM/DD style tokens loosely mapped if user passes them
    # Prefer real strftime; document %Y/%m/%d
    return dt.strftime(fmt)


def apply_date_placeholders(template: str, dt: datetime | None) -> str:
    if dt is None:
        return template

    def repl(m: re.Match[str]) -> str:
        fmt = m.group(1)
        return format_date(dt, fmt)

    return _DATE_RE.sub(repl, template)


def apply_list_placeholders(
    template: str,
    *,
    index: int,
    date: datetime | None = None,
) -> str:
    s = apply_index_placeholders(template, index)
    s = apply_date_placeholders(s, date)
    return s


def _apply_in_obj(obj: Any, *, index: int, date: datetime | None) -> Any:
    if isinstance(obj, str):
        return apply_list_placeholders(obj, index=index, date=date)
    if isinstance(obj, list):
        return [_apply_in_obj(x, index=index, date=date) for x in obj]
    if isinstance(obj, dict):
        return {k: _apply_in_obj(v, index=index, date=date) for k, v in obj.items()}
    return obj


def _set_by_path(root: dict[str, Any], path: str, value: Any) -> None:
    parts = path.split(".")
    cur: Any = root
    for p in parts[:-1]:
        if p not in cur or not isinstance(cur[p], dict):
            cur[p] = {}
        cur = cur[p]
    cur[parts[-1]] = value


def expand_list_in_body(
    body: str,
    *,
    list_key: str | None,
    list_item: str | None,
    list_count: int | None,
    list_start: int = 1,
    list_date_start: str | None = None,
    list_date_increment_type: str | None = None,
    list_date_increment_unit: int = 1,
) -> str:
    """If list_* is configured, fill envelope[list_key] with generated items.

    - list_item: JSON string for one item (supports {INDEX}, {INDEX:05}, {DATE}, {DATE:%Y/%m/%d})
    - list_date_start + increment type/unit: date series for {DATE}
    """
    if not list_key or list_item is None or list_count is None:
        return body

    count = max(0, int(list_count))
    start = int(list_start)

    base_date: datetime | None = None
    inc_type: str | None = None
    unit = int(list_date_increment_unit or 1)
    if list_date_start:
        base_date = parse_date_start(list_date_start)
        inc_type = normalize_increment_type(list_date_increment_type) or "day"

    try:
        item_template = json.loads(list_item)
    except json.JSONDecodeError:
        item_template = list_item

    items: list[Any] = []
    for i in range(count):
        idx = start + i
        dt: datetime | None = None
        if base_date is not None and inc_type is not None:
            dt = add_date_offset(base_date, inc_type=inc_type, unit=unit, steps=i)

        if isinstance(item_template, str):
            items.append(apply_list_placeholders(item_template, index=idx, date=dt))
        else:
            cloned = json.loads(json.dumps(item_template))
            items.append(_apply_in_obj(cloned, index=idx, date=dt))

    try:
        envelope: Any = json.loads(body)
    except json.JSONDecodeError:
        return body

    if not isinstance(envelope, dict):
        return body

    _set_by_path(envelope, list_key, items)

    text = json.dumps(envelope, ensure_ascii=False)
    text = text.replace("{LIST_COUNT}", str(count))
    return text
