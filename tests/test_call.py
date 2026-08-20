from __future__ import annotations

from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from types import SimpleNamespace

import pytest

from rapi.commands import call as call_cmd


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def do_GET(self):
        body = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        _ = self.rfile.read(n)
        body = b'{"created":true}'
        self.send_response(201)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


@pytest.fixture
def http_port():
    server = HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    yield port
    server.shutdown()
    server.server_close()


def test_format_curl():
    s = call_cmd._format_curl(
        "POST",
        "http://127.0.0.1:8000/api",
        {"Content-Type": "application/json"},
        '{"id":"1"}',
    )
    assert "curl" in s
    assert "-X" in s
    assert "POST" in s
    assert "Content-Type" in s


def test_call_get(http_port, capsys, monkeypatch):
    monkeypatch.setattr(call_cmd, "get_pid", lambda *a, **k: 1)
    monkeypatch.setattr(call_cmd, "get_port", lambda *a, **k: http_port)
    call_cmd.run(
        SimpleNamespace(
            path="/ping",
            method="get",
            group="default",
            host="127.0.0.1",
            port=None,
            query=["x=1"],
            body=None,
            body_file=None,
            header=[],
            timeout=5.0,
            verbose=False,
            show_curl=False,
        )
    )
    out = capsys.readouterr().out
    assert "→ GET" in out
    assert "← 200" in out
    assert "ok" in out


def test_call_post_curl(http_port, capsys):
    call_cmd.run(
        SimpleNamespace(
            path="/api",
            method="post",
            group="default",
            host="127.0.0.1",
            port=http_port,
            query=[],
            body='{"id":"001"}',
            body_file=None,
            header=[],
            timeout=5.0,
            verbose=True,
            show_curl=True,
        )
    )
    out = capsys.readouterr().out
    assert "← 201" in out
    assert "equivalent curl" in out
    assert "curl" in out
    assert "-X" in out


def test_call_not_running(monkeypatch):
    monkeypatch.setattr(call_cmd, "get_pid", lambda *a, **k: None)
    monkeypatch.setattr(call_cmd, "get_port", lambda *a, **k: None)
    with pytest.raises(SystemExit):
        call_cmd.run(
            SimpleNamespace(
                path="/x",
                method="get",
                group="default",
                host="127.0.0.1",
                port=None,
                query=[],
                body=None,
                body_file=None,
                header=[],
                timeout=5.0,
                verbose=False,
                show_curl=False,
            )
        )


def test_call_http_error(http_port, capsys):
    # port open but path will 501 for PUT on our handler - use wrong method
    # Our handler only GET/POST; PUT → 501 from BaseHTTPRequestHandler
    call_cmd.run(
        SimpleNamespace(
            path="/x",
            method="put",
            group="default",
            host="127.0.0.1",
            port=http_port,
            query=[],
            body=None,
            body_file=None,
            header=[],
            timeout=5.0,
            verbose=False,
            show_curl=False,
        )
    )
    out = capsys.readouterr().out
    assert "←" in out


def test_parse_helpers():
    assert call_cmd._parse_query(["a=1", "b"]) == [("a", "1"), ("b", "")]
    assert call_cmd._parse_headers(["X-A: 1"])["X-A"] == "1"
    with pytest.raises(SystemExit):
        call_cmd._parse_headers(["bad"])


def test_looks_like_json_and_build_url():
    assert call_cmd._looks_like_json("not json") is False
    assert call_cmd._looks_like_json("{bad") is False
    assert call_cmd._looks_like_json('{"a":1}') is True
    assert call_cmd._looks_like_json("[1,2]") is True
    assert call_cmd._looks_like_json('{"a":}') is False  # invalid JSON, triggers JSONDecodeError
    url = call_cmd._build_url("127.0.0.1", 9, "no-slash", [])
    assert url.endswith("/no-slash")
    assert "://" in url


def test_call_body_file_plain(tmp_path, http_port, capsys):
    f = tmp_path / "body.txt"
    f.write_text("hello plain", encoding="utf-8")
    call_cmd.run(
        SimpleNamespace(
            path="/api",
            method="post",
            group="default",
            host="127.0.0.1",
            port=http_port,
            query=[],
            body=None,
            body_file=str(f),
            header=[],
            timeout=5.0,
            verbose=True,
            show_curl=False,
        )
    )
    out = capsys.readouterr().out
    assert "← 201" in out
    assert "body:" in out


def test_call_body_file_missing(http_port):
    with pytest.raises(SystemExit):
        call_cmd.run(
            SimpleNamespace(
                path="/api",
                method="post",
                group="default",
                host="127.0.0.1",
                port=http_port,
                query=[],
                body=None,
                body_file="/no/such/file.txt",
                header=[],
                timeout=5.0,
                verbose=False,
                show_curl=False,
            )
        )


def test_call_connection_error_with_curl(capsys):
    with pytest.raises(SystemExit):
        call_cmd.run(
            SimpleNamespace(
                path="/x",
                method="get",
                group="default",
                host="127.0.0.1",
                port=1,  # almost certainly closed
                query=[],
                body=None,
                body_file=None,
                header=[],
                timeout=0.5,
                verbose=False,
                show_curl=True,
            )
        )
    # stderr has error; curl may be on stdout
    captured = capsys.readouterr()
    assert "curl" in captured.out or "connection error" in captured.err.lower() or "error" in captured.err.lower()


def test_call_binary_response(http_port, capsys, monkeypatch):
    class BinHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            body = b"\xff\xfe binary"
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), BinHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        call_cmd.run(
            SimpleNamespace(
                path="/bin",
                method="get",
                group="default",
                host="127.0.0.1",
                port=port,
                query=[],
                body=None,
                body_file=None,
                header=[],
                timeout=5.0,
                verbose=False,
                show_curl=False,
            )
        )
        out = capsys.readouterr().out
        assert "binary" in out.lower()
    finally:
        server.shutdown()
        server.server_close()


def test_register_and_json_decode_branch():
    import argparse
    parser = argparse.ArgumentParser()
    sub = parser.add_subparsers()
    call_cmd.register(sub)
    assert "call" in (sub.choices or {})

    # passes brace check but invalid JSON
    assert call_cmd._looks_like_json("{\"a\":}") is False


def test_http_error_binary_body(capsys):
    class ErrHandler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def do_GET(self):
            body = b"\xff\xfe"
            self.send_response(500)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    server = HTTPServer(("127.0.0.1", 0), ErrHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        call_cmd.run(
            SimpleNamespace(
                path="/e",
                method="get",
                group="default",
                host="127.0.0.1",
                port=port,
                query=[],
                body=None,
                body_file=None,
                header=[],
                timeout=5.0,
                verbose=False,
                show_curl=False,
            )
        )
        out = capsys.readouterr().out
        assert "← 500" in out
        assert "binary" in out.lower()
    finally:
        server.shutdown()
        server.server_close()
