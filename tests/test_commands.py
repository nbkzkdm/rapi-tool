from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from rapi.commands import host as host_cmd
from rapi.commands import save as save_cmd
from rapi.commands import load as load_cmd
from rapi.commands import status as status_cmd
from rapi.commands import stop as stop_cmd
from rapi.commands import delete as delete_cmd
from rapi.commands import start as start_cmd
from rapi.commands import restart as restart_cmd
from rapi.core.models import Endpoint, ResponseSpec
from rapi.core.store import DefinitionStore


def test_host_basic(tmp_store: DefinitionStore, tmp_path: Path, capsys):
    resp = tmp_path / "r.json"
    resp.write_text('{"ok":true}', encoding="utf-8")
    args = SimpleNamespace(
        path="users",
        method="post",
        response="OK",
        response_file=str(resp),
        status=201,
        content_type=None,
        body=None,
        body_file=None,
        param=["q=1", "x"],
        strict=True,
        name=None,
        when=["body.id=004", "body.id=~^9,query.t=1"],
        rule_status=[400, 503],
        rule_response=['{"e":1}', '{"e":2}'],
        rule_response_file=[],
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get_by_path_method("/users", "POST")
    assert ep is not None
    assert ep.default.status == 201
    assert len(ep.rules) == 2
    assert ep.params["q"] == "1"
    assert ep.strict_params
    out = capsys.readouterr().out
    assert "Registered" in out


def test_host_body_file_and_rule_file(tmp_store: DefinitionStore, tmp_path: Path):
    bodyf = tmp_path / "exp.json"
    bodyf.write_text('{"name":"t"}', encoding="utf-8")
    rf = tmp_path / "err.json"
    rf.write_text('{"error":1}', encoding="utf-8")
    args = SimpleNamespace(
        path="/x",
        method="POST",
        response='{"ok":true}',
        response_file=None,
        status=200,
        content_type=None,
        body=None,
        body_file=str(bodyf),
        param=[],
        strict=False,
        name="custom",
        when=["body.id=1"],
        rule_status=[],
        rule_response=[],
        rule_response_file=[str(rf)],
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get("custom")
    assert ep is not None
    assert ep.expected_body == '{"name":"t"}'
    assert ep.rules[0].response.body == '{"error":1}'


def test_host_missing_files(tmp_store: DefinitionStore):
    args = SimpleNamespace(
        path="/x", method="GET", response="OK", response_file="/no/such",
        status=200, content_type=None, body=None, body_file=None,
        param=[], strict=False, name=None, when=[], rule_status=[],
        rule_response=[], rule_response_file=[],
    )
    with pytest.raises(SystemExit):
        host_cmd.run(args)


def test_save_load(tmp_store: DefinitionStore, tmp_path: Path, monkeypatch):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    out = tmp_path / "out.json"
    save_cmd.run(SimpleNamespace(file=str(out)))
    assert out.is_file()
    tmp_store.clear()
    load_cmd.run(SimpleNamespace(file=str(out), replace=False))
    tmp_store.load()
    assert len(tmp_store.list()) == 1


def test_load_missing(tmp_store: DefinitionStore):
    with pytest.raises(SystemExit):
        load_cmd.run(SimpleNamespace(file="/no/file.json", replace=False))


def test_status(tmp_store: DefinitionStore, capsys, monkeypatch):
    tmp_store.upsert(
        Endpoint(
            name="POST:/a",
            path="/a",
            method="POST",
            rules=[],
            default=ResponseSpec(status=200, body="x"),
        )
    )
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda: None)
    status_cmd.run(SimpleNamespace())
    out = capsys.readouterr().out
    assert "not running" in out
    assert "POST" in out

    monkeypatch.setattr("rapi.commands.status.get_pid", lambda: 123)
    monkeypatch.setattr("rapi.commands.status.get_port", lambda: 9000)
    status_cmd.run(SimpleNamespace())
    out = capsys.readouterr().out
    assert "running" in out
    assert "9000" in out


def test_stop(monkeypatch, capsys):
    monkeypatch.setattr("rapi.commands.stop.get_pid", lambda: None)
    stop_cmd.run(SimpleNamespace())
    assert "Not running" in capsys.readouterr().out

    monkeypatch.setattr("rapi.commands.stop.get_pid", lambda: 1)
    monkeypatch.setattr("rapi.commands.stop.stop_server", lambda: True)
    stop_cmd.run(SimpleNamespace())
    assert "Stopped" in capsys.readouterr().out

    monkeypatch.setattr("rapi.commands.stop.stop_server", lambda: False)
    stop_cmd.run(SimpleNamespace())
    assert "Failed" in capsys.readouterr().out


def test_delete(tmp_store: DefinitionStore, monkeypatch, capsys):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    monkeypatch.setattr("rapi.commands.delete.get_pid", lambda: None)
    delete_cmd.run(SimpleNamespace(name="/a", all=False))
    tmp_store.load()
    assert tmp_store.list() == []

    tmp_store.upsert(Endpoint(name="GET:/b", path="/b", method="GET"))
    delete_cmd.run(SimpleNamespace(name=None, all=True))
    tmp_store.load()
    assert tmp_store.list() == []

    with pytest.raises(SystemExit):
        delete_cmd.run(SimpleNamespace(name=None, all=False))

    delete_cmd.run(SimpleNamespace(name="missing", all=False))
    assert "Not found" in capsys.readouterr().out


def test_start_restart(monkeypatch, tmp_store: DefinitionStore):
    called = {}

    def fake_run_server(host="127.0.0.1", port=8000, background=True):
        called["args"] = (host, port, background)

    monkeypatch.setattr("rapi.commands.start.run_server", fake_run_server)
    start_cmd.run(SimpleNamespace(host="0.0.0.0", port=9000, foreground=True))
    assert called["args"] == ("0.0.0.0", 9000, False)

    monkeypatch.setattr("rapi.commands.restart.get_pid", lambda: 1)
    monkeypatch.setattr("rapi.commands.restart.stop_server", lambda: True)
    monkeypatch.setattr("rapi.commands.restart.run_server", fake_run_server)
    monkeypatch.setattr("rapi.commands.restart.time.sleep", lambda s: None)
    restart_cmd.run(SimpleNamespace(host="127.0.0.1", port=8000))
    assert called["args"][2] is True


def test_parse_when():
    assert host_cmd._parse_when("body.id=004,query.x=1") == {
        "body.id": "004",
        "query.x": "1",
    }
    assert host_cmd._parse_when("onlykey") == {"onlykey": "~.+"}


def test_main_cli(tmp_store: DefinitionStore):
    from rapi.__main__ import main

    with pytest.raises(SystemExit):
        main([])  # missing command

    main(["status"])
