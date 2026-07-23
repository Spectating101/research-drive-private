"""
Alpha Vantage Data Source Integration
20+ years historical data, technical indicators, global markets
"""

import aiohttp
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime
import asyncio

from src.data_sources.base import DataSource, DataSourceCapability, DataSourceType, FinancialData

logger = structlog.get_logger(__name__)


class AlphaVantageSource(DataSource):
    """
    Alpha Vantage data source integration

    Provides:
    - 20+ years historical price data
    - Technical indicators (50+ built-in)
    - Fundamental data (balance sheets, income statements)
    - Global market coverage
    - Intraday data
    """

    def __init__(self, config: Dict[str, Any]):
        self.name = "ALPHA_VANTAGE"
        self.api_key = config.get("api_key")
        self.base_url = "https://www.alphavantage.co/query"
        self.capabilities = [
            DataSourceCapability.MARKET_PRICES,
            DataSourceCapability.HISTORICAL_DATA,
            DataSourceCapability.FUNDAMENTALS,
        ]
        self.rate_limit_delay = 12  # Free tier: 5 calls/min = 12s between calls

    async def _make_request(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Make rate-limited request to Alpha Vantage API"""
        params["apikey"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(self.base_url, params=params) as response:
                if response.status != 200:
                    raise Exception(f"Alpha Vantage API error: {response.status}")

                data = await response.json()

                # Check for rate limit or error
                if "Note" in data:
                    raise Exception("Alpha Vantage rate limit exceeded")
                if "Error Message" in data:
                    raise Exception(f"Alpha Vantage error: {data['Error Message']}")

                return data

    async def get_daily_prices(
        self,
        ticker: str,
        outputsize: str = "full"  # "compact" = 100 days, "full" = 20+ years
    ) -> List[Dict[str, Any]]:
        """
        Get daily historical prices

        Args:
            ticker: Stock symbol
            outputsize: "compact" (100 days) or "full" (20+ years)

        Returns:
            List of daily price records
        """
        try:
            data = await self._make_request({
                "function": "TIME_SERIES_DAILY_ADJUSTED",
                "symbol": ticker.upper(),
                "outputsize": outputsize
            })

            time_series = data.get("Time Series (Daily)", {})

            if not time_series:
                logger.warning("No daily data found", ticker=ticker)
                return []

            records = []
            for date, values in time_series.items():
                records.append({
                    "ticker": ticker.upper(),
                    "date": date,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "adjusted_close": float(values.get("5. adjusted close", 0)),
                    "volume": int(values.get("6. volume", 0)),
                    "dividend": float(values.get("7. dividend amount", 0)),
                    "split_coefficient": float(values.get("8. split coefficient", 1.0))
                })

            # Sort by date (oldest first)
            records.sort(key=lambda x: x["date"])

            logger.info(f"Fetched {len(records)} daily records", ticker=ticker)
            return records

        except Exception as e:
            logger.error("Failed to fetch daily prices", ticker=ticker, error=str(e))
            raise

    async def get_intraday_prices(
        self,
        ticker: str,
        interval: str = "5min",  # 1min, 5min, 15min, 30min, 60min
        outputsize: str = "compact"  # compact = latest 100 data points
    ) -> List[Dict[str, Any]]:
        """
        Get intraday price data

        Args:
            ticker: Stock symbol
            interval: Time interval (1min, 5min, 15min, 30min, 60min)
            outputsize: "compact" or "full"

        Returns:
            Intraday price records
        """
        try:
            await asyncio.sleep(self.rate_limit_delay)  # Rate limiting

            data = await self._make_request({
                "function": "TIME_SERIES_INTRADAY",
                "symbol": ticker.upper(),
                "interval": interval,
                "outputsize": outputsize
            })

            key = f"Time Series ({interval})"
            time_series = data.get(key, {})

            if not time_series:
                return []

            records = []
            for timestamp, values in time_series.items():
                records.append({
                    "ticker": ticker.upper(),
                    "timestamp": timestamp,
                    "open": float(values.get("1. open", 0)),
                    "high": float(values.get("2. high", 0)),
                    "low": float(values.get("3. low", 0)),
                    "close": float(values.get("4. close", 0)),
                    "volume": int(values.get("5. volume", 0)),
                    "interval": interval
                })

            records.sort(key=lambda x: x["timestamp"])
            return records

        except Exception as e:
            logger.error("Failed to fetch intraday prices", ticker=ticker, error=str(e))
            return []

    async def get_technical_indicator(
        self,
        ticker: str,
        indicator: str,  # SMA, EMA, RSI, MACD, BBANDS, etc.
        interval: str = "daily",
        time_period: int = 14,
        series_type: str = "close",
        **kwargs
    ) -> Dict[str, Any]:
        """
        Get technical indicator from Alpha Vantage

        Args:
            ticker: Stock symbol
            indicator: Indicator name (SMA, EMA, RSI, MACD, BBANDS, ATR, ADX, etc.)
            interval: Time interval (1min, 5min, 15min, 30min, 60min, daily, weekly, monthly)
            time_period: Number of data points for calculation
            series_type: Price type (close, open, high, low)
            **kwargs: Additional indicator-specific parameters

        Returns:
            Technical indicator data
        """
        try:
            await asyncio.sleep(self.rate_limit_delay)

            params = {
                "function": indicator,
                "symbol": ticker.upper(),
                "interval": interval,
                "time_period": time_period,
                "series_type": series_type
            }

            # Add additional parameters
            params.update(kwargs)

            data = await self._make_request(params)

            # Parse response (format varies by indicator)
            technical_key = f"Technical Analysis: {indicator}"
            if technical_key not in data:
                logger.warning(f"No {indicator} data found", ticker=ticker)
                return {}

            return {
                "ticker": ticker.upper(),
                "indicator": indicator,
                "interval": interval,
                "time_period": time_period,
                "data": data[technical_key],
                "metadata": data.get("Meta Data", {})
            }

        except Exception as e:
            logger.error(f"Failed to fetch {indicator}", ticker=ticker, error=str(e))
            return {}

    async def get_company_overview(self, ticker: str) -> Dict[str, Any]:
        """
        Get company fundamental overview

        Returns key metrics, ratios, and company info
        """
        try:
            await asyncio.sleep(self.rate_limit_delay)

            data = await self._make_request({
                "function": "OVERVIEW",
                "symbol": ticker.upper()
            })

            if not data or "Symbol" not in data:
                return {}

            return {
                "ticker": ticker.upper(),
                "name": data.get("Name"),
                "description": data.get("Description"),
                "sector": data.get("Sector"),
                "industry": data.get("Industry"),
                "market_cap": float(data.get("MarketCapitalization", 0)),
                "pe_ratio": float(data.get("PERatio", 0)) if data.get("PERatio") != "None" else None,
                "peg_ratio": float(data.get("PEGRatio", 0)) if data.get("PEGRatio") != "None" else None,
                "book_value": float(data.get("BookValue", 0)) if data.get("BookValue") != "None" else None,
                "dividend_per_share": float(data.get("DividendPerShare", 0)) if data.get("DividendPerShare") != "None" else None,
                "dividend_yield": float(data.get("DividendYield", 0)) if data.get("DividendYield") != "None" else None,
                "eps": float(data.get("EPS", 0)) if data.get("EPS") != "None" else None,
                "revenue_ttm": float(data.get("RevenueTTM", 0)) if data.get("RevenueTTM") != "None" else None,
                "profit_margin": float(data.get("ProfitMargin", 0)) if data.get("ProfitMargin") != "None" else None,
                "52_week_high": float(data.get("52WeekHigh", 0)) if data.get("52WeekHigh") != "None" else None,
                "52_week_low": float(data.get("52WeekLow", 0)) if data.get("52WeekLow") != "None" else None,
                "beta": float(data.get("Beta", 0)) if data.get("Beta") != "None" else None,
                "shares_outstanding": float(data.get("SharesOutstanding", 0)) if data.get("SharesOutstanding") != "None" else None
            }

        except Exception as e:
            logger.error("Failed to fetch company overview", ticker=ticker, error=str(e))
            return {}

    async def get_income_statement(self, ticker: str) -> List[Dict[str, Any]]:
        """Get annual income statements"""
        try:
            await asyncio.sleep(self.rate_limit_delay)

            data = await self._make_request({
                "function": "INCOME_STATEMENT",
                "symbol": ticker.upper()
            })

            annual_reports = data.get("annualReports", [])

            statements = []
            for report in annual_reports:
                statements.append({
                    "ticker": ticker.upper(),
                    "fiscal_date": report.get("fiscalDateEnding"),
                    "revenue": float(report.get("totalRevenue", 0)),
                    "gross_profit": float(report.get("grossProfit", 0)),
                    "operating_income": float(report.get("operatingIncome", 0)),
                    "net_income": float(report.get("netIncome", 0)),
                    "ebitda": float(report.get("ebitda", 0)),
                    "eps": float(report.get("reportedEPS", 0))
                })

            return statements

        except Exception as e:
            logger.error("Failed to fetch income statement", ticker=ticker, error=str(e))
            return []

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """
        Get financial data (implements DataSource interface)

        Returns fundamental metrics from Alpha Vantage
        """
        results = []

        try:
            overview = await self.get_company_overview(ticker)

            if not overview:
                return results

            # Map concepts to overview fields
            concept_map = {
                "market_cap": overview.get("market_cap"),
                "pe_ratio": overview.get("pe_ratio"),
                "eps": overview.get("eps"),
                "revenue": overview.get("revenue_ttm"),
                "dividend_yield": overview.get("dividend_yield"),
                "beta": overview.get("beta")
            }

            for concept in concepts:
                value = concept_map.get(concept)

                if value is None:
                    continue

                results.append(FinancialData(
                    ticker=ticker.upper(),
                    concept=concept,
                    value=value,
                    unit="USD" if concept in ["market_cap", "revenue"] else "ratio",
                    period=period or "ttm",
                    source=DataSourceType.ALPHA_VANTAGE,
                    citation={
                        "source": "Alpha Vantage",
                        "type": "company_overview",
                        "timestamp": datetime.now().isoformat()
                    }
                ))

        except Exception as e:
            logger.error("Failed to get financial data from Alpha Vantage", ticker=ticker, error=str(e))

        return results
