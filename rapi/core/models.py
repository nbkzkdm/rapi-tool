from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class ResponseSpec:
    status: int = 200
    body: str = "OK"
    content_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"status": self.status, "body": self.body}
        if self.content_type:
            d["content_type"] = self.content_type
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ResponseSpec:
        return cls(
            status=int(data.get("status", 200)),
            body=str(data.get("body", "OK")),
            content_type=data.get("content_type"),
        )


@dataclass
class Rule:
    """Conditional response. conditions are AND-ed."""
    conditions: dict[str, str] = field(default_factory=dict)  # key -> expected (exact or ~regex)
    response: ResponseSpec = field(default_factory=ResponseSpec)

    def to_dict(self) -> dict[str, Any]:
        return {
            "when": self.conditions,
            "status": self.response.status,
            "body": self.response.body,
            **({"content_type": self.response.content_type} if self.response.content_type else {}),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Rule:
        when = data.get("when") or data.get("conditions") or {}
        if not isinstance(when, dict):
            when = {}
        return cls(
            conditions={str(k): str(v) for k, v in when.items()},
            response=ResponseSpec(
                status=int(data.get("status", 200)),
                body=str(data.get("body", "OK")),
                content_type=data.get("content_type"),
            ),
        )


@dataclass
class Endpoint:
    """A registered mock endpoint definition."""
    name: str  # unique id, often path+method
    path: str
    method: str
    default: ResponseSpec = field(default_factory=ResponseSpec)
    rules: list[Rule] = field(default_factory=list)
    # legacy / extra validation
    params: dict[str, str | None] = field(default_factory=dict)  # required query params
    strict_params: bool = False
    expected_body: str | None = None  # exact or ~regex for request body validation
    # list expansion (envelope + item template)
    list_key: str | None = None
    list_item: str | None = None  # JSON template for one element
    list_count: int | None = None
    list_start: int = 1

    def __post_init__(self) -> None:
        if not self.path.startswith("/"):
            self.path = "/" + self.path
        self.method = self.method.upper()
        if not self.name:
            self.name = f"{self.method}:{self.path}"

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "name": self.name,
            "path": self.path,
            "method": self.method,
            "default": self.default.to_dict(),
            "rules": [r.to_dict() for r in self.rules],
        }
        if self.params:
            d["params"] = self.params
        if self.strict_params:
            d["strict_params"] = True
        if self.expected_body is not None:
            d["expected_body"] = self.expected_body
        if self.list_key:
            d["list_key"] = self.list_key
        if self.list_item is not None:
            d["list_item"] = self.list_item
        if self.list_count is not None:
            d["list_count"] = self.list_count
        if self.list_start != 1:
            d["list_start"] = self.list_start
        return d

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Endpoint:
        default_data = data.get("default") or {}
        if "status" in data and "default" not in data:
            # flat format fallback
            default_data = {
                "status": data.get("status", 200),
                "body": data.get("response") or data.get("body", "OK"),
                "content_type": data.get("content_type"),
            }
        rules_data = data.get("rules") or []
        params = data.get("params") or {}
        # normalize params list form
        if isinstance(params, list):
            pdict: dict[str, str | None] = {}
            for p in params:
                if isinstance(p, str):
                    if "=" in p:
                        k, v = p.split("=", 1)
                        pdict[k] = v
                    else:
                        pdict[p] = None
                elif isinstance(p, dict):
                    k = p.get("key") or p.get("name")
                    if k:
                        pdict[str(k)] = p.get("value")
            params = pdict

        return cls(
            name=str(data.get("name") or f"{data.get('method', 'GET')}:{data.get('path', '/')}"),
            path=str(data.get("path", "/")),
            method=str(data.get("method", "GET")),
            default=ResponseSpec.from_dict(default_data) if isinstance(default_data, dict) else ResponseSpec(),
            rules=[Rule.from_dict(r) for r in rules_data if isinstance(r, dict)],
            params={str(k): (None if v is None else str(v)) for k, v in params.items()},
            strict_params=bool(data.get("strict_params") or data.get("strict", False)),
            expected_body=data.get("expected_body") or data.get("body"),
            list_key=data.get("list_key"),
            list_item=data.get("list_item"),
            list_count=(int(data["list_count"]) if data.get("list_count") is not None else None),
            list_start=int(data.get("list_start", 1)),
        )
