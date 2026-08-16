from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Endpoint


def default_store_path() -> Path:
    d = Path.home() / ".rapi"
    d.mkdir(parents=True, exist_ok=True)
    return d / "definitions.json"


class DefinitionStore:
    """Persistent store of endpoint definitions (JSON file)."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or default_store_path()
        self._endpoints: dict[str, Endpoint] = {}
        self.load()

    def load(self) -> None:
        self._endpoints.clear()
        if not self.path.is_file():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return
        items = data if isinstance(data, list) else data.get("endpoints", [])
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                ep = Endpoint.from_dict(item)
                self._endpoints[ep.name] = ep
            except Exception:  # pragma: no cover
                continue

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "endpoints": [ep.to_dict() for ep in self._endpoints.values()],
        }
        self.path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    def list(self) -> list[Endpoint]:
        return list(self._endpoints.values())

    def get(self, name: str) -> Endpoint | None:
        return self._endpoints.get(name)

    def get_by_path_method(self, path: str, method: str) -> Endpoint | None:
        path = path if path.startswith("/") else "/" + path
        method = method.upper()
        for ep in self._endpoints.values():
            if ep.path == path and ep.method == method:
                return ep
        return None

    def upsert(self, ep: Endpoint) -> None:
        # if same path+method exists under different name, replace that one
        existing = self.get_by_path_method(ep.path, ep.method)
        if existing and existing.name != ep.name:
            del self._endpoints[existing.name]
        self._endpoints[ep.name] = ep
        self.save()

    def delete(self, name: str) -> bool:
        if name in self._endpoints:
            del self._endpoints[name]
            self.save()
            return True
        # try path or method:path
        for key, ep in list(self._endpoints.items()):
            if ep.path == name or ep.path.lstrip("/") == name.lstrip("/") or key == name:
                del self._endpoints[key]
                self.save()
                return True
        return False

    def clear(self) -> None:
        self._endpoints.clear()
        self.save()

    def import_from(self, data: list[dict[str, Any]] | dict[str, Any], merge: bool = True) -> int:
        if isinstance(data, dict):
            items = data.get("endpoints", [])
        else:
            items = data
        count = 0
        if not merge:
            self._endpoints.clear()
        for item in items:
            if not isinstance(item, dict):
                continue
            try:
                ep = Endpoint.from_dict(item)
                self._endpoints[ep.name] = ep
                count += 1
            except Exception:  # pragma: no cover
                continue
        self.save()
        return count

    def export(self) -> dict[str, Any]:
        return {"endpoints": [ep.to_dict() for ep in self._endpoints.values()]}
