#!/usr/bin/env python3
"""Credential and license gates before procurement."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.research_data_mcp.credential_vault import credential_for_url, has_license_approval
from scripts.research_data_mcp.procureability import BADGE_NEEDS_CREDENTIALS, badge_label, badge_tone


def classify_collect_gate(
    *,
    url: str = "",
    license_text: str = "",
    governance_class: str = "",
    repository: str = "",
    doi: str = "",
    repo_root: Path | str | None = None,
) -> dict[str, Any]:
    """Return whether auto-collect is allowed and if user approval is required."""
    blocked_reason = ""
    needs_approval = False
    root = Path(repo_root) if repo_root else None

    if governance_class == "commercial":
        blocked_reason = "commercial data source — credentials required"
    elif governance_class == "credentials_required":
        blocked_reason = "source requires authenticated access"

    license_lower = (license_text or "").lower()
    license_gate = False
    if any(token in license_lower for token in ("restricted", "request access", "upon request", "cc-by-nc")):
        needs_approval = True
        license_gate = True
        if "cc-by-nc" in license_lower:
            blocked_reason = blocked_reason or "non-commercial license — confirm usage before collect"
        else:
            blocked_reason = blocked_reason or "restricted license — confirm before collect"

    if not repository or repository == "unknown":
        blocked_reason = blocked_reason or "repository not supported for automatic download"

    cred = credential_for_url(root, url) if root and url else None
    if (
        cred
        and cred.get("required")
        and not cred.get("token_present")
        and cred.get("env_var")
    ):
        blocked_reason = blocked_reason or f"credential {cred.get('env_var')} not configured"

    if root and license_gate and has_license_approval(root, doi=doi, url=url):
        needs_approval = False
        if license_gate and blocked_reason and (
            "license" in blocked_reason.lower() or "confirm" in blocked_reason.lower()
        ):
            blocked_reason = ""

    allowed = not bool(blocked_reason)

    badges = [BADGE_NEEDS_CREDENTIALS] if blocked_reason and not needs_approval else []
    if needs_approval and not blocked_reason:
        badges.append("needs_approval")

    return {
        "allowed": allowed,
        "needs_approval": needs_approval,
        "blocked_reason": blocked_reason,
        "badges": badges,
        "badge_labels": [badge_label(b) for b in badges],
        "tone": badge_tone(BADGE_NEEDS_CREDENTIALS) if badges else "green",
        "url": url,
        "license": license_text,
        "governance_class": governance_class,
        "credential_profile": cred,
    }
