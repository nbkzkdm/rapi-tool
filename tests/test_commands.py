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
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: None)
    status_cmd.run(SimpleNamespace(group=None, verbose=False))
    out = capsys.readouterr().out
    assert "not running" in out
    assert "POST" in out
    assert "=== Server ===" in out

    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: 123)
    monkeypatch.setattr("rapi.commands.status.get_port", lambda *a, **k: 9000)
    status_cmd.run(SimpleNamespace(group=None, verbose=False))
    out = capsys.readouterr().out
    assert "running" in out
    assert "9000" in out


def test_stop(monkeypatch, capsys):
    monkeypatch.setattr("rapi.commands.stop.get_pid", lambda *a, **k: None)
    monkeypatch.setattr("rapi.commands.stop.get_port", lambda *a, **k: None)
    stop_cmd.run(SimpleNamespace(group="default", force=False))
    assert "no running process" in capsys.readouterr().out.lower()

    monkeypatch.setattr("rapi.commands.stop.get_pid", lambda *a, **k: 1)
    monkeypatch.setattr("rapi.commands.stop.stop_server", lambda *a, **k: True)
    stop_cmd.run(SimpleNamespace(group="default", force=False))
    out = capsys.readouterr().out
    assert "stopped" in out.lower()

    monkeypatch.setattr("rapi.commands.stop.stop_server", lambda *a, **k: False)
    stop_cmd.run(SimpleNamespace())
    assert "Failed" in capsys.readouterr().out


def test_delete(tmp_store: DefinitionStore, monkeypatch, capsys):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    monkeypatch.setattr("rapi.commands.delete.get_pid", lambda *a, **k: None)
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

    def fake_run_server(host="127.0.0.1", port=8000, background=True, group="default"):
        called["args"] = (host, port, background, group)

    monkeypatch.setattr("rapi.commands.start.run_server", fake_run_server)
    start_cmd.run(SimpleNamespace(host="0.0.0.0", port=9000, foreground=True, group="default"))
    assert called["args"] == ("0.0.0.0", 9000, False, "default")

    monkeypatch.setattr("rapi.commands.restart.get_pid", lambda *a, **k: 1)
    monkeypatch.setattr("rapi.commands.restart.stop_server", lambda *a, **k: True)
    monkeypatch.setattr("rapi.commands.restart.run_server", fake_run_server)
    monkeypatch.setattr("rapi.commands.restart.time.sleep", lambda s: None)
    restart_cmd.run(SimpleNamespace(host="127.0.0.1", port=8000, group="default"))
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


def test_host_list_validation_errors(tmp_store):
    def base(**kw):
        d = dict(
            path="/items", method="GET", response='{"results":[]}', response_file=None,
            status=200, content_type=None, body=None, body_file=None,
            param=[], strict=False, name=None, when=[], rule_status=[],
            rule_response=[], rule_response_file=[],
            list_item=None, list_item_file=None, list_start=1,
            list_key=None, list_count=None,
        )
        d.update(kw)
        return SimpleNamespace(**d)
    # list_key without item
    with pytest.raises(SystemExit):
        host_cmd.run(base(list_key="results", list_count=3))
    # list_key without count
    with pytest.raises(SystemExit):
        host_cmd.run(base(list_key="results", list_item='{"a":1}'))
    # missing list item file
    with pytest.raises(SystemExit):
        host_cmd.run(base(
            list_key="results", list_count=2,
            list_item_file="/no/such/item.json",
        ))


def test_host_list_item_file_ok(tmp_store, tmp_path, capsys):
    item = tmp_path / "item.json"
    item.write_text('{"id":"{INDEX:03}"}', encoding="utf-8")
    args = SimpleNamespace(
        path="/items", method="GET", response='{"status":"ok","results":[]}',
        response_file=None, status=200, content_type=None, body=None, body_file=None,
        param=[], strict=False, name=None, when=[], rule_status=[],
        rule_response=[], rule_response_file=[],
        list_key="results", list_item=None, list_item_file=str(item),
        list_count=2, list_start=1,
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get_by_path_method("/items", "GET")
    assert ep is not None
    assert ep.list_key == "results"
    assert ep.list_count == 2
    assert "list" in capsys.readouterr().out


def test_load_group_override_list(tmp_store: DefinitionStore, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rapi.commands.load.get_pid", lambda *a, **k: None)
    f = tmp_path / "eps.json"
    f.write_text(json.dumps([
        {"path": "/g1", "method": "GET", "default": {"status": 200, "body": "x"}},
        "skip-me",
    ]), encoding="utf-8")
    load_cmd.run(SimpleNamespace(file=str(f), fmt="json", replace=True, group="team-a"))
    tmp_store.load()
    eps = [e for e in tmp_store.list() if e.path == "/g1"]
    assert eps and eps[0].group == "team-a"


def test_load_group_override_wrapped(tmp_store: DefinitionStore, tmp_path: Path, monkeypatch):
    monkeypatch.setattr("rapi.commands.load.get_pid", lambda *a, **k: None)
    f = tmp_path / "eps2.json"
    f.write_text(json.dumps({
        "endpoints": [
            {"path": "/g2", "method": "POST", "default": {"status": 201, "body": "y"}},
            None,
        ]
    }), encoding="utf-8")
    load_cmd.run(SimpleNamespace(file=str(f), fmt="json", replace=False, group="team-b"))
    tmp_store.load()
    eps = [e for e in tmp_store.list() if e.path == "/g2"]
    assert eps and eps[0].group == "team-b"


def test_status_filter_group(tmp_store: DefinitionStore, monkeypatch, capsys):
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET", group="only-me"))
    tmp_store.upsert(Endpoint(name="GET:/b", path="/b", method="GET", group="other"))
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: None)
    status_cmd.run(SimpleNamespace(group="only-me", verbose=False))
    out = capsys.readouterr().out
    assert "[only-me]" in out
    assert "/a" in out


def test_stop_force_and_stale(tmp_path, monkeypatch, capsys):
    from rapi.core import server as srv

    state = tmp_path / "st"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)

    # stale files, no live pid
    g = state / "groups" / "default"
    g.mkdir(parents=True)
    (g / "rapi.pid").write_text("99999999", encoding="utf-8")
    (g / "rapi.port").write_text("8000", encoding="utf-8")

    stop_cmd.run(SimpleNamespace(group="default", force=False))
    out = capsys.readouterr().out
    assert "no running process" in out.lower() or "No running" in out or "has no running" in out
    assert "ss -ltnp" in out
    assert "lsof" in out
    assert not (g / "rapi.pid").exists()

    # force with live-looking pid (mock get_pid + stop)
    monkeypatch.setattr("rapi.commands.stop.get_pid", lambda *a, **k: 1234)
    monkeypatch.setattr("rapi.commands.stop.get_port", lambda *a, **k: 8000)
    monkeypatch.setattr("rapi.commands.stop.stop_server", lambda *a, **k: True)
    stop_cmd.run(SimpleNamespace(group="default", force=True))
    out = capsys.readouterr().out
    assert "1234" in out
    assert "force" in out.lower() or "SIGKILL" in out or "stopped" in out.lower()


def test_status_verbose_details(tmp_store: DefinitionStore, monkeypatch, capsys):
    from rapi.core.models import Rule
    tmp_store.upsert(
        Endpoint(
            name="GET:/slow",
            path="/slow",
            method="GET",
            group="default",
            default=ResponseSpec(status=200, body='{"ok":true}', delay_ms=1500),
            params={"q": "1"},
            strict_params=True,
            list_key="results",
            list_item="{}",
            list_count=3,
            rules=[
                Rule(
                    conditions={"query.q": "x"},
                    response=ResponseSpec(status=400, body="bad", delay_ms=100),
                )
            ],
        )
    )
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: None)
    status_cmd.run(SimpleNamespace(group="default", verbose=True))
    out = capsys.readouterr().out
    assert "delay=1500ms" in out
    assert "rules=1" in out
    assert "query:" in out
    assert "list key=results" in out
    assert "response:" in out


def test_status_coverage_edges(tmp_store: DefinitionStore, tmp_path, monkeypatch, capsys):
    from rapi.core import server as srv
    from rapi.core.models import Rule

    # known groups from state dir
    state = tmp_path / "st"
    (state / "groups" / "ghost").mkdir(parents=True)
    monkeypatch.setattr("rapi.commands.status.state_dir", lambda: state)

    # empty store → default group still listed via ghost dir + empty
    tmp_store.clear()
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: None)
    monkeypatch.setattr("rapi.commands.status.get_port", lambda g: 8123 if g == "ghost" else None)
    status_cmd.run(SimpleNamespace(group=None, verbose=False))
    out = capsys.readouterr().out
    assert "ghost" in out
    assert "stale" in out or "8123" in out

    # filter group with zero defs
    status_cmd.run(SimpleNamespace(group="empty-only", verbose=False))
    out = capsys.readouterr().out
    assert "defs   : 0" in out or "0" in out

    # body-check + long fields + verbose truncations
    long_body = "B" * 120
    long_expect = "E" * 120
    long_rule = "R" * 120
    tmp_store.upsert(
        Endpoint(
            name="POST:/cov",
            path="/cov",
            method="POST",
            group="default",
            default=ResponseSpec(status=200, body=long_body, delay_ms=0),
            expected_body=long_expect,
            params={"flag": None},
            strict_params=True,
            rules=[
                Rule(conditions={"body.x": "1"}, response=ResponseSpec(status=400, body=long_rule, delay_ms=50)),
            ],
        )
    )
    status_cmd.run(SimpleNamespace(group="default", verbose=True))
    out = capsys.readouterr().out
    assert "body-check" in out
    assert "strict" in out
    assert "expect body:" in out
    assert "..." in out
    assert "delay=50ms" in out


def test_fmt_params_and_known_groups_empty(monkeypatch, tmp_path):
    from rapi.commands.status import _fmt_params, _known_groups
    from rapi.core.store import DefinitionStore

    assert _fmt_params({}) == ""
    assert _fmt_params({"a": None, "b": "1"}) == "a, b=1"

    state = tmp_path / "empty"
    state.mkdir()
    monkeypatch.setattr("rapi.commands.status.state_dir", lambda: state)
    store = DefinitionStore(path=tmp_path / "d.json")
    store.clear()
    # no groups dir contents, no endpoints
    gs = _known_groups(store)
    assert "default" in gs
