from __future__ import annotations

import json
from pathlib import Path

from rapi.core.models import Endpoint, ResponseSpec
from rapi.core.store import DefinitionStore


def test_upsert_list_delete(tmp_store: DefinitionStore):
    ep = Endpoint(name="GET:/a", path="/a", method="GET", default=ResponseSpec(body="a"))
    tmp_store.upsert(ep)
    assert len(tmp_store.list()) == 1
    assert tmp_store.get("GET:/a") is not None
    assert tmp_store.get_by_path_method("/a", "GET") is not None
    assert tmp_store.delete("GET:/a")
    assert len(tmp_store.list()) == 0
    assert not tmp_store.delete("missing")


def test_upsert_replaces_same_path_method(tmp_store: DefinitionStore):
    tmp_store.upsert(Endpoint(name="n1", path="/a", method="GET", default=ResponseSpec(body="1")))
    tmp_store.upsert(Endpoint(name="n2", path="/a", method="GET", default=ResponseSpec(body="2")))
    assert len(tmp_store.list()) == 1
    assert tmp_store.list()[0].name == "n2"


def test_delete_by_path(tmp_store: DefinitionStore):
    tmp_store.upsert(Endpoint(name="GET:/x", path="/x", method="GET"))
    assert tmp_store.delete("/x")
    assert tmp_store.list() == []


def test_clear_and_export_import(tmp_store: DefinitionStore, tmp_path: Path):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    data = tmp_store.export()
    assert len(data["endpoints"]) == 1
    tmp_store.clear()
    assert tmp_store.list() == []
    n = tmp_store.import_from(data, merge=False)
    assert n == 1
    n2 = tmp_store.import_from({"endpoints": [{"path": "/b", "method": "POST"}]}, merge=True)
    assert n2 == 1
    assert len(tmp_store.list()) == 2


def test_load_corrupt_file(tmp_path: Path, monkeypatch):
    p = tmp_path / "bad.json"
    p.write_text("{not json", encoding="utf-8")
    monkeypatch.setattr("rapi.core.store.default_store_path", lambda: p)
    store = DefinitionStore(path=p)
    assert store.list() == []


def test_load_skips_bad_items(tmp_path: Path):
    p = tmp_path / "defs.json"
    p.write_text(json.dumps({"endpoints": [None, "x", {"path": "/ok", "method": "GET"}]}), encoding="utf-8")
    store = DefinitionStore(path=p)
    assert len(store.list()) == 1


def test_import_replace(tmp_store: DefinitionStore):
    tmp_store.upsert(Endpoint(name="GET:/old", path="/old", method="GET"))
    tmp_store.import_from([{"path": "/new", "method": "GET"}], merge=False)
    names = [e.path for e in tmp_store.list()]
    assert names == ["/new"]
