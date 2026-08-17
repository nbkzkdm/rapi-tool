from __future__ import annotations

import json
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.pathmatch import is_template, match_path, path_param_names
from rapi.core.placeholders import apply_placeholders, build_input_context
from rapi.core.matching import match_conditions
from rapi.core.server import MockHandler


def test_match_exact():
    assert match_path("/users", "/users") == {}
    assert match_path("/users", "/users/1") is None


def test_match_template():
    assert match_path("/users/{id}", "/users/123") == {"id": "123"}
    assert match_path("/users/{id}/orders/{oid}", "/users/1/orders/9") == {
        "id": "1",
        "oid": "9",
    }
    assert match_path("/users/{id}", "/users/1/extra") is None
    assert is_template("/users/{id}")
    assert path_param_names("/a/{b}/c/{d}") == ["b", "d"]


def test_placeholder_path_param():
    ctx = build_input_context(
        "GET", "/users/42", {}, {}, None, path_params={"id": "42"}
    )
    assert apply_placeholders("{INPUT.path}", ctx) == "/users/42"
    assert apply_placeholders("ID={INPUT.path.id}", ctx) == "ID=42"


def test_condition_path_param():
    assert match_conditions(
        {"path.id": "42"}, "GET", "/users/42", {}, {}, None, path_params={"id": "42"}
    )
    assert not match_conditions(
        {"path.id": "99"}, "GET", "/users/42", {}, {}, None, path_params={"id": "42"}
    )


def test_http_path_param():
    MockHandler.endpoints = [
        Endpoint(
            name="GET:/users/{id}",
            path="/users/{id}",
            method="GET",
            default=ResponseSpec(
                status=200,
                body='{"id":"{INPUT.path.id}"}',
                content_type="application/json",
            ),
            rules=[
                Rule(
                    conditions={"path.id": "000"},
                    response=ResponseSpec(status=404, body='{"error":"not found"}'),
                )
            ],
        )
    ]
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/users/42")
        r = conn.getresponse()
        body = json.loads(r.read().decode())
        assert r.status == 200
        assert body["id"] == "42"
        conn.close()

        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/users/000")
        r = conn.getresponse()
        assert r.status == 404
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_path_param_missing_in_condition():
    # path.id requested but no path_params
    assert not match_conditions(
        {"path.id": "1"}, "GET", "/users/1", {}, {}, None, path_params=None
    )
    assert not match_conditions(
        {"path.id": "1"}, "GET", "/users/1", {}, {}, None, path_params={}
    )


def test_template_regex_error(monkeypatch):
    import rapi.core.pathmatch as pm
    real = pm.re.compile

    def boom(pat):
        raise pm.re.error("forced")

    monkeypatch.setattr(pm.re, "compile", boom)
    assert match_path("/users/{id}", "/users/1") is None
