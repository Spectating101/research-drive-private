#!/usr/bin/env python3
"""Production ASGI front end over the existing router.

The desk served 123 endpoints from http.server.ThreadingHTTPServer, which the
Python docs say is not for production: no worker model, no request timeouts, no
backpressure, no graceful reload, one thread per connection.

This is an adapter, not a rewrite. All logic already lives in
ResearchDataGateway + http_router, and desk_auth only reads two headers, so the
same handlers and the same authorization run unchanged behind uvicorn.

Run:
    uvicorn scripts.research_query_engine.asgi_app:app --host 0.0.0.0 --port 8765
    # production: --workers N is unsafe while the registry is a JSON file under
    # flock; keep workers=1 until the registry moves to a database.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from scripts.research_data_mcp.desk_auth import authorize
from scripts.research_data_mcp.http_router import handle_get, handle_post

_LOG = logging.getLogger("research_drive.asgi")

MAX_BODY_BYTES = 4 * 1024 * 1024


class _HeaderShim:
    """desk_auth.authorize expects BaseHTTPRequestHandler; it only reads headers."""

    def __init__(self, request: Request) -> None:
        self.headers = request.headers
        self.client_address = (request.client.host if request.client else "", 0)
        self.path = request.url.path
        self.command = request.method


def _stack():
    import os

    from scripts.research_data_mcp.bootstrap import create_stack

    return create_stack(
        repo_root=os.getenv("SHARPE_REPO_ROOT") or None,
        registry_path=os.getenv("SHARPE_REGISTRY_PATH") or None,
    )


def create_app(stack: Any = None) -> FastAPI:
    @asynccontextmanager
    async def lifespan(instance: FastAPI):
        if instance.state.stack is None:
            instance.state.stack = _stack()
        yield

    app = FastAPI(
        title="Research Drive desk", docs_url=None, redoc_url=None, lifespan=lifespan
    )
    app.state.stack = stack

    def _ensure_stack() -> Any:
        # Built lazily rather than only on startup: a client that skips the
        # lifespan (TestClient without a context manager, some ASGI runners)
        # would otherwise hit every route with stack=None and get a 500.
        if app.state.stack is None:
            app.state.stack = _stack()
        return app.state.stack

    @app.get("/health")
    def health() -> dict[str, Any]:
        return {"status": "ok", "service": "research-drive-desk"}

    @app.api_route("/{full_path:path}", methods=["GET", "POST"])
    async def dispatch(full_path: str, request: Request) -> JSONResponse:
        started = time.perf_counter()
        path = "/" + full_path.lstrip("/")
        shim = _HeaderShim(request)

        allowed, reason = authorize(shim, path, method=request.method)
        if not allowed:
            return JSONResponse({"error": "forbidden", "detail": reason}, status_code=403)

        query = dict(request.query_params)
        try:
            if request.method == "GET":
                out = handle_get(path, query, _ensure_stack())
            else:
                raw = await request.body()
                if len(raw) > MAX_BODY_BYTES:
                    return JSONResponse({"error": "payload_too_large"}, status_code=413)
                payload = {}
                if raw:
                    import json

                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError:
                        return JSONResponse({"error": "invalid_json"}, status_code=400)
                    payload = parsed if isinstance(parsed, dict) else {"value": parsed}
                out = handle_post(path, payload, _ensure_stack(), query)
        except KeyError:
            return JSONResponse({"error": "not_found", "path": path}, status_code=404)
        except ValueError as exc:
            return JSONResponse({"error": "bad_request", "detail": str(exc)[:400]}, status_code=400)
        except Exception:  # noqa: BLE001 - never leak a stack trace to a client
            _LOG.exception("unhandled error on %s %s", request.method, path)
            return JSONResponse({"error": "internal_error"}, status_code=500)

        elapsed_ms = (time.perf_counter() - started) * 1000
        if out is None:
            return JSONResponse({"error": "not_found", "path": path}, status_code=404)

        # The router answers with a {status, body} envelope rather than raising,
        # and marks binary/stream payloads inside body. Unwrap exactly as the
        # stdlib server does so clients see no difference.
        status = 200
        body: Any = out
        if isinstance(out, dict) and "status" in out and "body" in out:
            status = int(out.get("status") or 200)
            body = out.get("body")

        if isinstance(body, dict) and (body.get("_file_delivery") or body.get("_stream")):
            return JSONResponse(
                {"error": "unsupported_transfer", "detail": "binary delivery not served over ASGI yet"},
                status_code=501,
            )

        _LOG.info("%s %s %s %.0fms", request.method, path, status, elapsed_ms)
        return JSONResponse(
            body, status_code=status, headers={"X-Response-Time-Ms": f"{elapsed_ms:.0f}"}
        )

    return app


app = create_app()
