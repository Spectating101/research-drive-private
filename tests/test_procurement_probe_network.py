"""The synchronous Discover probe must use the DNS-pinned worker primitive."""

from __future__ import annotations

from email.message import Message

import pytest

from scripts.research_query_engine import procurement


class _Response:
    def __init__(
        self,
        url: str,
        *,
        status: int = 200,
        body: bytes = b"ok",
        location: str = "",
    ) -> None:
        self.url = url
        self.status = status
        self._body = body
        self.headers = Message()
        self.headers["Content-Type"] = "text/plain"
        if location:
            self.headers["Location"] = location

    def read(self, amount: int | None = None) -> bytes:
        return self._body if amount is None else self._body[:amount]

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None


def test_probe_reader_uses_pinned_socket_for_initial_request(monkeypatch):
    calls: list[str] = []

    def open_pinned(url: str, **_kwargs):
        calls.append(url)
        return _Response(url, body=b"payload")

    monkeypatch.setattr(
        procurement.network_policy, "open_pinned_public_url", open_pinned
    )
    final_url, status, _, body, truncated = procurement._read_pinned_public_url(
        "https://example.test/data",
        timeout=3,
        max_bytes=32,
    )

    assert calls == ["https://example.test/data"]
    assert (final_url, status, body, truncated) == (
        "https://example.test/data",
        200,
        b"payload",
        False,
    )


def test_probe_redirect_is_revalidated_and_private_target_is_blocked(monkeypatch):
    calls: list[str] = []

    def open_pinned(url: str, **_kwargs):
        calls.append(url)
        if url.startswith("http://127.0.0.1"):
            raise ValueError("target address is not public")
        return _Response(
            url,
            status=302,
            location="http://127.0.0.1/internal",
        )

    monkeypatch.setattr(
        procurement.network_policy, "open_pinned_public_url", open_pinned
    )

    with pytest.raises(ValueError, match="not public"):
        procurement._read_pinned_public_url(
            "https://example.test/start",
            timeout=3,
            max_bytes=32,
        )

    assert calls == [
        "https://example.test/start",
        "http://127.0.0.1/internal",
    ]
