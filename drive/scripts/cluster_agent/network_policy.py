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
    }
