from __future__ import annotations

import pytest

from rapi.core.matching import match_body_pattern, match_conditions, match_value


class TestMatchValue:
    def test_exact(self):
        assert match_value("hello", "hello")
        assert not match_value("hello", "world")

    def test_regex_fullmatch(self):
        assert match_value("123", r"~\d+")
        assert not match_value("12a", r"~\d+")
        assert match_value("abc", r"~^[a-z]+$")

    def test_regex_invalid(self):
        assert not match_value("x", "~[")

    def test_simple_pattern_digits(self):
        assert match_value("123", "NNN")
        assert not match_value("12", "NNN")
        assert not match_value("12a", "NNN")

    def test_simple_pattern_alpha(self):
        assert match_value("ab", "AA")
        assert not match_value("a1", "AA")

    def test_simple_pattern_alnum_and_star(self):
        assert match_value("a1", "XX")
        assert match_value("xy", "**")
        assert match_value("a-b", "A-A")  # literal dash

    def test_simple_pattern_with_literal(self):
        assert match_value("ID-01", "ID-NN")
        assert not match_value("ID-ab", "ID-NN")


class TestMatchBodyPattern:
    def test_exact(self):
        assert match_body_pattern('{"a":1}', '{"a":1}')

    def test_trailing_newline(self):
        assert match_body_pattern('{"a":1}', '{"a":1}\n')

    def test_json_key_order(self):
        assert match_body_pattern('{"b":2,"a":1}', '{"a":1,"b":2}')

    def test_mismatch(self):
        assert not match_body_pattern('{"a":1}', '{"a":2}')

    def test_regex(self):
        assert match_body_pattern('{"name":"taro"}', '~"name"')
        assert not match_body_pattern('{"age":1}', '~"name"')

    def test_regex_invalid(self):
        assert not match_body_pattern("x", "~[")

    def test_non_json_strip(self):
        assert match_body_pattern("hello\n", "hello")
        assert not match_body_pattern("hello", "world")


class TestMatchConditions:
    def test_empty(self):
        assert match_conditions({}, "GET", "/", {}, {}, None)

    def test_method_path(self):
        assert match_conditions({"method": "POST"}, "POST", "/x", {}, {}, None)
        assert not match_conditions({"method": "GET"}, "POST", "/x", {}, {}, None)
        assert match_conditions({"path": "/x"}, "GET", "/x", {}, {}, None)

    def test_query(self):
        q = {"aaa": ["123"]}
        assert match_conditions({"query.aaa": "123"}, "GET", "/", q, {}, None)
        assert match_conditions({"query.aaa": r"~\d+"}, "GET", "/", q, {}, None)
        assert not match_conditions({"query.missing": "1"}, "GET", "/", q, {}, None)

    def test_header(self):
        h = {"X-Request-Id": "abc"}
        assert match_conditions({"header.X-Request-Id": "abc"}, "GET", "/", {}, h, None)
        assert not match_conditions({"header.Missing": "x"}, "GET", "/", {}, h, None)

    def test_body_field(self):
        body = '{"id":"004","user":{"name":"t"}}'
        assert match_conditions({"body.id": "004"}, "POST", "/", {}, {}, body)
        assert match_conditions({"body.id": "~^0"}, "POST", "/", {}, {}, body)
        assert match_conditions({"body.user.name": "t"}, "POST", "/", {}, {}, body)
        assert not match_conditions({"body.id": "999"}, "POST", "/", {}, {}, body)

    def test_body_whole(self):
        assert match_conditions({"body": "~taro"}, "POST", "/", {}, {}, '{"name":"taro"}')

    def test_body_field_missing_json(self):
        assert not match_conditions({"body.id": "1"}, "POST", "/", {}, {}, "not-json")

    def test_and_logic(self):
        body = '{"id":"1"}'
        q = {"t": ["x"]}
        assert match_conditions(
            {"body.id": "1", "query.t": "x"}, "POST", "/", q, {}, body
        )
        assert not match_conditions(
            {"body.id": "1", "query.t": "y"}, "POST", "/", q, {}, body
        )

    def test_nested_list_index(self):
        body = '{"items":[{"id":"a"},{"id":"b"}]}'
        assert match_conditions({"body.items.1.id": "b"}, "POST", "/", {}, {}, body)
