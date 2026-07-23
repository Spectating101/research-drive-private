#!/usr/bin/env python3
"""Outbound network policy for generic collection workers.

Faculty/Composer collection may target arbitrary public HTTP(S) sources, but it
must never become an internal-network request primitive. Validate both the
literal hostname and every resolved address before a request or redirect is
allowed.
"""
from __future__ import annotations

import ipaddress
import socket
from collections.abc import Callable, Iterable
from typing import Any
from urllib.parse import urlsplit

Resolver = Callable[..., Iterable[tuple[Any, ...]]]

_BLOCKED_HOST_SUFFIXES = (
    ".localhost",
    ".local",
    ".internal",
    ".lan",
    ".home",
)
_BLOCKED_HOSTS = frozenset(
    {
        "localhost",
        "localhost.localdomain",
        "metadata.google.internal",
        "metadata",
        "instance-data",
    }
)


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return bool(address.is_global)


def _resolved_addresses(
    host: str,
    port: int,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> set[str]:
    try:
        rows = resolver(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValueError(f"target host does not resolve: {host}") from exc
    addresses: set[str] = set()
    for row in rows:
        try:
            address = str(row[4][0])
        except (IndexError, TypeError):
            continue
        if address:
            addresses.add(address)
    if not addresses:
        raise ValueError(f"target host resolved to no usable addresses: {host}")
    return addresses


def validate_public_http_url(
    url: str,
    *,
    resolver: Resolver = socket.getaddrinfo,
) -> dict[str, Any]:
    """Validate an outbound URL and return its public resolution evidence.

    The policy is deliberately fail-closed. A hostname is rejected when any
    resolved address is non-public, preventing mixed public/private DNS answers
    from being used as a rebinding or redirect path into the cluster network.
    """

    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("item URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in item URLs")

    host = parsed.hostname.rstrip(".").lower()
    if host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES):
        raise ValueError(f"target host is internal or local: {host}")

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        if not literal.is_global:
            raise ValueError(f"target address is not public: {literal}")
        addresses = {str(literal)}
    else:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = _resolved_addresses(host, port, resolver=resolver)
        rejected = sorted(address for address in addresses if not _is_public_address(address))
        if rejected:
            raise ValueError(
                f"target host resolves to non-public address(es): {host} -> {', '.join(rejected)}"
            )

    return {
        "url": parsed.geturl(),
        "scheme": parsed.scheme,
        "host": host,
        "resolved_addresses": sorted(addresses),
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "path": parsed.path or "/",
        "query": parsed.query,
    }


def pick_pinned_address(evidence: dict[str, Any]) -> str:
    """Prefer IPv4 public address for pinned sockets."""
    addresses = [str(a) for a in (evidence.get("resolved_addresses") or [])]
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if parsed.version == 4 and parsed.is_global:
            return str(parsed)
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if parsed.is_global:
            return str(parsed)
    raise ValueError("no public address available to pin")


def open_pinned_public_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    method: str = "GET",
    resolver: Resolver = socket.getaddrinfo,
):
    """Open an HTTP(S) URL by connecting to a validated public IP (DNS pin).

    Sets Host / SNI to the original hostname so virtual-hosted APIs still work,
    while the TCP connection cannot be rebound to a private address after check.
    """
    import http.client
    import ssl
    from email.message import Message

    evidence = validate_public_http_url(url, resolver=resolver)
    pinned = pick_pinned_address(evidence)
    host = str(evidence["host"])
    port = int(evidence["port"])
    path = str(evidence["path"] or "/")
    query = str(evidence.get("query") or "")
    target = f"{path}?{query}" if query else path
    hdrs = {"Host": host, "User-Agent": "ResearchDrive-YZU-Worker/1.0", "Accept": "*/*"}
    if headers:
        for key, value in headers.items():
            key_text = str(key).strip()
            if key_text and key_text.lower() not in {"host", "content-length"}:
                hdrs[key_text] = str(value)

    if evidence["scheme"] == "https":
        context = ssl.create_default_context()
        # Pin IP in connect, keep SNI on the public hostname.
        conn: http.client.HTTPConnection = http.client.HTTPSConnection(
            pinned,
            port=port,
            timeout=timeout,
            context=context,
        )
        # http.client uses host for SNI when tunnel/server_hostname set via wrap —
        # HTTPSConnection(host=ip) uses IP for SNI by default; override via _tunnel_host
        # isn't enough. Use server_hostname on context wrap by setting conn.host carefully.
        conn._tunnel_host = host  # type: ignore[attr-defined]
        # Preferred: pass server_hostname through ssl wrap by monkeypatching connect.
        _orig_connect = conn.connect

        def _connect_with_sni() -> None:  # noqa: ANN202
            sock = socket.create_connection((pinned, port), timeout)
            conn.sock = context.wrap_socket(sock, server_hostname=host)

        conn.connect = _connect_with_sni  # type: ignore[method-assign]
    else:
        conn = http.client.HTTPConnection(pinned, port=port, timeout=timeout)

    conn.request(method.upper(), target, headers=hdrs)
    response = conn.getresponse()

    class _PinnedResponse:
        def __init__(self) -> None:
            self.status = int(response.status)
            self.headers = response.headers
            self._raw = response
            self._conn = conn
            self.url = url
            self.evidence = {**evidence, "pinned_address": pinned}

        def getcode(self) -> int:
            return self.status

        def geturl(self) -> str:
            return self.url

        def read(self, amt: int | None = None) -> bytes:
            return self._raw.read(amt)

        def __enter__(self):
            return self

        def __exit__(self, *args: object) -> None:
            try:
                self._raw.close()
            finally:
                self._conn.close()

    return _PinnedResponse()

