from __future__ import annotations

from rapi.core.models import Endpoint, ResponseSpec, Rule


class TestResponseSpec:
    def test_roundtrip(self):
        r = ResponseSpec(status=201, body='{"a":1}', content_type="application/json")
        d = r.to_dict()
        r2 = ResponseSpec.from_dict(d)
        assert r2.status == 201
        assert r2.body == '{"a":1}'
        assert r2.content_type == "application/json"

    def test_defaults(self):
        r = ResponseSpec.from_dict({})
        assert r.status == 200
        assert r.body == "OK"


class TestRule:
    def test_roundtrip(self):
        rule = Rule(
            conditions={"body.id": "004"},
            response=ResponseSpec(status=400, body='{"e":1}'),
        )
        d = rule.to_dict()
        r2 = Rule.from_dict(d)
        assert r2.conditions == {"body.id": "004"}
        assert r2.response.status == 400


class TestEndpoint:
    def test_path_method_normalize(self):
        ep = Endpoint(name="", path="sample", method="get")
        assert ep.path == "/sample"
        assert ep.method == "GET"
        assert ep.name == "GET:/sample"

    def test_roundtrip(self):
        ep = Endpoint(
            name="POST:/u",
            path="/u",
            method="POST",
            default=ResponseSpec(status=200, body="ok"),
            rules=[Rule(conditions={"body.id": "1"}, response=ResponseSpec(400, "err"))],
            params={"q": "1"},
            strict_params=True,
            expected_body="~x",
        )
        d = ep.to_dict()
        ep2 = Endpoint.from_dict(d)
        assert ep2.name == "POST:/u"
        assert ep2.strict_params
        assert ep2.expected_body == "~x"
        assert len(ep2.rules) == 1

    def test_from_dict_flat_format(self):
        ep = Endpoint.from_dict(
            {"path": "/x", "method": "get", "status": 201, "response": "hi"}
        )
        assert ep.default.status == 201
        assert ep.default.body == "hi"

    def test_from_dict_params_list(self):
        ep = Endpoint.from_dict(
            {
                "path": "/x",
                "method": "GET",
                "params": ["aaa=1", "bbb", {"key": "c", "value": "3"}],
            }
        )
        assert ep.params["aaa"] == "1"
        assert ep.params["bbb"] is None
        assert ep.params["c"] == "3"
