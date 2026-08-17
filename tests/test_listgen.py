from __future__ import annotations

import json

from rapi.core.listgen import apply_index_placeholders, expand_list_in_body, format_index


def test_format_index():
    assert format_index(1) == "1"
    assert format_index(1, 5) == "00001"
    assert format_index(12, 3) == "012"


def test_apply_index_placeholders():
    assert apply_index_placeholders("TEST_{INDEX}", 3) == "TEST_3"
    assert apply_index_placeholders("TEST_{INDEX:05}", 3) == "TEST_00003"
    assert apply_index_placeholders("{INDEX:03}-{INDEX}", 7) == "007-7"


def test_expand_list():
    envelope = '{"status":"ok","total":"{LIST_COUNT}","results":[]}'
    item = '{"id":"TEST_{INDEX:05}","name":"item-{INDEX:03}"}'
    out = expand_list_in_body(
        envelope,
        list_key="results",
        list_item=item,
        list_count=3,
        list_start=1,
    )
    data = json.loads(out)
    assert data["status"] == "ok"
    assert data["total"] == "3"
    assert len(data["results"]) == 3
    assert data["results"][0]["id"] == "TEST_00001"
    assert data["results"][2]["name"] == "item-003"


def test_expand_nested_key():
    envelope = '{"data":{"items":[]}}'
    out = expand_list_in_body(
        envelope,
        list_key="data.items",
        list_item='{"n":"{INDEX}"}',
        list_count=2,
        list_start=0,
    )
    data = json.loads(out)
    assert data["data"]["items"][0]["n"] == "0"
    assert data["data"]["items"][1]["n"] == "1"


def test_expand_noop_without_config():
    body = '{"a":1}'
    assert expand_list_in_body(body, list_key=None, list_item=None, list_count=None) == body

from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

from rapi.core.models import Endpoint, ResponseSpec
from rapi.core.server import MockHandler


def test_http_list_endpoint():
    MockHandler.endpoints = [
        Endpoint(
            name="GET:/items",
            path="/items",
            method="GET",
            default=ResponseSpec(
                status=200,
                body='{"status":"ok","results":[]}',
                content_type="application/json",
            ),
            list_key="results",
            list_item='{"id":"TEST_{INDEX:05}"}',
            list_count=2,
            list_start=1,
        )
    ]
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/items")
        r = conn.getresponse()
        body = json.loads(r.read().decode())
        assert r.status == 200
        assert body["results"][0]["id"] == "TEST_00001"
        assert body["results"][1]["id"] == "TEST_00002"
        conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_apply_index_in_nested_structures():
    from rapi.core.listgen import _apply_index_in_obj
    obj = {
        "id": "{INDEX:02}",
        "tags": ["a-{INDEX}", {"n": "{INDEX}"}],
        "meta": 1,
    }
    out = _apply_index_in_obj(obj, 4)
    assert out["id"] == "04"
    assert out["tags"][0] == "a-4"
    assert out["tags"][1]["n"] == "4"
    assert out["meta"] == 1


def test_expand_item_as_plain_string():
    out = expand_list_in_body(
        '{"results":[]}',
        list_key="results",
        list_item="item-{INDEX:02}",  # not JSON
        list_count=2,
        list_start=1,
    )
    data = json.loads(out)
    assert data["results"] == ["item-01", "item-02"]


def test_expand_invalid_envelope_json():
    body = "not-json"
    assert expand_list_in_body(
        body, list_key="results", list_item='{"a":1}', list_count=1
    ) == body


def test_expand_envelope_not_dict():
    body = "[1,2,3]"
    assert expand_list_in_body(
        body, list_key="results", list_item='{"a":1}', list_count=1
    ) == body


def test_set_by_path_creates_intermediate():
    out = expand_list_in_body(
        '{"a":1}',
        list_key="data.items",
        list_item='{"x":"{INDEX}"}',
        list_count=1,
        list_start=1,
    )
    data = json.loads(out)
    assert data["data"]["items"][0]["x"] == "1"


def test_set_by_path_when_mid_not_dict():
    from rapi.core.listgen import _set_by_path
    # mid value is scalar → replaced with dict so path can be created
    root = {"data": "scalar"}
    _set_by_path(root, "data.items", [1])
    assert root["data"]["items"] == [1]

def test_set_by_path_single_segment():
    from rapi.core.listgen import _set_by_path
    root = {}
    _set_by_path(root, "results", [1, 2])
    assert root["results"] == [1, 2]
