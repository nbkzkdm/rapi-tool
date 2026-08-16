from __future__ import annotations

import json
from pathlib import Path

import pytest

from rapi.core.store import DefinitionStore


@pytest.fixture
def tmp_store(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> DefinitionStore:
    """Isolated DefinitionStore under tmp_path; also redirect server state dir."""
    state = tmp_path / ".rapi"
    state.mkdir()
    store_path = state / "definitions.json"

    monkeypatch.setattr("rapi.core.store.default_store_path", lambda: store_path)
    monkeypatch.setattr("rapi.core.server.state_dir", lambda: state)

    # clear any import-time assumptions
    store = DefinitionStore(path=store_path)
    store.clear()
    return store


@pytest.fixture
def sample_endpoint_dict() -> dict:
    return {
        "name": "POST:/users",
        "path": "/users",
        "method": "POST",
        "default": {"status": 200, "body": '{"ok":true,"id":"{INPUT.body.id}"}'},
        "rules": [
            {
                "when": {"body.id": "004"},
                "status": 400,
                "body": '{"error":"bad","id":"{INPUT.body.id}"}',
            },
            {
                "when": {"body.id": "~^9"},
                "status": 503,
                "body": '{"error":"unavailable"}',
            },
        ],
        "params": {},
        "strict_params": False,
        "expected_body": None,
    }
