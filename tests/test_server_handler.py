from __future__ import annotations

import io
import json
from http.client import HTTPConnection
from threading import Thread

import pytest

from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.server import MockHandler, looks_like_json
from http.server import HTTPServer


@pytest.fixture
def http_server():
    endpoints = [
        Endpoint(
            name="GET:/sample",
            path="/sample",
            method="GET",
            default=ResponseSpec(status=200, body='{"q":"{INPUT.query.aaa}"}', content_type="application/json"),
            params={"aaa": r"~\d+"},
        ),
        Endpoint(
            name="POST:/sample",
            path="/sample",
            method="POST",
            default=ResponseSpec(status=200, body='{"id":"{INPUT.body.id}"}'),
            rules=[
                Rule(
                    conditions={"body.id": "004"},
                    response=ResponseSpec(status=400, body='{"error":"bad","id":"{INPUT.body.id}"}'),
                ),
                Rule(
                    conditions={"body.id": "~^9"},
                    response=ResponseSpec(status=503, body='{"error":"unavailable"}'),
                ),
            ],
            expected_body=None,
        ),
        Endpoint(
            name="POST:/strict",
            path="/strict",
            method="POST",
            default=ResponseSpec(body="ok"),
            params={"a": "1"},
            strict_params=True,
            expected_body='{"name":"taro"}',
        ),
        Endpoint(
            name="QUERY:/search",
            path="/search",
            method="QUERY",
            default=ResponseSpec(body='{"ok":true}'),
        ),
    ]
    MockHandler.endpoints = endpoints
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    t = Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield port
    server.shutdown()
    server.server_close()


def _req(port, method, path, body=None, headers=None):
    conn = HTTPConnection("127.0.0.1", port, timeout=2)
    hdrs = headers or {}
    if body is not None and "Content-Type" not in hdrs:
        hdrs["Content-Type"] = "application/json"
    conn.request(method, path, body=body, headers=hdrs)
    resp = conn.getresponse()
    data = resp.read().decode("utf-8")
    status = resp.status
    conn.close()
    return status, data


def test_get_placeholder_and_param(http_server):
    st, data = _req(http_server, "GET", "/sample?aaa=123")
    assert st == 200
    assert json.loads(data)["q"] == "123"


def test_get_param_missing(http_server):
    st, data = _req(http_server, "GET", "/sample")
    assert st == 400
    assert "Missing" in data


def test_get_param_invalid(http_server):
    st, data = _req(http_server, "GET", "/sample?aaa=abc")
    assert st == 400
    assert "Invalid" in data


def test_post_default_and_rules(http_server):
    st, data = _req(http_server, "POST", "/sample", body='{"id":"001"}')
    assert st == 200
    assert json.loads(data)["id"] == "001"

    st, data = _req(http_server, "POST", "/sample", body='{"id":"004"}')
    assert st == 400
    assert json.loads(data).get("id") == "004"

    st, data = _req(http_server, "POST", "/sample", body='{"id":"999"}')
    assert st == 503


def test_404(http_server):
    st, _ = _req(http_server, "GET", "/nope")
    assert st == 404


def test_strict_and_body_validation(http_server):
    st, data = _req(http_server, "POST", "/strict?a=1&b=2", body='{"name":"taro"}')
    assert st == 400
    assert "Unexpected" in data

    st, data = _req(http_server, "POST", "/strict?a=1", body='{"name":"jiro"}')
    assert st == 400
    assert "body" in data.lower() or "match" in data.lower()

    st, data = _req(http_server, "POST", "/strict?a=1", body='{"name":"taro"}')
    assert st == 200
    assert data == "ok"


def test_query_method(http_server):
    st, data = _req(http_server, "QUERY", "/search", body='{"filter":1}')
    assert st == 200
    assert "ok" in data


def test_looks_like_json():
    assert looks_like_json('{"a":1}')
    assert looks_like_json("[1,2]")
    assert not looks_like_json("hello")
    assert not looks_like_json("{bad")
