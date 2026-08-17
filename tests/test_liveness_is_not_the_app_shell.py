#!/usr/bin/env python3
"""A 200 must not be the SPA shell wearing a health probe's clothes.

/healthz, /api/registry and /api/v1/datasets all returned 200 text/html — the
static fallback for an unknown path. Status-code-only monitoring could never see a
failure. Asserted against a real handler with a real static dir, because the bug was
in the interaction between routing and the SPA fallback, not in either alone.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.research_query_engine import server as srv


class _Recorder(srv.ResearchQueryHandler):
    """Drives do_GET without a socket."""

    def __init__(self, path: str, static_dir: Path):  # noqa: D107
        self.path = path
        self.static_dir = static_dir
        self.sent: dict = {}
        self.headers = {}
        self.client_address = ("127.0.0.1", 0)

    def _send_json(self, payload, status=200, *, extra_headers=None, close_connection=False):
        self.sent = {"kind": "json", "status": status, "body": payload}

    def _send_bytes(self, body, *, status=200, content_type="application/octet-stream", download_name=""):
        self.sent = {"kind": "bytes", "status": status, "content_type": content_type, "body": body}

    def log_message(self, *a, **k):  # noqa: D102
        pass


@pytest.fixture
def static_dir(tmp_path: Path) -> Path:
    d = tmp_path / "dist"
    d.mkdir()
    (d / "index.html").write_text("<!doctype html><title>desk</title>", encoding="utf-8")
    return d


class _Stack:
    serve_ui = True


def _get(path: str, static_dir: Path) -> dict:
    h = _Recorder(path, static_dir)
    h.stack = _Stack()
    h.cors_origin = ""
    srv.ResearchQueryHandler.do_GET(h)
    return h.sent


def test_healthz_is_json_not_html(static_dir: Path) -> None:
    sent = _get("/healthz", static_dir)
    assert sent["kind"] == "json"
    assert sent["status"] == 200
    assert sent["body"] == {"status": "ok"}


@pytest.mark.parametrize("path", ["/api/registry", "/api/v1/datasets", "/api/nope"])
def test_unknown_api_routes_404_as_json(path: str, static_dir: Path) -> None:
    sent = _get(path, static_dir)
    assert sent["status"] == 404, f"{path} returned {sent['status']}"
    assert sent["kind"] == "json"
    assert sent["body"]["error"] == "NotFound"


@pytest.mark.parametrize("path", ["/", "/library", "/settings"])
def test_app_routes_still_get_the_shell(path: str, static_dir: Path) -> None:
    """The SPA must keep working for real front-end routes."""
    sent = _get(path, static_dir)
    if sent.get("kind") == "bytes":
        assert sent["status"] == 200
        assert "text/html" in sent["content_type"]
    else:
        # /library is an API prefix and correctly reaches the auth gate instead.
        assert sent["status"] in {401, 403, 200}


def test_healthz_is_not_an_api_prefix_but_is_still_handled() -> None:
    """Regression anchor: the fix is an explicit branch, not a prefix change."""
    assert srv.is_api_path("/healthz") is False
    assert srv.is_api_path("/health") is True
