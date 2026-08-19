from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

from rapi.core.models import Endpoint, ResponseSpec
from rapi.core.server import MockHandler


def _serve(endpoints):
    MockHandler.endpoints = endpoints
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    return server, port


def test_request_log_success_contains_status_and_duration():
    server, port = _serve([
        Endpoint(
            name="GET:/ping",
            path="/ping",
            method="GET",
            default=ResponseSpec(status=200, body='{"ok":true}'),
        )
    ])
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            # Handler prints to process stdout; capture via connection only verifies response.
            # Call handle_request logic by real HTTP; log goes to server thread stdout.
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request("GET", "/ping?x=1")
            r = conn.getresponse()
            assert r.status == 200
            r.read()
            conn.close()
    finally:
        server.shutdown()
        server.server_close()

    # Direct unit test of _log_request formatting
    h = MockHandler.__new__(MockHandler)
    h.command = "GET"
    h.path = "/ping?x=1"
    out = io.StringIO()
    with redirect_stdout(out):
        h._log_request(
            status=200,
            duration_ms=12.3,
            endpoint="GET:/ping",
            query={"x": ["1"]},
            body_text="",
            path_params=None,
        )
    text = out.getvalue()
    assert "REQ  GET /ping?x=1" in text
    assert "status=200" in text
    assert "duration=12ms" in text
    assert "endpoint=GET:/ping" in text
    assert "query=" in text


def test_request_log_includes_body_and_path_params():
    h = MockHandler.__new__(MockHandler)
    h.command = "POST"
    h.path = "/users/42"
    out = io.StringIO()
    with redirect_stdout(out):
        h._log_request(
            status=201,
            duration_ms=5,
            endpoint="POST:/users/{id}",
            query={},
            body_text='{"name":"a"}',
            path_params={"id": "42"},
            note=None,
        )
    text = out.getvalue()
    assert "path_params={'id': '42'}" in text
    assert 'body={"name":"a"}' in text
    assert "status=201" in text


def test_request_log_binary_and_truncate():
    h = MockHandler.__new__(MockHandler)
    h.command = "POST"
    h.path = "/bin"
    out = io.StringIO()
    with redirect_stdout(out):
        h._log_request(status=400, duration_ms=1, body_text=None, note="binary body")
    assert "body=<binary>" in out.getvalue()

    out = io.StringIO()
    long_body = "x" * 600
    with redirect_stdout(out):
        h._log_request(status=200, duration_ms=1, body_text=long_body)
    assert "truncated" in out.getvalue()


def test_http_404_logs_request(monkeypatch):
    logs = []
    real = MockHandler._log_request

    def wrap(self, **kwargs):
        logs.append(kwargs)
        return real(self, **kwargs)

    monkeypatch.setattr(MockHandler, "_log_request", wrap)
    server, port = _serve([])
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("GET", "/missing")
        r = conn.getresponse()
        assert r.status == 404
        r.read()
        conn.close()
    finally:
        server.shutdown()
        server.server_close()
    assert logs and logs[0]["status"] == 404
