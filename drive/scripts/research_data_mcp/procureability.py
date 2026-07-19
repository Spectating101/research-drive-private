#!/usr/bin/env python3
"""Procureability badges for search and dataset cards."""

from __future__ import annotations

from typing import Any

BADGE_DOWNLOADABLE = "downloadable"
BADGE_METADATA_ONLY = "metadata_only"
BADGE_NEEDS_CREDENTIALS = "needs_credentials"
BADGE_UNKNOWN_REPO = "unknown_repo"
BADGE_FILE_TOO_LARGE = "file_too_large"
BADGE_SAMPLE_ONLY = "sample_only"
BADGE_READY = "ready"
BADGE_PROMOTED = "promoted"
BADGE_HF_REFERENCE = "huggingface_reference"
BADGE_LOCAL = "local_registry"


def badge_label(badge: str) -> str:
    return {
        BADGE_DOWNLOADABLE: "Downloadable",
        BADGE_METADATA_ONLY: "Metadata only",
        BADGE_NEEDS_CREDENTIALS: "Needs credentials",
        BADGE_UNKNOWN_REPO: "Unknown repository",
        BADGE_FILE_TOO_LARGE: "File too large",
        BADGE_SAMPLE_ONLY: "Sample only",
        BADGE_READY: "Ready",
        BADGE_PROMOTED: "In library",
        BADGE_HF_REFERENCE: "On Hugging Face",
        BADGE_LOCAL: "Local registry",
    }.get(badge, badge.replace("_", " ").title())


def badge_tone(badge: str) -> str:
    if badge in {BADGE_DOWNLOADABLE, BADGE_READY, BADGE_PROMOTED, BADGE_LOCAL}:
        return "green"
    if badge in {BADGE_METADATA_ONLY, BADGE_HF_REFERENCE, BADGE_SAMPLE_ONLY}:
        return "blue"
    if badge in {BADGE_FILE_TOO_LARGE, BADGE_UNKNOWN_REPO}:
        return "amber"
    if badge == BADGE_NEEDS_CREDENTIALS:
        return "red"
    return "blue"


def datacite_procureability(resolved: dict[str, Any], *, governance_class: str = "") -> dict[str, Any]:
    files = resolved.get("files") or []
    all_files = resolved.get("all_files") or files
    repository = str(resolved.get("repository") or "")
    badges: list[str] = []

    if governance_class == "commercial":
        badges.append(BADGE_NEEDS_CREDENTIALS)
        return _row(badges, "blocked", can_collect=False, reason="commercial source")

    if not repository or repository == "unknown":
        badges.append(BADGE_UNKNOWN_REPO)
        badges.append(BADGE_METADATA_ONLY)
        return _row(badges, "metadata_only", can_collect=False, reason="no repository adapter")

    if not all_files:
        badges.append(BADGE_METADATA_ONLY)
        return _row(badges, "metadata_only", can_collect=False, reason="no files listed")

    if not files and all_files:
        badges.extend([BADGE_FILE_TOO_LARGE, BADGE_SAMPLE_ONLY])
        return _row(badges, "sample_only", can_collect=False, reason="files exceed size cap")

    badges.append(BADGE_DOWNLOADABLE)
    return _row(badges, "downloadable", can_collect=True, reason="")


def registry_procureability(dataset: dict[str, Any]) -> dict[str, Any]:
    badges = [BADGE_LOCAL]
    readiness = str(dataset.get("analysis_readiness") or "")
    access = str(dataset.get("access_shape") or dataset.get("access_mode") or "")
    if dataset.get("procurement", {}).get("promoted_at"):
        badges.append(BADGE_PROMOTED)
    if readiness == "instant":
        badges.append(BADGE_READY)
    elif readiness == "metadata_search":
        badges.append(BADGE_METADATA_ONLY)
    can_collect = access not in {"ops_status", "credentials_required"}
    return _row(badges, "ready" if BADGE_READY in badges else "local", can_collect=can_collect, reason="")


def hf_reference_procureability(row: dict[str, Any]) -> dict[str, Any]:
    badges = [BADGE_HF_REFERENCE]
    return {
        "badges": badges,
        "badge_labels": [badge_label(b) for b in badges],
        "tone": badge_tone(BADGE_HF_REFERENCE),
        "status": "external_hub",
        "can_collect": False,
        "collect_via": "huggingface",
        "reason": "Load via Hugging Face Hub",
        "hf_id": row.get("id"),
        "hf_url": row.get("url"),
    }


def _row(badges: list[str], status: str, *, can_collect: bool, reason: str) -> dict[str, Any]:
    return {
        "badges": badges,
        "badge_labels": [badge_label(b) for b in badges],
        "tone": badge_tone(badges[0]) if badges else "blue",
        "status": status,
        "can_collect": can_collect,
        "reason": reason,
    }
