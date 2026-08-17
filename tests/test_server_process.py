from __future__ import annotations

import os
from pathlib import Path

import pytest

from rapi.core import server as srv
from rapi.core.models import Endpoint, ResponseSpec
from rapi.core.store import DefinitionStore


def test_get_pid_port_stop(tmp_path: Path, monkeypatch):
    state = tmp_path / "s"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)

    assert srv.get_pid() is None
    assert srv.get_port() is None
    assert not srv.is_running()
    assert not srv.stop_server()

    g = state / "groups" / "default"
    g.mkdir(parents=True, exist_ok=True)
    # invalid pid file
    (g / "rapi.pid").write_text("not-a-pid", encoding="utf-8")
    assert srv.get_pid() is None

    (g / "rapi.port").write_text("abc", encoding="utf-8")
    assert srv.get_port() is None

    g = state / "groups" / "default"
    g.mkdir(parents=True, exist_ok=True)
    (g / "rapi.port").write_text("8080", encoding="utf-8")
    assert srv.get_port() == 8080

    # dead pid
    (g / "rapi.pid").write_text("99999999", encoding="utf-8")
    assert srv.get_pid() is None  # cleaned up


def test_run_server_no_endpoints(tmp_store: DefinitionStore, monkeypatch):
    monkeypatch.setattr(srv, "DefinitionStore", lambda: tmp_store)
    with pytest.raises(SystemExit):
        srv.run_server(background=False)


def test_run_server_already_running(tmp_store: DefinitionStore, monkeypatch):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    monkeypatch.setattr(srv, "DefinitionStore", lambda: tmp_store)
    monkeypatch.setattr(srv, "is_running", lambda *a, **k: True)
    with pytest.raises(SystemExit):
        srv.run_server(background=True)


def test_run_server_foreground(tmp_store: DefinitionStore, monkeypatch):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET", default=ResponseSpec(body="x")))
    monkeypatch.setattr(srv, "DefinitionStore", lambda: tmp_store)

    class FakeServer:
        def __init__(self, addr, handler):
            self.addr = addr
            self.handler = handler

        def serve_forever(self):
            raise KeyboardInterrupt()

        def server_close(self):
            pass

    monkeypatch.setattr(srv, "HTTPServer", FakeServer)
    # should return without error
    srv.run_server(host="127.0.0.1", port=8999, background=False)


def test_run_server_background_parent(tmp_store: DefinitionStore, monkeypatch, tmp_path: Path, capsys):
    state = tmp_path / "st"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)
    monkeypatch.setattr(srv, "DefinitionStore", lambda: tmp_store)
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))

    monkeypatch.setattr(srv, "is_running", lambda *a, **k: False)
    monkeypatch.setattr(os, "fork", lambda *a, **k: 12345)  # parent path

    srv.run_server(host="127.0.0.1", port=7777, background=True)
    out = capsys.readouterr().out
    assert "Started" in out
    g = state / "groups" / "default"
    assert (g / "rapi.pid").read_text() == "12345"
    assert (g / "rapi.port").read_text() == "7777"
    log = (g / "rapi.log").read_text()
    assert "port=7777" in log
