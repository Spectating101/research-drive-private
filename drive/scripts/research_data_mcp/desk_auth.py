#!/usr/bin/env python3
"""Optional shared-secret gate for desk write operations."""

from __future__ import annotations

import os
from http.server import BaseHTTPRequestHandler


def access_token_required() -> str | None:
    return (os.getenv("YZU_DESK_ACCESS_TOKEN") or os.getenv("DESK_ACCESS_TOKEN") or "").strip() or None


def path_requires_auth(path: str) -> bool:
    if path in {
        "/library/chat",
        "/library/chat/stream",
        "/library/jobs",
        "/library/jobs/approve-safe",
        "/library/discover/collect",
        "/library/discover/sources/preview",
        "/library/archive",
        "/library/desk/warm",
        "/library/datacite/collect",
        "/library/datacite/enrich",
        "/library/synthesis/run",
        "/library/synthesis/pair",
        "/yzu/jobs",
        "/yzu/jobs/approve-safe",
    }:
        return True
    if path.startswith("/library/discover/intents"):
        return True
    if path.startswith("/library/discover/subscriptions"):
        return True
    if path.startswith("/library/synthesis/threads/") and path.rsplit("/", 1)[-1] in {
        "patches",
        "proposal",
        "execute",
        "conversation",
    }:
        return True
    if path.startswith("/library/licenses/"):
        return True
    if path.startswith("/library/jobs/") and path.rsplit("/", 1)[-1] in {"approve", "cancel"}:
        return True
    if path.startswith("/yzu/schedules/") and path.endswith("/run"):
        return True
    if path.startswith("/yzu/jobs/") and path.rsplit("/", 1)[-1] in {"approve", "cancel"}:
        return True
    if path.startswith("/library/campaigns/") and path.rsplit("/", 1)[-1] in {
        "approve-collect",
        "resume",
        "add-datacite",
    }:
        return True
    return False


def authorize(handler: BaseHTTPRequestHandler, path: str) -> tuple[bool, str]:
    token = access_token_required()
    if not token or not path_requires_auth(path):
        return True, ""
    auth = str(handler.headers.get("Authorization") or "")
    header = str(handler.headers.get("X-Desk-Token") or "")
    if auth.startswith("Bearer ") and auth[7:].strip() == token:
        return True, ""
    if header.strip() == token:
        return True, ""
    return False, "Desk access token required (set Authorization: Bearer or X-Desk-Token)"
