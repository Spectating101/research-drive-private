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
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
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


@dataclass(frozen=True)
class _TestNetworkPolicy:
    """Process-local overrides used only by tests. Production keeps these empty."""

    resolver: Resolver | None = None
    allow_hosts: frozenset[str] = field(default_factory=frozenset)
    allow_addresses: frozenset[str] = field(default_factory=frozenset)


_TEST_POLICY = _TestNetworkPolicy()
_TEST_POLICY_LOCK = threading.RLock()


def _active_test_policy() -> _TestNetworkPolicy:
    with _TEST_POLICY_LOCK:
        return _TEST_POLICY


@contextmanager
def test_network_policy(
    *,
    resolver: Resolver | None = None,
    allow_hosts: Iterable[str] = (),
    allow_addresses: Iterable[str] = (),
) -> Iterator[_TestNetworkPolicy]:
    """Install deterministic resolver/allow-list hooks for tests only.

    Production callers must never use this. Empty overrides leave the fail-closed
    public-URL policy unchanged.
    """
    global _TEST_POLICY
    hosts = frozenset(str(item).strip().rstrip(".").lower() for item in allow_hosts if str(item).strip())
    addresses = frozenset(str(item).strip() for item in allow_addresses if str(item).strip())
    installed = _TestNetworkPolicy(resolver=resolver, allow_hosts=hosts, allow_addresses=addresses)
    with _TEST_POLICY_LOCK:
        previous = _TEST_POLICY
        _TEST_POLICY = installed
    try:
        yield installed
    finally:
        with _TEST_POLICY_LOCK:
            _TEST_POLICY = previous


def _is_public_address(value: str) -> bool:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except ValueError:
        return False
    return bool(address.is_global)


def _host_test_allowed(host: str, addresses: set[str], policy: _TestNetworkPolicy) -> bool:
    if host in policy.allow_hosts:
        return True
    if addresses and addresses.issubset(policy.allow_addresses):
        return True
    return False


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
    resolver: Resolver | None = None,
    allow_hosts: Iterable[str] | None = None,
    allow_addresses: Iterable[str] | None = None,
) -> dict[str, Any]:
    """Validate an outbound URL and return its public resolution evidence.

    The policy is deliberately fail-closed. A hostname is rejected when any
    resolved address is non-public, preventing mixed public/private DNS answers
    from being used as a rebinding or redirect path into the cluster network.

    Optional ``allow_hosts`` / ``allow_addresses`` (and the test-only context
    manager) exist solely for deterministic fixtures. They are never set by
    production call sites.
    """

    policy = _active_test_policy()
    active_resolver = resolver or policy.resolver or socket.getaddrinfo
    extra_hosts = frozenset(str(item).strip().rstrip(".").lower() for item in (allow_hosts or ()) if str(item).strip())
    extra_addresses = frozenset(str(item).strip() for item in (allow_addresses or ()) if str(item).strip())
    effective = _TestNetworkPolicy(
        resolver=active_resolver if active_resolver is not socket.getaddrinfo else policy.resolver,
        allow_hosts=policy.allow_hosts | extra_hosts,
        allow_addresses=policy.allow_addresses | extra_addresses,
    )

    parsed = urlsplit(str(url or "").strip())
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("item URL must use http or https")
    if parsed.username or parsed.password:
        raise ValueError("credentials must not be embedded in item URLs")

    host = parsed.hostname.rstrip(".").lower()
    test_host_allowed = host in effective.allow_hosts
    if not test_host_allowed and (
        host in _BLOCKED_HOSTS or any(host.endswith(suffix) for suffix in _BLOCKED_HOST_SUFFIXES)
    ):
        raise ValueError(f"target host is internal or local: {host}")

    try:
        literal = ipaddress.ip_address(host.split("%", 1)[0])
    except ValueError:
        literal = None
    if literal is not None:
        addresses = {str(literal)}
        if not literal.is_global and not _host_test_allowed(host, addresses, effective):
            raise ValueError(f"target address is not public: {literal}")
    else:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        addresses = _resolved_addresses(host, port, resolver=active_resolver)
        if not _host_test_allowed(host, addresses, effective):
            rejected = sorted(address for address in addresses if not _is_public_address(address))
            if rejected:
                raise ValueError(
                    f"target host resolves to non-public address(es): {host} -> {', '.join(rejected)}"
                )

    evidence = {
        "url": parsed.geturl(),
        "scheme": parsed.scheme,
        "host": host,
        "resolved_addresses": sorted(addresses),
        "port": parsed.port or (443 if parsed.scheme == "https" else 80),
        "path": parsed.path or "/",
        "query": parsed.query,
    }
    # Keep the public evidence shape stable; only mark fixture-allowed targets
    # when a non-public address was intentionally accepted for tests.
    if _host_test_allowed(host, addresses, effective) and any(
        not _is_public_address(address) for address in addresses
    ):
        evidence["test_policy_allowed"] = True
    return evidence


def pick_pinned_address(evidence: dict[str, Any]) -> str:
    """Prefer IPv4 public address for pinned sockets."""
    addresses = [str(a) for a in (evidence.get("resolved_addresses") or [])]
    allow_non_public = bool(evidence.get("test_policy_allowed"))
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if parsed.version == 4 and (parsed.is_global or allow_non_public):
            return str(parsed)
    for address in addresses:
        try:
            parsed = ipaddress.ip_address(address.split("%", 1)[0])
        except ValueError:
            continue
        if parsed.is_global or allow_non_public:
            return str(parsed)
    raise ValueError("no public address available to pin")


def open_pinned_public_url(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    timeout: float = 60.0,
    method: str = "GET",
    resolver: Resolver | None = None,
    allow_hosts: Iterable[str] | None = None,
    allow_addresses: Iterable[str] | None = None,
):
    """Open an HTTP(S) URL by connecting to a validated public IP (DNS pin).

    Sets Host / SNI to the original hostname so virtual-hosted APIs still work,
    while the TCP connection cannot be rebound to a private address after check.
    """
    import http.client
    import ssl
    from email.message import Message

    evidence = validate_public_http_url(
        url,
        resolver=resolver,
        allow_hosts=allow_hosts,
        allow_addresses=allow_addresses,
    )
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

