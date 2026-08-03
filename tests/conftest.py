import os
import socket
import sys
from collections.abc import Iterator
from pathlib import Path
from urllib.parse import urlsplit

import pytest

import pytest

# Ensure project root is on sys.path for tests
ROOT = Path(__file__).resolve().parent.parent
for candidate in (ROOT, ROOT / "drive", ROOT / "kernel"):
    text = str(candidate)
    if text not in sys.path:
        sys.path.insert(0, text)

KERNEL = ROOT / "kernel"
if KERNEL.is_dir() and str(KERNEL) not in sys.path:
    sys.path.insert(0, str(KERNEL))

# Default to mock mode for tests to avoid external dependencies
os.environ.setdefault("MODE", "mock")


def _public_fixture_resolver(host: str, port: int, *, type: int = socket.SOCK_STREAM):  # noqa: A002
    """Deterministic public A-record for fixture hostnames such as example.test."""
    del type
    host_key = str(host or "").rstrip(".").lower()
    if host_key in {"example.test", "www.example.test"}:
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", port))]
    return socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)


@pytest.fixture
def public_fixture_network_policy() -> Iterator[None]:
    """Resolve example.test-style fixtures without weakening production SSRF policy."""
    from scripts.cluster_agent.network_policy import test_network_policy

    # Resolver returns a public A-record only — no private-address allow-list.
    with test_network_policy(resolver=_public_fixture_resolver):
        yield


@pytest.fixture
def loopback_collect_network_policy() -> Iterator[None]:
    """Allow deterministic loopback HTTP fixtures for remote_collect tests only."""
    from scripts.cluster_agent.network_policy import test_network_policy

    with test_network_policy(allow_hosts=("127.0.0.1", "::1"), allow_addresses=("127.0.0.1", "::1")):
        yield


@pytest.fixture(autouse=True)
def deterministic_example_test_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """Resolve the reserved test domain without relying on external DNS.

    The production validator still evaluates the synthetic public address, so
    tests exercise the SSRF policy instead of bypassing it.
    """
    from scripts.cluster_agent import network_policy

    validate_public_http_url = network_policy.validate_public_http_url

    def example_test_resolver(host: str, port: int, **_kwargs):
        if host != "example.test":
            raise socket.gaierror(socket.EAI_NONAME, "test resolver only handles example.test")
        return [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", port),
            )
        ]

    def validate_with_test_dns(url: str, *, resolver=None):
        if resolver is not None:
            return validate_public_http_url(url, resolver=resolver)
        if urlsplit(str(url)).hostname == "example.test":
            return validate_public_http_url(url, resolver=example_test_resolver)
        return validate_public_http_url(url)

    monkeypatch.setattr(network_policy, "validate_public_http_url", validate_with_test_dns)
