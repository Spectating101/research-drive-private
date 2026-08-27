from __future__ import annotations

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
