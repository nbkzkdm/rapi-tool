from __future__ import annotations

import json
import time
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from rapi.commands import host as host_cmd
from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.server import MockHandler
from rapi.core.store import DefinitionStore


def test_response_spec_delay_roundtrip():
    r = ResponseSpec(status=200, body="ok", delay_ms=1500)
    d = r.to_dict()
    assert d["delay_ms"] == 1500
    r2 = ResponseSpec.from_dict(d)
    assert r2.delay_ms == 1500
    assert ResponseSpec.from_dict({}).delay_ms == 0


def test_rule_delay_in_to_dict():
    rule = Rule(
        conditions={"body.id": "1"},
        response=ResponseSpec(status=400, body="e", delay_ms=200),
    )
    d = rule.to_dict()
    assert d["delay_ms"] == 200
    r2 = Rule.from_dict(d)
    assert r2.response.delay_ms == 200


def test_host_delay_args(tmp_store: DefinitionStore, capsys):
    args = SimpleNamespace(
        path="/slow", method="get", response='{"ok":true}', response_file=None,
        status=200, content_type=None, delay=250, body=None, body_file=None,
        param=[], strict=False, name=None, group="default",
        when=[], rule_status=[], rule_response=[], rule_response_file=[], rule_delay=[],
        list_item=None, list_item_file=None, list_key=None, list_count=None, list_start=1,
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get_by_path_method("/slow", "GET")
    assert ep is not None
    assert ep.default.delay_ms == 250
    assert "250" in capsys.readouterr().out


def test_host_rule_delay(tmp_store: DefinitionStore):
    args = SimpleNamespace(
        path="/x", method="post", response='{"ok":true}', response_file=None,
        status=200, content_type=None, delay=0, body=None, body_file=None,
        param=[], strict=False, name=None, group="default",
        when=["body.id=1"], rule_status=[503], rule_response=['{"e":1}'],
        rule_response_file=[], rule_delay=[800],
        list_item=None, list_item_file=None, list_key=None, list_count=None, list_start=1,
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get_by_path_method("/x", "POST")
    assert ep.rules[0].response.delay_ms == 800


def test_http_delay_is_applied(monkeypatch):
    slept = []

    def fake_sleep(sec):
        slept.append(sec)

    monkeypatch.setattr(time, "sleep", fake_sleep)

    MockHandler.endpoints = [
        Endpoint(
            name="GET:/slow",
            path="/slow",
            method="GET",
            default=ResponseSpec(status=200, body='{"ok":true}', delay_ms=500),
        )
    ]
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/slow")
        r = conn.getresponse()
        assert r.status == 200
        assert json.loads(r.read().decode())["ok"] is True
        conn.close()
    finally:
        server.shutdown()
        server.server_close()

    assert slept and abs(slept[0] - 0.5) < 1e-9


def test_http_no_delay_skips_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(time, "sleep", lambda s: slept.append(s))
    MockHandler.endpoints = [
        Endpoint(
            name="GET:/fast",
            path="/fast",
            method="GET",
            default=ResponseSpec(status=200, body="ok", delay_ms=0),
        )
    ]
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/fast")
        r = conn.getresponse()
        assert r.status == 200
        r.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
    assert slept == []
