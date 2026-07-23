from __future__ import annotations

"""
Thin client for Cite-Finance API (HTTP).

Why this exists:
- Cite-Finance provides cited SEC metrics + consistency scores + AI-ready "insights" endpoints.
- Sharpe-Renaissance can consume those as *inputs* (fundamentals/sentiment/metrics) while keeping
  portfolio logic deterministic.

This module avoids any dependency on running cite-finance locally; it can target a remote URL.
"""

import json
import os
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Dict, List, Optional


@dataclass(frozen=True)
class CiteFinanceConfig:
    base_url: str
    api_key: str = ""

    @staticmethod
    def from_env() -> Optional["CiteFinanceConfig"]:
        base = (os.getenv("CITE_FINANCE_BASE_URL") or "").strip()
        key = (os.getenv("CITE_FINANCE_API_KEY") or "").strip()
        no_auth = (os.getenv("CITE_FINANCE_NO_AUTH") or "").strip().lower() in {"1", "true", "yes", "y"}
        if not base or (not key and not no_auth):
            return None
        return CiteFinanceConfig(base_url=base.rstrip("/"), api_key=key)


class CiteFinanceClient:
    def __init__(self, config: CiteFinanceConfig, *, timeout_s: int = 30):
        self.config = config
        self.timeout_s = int(timeout_s)

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Any:
        url = self.config.base_url + path
        if params:
            url = url + "?" + urllib.parse.urlencode({k: str(v) for k, v in params.items()})
        req = urllib.request.Request(url, method="GET")
        if self.config.api_key:
            req.add_header("X-API-Key", self.config.api_key)
        with urllib.request.urlopen(req, timeout=self.timeout_s) as resp:
            payload = resp.read().decode("utf-8", errors="replace")
        try:
            return json.loads(payload)
        except Exception:
            return payload

    def companies_search(self, q: str) -> Any:
        return self._get("/api/v1/companies/search", {"q": q})

    def metrics(self, ticker: str, metrics: List[str], period: Optional[str] = None) -> Any:
        params: Dict[str, Any] = {"ticker": ticker, "metrics": ",".join(metrics)}
        if period:
            params["period"] = period
        return self._get("/api/v1/metrics", params)

    def insights(self, ticker: str, types: Optional[List[str]] = None, min_confidence: float = 0.6) -> Any:
        params: Dict[str, Any] = {"ticker": ticker, "min_confidence": min_confidence}
        if types:
            params["types"] = ",".join(types)
        return self._get("/api/v1/intelligence/insights", params)

    def recommendation(self, ticker: str) -> Any:
        return self._get("/api/v1/intelligence/recommendation", {"ticker": ticker})


__all__ = ["CiteFinanceClient", "CiteFinanceConfig"]
