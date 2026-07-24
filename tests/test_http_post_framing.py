#!/usr/bin/env python3
"""Regression: unauthorized POST bodies must not poison keep-alive GETs."""

from __future__ import annotations

import http.client
import json
import os
import threading
import unittest
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.bootstrap import create_stack
from scripts.research_data_mcp.http_router import ROUTE_CATALOG
from scripts.research_query_engine.server import ResearchQueryHandler

REPO_ROOT = Path(__file__).resolve().parents[1]
REGISTRY = "drive/config/research_query_registry.json"


class UnauthorizedPostFramingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.token = "framing-test-desk-token"
        self._env = patch.dict(os.environ, {"YZU_DESK_ACCESS_TOKEN": self.token}, clear=False)
        self._env.start()
        stack = create_stack(registry_path=REGISTRY)
        stack.serve_ui = False
        ResearchQueryHandler.stack = stack
        ResearchQueryHandler.static_dir = REPO_ROOT / "dist"
        ResearchQueryHandler.cors_origin = ""
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), ResearchQueryHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.host, self.port = self.server.server_address[:2]

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self._env.stop()

    def test_desk_warm_route_and_session_bootstrap_remain_coherent(self) -> None:
        warm_routes = [row for row in ROUTE_CATALOG if row.get("path") == "/library/desk/warm"]
        session_routes = [row for row in ROUTE_CATALOG if row.get("path") == "/library/desk/session"]
        self.assertTrue(any(row.get("method") == "POST" for row in warm_routes))
        self.assertFalse(desk_auth.path_requires_auth("/library/desk/session", "POST"))
        self.assertTrue(desk_auth.path_requires_auth("/library/desk/warm", "POST"))
        # Session minting is handled in server.py before the generic authorize gate.
        self.assertFalse(session_routes)  # dedicated server handler, not router table

    def test_unauthorized_desk_warm_does_not_poison_following_get(self) -> None:
        body = json.dumps(
            {
                "user_email": "faculty@example.test",
                "session_id": "poison-canary-session",
                "background": True,
                "padding": "x" * 4096,
            }
        ).encode("utf-8")
        conn = http.client.HTTPConnection(self.host, self.port, timeout=5)
        try:
            conn.request(
                "POST",
                "/library/desk/warm",
                body=body,
                headers={
                    "Content-Type": "application/json",
                    "Content-Length": str(len(body)),
                    "Connection": "keep-alive",
                },
            )
            denied = conn.getresponse()
            denied_payload = json.loads(denied.read().decode("utf-8"))
            self.assertEqual(denied.status, 401)
            self.assertEqual(denied_payload.get("error"), "Unauthorized")
            connection_hdr = (denied.getheader("Connection") or "").lower()
            if "close" in connection_hdr:
                conn.close()
                conn = http.client.HTTPConnection(self.host, self.port, timeout=5)

            conn.request("GET", "/health", headers={"Connection": "keep-alive"})
            health = conn.getresponse()
            health_raw = health.read().decode("utf-8")
            self.assertEqual(health.status, 200, health_raw)
            health_payload = json.loads(health_raw)
            self.assertEqual(health_payload.get("status"), "ok")
            self.assertEqual(health_payload.get("service"), "research_library_api")
        finally:
            conn.close()


if __name__ == "__main__":
    unittest.main()
