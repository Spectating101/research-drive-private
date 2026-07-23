"""
yfinance Data Source (Fallback/Free Tier)
Free market data from Yahoo Finance
"""

import yfinance as yf
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime

from src.data_sources.base import DataSource, DataSourceCapability, DataSourceType, FinancialData

logger = structlog.get_logger(__name__)


class YFinanceSource(DataSource):
    """
    Yahoo Finance data source (free tier fallback)

    Provides:
    - Real-time quotes (15-min delayed)
    - Historical price data (10+ years)
    - Intraday data (limited)
    - Basic fundamentals
    """

    def __init__(self, config: Dict[str, Any] = None):
        self.name = "YFINANCE"
        self.capabilities = [
            DataSourceCapability.MARKET_PRICES,
            DataSourceCapability.HISTORICAL_DATA,
            DataSourceCapability.REAL_TIME,
            DataSourceCapability.FUNDAMENTALS,
        ]

    async def get_quote(self, ticker: str) -> Dict[str, Any]:
        """
        Get current quote (15-min delayed)
        """
        try:
            stock = yf.Ticker(ticker.upper())
            info = stock.info

            return {
                "ticker": ticker.upper(),
                "price": info.get("currentPrice") or info.get("regularMarketPrice"),
                "timestamp": datetime.now().isoformat(),
                "day": {
                    "open": info.get("regularMarketOpen"),
                    "high": info.get("regularMarketDayHigh"),
                    "low": info.get("regularMarketDayLow"),
                    "close": info.get("regularMarketPreviousClose"),
                    "volume": info.get("regularMarketVolume")
                },
                "change_percent": info.get("regularMarketChangePercent"),
                "source": "yfinance_delayed"
            }

        except Exception as e:
            logger.error("Failed to fetch quote from yfinance", ticker=ticker, error=str(e))
            raise

    async def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        """Get comprehensive snapshot"""
        return await self.get_quote(ticker)

    async def get_historical(
        self,
        ticker: str,
        period: str = "1y",
        interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data

        Args:
            ticker: Stock symbol
            period: Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max)
            interval: Data interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)

        Returns:
            List of price records
        """
        try:
            stock = yf.Ticker(ticker.upper())
            hist = stock.history(period=period, interval=interval)

            records = []
            for index, row in hist.iterrows():
                records.append({
                    "ticker": ticker.upper(),
                    "date": index.isoformat(),
                    "open": float(row["Open"]),
                    "high": float(row["High"]),
                    "low": float(row["Low"]),
                    "close": float(row["Close"]),
                    "volume": int(row["Volume"]),
                    "source": "yfinance"
                })

            logger.info(f"Fetched {len(records)} records from yfinance", ticker=ticker)
            return records

        except Exception as e:
            logger.error("Failed to fetch historical from yfinance", ticker=ticker, error=str(e))
            return []

    async def get_fundamentals(self, ticker: str) -> Dict[str, Any]:
        """
        Get company fundamentals
        """
        try:
            stock = yf.Ticker(ticker.upper())
            info = stock.info

            return {
                "ticker": ticker.upper(),
                "name": info.get("longName"),
                "sector": info.get("sector"),
                "industry": info.get("industry"),
                "market_cap": info.get("marketCap"),
                "pe_ratio": info.get("trailingPE"),
                "forward_pe": info.get("forwardPE"),
                "peg_ratio": info.get("pegRatio"),
                "book_value": info.get("bookValue"),
                "dividend_yield": info.get("dividendYield"),
                "eps": info.get("trailingEps"),
                "revenue_ttm": info.get("totalRevenue"),
                "profit_margin": info.get("profitMargins"),
                "52_week_high": info.get("fiftyTwoWeekHigh"),
                "52_week_low": info.get("fiftyTwoWeekLow"),
                "beta": info.get("beta"),
                "shares_outstanding": info.get("sharesOutstanding"),
                "source": "yfinance"
            }

        except Exception as e:
            logger.error("Failed to fetch fundamentals from yfinance", ticker=ticker, error=str(e))
            return {}

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """
        Get financial data (implements DataSource interface)
        """
        results = []

        try:
            quote = await self.get_quote(ticker)
            fundamentals = await self.get_fundamentals(ticker)

            concept_map = {
                "price": quote.get("price"),
                "market_cap": fundamentals.get("market_cap"),
                "pe_ratio": fundamentals.get("pe_ratio"),
                "eps": fundamentals.get("eps"),
                "revenue": fundamentals.get("revenue_ttm"),
                "dividend_yield": fundamentals.get("dividend_yield"),
                "beta": fundamentals.get("beta")
            }

            for concept in concepts:
                value = concept_map.get(concept)

                if value is None:
                    continue

                results.append(FinancialData(
                    ticker=ticker.upper(),
                    concept=concept,
                    value=value,
                    unit="USD" if concept in ["price", "market_cap", "revenue"] else "ratio",
                    period=period or "current",
                    source=DataSourceType.YAHOO_FINANCE,
                    citation={
                        "source": "Yahoo Finance",
                        "type": "delayed_quote",
                        "timestamp": datetime.now().isoformat(),
                        "delay": "15 minutes"
                    }
                ))

        except Exception as e:
            logger.error("Failed to get financial data from yfinance", ticker=ticker, error=str(e))

        return results
