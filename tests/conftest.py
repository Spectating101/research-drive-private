import os
import socket
import sys
from pathlib import Path
from urllib.parse import urlsplit

import pytest

# Ensure project root is on sys.path for tests
ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

KERNEL = ROOT / "kernel"
if KERNEL.is_dir() and str(KERNEL) not in sys.path:
    sys.path.insert(0, str(KERNEL))

# Default to mock mode for tests to avoid external dependencies
os.environ.setdefault("MODE", "mock")


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
