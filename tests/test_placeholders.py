from __future__ import annotations

from rapi.core.placeholders import apply_placeholders, build_input_context


def _ctx(**kwargs):
    return build_input_context(
        method=kwargs.get("method", "POST"),
        path=kwargs.get("path", "/sample"),
        query=kwargs.get("query", {}),
        headers=kwargs.get("headers", {}),
        body_text=kwargs.get("body_text"),
    )


class TestPlaceholders:
    def test_method_path(self):
        ctx = _ctx(method="GET", path="/api")
        assert apply_placeholders("{INPUT.method}", ctx) == "GET"
        assert apply_placeholders("{INPUT.path}", ctx) == "/api"

    def test_query(self):
        ctx = _ctx(query={"aaa": ["123"]})
        assert apply_placeholders("q={INPUT.query.aaa}", ctx) == "q=123"
        assert apply_placeholders("{INPUT.query.missing}", ctx) == ""

    def test_body_json_field(self):
        ctx = _ctx(body_text='{"id":"004","user":{"name":"taro"}}')
        assert apply_placeholders("Test{INPUT.body.id}", ctx) == "Test004"
        assert apply_placeholders("{INPUT.body.user.name}", ctx) == "taro"

    def test_body_raw(self):
        ctx = _ctx(body_text='{"a":1}')
        assert apply_placeholders("{INPUT.body}", ctx) == '{"a":1}'

    def test_body_raw_when_not_json(self):
        ctx = _ctx(body_text="plain")
        assert apply_placeholders("{INPUT.body}", ctx) == "plain"

    def test_header(self):
        ctx = _ctx(headers={"X-Request-Id": "rid-1"})
        assert apply_placeholders("{INPUT.header.X-Request-Id}", ctx) == "rid-1"
        assert apply_placeholders("{INPUT.header.missing}", ctx) == ""

    def test_missing_becomes_empty(self):
        ctx = _ctx()
        assert apply_placeholders("x{INPUT.body.id}y", ctx) == "xy"

    def test_nested_object_dumped(self):
        ctx = _ctx(body_text='{"user":{"name":"t"}}')
        out = apply_placeholders("{INPUT.body.user}", ctx)
        assert "name" in out

    def test_no_placeholder(self):
        ctx = _ctx()
        assert apply_placeholders("static", ctx) == "static"
