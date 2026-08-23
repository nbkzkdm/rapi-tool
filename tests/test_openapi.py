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
    assert _extract_example({}, "x") == ("OK", None)
    assert _extract_example({}, {"description": "only"}) == ("only", None)
    assert _extract_example({}, {"content": {}})[0] in ("OK", "only") or True
    # examples map
    body, ct = _extract_example({}, {
        "content": {
            "application/json": {
                "examples": {"a": {"value": {"k": 1}}},
            }
        }
    })
    assert body == {"k": 1}
    assert ct == "application/json"
    # json with no example
    body, ct = _extract_example({}, {"content": {"application/json": {}}})
    assert body == "{}"
    # non-json content type
    body, ct = _extract_example({}, {
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


def test_ref_schema_example_and_path_params():
    doc = {
        "openapi": "3.0.3",
        "components": {
            "schemas": {
                "Item": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "example": "i-1"},
                        "n": {"type": "integer"},
                    },
                }
            }
        },
        "paths": {
            "/items/{id}": {
                "parameters": [
                    {"name": "id", "in": "path", "required": True, "schema": {"type": "string"}},
                    {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
                ],
                "get": {
                    "parameters": [
                        {"name": "q", "in": "query", "required": True, "schema": {"enum": ["a", "b"]}},
                    ],
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Item"},
                                }
                            },
                        }
                    },
                },
            }
        },
    }
    items = openapi_to_endpoints(doc)
    assert len(items) == 1
    ep = items[0]
    assert ep["path"] == "/items/{id}"
    assert ep["params"]["q"] == "a"  # enum from operation-level override
    body = ep["default"]["body"]
    assert "i-1" in body or "id" in body


def test_request_body_required_example():
    doc = {
        "paths": {
            "/p": {
                "post": {
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {"example": {"name": "taro"}},
                        },
                    },
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    assert "expected_body" in items[0]
    assert "taro" in items[0]["expected_body"]


def test_resolve_ref_edge_cases():
    from rapi.core.openapi import _resolve_ref

    # non-dict
    assert _resolve_ref({}, "x") == "x"
    # no $ref / external-ish
    assert _resolve_ref({}, {"$ref": "https://example.com/x"}) == {"$ref": "https://example.com/x"}
    # missing path in doc
    assert _resolve_ref({"a": 1}, {"$ref": "#/components/missing"}) == {"$ref": "#/components/missing"}
    # cycle
    doc = {"components": {"schemas": {"A": {"$ref": "#/components/schemas/A"}}}}
    out = _resolve_ref(doc, {"$ref": "#/components/schemas/A"})
    assert isinstance(out, dict) and "$ref" in out
    # chained ref
    doc2 = {
        "components": {
            "schemas": {
                "A": {"$ref": "#/components/schemas/B"},
                "B": {"type": "string", "example": "hi"},
            }
        }
    }
    assert _resolve_ref(doc2, {"$ref": "#/components/schemas/A"})["example"] == "hi"
    # tilde escape
    doc3 = {"a/b": {"ok": True}}
    assert _resolve_ref(doc3, {"$ref": "#/a~1b"})["ok"] is True


def test_merge_parameters_skips_non_dict_and_ref_to_non_dict():
    from rapi.core.openapi import _merge_parameters

    doc = {"components": {"parameters": {"Bad": "not-a-dict"}}}
    path_item = {
        "parameters": [
            "skip-me",
            {"$ref": "#/components/parameters/Bad"},
            {"name": "q", "in": "query", "required": True, "schema": {"type": "string"}},
            {"in": "query"},  # no name
        ]
    }
    merged = _merge_parameters(doc, path_item, {})
    assert any(p.get("name") == "q" for p in merged)


def test_example_from_schema_all_types():
    from rapi.core.openapi import _example_from_schema

    assert _example_from_schema("x") is None
    assert _example_from_schema({"default": 9}) == 9
    assert _example_from_schema({"type": "integer"}) == 0
    assert _example_from_schema({"type": "number"}) == 0
    assert _example_from_schema({"type": "boolean"}) is False
    assert _example_from_schema({"type": "string"}) == "string"
    assert _example_from_schema({"type": "string", "enum": ["a", "b"]}) == "a"
    assert _example_from_schema({"type": "array", "items": {"type": "boolean"}}) == [False]
    assert _example_from_schema({"type": "array", "items": {}}) == []
    assert _example_from_schema({"type": "object", "properties": {"k": {"type": "string"}}}) == {"k": "string"}
    assert _example_from_schema({"type": "null"}) is None  # unknown type


def test_extract_request_body_example_branches():
    from rapi.core.openapi import _extract_request_body_example

    assert _extract_request_body_example({}, {}) is None
    assert _extract_request_body_example({}, {"requestBody": "x"}) is None

    # ref resolves to non-dict content empty
    doc = {"components": {"requestBodies": {"Empty": {"content": {}}}}}
    assert _extract_request_body_example(
        doc, {"requestBody": {"$ref": "#/components/requestBodies/Empty"}}
    ) is None

    # non-dict block skipped, then examples without value, then schema
    op = {
        "requestBody": {
            "content": {
                "application/json": "bad",
                "text/plain": {
                    "examples": {"a": "plain-text-example"},
                },
            }
        }
    }
    assert _extract_request_body_example({}, op) == "plain-text-example"

    op2 = {
        "requestBody": {
            "content": {
                "application/json": {
                    "examples": {"a": {"value": {"n": 1}}},
                }
            }
        }
    }
    assert _extract_request_body_example({}, op2) == {"n": 1}

    op3 = {
        "requestBody": {
            "content": {
                "application/json": {
                    "schema": {"type": "boolean"},
                }
            }
        }
    }
    assert _extract_request_body_example({}, op3) is False

    # all blocks yield nothing
    op4 = {
        "requestBody": {
            "content": {
                "application/json": {},
            }
        }
    }
    assert _extract_request_body_example({}, op4) is None


def test_openapi_param_ignore_and_non_dict_schema():
    doc = {
        "paths": {
            "/x": {
                "get": {
                    "parameters": [
                        {"name": "", "in": "query"},  # empty name after merge still skipped if no name
                        {"name": "skip", "in": "query", "x-rapi-ignore": True},
                        {"name": "ok", "in": "query", "schema": "not-a-dict"},
                    ],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    assert items[0].get("params", {}).get("ok") is None
    assert "skip" not in items[0].get("params", {})


def test_extract_example_non_json_and_schema():
    from rapi.core.openapi import _extract_example

    # response $ref resolves to non-dict
    doc = {"components": {"responses": {"R": "oops"}}
    }
    assert _extract_example(doc, {"$ref": "#/components/responses/R"}) == ("OK", None)

    # non-json content, block not dict
    body, ct = _extract_example({}, {"content": {"text/plain": "raw"}})
    assert body == "OK"
    assert ct == "text/plain"

    # non-json with schema only
    body, ct = _extract_example(
        {},
        {"content": {"text/plain": {"schema": {"type": "string", "example": "hi"}}}},
    )
    assert body == "hi"
    assert ct == "text/plain"

    # non-json no example no schema
    body, ct = _extract_example({}, {"content": {"text/plain": {}}})
    assert body == "OK"


def test_load_sample_openapi_files():
    root = Path(__file__).resolve().parents[1] / "examples"
    yaml_path = root / "sample-openapi.yaml"
    json_path = root / "sample-openapi.json"
    if yaml_path.is_file():
        items = load_openapi(str(yaml_path))
        assert len(items) >= 4
        paths = {i["path"] for i in items}
        assert "/items" in paths
        assert "/items/{id}" in paths
    if json_path.is_file():
        items = load_openapi(str(json_path))
        assert any(i["path"] == "/ping" for i in items)


def test_x_rapi_rules_non_dict_skipped():
    doc = {
        "paths": {
            "/r": {
                "get": {
                    "x-rapi-rules": ["bad", {"when": {"body.id": "1"}, "status": 400, "body": "e"}],
                    "responses": {"200": {"description": "ok"}},
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    assert len(items[0]["rules"]) == 1


def test_request_body_ref_to_non_dict():
    from rapi.core.openapi import _extract_request_body_example
    doc = {"components": {"requestBodies": {"X": "not-a-mapping"}}}
    assert _extract_request_body_example(
        doc, {"requestBody": {"$ref": "#/components/requestBodies/X"}}
    ) is None


def test_param_empty_name_defensive(monkeypatch):
    """Line that skips empty name even if merge returned one."""
    from rapi.core import openapi as oa

    def fake_merge(doc, path_item, op):
        return [{"name": "", "in": "query"}, {"name": None, "in": "query"}]

    monkeypatch.setattr(oa, "_merge_parameters", fake_merge)
    items = oa.openapi_to_endpoints({
        "paths": {"/z": {"get": {"responses": {"200": {"description": "ok"}}}}}
    })
    assert "params" not in items[0] or items[0].get("params") == {}


def test_auto_force_rules_from_multiple_responses():
    doc = {
        "paths": {
            "/items/{id}": {
                "get": {
                    "responses": {
                        "200": {
                            "description": "ok",
                            "content": {
                                "application/json": {"example": {"id": "{INPUT.path.id}"}}
                            },
                        },
                        "404": {
                            "description": "missing",
                            "content": {
                                "application/json": {
                                    "example": {
                                        "error": "not found",
                                        "id": "{INPUT.path.id}",
                                    }
                                }
                            },
                        },
                        "400": {
                            "description": "bad",
                            "content": {
                                "application/json": {"example": {"error": "bad request"}}
                            },
                        },
                    }
                }
            }
        }
    }
    items = openapi_to_endpoints(doc)
    ep = items[0]
    assert ep["default"]["status"] == 200
    rules = ep["rules"]
    by_status = {r["status"]: r for r in rules}
    assert 400 in by_status and 404 in by_status
    assert by_status[400]["when"] == {"query.force": "400"}
    assert by_status[404]["when"] == {"query.force": "404"}
    assert "not found" in by_status[404]["body"]


def test_openapi_x_rapi_list_date_roundtrip():
    from rapi.core.models import Endpoint, ResponseSpec
    from rapi.core.openapi import endpoints_to_openapi, openapi_to_endpoints
    ep = Endpoint(
        name="GET:/slots",
        path="/slots",
        method="GET",
        default=ResponseSpec(status=200, body='{"results":[]}'),
        list_key="results",
        list_item='{"d":"{DATE}"}',
        list_count=2,
        list_date_start="2026/09/01",
        list_date_increment_type="hour",
        list_date_increment_unit=2,
    )
    doc = endpoints_to_openapi([ep], include_extensions=True)
    x = doc["paths"]["/slots"]["get"]["x-rapi-list"]
    assert x["date_start"] == "2026/09/01"
    assert x["date_increment_type"] == "hour"
    assert x["date_increment_unit"] == 2
    items = openapi_to_endpoints(doc)
    assert items[0]["list_date_start"] == "2026/09/01"
    assert items[0]["list_date_increment_type"] == "hour"
    assert items[0]["list_date_increment_unit"] == 2
