#!/usr/bin/env python3
"""ASGI front end preserves the router contract: auth, envelope, errors."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "kernel"), str(ROOT / "drive")]

from fastapi.testclient import TestClient  # noqa: E402

from scripts.research_query_engine import asgi_app  # noqa: E402


class FakeStack:
    pass


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setattr(asgi_app, "authorize", lambda *_a, **_k: (True, ""))
    return TestClient(asgi_app.create_app(FakeStack()))


def test_health_needs_no_stack_and_no_token():
    app = asgi_app.create_app(FakeStack())
    with TestClient(app) as c:
        r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_denied_requests_never_reach_a_handler(monkeypatch):
    called = []
    monkeypatch.setattr(asgi_app, "authorize", lambda *_a, **_k: (False, "nope"))
    monkeypatch.setattr(asgi_app, "handle_get", lambda *a, **k: called.append(a))
    with TestClient(asgi_app.create_app(FakeStack())) as c:
        r = c.get("/library/overview")
    assert r.status_code == 403
    assert called == []


def test_status_body_envelope_becomes_the_http_status(client, monkeypatch):
    monkeypatch.setattr(
        asgi_app, "handle_get", lambda *a, **k: {"status": 404, "body": {"error": "not_found"}}
    )
    r = client.get("/library/whatever")
    assert r.status_code == 404
    assert r.json() == {"error": "not_found"}


def test_plain_dict_is_returned_as_200(client, monkeypatch):
    monkeypatch.setattr(asgi_app, "handle_get", lambda *a, **k: {"total": 3})
    r = client.get("/library/discover")
    assert r.status_code == 200
    assert r.json() == {"total": 3}
    assert r.headers.get("x-response-time-ms") is not None


def test_malformed_json_is_a_400_not_a_500(client):
    r = client.post("/library/discover/assessment", content=b"{not json")
    assert r.status_code == 400
    assert r.json()["error"] == "invalid_json"


def test_oversized_body_is_rejected(client):
    r = client.post("/library/upload", content=b"x" * (asgi_app.MAX_BODY_BYTES + 1))
    assert r.status_code == 413


def test_handler_exception_never_leaks_a_traceback(client, monkeypatch):
    def boom(*_a, **_k):
        raise RuntimeError("secret path /home/someone/private")

    monkeypatch.setattr(asgi_app, "handle_get", boom)
    r = client.get("/library/overview")
    assert r.status_code == 500
    assert r.json() == {"error": "internal_error"}
    assert "secret path" not in r.text


def test_value_error_is_a_400(client, monkeypatch):
    def bad(*_a, **_k):
        raise ValueError("limit must be positive")

    monkeypatch.setattr(asgi_app, "handle_get", bad)
    r = client.get("/library/overview")
    assert r.status_code == 400
    assert "limit must be positive" in r.json()["detail"]


def test_binary_delivery_is_refused_rather_than_corrupted(client, monkeypatch):
    monkeypatch.setattr(
        asgi_app,
        "handle_get",
        lambda *a, **k: {"status": 200, "body": {"_file_delivery": True, "file": "/tmp/x"}},
    )
    r = client.get("/library/campaigns/1/download")
    assert r.status_code == 501
