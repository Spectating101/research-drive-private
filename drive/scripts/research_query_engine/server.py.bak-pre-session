#!/usr/bin/env python3
"""Thin HTTP server — all logic lives in ResearchDataGateway + http_router."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from scripts.research_data_mcp.bootstrap import ResearchLibraryStack, create_stack
from scripts.research_data_mcp.desk_auth import authorize
from scripts.research_data_mcp.http_router import handle_get, handle_post
from sharpe_kernel.paths import repo_root_from_file

REPO_ROOT = repo_root_from_file(__file__)
STATIC_DIR = REPO_ROOT / "dist"
API_PREFIXES = (
    "/health",
    "/datasets",
    "/query/",
    "/library/",
    "/yzu/",
    "/agent/",
)


def normalize_api_path(path: str) -> str:
    """Strip dev/prod /api prefix so Vite proxy and --serve-ui share one route table."""
    if path == "/api":
        return "/"
    if path.startswith("/api/"):
        return path[4:]
    return path


def is_api_path(path: str) -> bool:
    path = normalize_api_path(path)
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in API_PREFIXES)


class ResearchQueryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    stack: ResearchLibraryStack

    def _send_json(self, payload: dict, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Desk-Token")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Desk-Token")
        self.end_headers()

    def _send_bytes(self, body: bytes, *, status: int = 200, content_type: str = "application/octet-stream", download_name: str = "") -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Access-Control-Allow-Origin", "*")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_static(self, path: str) -> bool:
        if not getattr(self.stack, "serve_ui", False) or not STATIC_DIR.is_dir():
            return False
        if is_api_path(path):
            return False
        rel = path.lstrip("/")
        if not rel or not Path(rel).suffix:
            rel = "index.html"
        target = (STATIC_DIR / rel).resolve()
        try:
            target.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self._send_json({"error": "NotFound", "message": "invalid path"}, status=404)
            return True
        if not target.is_file():
            target = STATIC_DIR / "index.html"
            if not target.is_file():
                self._send_json({"error": "NotFound", "message": "UI build missing — run npm run build"}, status=404)
                return True
        content = target.read_bytes()
        suffix = target.suffix.lower()
        content_type = {
            ".html": "text/html; charset=utf-8",
            ".js": "application/javascript; charset=utf-8",
            ".css": "text/css; charset=utf-8",
            ".svg": "image/svg+xml",
            ".png": "image/png",
            ".ico": "image/x-icon",
            ".json": "application/json; charset=utf-8",
            ".woff2": "font/woff2",
        }.get(suffix, "application/octet-stream")
        self._send_bytes(content, status=200, content_type=content_type)
        return True

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = normalize_api_path(parsed.path)
        if self._serve_static(path):
            return
        qs = {k: v[-1] for k, v in parse_qs(parsed.query).items()}
        result = handle_get(path, qs, self.stack)
        body = result.get("body")
        if isinstance(body, dict) and body.get("_file_delivery"):
            try:
                file_path = body["file"]
                content = Path(file_path).read_bytes()
                self._send_bytes(
                    content,
                    status=result["status"],
                    content_type=str(body.get("content_type") or "application/octet-stream"),
                    download_name=str(body.get("name") or Path(file_path).name),
                )
            except Exception as exc:
                self._send_json({"error": type(exc).__name__, "message": str(exc)}, status=404)
            return
        self._send_json(body, result["status"])

    def _send_ndjson_stream(self, events: Any, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "application/x-ndjson; charset=utf-8")
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Desk-Token")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        def write_chunk(body: bytes) -> None:
            self.wfile.write(f"{len(body):X}\r\n".encode("ascii"))
            self.wfile.write(body)
            self.wfile.write(b"\r\n")
            self.wfile.flush()

        try:
            for event in events:
                line = json.dumps(event, ensure_ascii=False).encode("utf-8") + b"\n"
                write_chunk(line)
        except BrokenPipeError:
            return
        except Exception as exc:
            error = {
                "type": "error",
                "error": type(exc).__name__,
                "message": str(exc)[:500],
            }
            write_chunk(json.dumps(error, ensure_ascii=False).encode("utf-8") + b"\n")
        finally:
            try:
                self.wfile.write(b"0\r\n\r\n")
                self.wfile.flush()
            except BrokenPipeError:
                pass

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = normalize_api_path(parsed.path)
        ok, msg = authorize(self, path)
        if not ok:
            self._send_json({"error": "Unauthorized", "message": msg}, status=401)
            return
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        result = handle_post(path, payload, self.stack)
        body = result.get("body")
        if isinstance(body, dict) and body.get("_stream"):
            self._send_ndjson_stream(body["events"], status=result["status"])
            return
        self._send_json(body, result["status"])


def main() -> int:
    parser = argparse.ArgumentParser(description="Research library HTTP API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--registry", default="config/research_query_registry.json")
    parser.add_argument(
        "--serve-ui",
        action="store_true",
        help="Serve production UI from dist/ on non-API GET paths (run npm run build first)",
    )
    args = parser.parse_args()
    stack = create_stack(registry_path=args.registry)
    stack.serve_ui = bool(args.serve_ui)
    stack.gateway._serve_ui = bool(args.serve_ui)
    ResearchQueryHandler.stack = stack
    server = ThreadingHTTPServer((args.host, args.port), ResearchQueryHandler)
    print(f"research_library_api=http://{args.host}:{args.port}")
    if args.serve_ui:
        print(f"research_desk_ui=http://{args.host}:{args.port}/  (static from {STATIC_DIR})")
    print("entry=scripts/research_data_mcp/bootstrap.py + gateway.py + http_router.py")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
