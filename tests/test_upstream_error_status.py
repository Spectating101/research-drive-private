"""An upstream catalogue's "no such record" is not this server failing.

Found by sweeping all 61 GET routes against a loopback instance: /library/doi and
/library/extensions/datacite/doi returned 500 with the message "HTTP Error 404:
Not Found" for a DOI that does not exist. The route works — a real DOI returns
200 — but a client could not tell a missing record from a broken desk, and the
route had no test naming it.

The dispatcher mapped PermissionError, KeyError and ValueError to 403/404/400 and
everything else to 500, so urllib's HTTPError fell through to "our fault".
"""

from __future__ import annotations

import urllib.error

import pytest

from scripts.research_data_mcp import http_router


def _dispatch(exc: Exception) -> dict:
    """Drive the real dispatcher's error mapping with a handler that raises.

    Registers a temporary route so this exercises _dispatch itself rather than a
    reimplementation of its mapping.
    """
    path = "/library/__upstream_probe__"
    name = "probe_raiser"

    def raiser(stack, query, payload, params):
        raise exc

    http_router._HANDLERS[name] = raiser
    http_router.ROUTE_CATALOG.append({"method": "GET", "path": path, "handler": name})
    try:
        return http_router._dispatch("GET", path, {}, {}, None)
    finally:
        http_router._HANDLERS.pop(name, None)
        http_router.ROUTE_CATALOG[:] = [r for r in http_router.ROUTE_CATALOG if r["path"] != path]


def _http_error(code: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("https://api.datacite.org/dois/x", code, "boom", {}, None)


def test_an_upstream_404_is_reported_as_not_found():
    out = _dispatch(_http_error(404))
    assert out["status"] == 404
    assert out["body"]["error"] == "not_found_upstream"
    assert out["body"]["upstream_status"] == 404


@pytest.mark.parametrize("code", [403, 429, 500, 503])
def test_any_other_upstream_failure_is_a_gateway_error(code):
    """502 says the upstream failed. 500 would claim this server did."""
    out = _dispatch(_http_error(code))
    assert out["status"] == 502
    assert out["body"]["error"] == "upstream_error"
    assert out["body"]["upstream_status"] == code


def test_an_unreachable_upstream_is_a_timeout_not_a_crash():
    out = _dispatch(urllib.error.URLError("name or service not known"))
    assert out["status"] == 504
    assert out["body"]["error"] == "upstream_unreachable"


def test_a_genuine_internal_fault_is_still_a_500():
    """Only upstream problems were reclassified; our own bugs stay ours."""
    out = _dispatch(TypeError("a real bug in this process"))
    assert out["status"] == 500
    assert out["body"]["error"] == "TypeError"


@pytest.mark.parametrize("exc,status", [
    (PermissionError("nope"), 403),
    (KeyError("missing"), 404),
    (ValueError("bad input"), 400),
])
def test_the_existing_mappings_are_unchanged(exc, status):
    assert _dispatch(exc)["status"] == status
