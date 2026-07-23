#!/usr/bin/env python3
"""Unit tests for desk session cookie auth."""

from __future__ import annotations

import os
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

    def test_issue_session_requires_same_origin(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            bad = _FakeHandler(
                {
                    "Host": "100.127.141.44:8765",
                    "Origin": "https://evil.example",
                }
            )
            ok, msg, cookie = desk_auth.issue_desk_session(bad)
            self.assertFalse(ok)
            self.assertIn("same-origin", msg)
            self.assertIsNone(cookie)

            good = _FakeHandler(
                {
                    "Host": "100.127.141.44:8765",
                    "Origin": "http://100.127.141.44:8765",
                }
            )
            ok, msg, cookie = desk_auth.issue_desk_session(good)
            self.assertTrue(ok)
            self.assertEqual(msg, "")
            self.assertIsNotNone(cookie)
            self.assertIn(desk_auth.DESK_SESSION_COOKIE, cookie or "")
            self.assertIn("HttpOnly", cookie or "")
            self.assertIn("SameSite=Strict", cookie or "")
            self.assertNotIn(token, cookie or "")

    def test_session_path_does_not_require_prior_auth(self):
        self.assertFalse(desk_auth.path_requires_auth("/library/desk/session"))

    def test_bootstrap_without_origin_or_referer_rejected(self):
        token = "test-desk-token-please-rotate"
        with patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": token}, clear=False):
            bare = _FakeHandler({"Host": "100.127.141.44:8765"})
            ok, msg, cookie = desk_auth.issue_desk_session(bare)
            self.assertFalse(ok)
            self.assertIn("same-origin", msg)
            self.assertIsNone(cookie)

    def test_mutating_library_posts_require_auth(self):
        self.assertTrue(desk_auth.path_requires_auth("/library/craft/collect-plan", "POST"))
        self.assertTrue(desk_auth.path_requires_auth("/library/advise", "POST"))


if __name__ == "__main__":
    unittest.main()
