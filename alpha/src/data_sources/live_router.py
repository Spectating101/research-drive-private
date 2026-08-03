from __future__ import annotations

import os
from typing import Optional

from api.data_sources.aggregator import DataPriority, DataSourceAggregator
from api.data_sources.alphavantage_source import AlphaVantageSource
from api.data_sources.finnhub_source import FinnhubSource
from api.data_sources.polygon_source import PolygonSource
from api.data_sources.sec_edgar import SECEdgarSource
from api.data_sources.yfinance_source import YFinanceSource


def build_aggregator(redis_client=None) -> DataSourceAggregator:
    """
    Register all supported live sources with a sane priority order.

    Priority philosophy:
    - Polygon: primary for real-time quotes if available
    - AlphaVantage: primary for historical/fundamentals if available
    - YFinance: always available fallback for market prices
    - Finnhub: news/sentiment/earnings
    - SEC EDGAR: authoritative fundamentals/filings (no key needed but user agent matters)
    """
    agg = DataSourceAggregator(redis_client=redis_client)

    # Always register Yahoo fallback.
    agg.register_source(YFinanceSource({}), priority=DataPriority.FALLBACK)

    polygon_key = os.getenv("POLYGON_API_KEY") or os.getenv("POLYGON_KEY")
    if polygon_key:
        agg.register_source(PolygonSource({"api_key": polygon_key}), priority=DataPriority.PRIMARY)

    av_key = os.getenv("ALPHAVANTAGE_API_KEY") or os.getenv("ALPHA_VANTAGE_API_KEY")
    if av_key:
        agg.register_source(AlphaVantageSource({"api_key": av_key}), priority=DataPriority.SECONDARY)

    finnhub_key = os.getenv("FINNHUB_API_KEY")
    if finnhub_key:
        agg.register_source(FinnhubSource({"api_key": finnhub_key}), priority=DataPriority.SECONDARY)

    # SEC EDGAR has no API key, but requires a descriptive User-Agent.
    sec_user_agent = os.getenv("SEC_USER_AGENT") or "Sharpe-Renaissance/0.1 (contact: local@example.com)"
    agg.register_source(SECEdgarSource({"user_agent": sec_user_agent}), priority=DataPriority.SECONDARY)

    return agg


def any_live_keys_configured() -> bool:
    return bool(
        os.getenv("POLYGON_API_KEY")
        or os.getenv("POLYGON_KEY")
        or os.getenv("ALPHAVANTAGE_API_KEY")
        or os.getenv("ALPHA_VANTAGE_API_KEY")
        or os.getenv("FINNHUB_API_KEY")
    )

