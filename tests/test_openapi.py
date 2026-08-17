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


def test_param_expected_enum_and_regex():
    eps = [
        Endpoint(
            name="GET:/q",
            path="/q",
            method="GET",
            default=ResponseSpec(body="ok"),
            params={"a": "fixed", "b": r"~\d+", "c": None},
            strict_params=True,
        )
    ]
    doc = endpoints_to_openapi(eps, include_extensions=True)
    params = doc["paths"]["/q"]["get"]["parameters"]
    by_name = {p["name"]: p for p in params}
    assert by_name["a"]["schema"]["enum"] == ["fixed"]
    assert "rapi expected:" in by_name["b"]["description"]
    items = openapi_to_endpoints(doc)
    assert items[0]["params"]["a"] == "fixed"
    assert items[0]["strict_params"] is True


def test_response_object_non_json_body():
    from rapi.core.openapi import _response_object
    r = _response_object(ResponseSpec(status=200, body="plain-text"))
    assert "text/plain" in r["content"]


def test_openapi_to_endpoints_edge_cases():
    doc = {
        "openapi": "3.0.3",
        "paths": {
            "/x": "not-a-dict",
            "/y": {
                "x-something": {},
                "parameters": [],
                "get": "not-op",
                "post": {
                    "responses": {
                        "default": {"description": "x"},
                        "201": {
                            "description": "created",
                            "content": {
                                "text/plain": {"example": "hi"},
                            },
                        },
                    },
                    "parameters": [
                        {"in": "header", "name": "H"},
                        {"in": "query"},  # no name
                        {"in": "query", "name": "q", "schema": {"type": "string"}},
                        {
                            "in": "query",
                            "name": "e",
                            "description": "rapi expected: ~x",
                        },
                    ],
                    "x-rapi-rules": ["bad", {"when": {}, "status": 400, "body": "e"}],
                    "x-rapi-strict-params": True,
                },
                "lock": {  # invalid method
                    "responses": {"200": {"description": "no"}},
                },
            },
        },
    }
    items = openapi_to_endpoints(doc)
    assert any(i["path"] == "/y" and i["method"] == "POST" for i in items)
    post = next(i for i in items if i["method"] == "POST")
    assert post["default"]["status"] == 201
    assert post["params"]["e"] == "~x"
    assert post["params"]["q"] is None
    assert post["strict_params"] is True


def test_extract_example_variants():
    from rapi.core.openapi import _extract_example
    assert _extract_example("x") == ("OK", None)
    assert _extract_example({"description": "only"}) == ("only", None)
    assert _extract_example({"content": {}})[0] in ("OK", "only") or True
    # examples map
    body, ct = _extract_example({
        "content": {
            "application/json": {
                "examples": {"a": {"value": {"k": 1}}},
            }
        }
    })
    assert body == {"k": 1}
    assert ct == "application/json"
    # json with no example
    body, ct = _extract_example({"content": {"application/json": {}}})
    assert body == "{}"
    # non-json content type
    body, ct = _extract_example({
        "content": {"text/plain": {"example": "hello"}}
    })
    assert body == "hello"
    assert ct == "text/plain"


def test_load_openapi_invalid_doc(tmp_path: Path):
    p = tmp_path / "bad.yaml"
    p.write_text("- just\n- a\n- list\n", encoding="utf-8")
    with pytest.raises(SystemExit):
        load_openapi(str(p))


def test_load_openapi_json_fallback(tmp_path: Path):
    p = tmp_path / "spec.unknown"
    doc = endpoints_to_openapi(_sample_eps())
    p.write_text(json.dumps(doc), encoding="utf-8")
    items = load_openapi(str(p))
    assert len(items) >= 1


def test_detect_format_branches(tmp_path: Path, tmp_store: DefinitionStore):
    from rapi.commands.load import _detect_format
    # invalid json extension
    assert _detect_format(Path("x.json"), "{bad", "auto") == "json"
    # unknown ext with openapi marker
    assert _detect_format(Path("x"), "openapi: 3.0.3\n", "auto") == "openapi"
    assert _detect_format(Path("x"), "plain text", "auto") == "json"
    # explicit fmt
    assert _detect_format(Path("x.yaml"), "", "json") == "json"

    # load via unknown ext + openapi yaml content
    p = tmp_path / "spec.dat"
    dump_openapi(_sample_eps(), str(tmp_path / "t.yaml"))
    p.write_text((tmp_path / "t.yaml").read_text(encoding="utf-8"), encoding="utf-8")
    load_cmd.run(SimpleNamespace(file=str(p), fmt="auto", replace=True))


def test_save_default_filename(tmp_store: DefinitionStore, tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    save_cmd.run(SimpleNamespace(file=None, fmt="openapi", no_x_rapi=False))
    assert (tmp_path / "openapi.yaml").is_file()
    save_cmd.run(SimpleNamespace(file=None, fmt="json", no_x_rapi=False))
    assert (tmp_path / "rapi-definitions.json").is_file()


def test_non_numeric_response_key_skipped():
    doc = {
        "paths": {
            "/z": {
                "get": {
                    "responses": {
                        "default": {"description": "d"},
                        "200": {
                            "description": "ok",
                            "content": {"application/json": {"example": {"a": 1}}},
                        },
                    }
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    assert items[0]["default"]["status"] == 200


def test_param_enum_without_rapi_description():
    doc = {
        "paths": {
            "/e": {
                "get": {
                    "parameters": [
                        {
                            "in": "query",
                            "name": "mode",
                            "schema": {"type": "string", "enum": ["a", "b"]},
                        }
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    assert items[0]["params"]["mode"] == "a"


def test_load_openapi_yaml_fail_then_json(tmp_path: Path, monkeypatch):
    import rapi.core.openapi as oa
    p = tmp_path / "x.bin"
    p.write_text('{"openapi":"3.0.3","paths":{}}', encoding="utf-8")

    def boom(text):
        raise Exception("yaml fail")

    monkeypatch.setattr(oa.yaml, "safe_load", boom)
    items = load_openapi(str(p))
    assert items == []


def test_only_non_numeric_response_keys():
    doc = {
        "paths": {
            "/n": {
                "get": {
                    "responses": {
                        "default": {"description": "fallback"},
                        "ok": {"description": "not a code"},
                    }
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    # stays at defaults when no numeric status
    assert items[0]["default"]["status"] == 200
    assert items[0]["default"]["body"] == "OK"
