"""
Real-Time Market Data Source
Integrates with yfinance for live quotes and historical data
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional
from enum import Enum
import structlog

from src.data_sources.base import DataSource, DataSourceCapability, DataSourceType, FinancialData

logger = structlog.get_logger(__name__)


class MarketDataInterval(str, Enum):
    """Market data interval options"""
    ONE_MIN = "1m"
    FIVE_MIN = "5m"
    FIFTEEN_MIN = "15m"
    THIRTY_MIN = "30m"
    ONE_HOUR = "1h"
    ONE_DAY = "1d"
    ONE_WEEK = "1wk"
    ONE_MONTH = "1mo"


class MarketDataSource(DataSource):
    """
    Market data source using yfinance

    Provides:
    - Real-time quotes (15-min delayed for free tier)
    - Historical price data
    - Volume data
    - Pre/post market data
    """

    def __init__(self, config: Dict[str, Any]):
        self.name = "MARKET_DATA"
        self.config = config
        self.capabilities = [
            DataSourceCapability.MARKET_PRICES,
            DataSourceCapability.HISTORICAL_DATA,
        ]

    async def get_realtime_quote(
        self,
        ticker: str,
        extended_hours: bool = False
    ) -> Dict[str, Any]:
        """
        Get real-time quote for a ticker

        Args:
            ticker: Stock symbol
            extended_hours: Include pre/post market data

        Returns:
            Real-time quote data
        """
        try:
            stock = yf.Ticker(ticker)
            info = stock.info

            quote = {
                "ticker": ticker.upper(),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "previous_close": info.get("previousClose"),
                "open": info.get("open") or info.get("regularMarketOpen"),
                "day_high": info.get("dayHigh") or info.get("regularMarketDayHigh"),
                "day_low": info.get("dayLow") or info.get("regularMarketDayLow"),
                "volume": info.get("volume") or info.get("regularMarketVolume"),
                "market_cap": info.get("marketCap"),
                "bid": info.get("bid"),
                "ask": info.get("ask"),
                "bid_size": info.get("bidSize"),
                "ask_size": info.get("askSize"),
                "timestamp": datetime.now().isoformat(),
                "currency": info.get("currency", "USD"),
            }

            # Calculate derived metrics
            if quote["price"] and quote["previous_close"]:
                quote["change"] = quote["price"] - quote["previous_close"]
                quote["change_percent"] = (quote["change"] / quote["previous_close"]) * 100

            # Add extended hours if requested
            if extended_hours:
                quote["pre_market_price"] = info.get("preMarketPrice")
                quote["post_market_price"] = info.get("postMarketPrice")

            logger.info("Fetched realtime quote", ticker=ticker, price=quote.get("price"))
            return quote

        except Exception as e:
            logger.error("Failed to fetch realtime quote", ticker=ticker, error=str(e))
            raise

    async def get_historical_prices(
        self,
        ticker: str,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        interval: MarketDataInterval = MarketDataInterval.ONE_DAY,
        period: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data

        Args:
            ticker: Stock symbol
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            interval: Data interval (1d, 1h, etc.)
            period: Alternative to start/end (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, ytd, max)

        Returns:
            List of historical price records
        """
        try:
            stock = yf.Ticker(ticker)

            # Fetch data
            if period:
                df = stock.history(period=period, interval=interval.value)
            else:
                df = stock.history(start=start_date, end=end_date, interval=interval.value)

            if df.empty:
                logger.warning("No historical data found", ticker=ticker)
                return []

            # Convert to list of dicts
            records = []
            for date, row in df.iterrows():
                records.append({
                    "ticker": ticker.upper(),
                    "date": date.strftime("%Y-%m-%d") if hasattr(date, 'strftime') else str(date),
                    "open": float(row["Open"]) if not pd.isna(row["Open"]) else None,
                    "high": float(row["High"]) if not pd.isna(row["High"]) else None,
                    "low": float(row["Low"]) if not pd.isna(row["Low"]) else None,
                    "close": float(row["Close"]) if not pd.isna(row["Close"]) else None,
                    "volume": int(row["Volume"]) if not pd.isna(row["Volume"]) else None,
                    "interval": interval.value
                })

            logger.info(
                "Fetched historical data",
                ticker=ticker,
                records=len(records),
                start=records[0]["date"] if records else None,
                end=records[-1]["date"] if records else None
            )

            return records

        except Exception as e:
            logger.error("Failed to fetch historical data", ticker=ticker, error=str(e))
            raise

    async def get_intraday_data(
        self,
        ticker: str,
        interval: MarketDataInterval = MarketDataInterval.FIVE_MIN,
        days: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get intraday price data

        Args:
            ticker: Stock symbol
            interval: Interval (1m, 5m, 15m, 30m, 1h)
            days: Number of days back (max 7 for <1h intervals)

        Returns:
            Intraday price records
        """
        # yfinance limits: 1m (7 days), 5m/15m/30m (60 days), 1h (730 days)
        if interval in [MarketDataInterval.ONE_MIN] and days > 7:
            days = 7
        elif interval in [MarketDataInterval.FIVE_MIN, MarketDataInterval.FIFTEEN_MIN, MarketDataInterval.THIRTY_MIN] and days > 60:
            days = 60

        period = f"{days}d"
        return await self.get_historical_prices(ticker, interval=interval, period=period)

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """
        Get financial data (implements DataSource interface)

        For market data source, this returns price-related data
        """
        try:
            quote = await self.get_realtime_quote(ticker)

            results = []
            for concept in concepts:
                if concept == "price":
                    value = quote.get("price")
                elif concept == "market_cap":
                    value = quote.get("market_cap")
                elif concept == "volume":
                    value = quote.get("volume")
                else:
                    continue

                if value is None:
                    continue

                result = FinancialData(
                    ticker=ticker.upper(),
                    concept=concept,
                    value=value,
                    unit="USD" if concept != "volume" else "shares",
                    period=period or "current",
                    source=DataSourceType.YAHOO_FINANCE,
                    citation={
                        "source": "Market Data",
                        "provider": "Yahoo Finance",
                        "timestamp": quote["timestamp"],
                        "url": f"https://finance.yahoo.com/quote/{ticker}"
                    }
                )
                results.append(result)

            return results

        except Exception as e:
            logger.error("Failed to get financial data", ticker=ticker, error=str(e))
            return []

    async def get_market_summary(self) -> Dict[str, Any]:
        """
        Get market indices summary

        Returns:
            Market indices (SPY, QQQ, DIA)
        """
        indices = ["SPY", "QQQ", "DIA", "^VIX"]
        summary = {}

        for ticker in indices:
            try:
                quote = await self.get_realtime_quote(ticker)
                summary[ticker] = {
                    "price": quote.get("price"),
                    "change_percent": quote.get("change_percent"),
                    "volume": quote.get("volume")
                }
            except Exception as e:
                logger.warning("Failed to fetch index", ticker=ticker, error=str(e))
                continue

        return summary
