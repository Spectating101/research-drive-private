"""
Polygon.io Data Source Integration
Real-time market data, options, tick-level data
"""

import aiohttp
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

from src.data_sources.base import DataSource, DataSourceCapability, DataSourceType, FinancialData

logger = structlog.get_logger(__name__)


class PolygonSource(DataSource):
    """
    Polygon.io data source integration

    Provides:
    - Real-time stock quotes (<200ms latency)
    - Tick-level trade data
    - Options chains
    - Aggregates (bars) data
    - Market status
    - Reference data (exchanges, tickers)
    """

    def __init__(self, config: Dict[str, Any]):
        self.name = "POLYGON"
        self.api_key = config.get("api_key")
        self.base_url = "https://api.polygon.io"
        self.capabilities = [
            DataSourceCapability.MARKET_PRICES,
            DataSourceCapability.HISTORICAL_DATA,
            DataSourceCapability.REAL_TIME,
        ]

    async def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Polygon API"""
        if params is None:
            params = {}

        params["apiKey"] = self.api_key

        async with aiohttp.ClientSession() as session:
            url = f"{self.base_url}{endpoint}"
            async with session.get(url, params=params) as response:
                if response.status == 429:
                    raise Exception("Polygon rate limit exceeded")
                elif response.status != 200:
                    text = await response.text()
                    raise Exception(f"Polygon API error {response.status}: {text}")

                return await response.json()

    async def get_last_trade(self, ticker: str) -> Dict[str, Any]:
        """
        Get last trade for a ticker (real-time)

        Returns most recent trade with sub-second latency
        """
        try:
            data = await self._make_request(f"/v2/last/trade/{ticker.upper()}")

            if data.get("status") != "OK":
                raise Exception(f"Polygon error: {data.get('status')}")

            last_trade = data.get("results", {})

            return {
                "ticker": ticker.upper(),
                "price": last_trade.get("p"),  # Price
                "size": last_trade.get("s"),  # Size
                "exchange": last_trade.get("x"),  # Exchange ID
                "timestamp": datetime.fromtimestamp(last_trade.get("t", 0) / 1000).isoformat(),
                "conditions": last_trade.get("c", []),  # Trade conditions
                "source": "polygon_realtime"
            }

        except Exception as e:
            logger.error("Failed to fetch last trade", ticker=ticker, error=str(e))
            raise

    async def get_last_quote(self, ticker: str) -> Dict[str, Any]:
        """
        Get last quote (bid/ask) for a ticker

        Returns current bid/ask spread
        """
        try:
            data = await self._make_request(f"/v2/last/nbbo/{ticker.upper()}")

            if data.get("status") != "OK":
                raise Exception(f"Polygon error: {data.get('status')}")

            last_quote = data.get("results", {})

            return {
                "ticker": ticker.upper(),
                "bid": last_quote.get("P"),  # Bid price
                "bid_size": last_quote.get("S"),  # Bid size
                "ask": last_quote.get("p"),  # Ask price
                "ask_size": last_quote.get("s"),  # Ask size
                "spread": last_quote.get("p", 0) - last_quote.get("P", 0),
                "timestamp": datetime.fromtimestamp(last_quote.get("t", 0) / 1000).isoformat(),
                "source": "polygon_realtime"
            }

        except Exception as e:
            logger.error("Failed to fetch last quote", ticker=ticker, error=str(e))
            raise

    async def get_snapshot(self, ticker: str) -> Dict[str, Any]:
        """
        Get snapshot (comprehensive current state)

        Returns day's OHLC, last trade, last quote, volume, etc.
        """
        try:
            data = await self._make_request(f"/v2/snapshot/locale/us/markets/stocks/tickers/{ticker.upper()}")

            if data.get("status") != "OK":
                raise Exception(f"Polygon error: {data.get('status')}")

            ticker_data = data.get("ticker", {})
            day_data = ticker_data.get("day", {})
            prev_day = ticker_data.get("prevDay", {})
            last_trade = ticker_data.get("lastTrade", {})
            last_quote = ticker_data.get("lastQuote", {})

            return {
                "ticker": ticker.upper(),
                "updated": ticker_data.get("updated"),
                "day": {
                    "open": day_data.get("o"),
                    "high": day_data.get("h"),
                    "low": day_data.get("l"),
                    "close": day_data.get("c"),
                    "volume": day_data.get("v"),
                    "vwap": day_data.get("vw")
                },
                "prev_day": {
                    "close": prev_day.get("c"),
                    "volume": prev_day.get("v")
                },
                "last_trade": {
                    "price": last_trade.get("p"),
                    "size": last_trade.get("s"),
                    "timestamp": last_trade.get("t")
                },
                "last_quote": {
                    "bid": last_quote.get("P"),
                    "bid_size": last_quote.get("S"),
                    "ask": last_quote.get("p"),
                    "ask_size": last_quote.get("s"),
                    "timestamp": last_quote.get("t")
                },
                "change_percent": ((day_data.get("c", 0) - prev_day.get("c", 1)) / prev_day.get("c", 1)) * 100 if prev_day.get("c") else None,
                "source": "polygon_realtime"
            }

        except Exception as e:
            logger.error("Failed to fetch snapshot", ticker=ticker, error=str(e))
            raise

    async def get_aggregates(
        self,
        ticker: str,
        multiplier: int = 1,
        timespan: str = "day",  # minute, hour, day, week, month, quarter, year
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        limit: int = 5000
    ) -> List[Dict[str, Any]]:
        """
        Get aggregate bars (OHLCV) data

        Args:
            ticker: Stock symbol
            multiplier: Size of timespan multiplier (e.g., 5 for 5-minute bars)
            timespan: Unit of time (minute, hour, day, etc.)
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            limit: Max number of results

        Returns:
            List of OHLCV bars
        """
        try:
            # Default to last 30 days if not specified
            if not from_date:
                from_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")

            endpoint = f"/v2/aggs/ticker/{ticker.upper()}/range/{multiplier}/{timespan}/{from_date}/{to_date}"

            data = await self._make_request(endpoint, params={
                "adjusted": "true",
                "sort": "asc",
                "limit": limit
            })

            if data.get("status") != "OK":
                raise Exception(f"Polygon error: {data.get('status')}")

            results = data.get("results", [])

            bars = []
            for bar in results:
                bars.append({
                    "ticker": ticker.upper(),
                    "timestamp": datetime.fromtimestamp(bar.get("t", 0) / 1000).isoformat(),
                    "open": bar.get("o"),
                    "high": bar.get("h"),
                    "low": bar.get("l"),
                    "close": bar.get("c"),
                    "volume": bar.get("v"),
                    "vwap": bar.get("vw"),
                    "transactions": bar.get("n"),  # Number of transactions
                    "timespan": f"{multiplier}{timespan}"
                })

            logger.info(f"Fetched {len(bars)} bars", ticker=ticker, timespan=timespan)
            return bars

        except Exception as e:
            logger.error("Failed to fetch aggregates", ticker=ticker, error=str(e))
            return []

    async def get_market_status(self) -> Dict[str, Any]:
        """
        Get current market status

        Returns whether markets are open, extended hours status, etc.
        """
        try:
            data = await self._make_request("/v1/marketstatus/now")

            return {
                "market": data.get("market"),
                "server_time": data.get("serverTime"),
                "exchanges": {
                    "nasdaq": data.get("exchanges", {}).get("nasdaq"),
                    "nyse": data.get("exchanges", {}).get("nyse"),
                    "otc": data.get("exchanges", {}).get("otc")
                },
                "currencies": data.get("currencies")
            }

        except Exception as e:
            logger.error("Failed to fetch market status", error=str(e))
            return {}

    async def get_options_chain(
        self,
        ticker: str,
        expiration_date: Optional[str] = None,
        contract_type: Optional[str] = None  # "call" or "put"
    ) -> List[Dict[str, Any]]:
        """
        Get options chain for a ticker

        Args:
            ticker: Stock symbol
            expiration_date: Filter by expiration (YYYY-MM-DD)
            contract_type: Filter by type ("call" or "put")

        Returns:
            List of option contracts
        """
        try:
            params = {
                "underlying_ticker": ticker.upper(),
                "limit": 1000
            }

            if expiration_date:
                params["expiration_date"] = expiration_date
            if contract_type:
                params["contract_type"] = contract_type

            data = await self._make_request("/v3/reference/options/contracts", params=params)

            if data.get("status") != "OK":
                return []

            contracts = []
            for contract in data.get("results", []):
                contracts.append({
                    "ticker": ticker.upper(),
                    "contract_type": contract.get("contract_type"),
                    "expiration_date": contract.get("expiration_date"),
                    "strike_price": contract.get("strike_price"),
                    "contract_ticker": contract.get("ticker"),
                    "exercise_style": contract.get("exercise_style")
                })

            return contracts

        except Exception as e:
            logger.error("Failed to fetch options chain", ticker=ticker, error=str(e))
            return []

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """
        Get financial data (implements DataSource interface)

        For Polygon, this returns real-time price data
        """
        results = []

        try:
            snapshot = await self.get_snapshot(ticker)

            for concept in concepts:
                if concept == "price":
                    value = snapshot["last_trade"]["price"]
                elif concept == "volume":
                    value = snapshot["day"]["volume"]
                elif concept == "change_percent":
                    value = snapshot["change_percent"]
                else:
                    continue

                if value is None:
                    continue

                results.append(FinancialData(
                    ticker=ticker.upper(),
                    concept=concept,
                    value=value,
                    unit="USD" if concept == "price" else ("percent" if concept == "change_percent" else "shares"),
                    period="realtime",
                    source=DataSourceType.POLYGON_IO,
                    citation={
                        "source": "Polygon.io",
                        "type": "realtime_snapshot",
                        "timestamp": datetime.now().isoformat(),
                        "latency_ms": "< 200"
                    }
                ))

        except Exception as e:
            logger.error("Failed to get financial data from Polygon", ticker=ticker, error=str(e))

        return results
