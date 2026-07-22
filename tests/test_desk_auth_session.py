#!/usr/bin/env python3
"""Unit tests for desk session cookie auth."""

from __future__ import annotations

import os
import time
import unittest
from unittest.mock import patch

from scripts.research_data_mcp import desk_auth


class _FakeHandler:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}


class DeskAuthSessionTests(unittest.TestCase):
    def test_session_cookie_round_trip_authorizes_chat(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            value = desk_auth.session_cookie_value(token)
            handler = _FakeHandler({"Cookie": f"{desk_auth.DESK_SESSION_COOKIE}={value}"})
            ok, msg = desk_auth.authorize(handler, "/library/chat")
            self.assertTrue(ok)
            self.assertEqual(msg, "")

    def test_invalid_cookie_rejected(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            handler = _FakeHandler({"Cookie": f"{desk_auth.DESK_SESSION_COOKIE}=v1.deadbeef"})
            ok, msg = desk_auth.authorize(handler, "/library/chat")
            self.assertFalse(ok)
            self.assertIn("Desk access token required", msg)

    def test_expired_cookie_rejected(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            expired = desk_auth.session_cookie_value(token, expires_at=int(time.time()) - 60)
            handler = _FakeHandler({"Cookie": f"{desk_auth.DESK_SESSION_COOKIE}={expired}"})
            ok, msg = desk_auth.authorize(handler, "/library/chat")
            self.assertFalse(ok)
            self.assertIn("Desk access token required", msg)

    def test_bearer_still_works(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            handler = _FakeHandler({"Authorization": f"Bearer {token}"})
            ok, _msg = desk_auth.authorize(handler, "/library/chat/stream")
            self.assertTrue(ok)

    def test_x_desk_token_still_works(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            handler = _FakeHandler({"X-Desk-Token": token})
            ok, _msg = desk_auth.authorize(handler, "/library/desk/warm")
            self.assertTrue(ok)

    def test_issue_session_accepts_canonical_8767_origin(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            good = _FakeHandler({"Origin": "http://100.127.141.44:8767"})
            ok, msg, cookie = desk_auth.issue_desk_session(good)
            self.assertTrue(ok)
            self.assertEqual(msg, "")
            self.assertIsNotNone(cookie)
            self.assertIn(desk_auth.DESK_SESSION_COOKIE, cookie or "")
            self.assertIn("HttpOnly", cookie or "")
            self.assertIn("SameSite=Strict", cookie or "")
            self.assertIn("Max-Age=", cookie or "")
            self.assertNotIn(token, cookie or "")

    def test_issue_session_rejects_cross_origin(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            bad = _FakeHandler({"Origin": "https://evil.example"})
            ok, msg, cookie = desk_auth.issue_desk_session(bad)
            self.assertFalse(ok)
            self.assertIn("allowed browser origin", msg)
            self.assertIsNone(cookie)

    def test_issue_session_rejects_missing_origin_and_referer(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            bare = _FakeHandler({})
            ok, msg, cookie = desk_auth.issue_desk_session(bare)
            self.assertFalse(ok)
            self.assertIn("allowed browser origin", msg)
            self.assertIsNone(cookie)

    def test_issue_session_allows_bearer_without_origin(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            proxied = _FakeHandler({"Authorization": f"Bearer {token}"})
            ok, msg, cookie = desk_auth.issue_desk_session(proxied)
            self.assertTrue(ok)
            self.assertEqual(msg, "")
            self.assertIsNotNone(cookie)

    def test_issue_session_allows_x_desk_token_without_origin(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            proxied = _FakeHandler({"X-Desk-Token": token})
            ok, msg, cookie = desk_auth.issue_desk_session(proxied)
            self.assertTrue(ok)
            self.assertIsNotNone(cookie)

    def test_session_path_does_not_require_prior_auth(self):
        self.assertFalse(desk_auth.path_requires_auth("/library/desk/session"))


if __name__ == "__main__":
    unittest.main()
