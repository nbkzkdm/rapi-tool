"""Match OpenAPI-style path templates like /users/{id}."""

from __future__ import annotations

import re
from typing import Any


_PARAM_RE = re.compile(r"\{([A-Za-z_][A-Za-z0-9_]*)\}")


def is_template(path: str) -> bool:
    return "{" in path and "}" in path


def template_to_regex(path: str) -> re.Pattern[str]:
    """Build a regex that matches the path and captures named groups."""
    parts: list[str] = []
    last = 0
    for m in _PARAM_RE.finditer(path):
        parts.append(re.escape(path[last:m.start()]))
        name = m.group(1)
        parts.append(f"(?P<{name}>[^/]+)")
        last = m.end()
    parts.append(re.escape(path[last:]))
    return re.compile("^" + "".join(parts) + "$")


def match_path(template: str, actual: str) -> dict[str, str] | None:
    """Return captured path params if actual matches template, else None.

    Exact paths (no {}) require full equality.
    """
    if not is_template(template):
        return {} if template == actual else None
    try:
        m = template_to_regex(template).match(actual)
    except re.error:
        return None
    if not m:
        return None
    return dict(m.groupdict())


def path_param_names(template: str) -> list[str]:
    return _PARAM_RE.findall(template)
