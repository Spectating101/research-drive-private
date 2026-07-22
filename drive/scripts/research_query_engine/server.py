#!/usr/bin/env python3
"""Thin HTTP server — all logic lives in ResearchDataGateway + http_router."""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from scripts.research_data_mcp.bootstrap import ResearchLibraryStack, create_stack
from scripts.research_data_mcp.desk_auth import (
    authorize,
    clear_desk_session,
    issue_desk_session,
)
from scripts.research_data_mcp.http_router import handle_get, handle_post
from sharpe_kernel.paths import repo_root_from_file

REPO_ROOT = repo_root_from_file(__file__)
DEFAULT_STATIC_DIR = REPO_ROOT / "dist"
API_PREFIXES = (
    "/health",
    "/datasets",
    "/query",
    "/library",
    "/yzu",
    "/agent",
)


def _env_bool(name: str, default: bool = False) -> bool:
    raw = str(os.getenv(name) or "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


def _env_port(name: str, default: int) -> int:
    raw = str(os.getenv(name) or "").strip()
    if not raw:
        return default
    try:
        port = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if not 1 <= port <= 65535:
        raise ValueError(f"{name} must be between 1 and 65535")
    return port


def normalize_cors_origin(value: str | None = None) -> str:
    """Return one explicit browser origin, or empty string for same-origin only."""
    raw = str(value if value is not None else os.getenv("YZU_DESK_CORS_ORIGIN") or "").strip()
    if not raw:
        return ""
    if raw == "*":
        raise ValueError("YZU_DESK_CORS_ORIGIN must be one explicit http(s) origin, not '*'")
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("YZU_DESK_CORS_ORIGIN must be an absolute http(s) origin")
    if parsed.params or parsed.query or parsed.fragment or parsed.path not in {"", "/"}:
        raise ValueError("YZU_DESK_CORS_ORIGIN must not include a path, query, or fragment")
    return f"{parsed.scheme}://{parsed.netloc}"


def resolve_static_dir(value: str | Path | None = None) -> Path:
    raw = value or os.getenv("YZU_DESK_STATIC_DIR") or DEFAULT_STATIC_DIR
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = REPO_ROOT / path
    return path.resolve()


def require_ui_build(static_dir: Path) -> Path:
    index = static_dir / "index.html"
    if not index.is_file():
        raise FileNotFoundError(
            f"Research Drive UI build missing at {index}. "
            "Build the public yzu-cluster authority and set YZU_DESK_STATIC_DIR to its dist directory."
        )
    return index


def normalize_api_path(path: str) -> str:
    """Strip dev/prod /api prefix so Vite proxy and --serve-ui share one route table."""
    if path == "/api":
        return "/"
    if path.startswith("/api/"):
        return path[4:]
    return path


def is_api_path(path: str) -> bool:
    path = normalize_api_path(path)
    return any(path == prefix or path.startswith(f"{prefix}/") for prefix in API_PREFIXES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Research library HTTP API")
    parser.add_argument("--host", default=os.getenv("YZU_DESK_HOST") or "127.0.0.1")
    parser.add_argument("--port", type=int, default=_env_port("YZU_DESK_PORT", 8765))
    parser.add_argument(
        "--registry",
        default=(
            os.getenv("SHARPE_REGISTRY_PATH")
            or os.getenv("YZU_REGISTRY_PATH")
            or "config/research_query_registry.json"
        ),
    )
    parser.add_argument(
        "--static-dir",
        default=os.getenv("YZU_DESK_STATIC_DIR") or str(DEFAULT_STATIC_DIR),
        help="Built public yzu-cluster dist directory used by --serve-ui",
    )
    parser.add_argument(
        "--serve-ui",
        action="store_true",
        default=_env_bool("YZU_DESK_SERVE_UI"),
        help="Serve production UI from --static-dir on non-API GET paths",
    )
    parser.add_argument(
        "--cors-origin",
        default=os.getenv("YZU_DESK_CORS_ORIGIN") or "",
        help="Optional single browser origin; empty keeps the desk same-origin only",
    )
    return parser


class ResearchQueryHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    stack: ResearchLibraryStack
    static_dir: Path = DEFAULT_STATIC_DIR
    cors_origin: str = ""

    def _send_cors_headers(self) -> None:
        if not self.cors_origin:
            return
        self.send_header("Access-Control-Allow-Origin", self.cors_origin)
        self.send_header("Vary", "Origin")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, DELETE, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Desk-Token")
        self.send_header("Access-Control-Allow-Credentials", "true")

    def _send_json(
        self,
        payload: dict,
        status: int = 200,
        *,
        extra_headers: list[tuple[str, str]] | None = None,
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self._send_cors_headers()
        self.send_header("X-Content-Type-Options", "nosniff")
        for key, value in extra_headers or []:
            self.send_header(key, value)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _handle_desk_session(self, *, clear: bool = False) -> None:
        if clear:
            ok, msg, cookie = clear_desk_session(self)
            body = {"ok": ok, "cleared": bool(ok), "desk_session_cookie": True}
        else:
            ok, msg, cookie = issue_desk_session(self)
            body = {"ok": ok, "authorized": bool(ok), "desk_session_cookie": True}
        if not ok:
            body["error"] = "Forbidden"
            body["message"] = msg
            self._send_json(body, status=403)
            return
        headers = [("Set-Cookie", cookie)] if cookie else None
        self._send_json(body, status=200, extra_headers=headers)

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self._send_cors_headers()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def _send_bytes(
        self,
        body: bytes,
        *,
        status: int = 200,
        content_type: str = "application/octet-stream",
        download_name: str = "",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self._send_cors_headers()
        self.send_header("X-Content-Type-Options", "nosniff")
        if download_name:
            self.send_header("Content-Disposition", f'attachment; filename="{download_name}"')
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except BrokenPipeError:
            pass

    def _serve_static(self, path: str) -> bool:
        static_dir = self.static_dir
        if not getattr(self.stack, "serve_ui", False) or not static_dir.is_dir():
            return False
        if is_api_path(path):
            return False
        rel = path.lstrip("/")
        if not rel or not Path(rel).suffix:
            rel = "index.html"
        target = (static_dir / rel).resolve()
        try:
            target.relative_to(static_dir.resolve())
        except ValueError:
            self._send_json({"error": "NotFound", "message": "invalid path"}, status=404)
            return True
        if not target.is_file():
            target = static_dir / "index.html"
            if not target.is_file():
                self._send_json({"error": "NotFound", "message": "UI build missing"}, status=404)
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
            ".woff": "font/woff",
            ".woff2": "font/woff2",
            ".ttf": "font/ttf",
            ".webp": "image/webp",
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
        self._send_cors_headers()
        self.send_header("X-Content-Type-Options", "nosniff")
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
        if path == "/library/desk/session":
            length = int(self.headers.get("Content-Length", "0"))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                payload = json.loads(raw or b"{}")
            except Exception:
                payload = {}
            clear = bool(isinstance(payload, dict) and payload.get("action") == "clear")
            self._handle_desk_session(clear=clear)
            return
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

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = normalize_api_path(parsed.path)
        if path == "/library/desk/session":
            self._handle_desk_session(clear=True)
            return
        self._send_json({"error": "not_found", "message": "DELETE not supported for this path"}, status=404)


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    static_dir = resolve_static_dir(args.static_dir)
    try:
        cors_origin = normalize_cors_origin(args.cors_origin)
    except ValueError as exc:
        parser.error(str(exc))
    if args.serve_ui:
        try:
            require_ui_build(static_dir)
        except FileNotFoundError as exc:
            parser.error(str(exc))

    stack = create_stack(registry_path=args.registry)
    stack.serve_ui = bool(args.serve_ui)
    stack.gateway._serve_ui = bool(args.serve_ui)
    ResearchQueryHandler.stack = stack
    ResearchQueryHandler.static_dir = static_dir
    ResearchQueryHandler.cors_origin = cors_origin
    server = ThreadingHTTPServer((args.host, args.port), ResearchQueryHandler)
    print(f"research_library_api=http://{args.host}:{args.port}")
    if args.serve_ui:
        print(f"research_desk_ui=http://{args.host}:{args.port}/  (static from {static_dir})")
    print(f"cors_origin={cors_origin or 'same-origin-only'}")
    print("entry=scripts/research_data_mcp/bootstrap.py + gateway.py + http_router.py")
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
