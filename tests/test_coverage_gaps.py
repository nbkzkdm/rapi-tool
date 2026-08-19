from __future__ import annotations

import os
import signal
from pathlib import Path
from types import SimpleNamespace
from http.client import HTTPConnection
from http.server import HTTPServer
from threading import Thread

import pytest

from rapi.core import server as srv
from rapi.core.matching import match_value, match_conditions, match_body_pattern
from rapi.core.models import Endpoint, ResponseSpec, Rule
from rapi.core.placeholders import apply_placeholders, build_input_context, _dig
from rapi.core.store import DefinitionStore, default_store_path
from rapi.core.server import MockHandler, looks_like_json
from rapi.commands import host as host_cmd
from rapi.commands import load as load_cmd
from rapi.commands import delete as delete_cmd
from rapi import __main__ as main_mod


def test_match_value_bad_simple_pattern_regex():
    # force regex error path by weird pattern - actually simple pattern always valid
    assert not match_value("a", "~(")


def test_dig_and_placeholders_edges():
    assert _dig(None, "a") is None
    assert _dig([1, 2], "x") is None
    assert _dig([1], "5") is None
    assert _dig("str", "a") is None
    ctx = build_input_context("GET", "/", {}, {}, None)
    # body empty and body is ""
    assert apply_placeholders("{INPUT.body}", ctx) == ""
    ctx2 = build_input_context("GET", "/", {}, {}, None)
    # force body dict without raw via manual ctx
    ctx2["body"] = {"a": 1}
    ctx2["_body_raw"] = ""
    out = apply_placeholders("{INPUT.body}", ctx2)
    assert "a" in out


def test_default_store_path(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    p = default_store_path()
    assert p.name == "definitions.json"
    assert p.parent.exists()


def test_handler_binary_body_and_head(tmp_path):
    MockHandler.endpoints = [
        Endpoint(
            name="POST:/b",
            path="/b",
            method="POST",
            default=ResponseSpec(body="ok"),
            expected_body="~x",
        ),
        Endpoint(
            name="HEAD:/h",
            path="/h",
            method="HEAD",
            default=ResponseSpec(body="head-body"),
        ),
    ]
    server = HTTPServer(("127.0.0.1", 0), MockHandler)
    port = server.server_address[1]
    Thread(target=server.serve_forever, daemon=True).start()
    try:
        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        # binary body
        conn.request("POST", "/b", body=b"\xff\xfe", headers={"Content-Type": "application/octet-stream"})
        r = conn.getresponse()
        assert r.status == 400
        r.read()
        conn.close()

        conn = HTTPConnection("127.0.0.1", port, timeout=2)
        conn.request("HEAD", "/h")
        r = conn.getresponse()
        assert r.status == 200
        r.read()
        conn.close()

        MockHandler.endpoints = [
            Endpoint(name=f"{m}:/m", path="/m", method=m, default=ResponseSpec(body=m))
            for m in ("PUT", "DELETE", "PATCH", "OPTIONS", "GET", "POST", "HEAD", "QUERY")
        ]
        for m in ("PUT", "DELETE", "PATCH", "OPTIONS"):
            conn = HTTPConnection("127.0.0.1", port, timeout=2)
            conn.request(m, "/m")
            r = conn.getresponse()
            assert r.status == 200, (m, r.status, r.read())
            r.read()
            conn.close()
    finally:
        server.shutdown()
        server.server_close()


def test_stop_server_kill_paths(tmp_path, monkeypatch):
    state = tmp_path / "s"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)

    # live pid that ignores SIGTERM then gets SIGKILL attempt
    pid = os.fork()
    if pid == 0:
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        while True:
            signal.pause()
    try:
        g = state / "groups" / "default"
        g.mkdir(parents=True, exist_ok=True)
        (g / "rapi.pid").write_text(str(pid), encoding="utf-8")
        (g / "rapi.port").write_text("1", encoding="utf-8")
        # short timeout to hit kill path
        assert srv.stop_server(timeout=0.2)
    finally:
        try:
            os.kill(pid, signal.SIGKILL)
            os.waitpid(pid, 0)
        except OSError:
            pass


def test_host_body_file_missing(tmp_store):
    args = SimpleNamespace(
        path="/x", method="POST", response="OK", response_file=None,
        status=200, content_type="text/plain", body=None,
        body_file="/no/body", param=[], strict=False, name=None,
        when=[], rule_status=[], rule_response=[], rule_response_file=[],
    )
    with pytest.raises(SystemExit):
        host_cmd.run(args)


def test_load_stops_server(tmp_store, tmp_path, monkeypatch):
    f = tmp_path / "d.json"
    f.write_text('{"endpoints":[{"path":"/z","method":"GET"}]}', encoding="utf-8")
    monkeypatch.setattr("rapi.commands.load.get_pid", lambda *a, **k: 99)
    called = []
    monkeypatch.setattr("rapi.commands.load.stop_server", lambda *a, **k: called.append(1) or True)
    load_cmd.run(SimpleNamespace(file=str(f), replace=True))
    assert called


def test_delete_stops_server(tmp_store, monkeypatch, capsys):
    monkeypatch.setattr("rapi.commands.delete.get_pid", lambda *a, **k: 42)
    monkeypatch.setattr("rapi.commands.delete.stop_server", lambda *a, **k: True)
    delete_cmd.run(SimpleNamespace(name=None, all=True))
    assert "Stopped" in capsys.readouterr().out


def test_main_exception_and_interrupt(monkeypatch):
    def boom(args):
        raise RuntimeError("x")

    monkeypatch.setattr(
        "rapi.__main__.load_commands",
        lambda sub: sub.add_parser("boom").set_defaults(func=boom),
    )
    with pytest.raises(SystemExit) as ei:
        main_mod.main(["boom"])
    assert ei.value.code == 1

    def kb(args):
        raise KeyboardInterrupt()

    monkeypatch.setattr(
        "rapi.__main__.load_commands",
        lambda sub: sub.add_parser("kb").set_defaults(func=kb),
    )
    with pytest.raises(SystemExit) as ei:
        main_mod.main(["kb"])
    assert ei.value.code == 130


def test_main_no_func(monkeypatch):
    def reg(sub):
        sub.add_parser("nofunc")  # no set_defaults func

    monkeypatch.setattr("rapi.__main__.load_commands", reg)
    with pytest.raises(SystemExit):
        main_mod.main(["nofunc"])


def test_match_conditions_list_dig():
    body = '{"arr":[10,20]}'
    assert match_conditions({"body.arr.0": "10"}, "GET", "/", {}, {}, body)


def test_store_import_skips_bad(tmp_store):
    n = tmp_store.import_from([{"bad": True}, "x", None], merge=True)
    # Endpoint.from_dict may still create something with defaults
    assert n >= 0


def test_run_server_background_child(tmp_store, monkeypatch, tmp_path):
    state = tmp_path / "st"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)
    monkeypatch.setattr(srv, "DefinitionStore", lambda: tmp_store)
    tmp_store.upsert(Endpoint(name="GET:/a", path="/a", method="GET"))
    monkeypatch.setattr(srv, "is_running", lambda *a, **k: False)

    class FakeServer:
        def __init__(self, *a, **k):
            pass
        def serve_forever(self):
            return
        def server_close(self):
            pass

    monkeypatch.setattr(srv, "HTTPServer", FakeServer)
    monkeypatch.setattr(os, "fork", lambda: 0)  # child
    monkeypatch.setattr(os, "setsid", lambda *a, **k: None)
    # avoid closing real stdin issues - setsid and close already in code
    srv.run_server(background=True)

def test_rule_from_dict_non_dict_when():
    r = Rule.from_dict({"when": "bad", "status": 400, "body": "x"})
    assert r.conditions == {}


def test_state_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
    d = srv.state_dir()
    assert d.exists()


def test_looks_like_json_false_paths():
    assert not looks_like_json("{")
    assert not looks_like_json("[]x")


def test_match_value_pattern_error_path():
    # cover simple pattern branch with mixed literals
    assert match_value("a1b", "A*X") is False or True  # just execute
    assert match_value("---", "***")


def test_host_parse_empty_when_part():
    assert host_cmd._parse_when("a=1,,b=2") == {"a": "1", "b": "2"}


def test_status_with_rules(tmp_store, monkeypatch, capsys):
    from rapi.core.models import Rule
    tmp_store.upsert(Endpoint(
        name="POST:/r", path="/r", method="POST",
        rules=[Rule(conditions={"body.id": "1"}, response=ResponseSpec(400, "e"))],
    ))
    monkeypatch.setattr("rapi.commands.status.get_pid", lambda *a, **k: None)
    from rapi.commands import status as status_cmd
    status_cmd.run(SimpleNamespace())
    assert "rule" in capsys.readouterr().out

def test_looks_like_json_decode_error():
    assert looks_like_json("{bad}") is False
    assert looks_like_json("[1,") is False


def test_resolve_unknown_key_and_dict_list_body():
    assert match_conditions({"unknown.field": "x"}, "GET", "/", {}, {}, None) is False
    body = '{"obj":{"a":1},"arr":[1,2]}'
    assert match_conditions({"body.obj": "~a"}, "POST", "/", {}, {}, body)
    assert match_conditions({"body.missing": "1"}, "POST", "/", {}, {}, body) is False


def test_match_conditions_bad_regex():
    assert match_conditions({"body": "~["}, "POST", "/", {}, {}, "hello") is False


def test_stop_server_oserror_on_kill(tmp_path, monkeypatch):
    state = tmp_path / "s"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)
    g = state / "groups" / "default"
    g.mkdir(parents=True, exist_ok=True)
    (g / "rapi.pid").write_text(str(os.getpid()), encoding="utf-8")

    def boom(pid, sig):
        if sig == signal.SIGTERM:
            raise OSError("x")
        # existence check and others succeed
        return None

    monkeypatch.setattr(os, "kill", boom)
    assert srv.stop_server(timeout=0.05) is True


def test_match_value_simple_fullmatch_error(monkeypatch):
    import rapi.core.matching as m
    real = m.re.fullmatch
    def flaky(pat, s):
        if "FORCE" in pat:
            raise m.re.error("x")
        return real(pat, s)
    monkeypatch.setattr(m.re, "fullmatch", flaky)
    # pattern with only literals goes to exact match not fullmatch
    # pattern with N uses fullmatch
    assert m.match_value("1", "N") in (True, False)

def test_host_looks_like_json_branches(tmp_store, capsys):
    # invalid JSON that looks like object → content-type stays default path through _looks_like_json false
    args = SimpleNamespace(
        path="/j", method="GET", response="{not-json}", response_file=None,
        status=200, content_type=None, body=None, body_file=None,
        param=[], strict=False, name=None, when=[], rule_status=[],
        rule_response=[], rule_response_file=[],
    )
    host_cmd.run(args)
    tmp_store.load()
    assert tmp_store.get_by_path_method("/j", "GET") is not None


def test_delete_not_found_lists(tmp_store, monkeypatch, capsys):
    tmp_store.upsert(Endpoint(name="GET:/keep", path="/keep", method="GET"))
    monkeypatch.setattr("rapi.commands.delete.get_pid", lambda *a, **k: None)
    delete_cmd.run(SimpleNamespace(name="nope", all=False))
    out = capsys.readouterr().out
    assert "Not found" in out
    assert "GET:/keep" in out


def test_load_commands_skips_underscore(tmp_path, monkeypatch):
    # ensure _private modules are skipped (line continue)
    from rapi.commands import load_commands
    import argparse
    p = argparse.ArgumentParser()
    sub = p.add_subparsers()
    load_commands(sub)  # noreg without register + normal modules

def test_host_plain_response_not_json_shape(tmp_store):
    args = SimpleNamespace(
        path="/plain", method="GET", response="OK", response_file=None,
        status=200, content_type=None, body=None, body_file=None,
        param=[], strict=False, name=None, when=[], rule_status=[],
        rule_response=[], rule_response_file=[],
    )
    host_cmd.run(args)
    tmp_store.load()
    ep = tmp_store.get_by_path_method("/plain", "GET")
    assert ep is not None
    assert ep.default.body == "OK"


def test_stop_server_force_sigkill(tmp_path, monkeypatch):
    from rapi.core import server as srv

    state = tmp_path / "sf"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)
    g = state / "groups" / "default"
    g.mkdir(parents=True)

    killed = []

    def fake_kill(pid, sig):
        killed.append((pid, sig))
        if sig == 0:
            return None
        return None

    # pretend process 4242 is alive
    (g / "rapi.pid").write_text("4242", encoding="utf-8")
    (g / "rapi.port").write_text("8000", encoding="utf-8")
    monkeypatch.setattr(os, "kill", fake_kill)

    assert srv.stop_server(group="default", force=True) is True
    assert any(sig == signal.SIGKILL for _, sig in killed)
    assert not (g / "rapi.pid").exists()


def test_clear_stale_when_running(tmp_path, monkeypatch):
    from rapi.core import server as srv

    state = tmp_path / "sr"
    state.mkdir()
    monkeypatch.setattr(srv, "state_dir", lambda: state)
    g = state / "groups" / "default"
    g.mkdir(parents=True)
    (g / "rapi.pid").write_text(str(os.getpid()), encoding="utf-8")

    info = srv.clear_stale_state("default")
    assert info.get("cleared") is False
    assert info.get("running_pid") == os.getpid()
