from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rapi.commands import load as load_cmd
from rapi.commands import save as save_cmd
from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.openapi import endpoints_to_openapi, openapi_to_endpoints, dump_openapi, load_openapi
from rapi.core.store import DefinitionStore


def _sample_eps():
    return [
        Endpoint(
            name="GET:/items",
            path="/items",
            method="GET",
            default=ResponseSpec(status=200, body='{"ok":true}', content_type="application/json"),
            params={"limit": None},
            list_key="results",
            list_item='{"id":"{INDEX}"}',
            list_count=3,
            list_start=1,
        ),
        Endpoint(
            name="POST:/items",
            path="/items",
            method="POST",
            default=ResponseSpec(status=201, body='{"id":"{INPUT.body.id}"}'),
            rules=[
                Rule(
                    conditions={"body.id": "004"},
                    response=ResponseSpec(status=400, body='{"error":"bad"}'),
                )
            ],
            expected_body='~"id"',
            strict_params=False,
        ),
    ]


def test_roundtrip_openapi_dict():
    doc = endpoints_to_openapi(_sample_eps())
    assert doc["openapi"].startswith("3.")
    assert "/items" in doc["paths"]
    assert "get" in doc["paths"]["/items"]
    assert "post" in doc["paths"]["/items"]
    items = openapi_to_endpoints(doc)
    assert len(items) == 2
    methods = {(i["method"], i["path"]) for i in items}
    assert ("GET", "/items") in methods
    assert ("POST", "/items") in methods
    post = next(i for i in items if i["method"] == "POST")
    assert post["rules"]
    assert post["expected_body"] == '~"id"'


def test_dump_and_load_yaml(tmp_path: Path):
    path = tmp_path / "api.yaml"
    dump_openapi(_sample_eps(), str(path))
    text = path.read_text(encoding="utf-8")
    assert "openapi:" in text
    assert "/items" in text
    items = load_openapi(str(path))
    assert len(items) >= 2


def test_dump_json_suffix(tmp_path: Path):
    path = tmp_path / "api.json"
    dump_openapi(_sample_eps(), str(path))
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert "paths" in doc


def test_save_load_commands(tmp_store: DefinitionStore, tmp_path: Path, monkeypatch):
    for ep in _sample_eps():
        tmp_store.upsert(ep)

    out = tmp_path / "out.yaml"
    save_cmd.run(SimpleNamespace(file=str(out), fmt="openapi"))
    assert out.is_file()

    tmp_store.clear()
    load_cmd.run(SimpleNamespace(file=str(out), fmt="openapi", replace=True))
    tmp_store.load()
    assert len(tmp_store.list()) == 2


def test_load_auto_detect_yaml(tmp_store: DefinitionStore, tmp_path: Path):
    path = tmp_path / "spec.yaml"
    dump_openapi(_sample_eps(), str(path))
    tmp_store.clear()
    load_cmd.run(SimpleNamespace(file=str(path), fmt="auto", replace=True))
    tmp_store.load()
    assert any(ep.path == "/items" for ep in tmp_store.list())


def test_load_auto_detect_openapi_json(tmp_store: DefinitionStore, tmp_path: Path):
    path = tmp_path / "spec.json"
    dump_openapi(_sample_eps(), str(path))
    tmp_store.clear()
    load_cmd.run(SimpleNamespace(file=str(path), fmt="auto", replace=False))
    tmp_store.load()
    assert len(tmp_store.list()) >= 1


def test_no_x_rapi_extensions():
    import json
    doc = endpoints_to_openapi(_sample_eps(), include_extensions=False)
    s = json.dumps(doc)
    assert "x-rapi" not in s
    # rule status still present as response
    post = doc["paths"]["/items"]["post"]
    assert "400" in post["responses"]


def test_save_no_x_rapi(tmp_store: DefinitionStore, tmp_path: Path):
    for ep in _sample_eps():
        tmp_store.upsert(ep)
    out = tmp_path / "plain.yaml"
    save_cmd.run(SimpleNamespace(file=str(out), fmt="openapi", no_x_rapi=True))
    text = out.read_text(encoding="utf-8")
    assert "x-rapi" not in text
    assert "openapi:" in text
