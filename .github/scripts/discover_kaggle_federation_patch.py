from pathlib import Path


def replace_once(path: str, old: str, new: str, label: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected one match in {path}, found {count}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


source_path = "drive/scripts/research_data_mcp/discover_source_search.py"
replace_once(
    source_path,
    '_LIVE_ADAPTERS = frozenset({"huggingface", "datacite", "zenodo", "openalex"})',
    '_LIVE_ADAPTERS = frozenset({"huggingface", "kaggle", "datacite", "zenodo", "openalex"})',
    "register Kaggle live adapter",
)
replace_once(
    source_path,
    '''_LIVE_CONNECTOR_BY_PROVIDER = {\n    "hugging face": "huggingface",\n''',
    '''_LIVE_CONNECTOR_BY_PROVIDER = {\n    "hugging face": "huggingface",\n    "kaggle": "kaggle",\n''',
    "map Kaggle provider identity",
)
replace_once(
    source_path,
    '''def _live_search_datacite(query: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:\n''',
    '''def _live_search_kaggle(query: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:\n    """Bounded Kaggle dataset search through the official dataset-list API.\n\n    Kaggle is a provider, not a new Discover mode. Results are normalized into\n    the same inspect-first live candidate contract as Hugging Face/DataCite and\n    still have to pass Discover's evidence-relevance gate before surfacing.\n    """\n    meta: dict[str, Any] = {"adapter": "kaggle", "ok": False, "error": None, "returned": 0}\n    try:\n        from scripts.research_data_mcp.kaggle_catalog import search_datasets\n\n        payload = search_datasets(query, limit=limit, timeout=_LIVE_TIMEOUT_SEC)\n        status = str(payload.get("status") or "").strip()\n        meta["auth_mode"] = payload.get("auth_mode")\n        meta["http_status"] = payload.get("http_status")\n        if status != "ok":\n            meta["error"] = status or "kaggle_search_unavailable"\n            meta["auth_required"] = status == "authentication_required"\n            meta["rate_limited"] = status == "rate_limited"\n            return [], meta\n\n        rows_out: list[dict[str, Any]] = []\n        for item in (payload.get("datasets") or [])[: max(0, int(limit or 0))]:\n            ref = str(item.get("ref") or "").strip()\n            if not ref:\n                continue\n            notes = " · ".join(\n                str(value).strip()\n                for value in (\n                    item.get("subtitle"),\n                    item.get("license"),\n                    f"{item.get('total_bytes')} bytes" if item.get("total_bytes") is not None else "",\n                    f"updated {item.get('updated_at')}" if item.get("updated_at") else "",\n                )\n                if str(value or "").strip()\n            )\n            row = _normalize_live_candidate(\n                provider="Kaggle",\n                title=str(item.get("title") or ref),\n                url=f"https://www.kaggle.com/datasets/{ref}",\n                external_id=ref,\n                capabilities=["kaggle_dataset", *(item.get("tags") or [])[:6]],\n                availability=str(item.get("license") or "kaggle_catalog"),\n                notes=notes,\n            )\n            row["license"] = item.get("license")\n            row["size_bytes"] = item.get("total_bytes")\n            row["updated_at"] = item.get("updated_at")\n            row["usability_rating"] = item.get("usability_rating")\n            rows_out.append({k: v for k, v in row.items() if v not in (None, "", [], {})})\n        meta.update({"ok": True, "returned": len(rows_out)})\n        return rows_out, meta\n    except Exception as exc:  # noqa: BLE001\n        meta["error"] = f"{type(exc).__name__}: {exc}"[:240]\n        return [], meta\n\n\ndef _live_search_datacite(query: str, *, limit: int) -> tuple[list[dict[str, Any]], dict[str, Any]]:\n''',
    "add Kaggle adapter implementation",
)
replace_once(
    source_path,
    '''    adapters = (\n        ("huggingface", _live_search_huggingface),\n        ("datacite", _live_search_datacite),\n''',
    '''    adapters = (\n        ("huggingface", _live_search_huggingface),\n        ("kaggle", _live_search_kaggle),\n        ("datacite", _live_search_datacite),\n''',
    "dispatch Kaggle with live federation",
)

Path("drive/scripts/research_data_mcp/kaggle_catalog.py").write_text(r'''"""Bounded Kaggle dataset catalogue client for Discover federation.

This module is intentionally read-only. It searches Kaggle's official dataset
catalogue and returns metadata only; acquisition remains a separate Discover
proposal/review/approval decision.
"""

from __future__ import annotations

import os
from typing import Any

import requests

_KAGGLE_DATASETS_LIST = "https://www.kaggle.com/api/v1/datasets/list"


def _auth_kwargs() -> tuple[dict[str, Any], str]:
    # Current Kaggle CLI/API tokens can be supplied directly as bearer tokens.
    token = str(os.environ.get("KAGGLE_API_TOKEN") or os.environ.get("KAGGLE_ACCESS_TOKEN") or "").strip()
    if token:
        return {"headers": {"Authorization": f"Bearer {token}"}}, "bearer"

    # Preserve compatibility with the long-standing username/API-key pair.
    username = str(os.environ.get("KAGGLE_USERNAME") or "").strip()
    key = str(os.environ.get("KAGGLE_KEY") or "").strip()
    if username and key:
        return {"auth": (username, key)}, "basic"
    return {}, "anonymous"


def _dataset_rows(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("datasets", "results", "items"):
        rows = payload.get(key)
        if isinstance(rows, list):
            return [row for row in rows if isinstance(row, dict)]
    return []


def _normalize_dataset(row: dict[str, Any]) -> dict[str, Any] | None:
    owner = str(row.get("ownerRef") or row.get("ownerSlug") or row.get("ownerName") or "").strip()
    slug = str(row.get("slug") or "").strip()
    ref = str(row.get("ref") or row.get("id") or "").strip()
    if not ref and owner and slug:
        ref = f"{owner}/{slug}"
    if not ref or "/" not in ref:
        return None

    tags_raw = row.get("tags") or []
    tags: list[str] = []
    if isinstance(tags_raw, list):
        for tag in tags_raw[:12]:
            if isinstance(tag, dict):
                value = tag.get("name") or tag.get("slug") or tag.get("ref")
            else:
                value = tag
            value_s = str(value or "").strip()
            if value_s:
                tags.append(value_s)

    total = row.get("totalBytes")
    try:
        total_bytes = int(total) if total not in (None, "") else None
    except (TypeError, ValueError):
        total_bytes = None

    usability = row.get("usabilityRating")
    try:
        usability_rating = float(usability) if usability not in (None, "") else None
    except (TypeError, ValueError):
        usability_rating = None

    return {
        "ref": ref,
        "title": str(row.get("title") or ref).strip(),
        "subtitle": str(row.get("subtitle") or row.get("description") or "").strip()[:500],
        "license": str(row.get("licenseName") or row.get("license") or "").strip(),
        "total_bytes": total_bytes,
        "updated_at": str(row.get("lastUpdated") or row.get("updatedAt") or row.get("lastUpdatedTime") or "").strip(),
        "usability_rating": usability_rating,
        "tags": tags,
    }


def search_datasets(query: str, *, limit: int = 5, timeout: float = 8.0) -> dict[str, Any]:
    """Search Kaggle dataset metadata without downloading or subscribing.

    Authentication failures and rate limits are returned as explicit states so
    Discover cannot convert missing access into an empty-search claim.
    """
    q = str(query or "").strip()
    bounded = min(max(int(limit or 0), 1), 20)
    if not q:
        return {"status": "empty_query", "datasets": [], "returned": 0, "auth_mode": "none"}

    auth_kwargs, auth_mode = _auth_kwargs()
    try:
        response = requests.get(
            _KAGGLE_DATASETS_LIST,
            params={"search": q, "page": 1, "pageSize": bounded, "sortBy": "hottest"},
            timeout=max(1.0, min(float(timeout), 15.0)),
            **auth_kwargs,
        )
    except requests.RequestException as exc:
        return {
            "status": "network_unavailable",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "error": f"{type(exc).__name__}: {exc}"[:240],
        }

    if response.status_code in {401, 403}:
        return {
            "status": "authentication_required",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }
    if response.status_code == 429:
        return {
            "status": "rate_limited",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }
    if not response.ok:
        return {
            "status": "provider_error",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }

    try:
        raw_rows = _dataset_rows(response.json())
    except ValueError:
        return {
            "status": "invalid_response",
            "datasets": [],
            "returned": 0,
            "auth_mode": auth_mode,
            "http_status": response.status_code,
        }

    datasets = []
    for raw in raw_rows:
        normalized = _normalize_dataset(raw)
        if normalized:
            datasets.append(normalized)
        if len(datasets) >= bounded:
            break
    return {
        "status": "ok",
        "datasets": datasets,
        "returned": len(datasets),
        "auth_mode": auth_mode,
        "http_status": response.status_code,
    }
''', encoding="utf-8")

Path("tests/test_discover_kaggle_federation.py").write_text(r'''from __future__ import annotations

from pathlib import Path

from scripts.research_data_mcp import kaggle_catalog


class _Response:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload
        self.ok = 200 <= status_code < 300

    def json(self):
        return self._payload


def test_kaggle_catalog_is_bounded_and_uses_bearer_token(monkeypatch):
    seen = {}

    def fake_get(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return _Response(
            200,
            [
                {
                    "ref": "researcher/taiwan-governance",
                    "title": "Taiwan governance board data",
                    "subtitle": "Issuer-level board and governance observations",
                    "licenseName": "CC BY 4.0",
                    "totalBytes": 123456,
                    "lastUpdated": "2026-08-20T00:00:00Z",
                    "usabilityRating": 0.9,
                    "tags": [{"name": "governance"}, {"name": "taiwan"}],
                },
                {"ref": "researcher/second", "title": "Second dataset"},
            ],
        )

    monkeypatch.setenv("KAGGLE_API_TOKEN", "KGAT_test_token")
    monkeypatch.setattr(kaggle_catalog.requests, "get", fake_get)

    out = kaggle_catalog.search_datasets("Taiwan governance", limit=1)

    assert out["status"] == "ok"
    assert out["auth_mode"] == "bearer"
    assert out["returned"] == 1
    assert out["datasets"][0]["ref"] == "researcher/taiwan-governance"
    assert out["datasets"][0]["license"] == "CC BY 4.0"
    assert seen["headers"]["Authorization"] == "Bearer KGAT_test_token"
    assert seen["params"]["search"] == "Taiwan governance"
    assert seen["params"]["pageSize"] == 1


def test_kaggle_catalog_reports_access_and_rate_limits_without_empty_claim(monkeypatch):
    monkeypatch.delenv("KAGGLE_API_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_ACCESS_TOKEN", raising=False)
    monkeypatch.delenv("KAGGLE_USERNAME", raising=False)
    monkeypatch.delenv("KAGGLE_KEY", raising=False)

    monkeypatch.setattr(kaggle_catalog.requests, "get", lambda *_args, **_kwargs: _Response(401, {}))
    auth = kaggle_catalog.search_datasets("governance")
    assert auth["status"] == "authentication_required"
    assert auth["auth_mode"] == "anonymous"
    assert auth["datasets"] == []

    monkeypatch.setattr(kaggle_catalog.requests, "get", lambda *_args, **_kwargs: _Response(429, {}))
    limited = kaggle_catalog.search_datasets("governance")
    assert limited["status"] == "rate_limited"
    assert limited["datasets"] == []


def test_live_federation_surfaces_kaggle_through_existing_candidate_contract(monkeypatch):
    from scripts.research_data_mcp import discover_source_search as mod

    monkeypatch.setattr(
        kaggle_catalog,
        "search_datasets",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "auth_mode": "bearer",
            "http_status": 200,
            "datasets": [
                {
                    "ref": "researcher/taiwan-governance",
                    "title": "Taiwan governance board data",
                    "subtitle": "Taiwan issuer governance and board observations",
                    "license": "CC BY 4.0",
                    "total_bytes": 123456,
                    "updated_at": "2026-08-20T00:00:00Z",
                    "usability_rating": 0.9,
                    "tags": ["taiwan", "governance", "board"],
                }
            ],
        },
    )
    for name in ("huggingface", "datacite", "zenodo", "openalex"):
        monkeypatch.setattr(
            mod,
            f"_live_search_{name}",
            lambda _query, *, limit, name=name: (
                [], {"adapter": name, "ok": True, "error": None, "returned": 0}
            ),
        )

    root = Path(__file__).resolve().parents[1] / "drive"
    out = mod.search_discover_sources(root, "Taiwan governance board", limit=10, live=True)

    adapters = {row["adapter"]: row for row in out["remote_search"]["adapters"]}
    assert adapters["kaggle"]["ok"] is True
    assert adapters["kaggle"]["returned"] >= 1
    rows = [row for row in out["results"] if row.get("provider") == "Kaggle"]
    assert rows
    row = rows[0]
    assert row["kind"] == "live_candidate"
    assert row["connector_id"] == "kaggle"
    assert row["candidate_key"] == "source:kaggle:researcher/taiwan-governance"
    assert row["license"] == "CC BY 4.0"
    assert row["url"] == "https://www.kaggle.com/datasets/researcher/taiwan-governance"
''', encoding="utf-8")

print("Applied bounded Kaggle federation through the existing Discover live-candidate contract")
