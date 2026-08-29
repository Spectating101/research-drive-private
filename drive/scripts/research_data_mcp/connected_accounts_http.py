#!/usr/bin/env python3
"""HTTP bindings for principal-bound Research Drive connected accounts."""

from __future__ import annotations

from typing import Any

from scripts.research_data_mcp.connected_accounts import (
    complete_oauth,
    connected_accounts_document,
    disconnect_connected_account,
    start_oauth,
    verify_connected_account,
)
from scripts.research_data_mcp.connected_accounts_security import (
    ensure_encrypted_credential_store,
    public_connected_account,
    public_connected_accounts_document,
)

CONNECTED_ACCOUNT_ROUTES: list[dict[str, str]] = [
    {"method": "GET", "path": "/library/accounts", "handler": "library_accounts"},
    {"method": "POST", "path": "/library/accounts/oauth/start", "handler": "library_accounts_oauth_start"},
    {"method": "POST", "path": "/library/accounts/oauth/complete", "handler": "library_accounts_oauth_complete"},
    {"method": "POST", "path": "/library/accounts/{account_id}/verify", "handler": "library_accounts_verify"},
    {"method": "POST", "path": "/library/accounts/{account_id}/disconnect", "handler": "library_accounts_disconnect"},
]


def connected_account_handlers() -> dict[str, Any]:
    def repo_root(stack):
        return stack.gateway.repo_root

    def library_accounts(stack, query, payload, params):
        return public_connected_accounts_document(connected_accounts_document(repo_root(stack)))

    def library_accounts_oauth_start(stack, query, payload, params):
        # Establish and prove encryption before an OAuth authorization code can
        # ever be exchanged for credentials on this host.
        ensure_encrypted_credential_store(repo_root(stack), initialize=True)
        return start_oauth(
            repo_root(stack),
            provider=str(payload.get("provider") or ""),
            access_mode=str(payload.get("access_mode") or "read"),
        )

    def library_accounts_oauth_complete(stack, query, payload, params):
        ensure_encrypted_credential_store(repo_root(stack))
        return {
            "ok": True,
            "account": public_connected_account(
                complete_oauth(
                    repo_root(stack),
                    provider=str(payload.get("provider") or ""),
                    state=str(payload.get("state") or ""),
                    code=str(payload.get("code") or ""),
                )
            ),
        }

    def library_accounts_verify(stack, query, payload, params):
        ensure_encrypted_credential_store(repo_root(stack))
        return {
            "ok": True,
            "account": public_connected_account(
                verify_connected_account(
                    repo_root(stack), account_id=str(params["account_id"])
                )
            ),
        }

    def library_accounts_disconnect(stack, query, payload, params):
        ensure_encrypted_credential_store(repo_root(stack))
        return disconnect_connected_account(
            repo_root(stack), account_id=str(params["account_id"])
        )

    return {
        "library_accounts": library_accounts,
        "library_accounts_oauth_start": library_accounts_oauth_start,
        "library_accounts_oauth_complete": library_accounts_oauth_complete,
        "library_accounts_verify": library_accounts_verify,
        "library_accounts_disconnect": library_accounts_disconnect,
    }
