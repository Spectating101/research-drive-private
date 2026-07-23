#!/usr/bin/env python3
"""In-process sliding-window rate limit for desk mutating routes."""

from __future__ import annotations

import os
import threading
import time
from collections import defaultdict, deque

_LOCK = threading.Lock()
_HITS: dict[str, deque[float]] = defaultdict(deque)


def _limits() -> tuple[int, float]:
    limit = int(os.getenv("YZU_DESK_RATE_LIMIT", "60") or 60)
    window = float(os.getenv("YZU_DESK_RATE_WINDOW_SECONDS", "60") or 60)
    return max(1, limit), max(1.0, window)


def client_key(handler) -> str:  # noqa: ANN001
    forwarded = str(handler.headers.get("X-Forwarded-For") or "").split(",")[0].strip()
    if forwarded:
        return f"xff:{forwarded}"
    try:
        return f"peer:{handler.client_address[0]}"
    except Exception:
        return "peer:unknown"


def allow(key: str, *, cost: int = 1) -> tuple[bool, int, int]:
    """Return (allowed, remaining, retry_after_seconds)."""
    limit, window = _limits()
    now = time.monotonic()
    with _LOCK:
        bucket = _HITS[key]
        while bucket and now - bucket[0] >= window:
            bucket.popleft()
        if len(bucket) + cost > limit:
            retry = int(max(1, window - (now - bucket[0]))) if bucket else int(window)
            return False, 0, retry
        for _ in range(cost):
            bucket.append(now)
        remaining = max(0, limit - len(bucket))
        return True, remaining, 0


def reset_for_tests() -> None:
    with _LOCK:
        _HITS.clear()
