from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import os
import pandas as pd

from data_tools.feature_store import load_market_panel_any
from src.data_sources.live_router import any_live_keys_configured, build_aggregator
from api.models.user import PricingTier
from sharpe_kernel.paths import repo_root_from_file


class MarketDataInterval(str, Enum):
    ONE_DAY = "1d"


def _period_to_days(period: str) -> int:
    period = (period or "").strip().lower()
    mapping = {
        "1mo": 31,
        "3mo": 93,
        "6mo": 186,
        "1y": 366,
        "2y": 366 * 2,
        "5y": 366 * 5,
        "max": 366 * 50,
    }
    return mapping.get(period, 366)


@lru_cache(maxsize=1)
def _offline_panel() -> pd.DataFrame:
    base_dir = repo_root_from_file(__file__)
    return load_market_panel_any(base_dir / "From-refinitiv")


async def get_real_time_quote(ticker: str) -> Dict[str, Any]:
    """
    Fetch a best-effort real-time-ish quote via yfinance.

    Note: yfinance is not truly real-time for many instruments and may be delayed.
    """
    import yfinance as yf

    data: Dict[str, Any] = {"ticker": ticker}
    t = yf.Ticker(ticker)
    info = getattr(t, "fast_info", None)
    if info:
        price = info.get("last_price") or info.get("lastPrice")
        if price is not None:
            data["price"] = float(price)

    if "price" not in data:
        hist = t.history(period="5d", interval="1d")
        if not hist.empty and "Close" in hist.columns:
            data["price"] = float(hist["Close"].dropna().iloc[-1])
            data["timestamp"] = hist.index[-1].isoformat()

    data.setdefault("source", "yfinance")
    return data


async def get_historical_data(ticker: str, period: str = "1y", interval: str = "1d") -> List[Dict[str, Any]]:
    """
    Fetch historical OHLCV via yfinance and normalize to the API's expected schema.
    """
    import yfinance as yf

    df = yf.download(ticker, period=period, interval=interval, auto_adjust=False, progress=False)
    if df is None or df.empty:
        return []

    df = df.reset_index()
    # yfinance can name the date column "Date" or "Datetime"
    date_col = "Date" if "Date" in df.columns else ("Datetime" if "Datetime" in df.columns else None)
    if date_col is None:
        return []

    out: List[Dict[str, Any]] = []
    for row in df.itertuples(index=False):
        dt = getattr(row, date_col)
        out.append(
            {
                "ticker": ticker,
                "date": pd.Timestamp(dt).isoformat(),
                "open": float(getattr(row, "Open")),
                "high": float(getattr(row, "High")),
                "low": float(getattr(row, "Low")),
                "close": float(getattr(row, "Close")),
                "volume": float(getattr(row, "Volume")) if hasattr(row, "Volume") else None,
                "source": "yfinance",
            }
        )
    return out


@dataclass(slots=True)
class MarketDataSource:
    """
    Minimal market data source used by the API routes.

    In this workspace snapshot we implement an offline loader backed by the
    local Refinitiv patch CSVs (or a tidy panel, if present).
    """

    config: Dict[str, Any]
    prefer_live: bool = True

    def __post_init__(self) -> None:
        # Allow forcing offline behavior even in non-mock runs.
        if os.getenv("OFFLINE_ONLY", "").strip() == "1":
            self.prefer_live = False

    async def get_historical_prices(
        self,
        ticker: str,
        period: str = "3mo",
        interval: MarketDataInterval = MarketDataInterval.ONE_DAY,
    ) -> List[Dict[str, Any]]:
        mode = (self.config.get("mode") or "").strip().lower() or os.getenv("MODE", "mock").lower()

        if self.prefer_live and mode != "mock" and any_live_keys_configured():
            try:
                agg = build_aggregator(redis_client=None)
                interval_str = "1d" if interval == MarketDataInterval.ONE_DAY else str(interval)
                records = await agg.get_historical_data(
                    ticker=ticker,
                    tier=PricingTier.PROFESSIONAL,
                    period=period,
                    interval=interval_str,
                )
                if records:
                    return [
                        {
                            "date": r.get("date") or r.get("timestamp"),
                            "open": r.get("open"),
                            "high": r.get("high"),
                            "low": r.get("low"),
                            "close": r.get("close"),
                            "volume": r.get("volume"),
                        }
                        for r in records
                    ]
            except Exception:
                # Fall back to offline below.
                pass

        if interval != MarketDataInterval.ONE_DAY:
            raise ValueError(f"Unsupported interval in offline mode: {interval}")

        panel = _offline_panel()
        if not {"Instrument", "Date", "Price_Close"}.issubset(set(panel.columns)):
            raise ValueError("Offline panel is not in tidy format.")

        df = panel[panel["Instrument"].astype(str) == str(ticker)].copy()
        if df.empty:
            return []

        df = df.dropna(subset=["Date"]).sort_values("Date").drop_duplicates(subset=["Date"], keep="last")
        df["Price_Close"] = pd.to_numeric(df["Price_Close"], errors="coerce")
        if "Volume" in df.columns:
            df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")
        else:
            df["Volume"] = pd.NA

        cutoff = df["Date"].max() - pd.Timedelta(days=_period_to_days(period))
        df = df[df["Date"] >= cutoff]

        records: List[Dict[str, Any]] = []
        for row in df.itertuples(index=False):
            close = float(getattr(row, "Price_Close"))
            volume = getattr(row, "Volume", None)
            records.append(
                {
                    "date": pd.Timestamp(getattr(row, "Date")).isoformat(),
                    "open": close,
                    "high": close,
                    "low": close,
                    "close": close,
                    "volume": None if volume is None or pd.isna(volume) else float(volume),
                }
            )
        return records

    async def get_realtime_quote(self, ticker: str) -> Optional[Dict[str, Any]]:
        mode = (self.config.get("mode") or "").strip().lower() or os.getenv("MODE", "mock").lower()

        if self.prefer_live and mode != "mock" and any_live_keys_configured():
            try:
                agg = build_aggregator(redis_client=None)
                quote = await agg.get_real_time_quote(
                    ticker=ticker,
                    tier=PricingTier.PROFESSIONAL,
                    include_fundamentals=False,
                )
                if quote and quote.get("price") is not None:
                    return quote
            except Exception:
                pass

        prices = await self.get_historical_prices(ticker=ticker, period="1mo")
        if not prices:
            return None
        last = prices[-1]
        return {
            "ticker": ticker,
            "price": last["close"],
            "timestamp": last["date"],
            "source": "offline_refinitiv_patch",
        }


__all__ = ["MarketDataInterval", "MarketDataSource"]
