#!/usr/bin/env python3
"""Research Drive HTTP router with connected-account extensions.

The release-certified router is preserved byte-for-byte in http_router_legacy.
This module adds federated-storage routes without forking its dispatch logic.
"""

from __future__ import annotations

from scripts.research_data_mcp import http_router_legacy as _legacy
from scripts.research_data_mcp.connected_accounts_http import (
    CONNECTED_ACCOUNT_ROUTES,
    connected_account_handlers,
)
from scripts.research_data_mcp.library_federation_http import (
    LIBRARY_FEDERATION_ROUTES,
    library_federation_handlers,
)

for _name in dir(_legacy):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_legacy, _name)

_extensions = [*CONNECTED_ACCOUNT_ROUTES, *LIBRARY_FEDERATION_ROUTES]
_existing = {(row["method"], row["path"]) for row in _legacy.ROUTE_CATALOG}
_legacy.ROUTE_CATALOG = [
    *[
        row
        for row in _extensions
        if (row["method"], row["path"]) not in _existing
    ],
    *_legacy.ROUTE_CATALOG,
]
_legacy._HANDLERS.update(connected_account_handlers())
_legacy._HANDLERS.update(library_federation_handlers())

ROUTE_CATALOG = _legacy.ROUTE_CATALOG
_HANDLERS = _legacy._HANDLERS
handle_get = _legacy.handle_get
handle_post = _legacy.handle_post
