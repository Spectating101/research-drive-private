"""
Multi-Source Data Aggregation Layer
Intelligently routes requests across multiple data sources
"""

import asyncio
import json
import structlog
from typing import List, Dict, Any, Optional, Set
from datetime import datetime, timedelta
from enum import Enum

from src.data_sources.base import DataSource, DataSourceCapability, FinancialData
from src.models.user import PricingTier

logger = structlog.get_logger(__name__)


class DataPriority(Enum):
    """Priority levels for data sources"""
    PRIMARY = "primary"
    SECONDARY = "secondary"
    FALLBACK = "fallback"


class DataSourceAggregator:
    """
    Intelligent multi-source data aggregation

    Features:
    - Tier-based source routing (free users get yfinance, Pro gets Polygon)
    - Cross-source validation for consistency scores
    - Automatic fallback if primary source fails
    - Rate limit optimization
    - Result caching
    """

    def __init__(self, redis_client=None):
        self.sources: Dict[str, DataSource] = {}
        self.redis_client = redis_client
        self.cache_ttl = {
            "real_time": 60,  # 1 minute
            "quote": 300,  # 5 minutes
            "historical": 3600,  # 1 hour
            "fundamentals": 86400,  # 24 hours
        }

    def register_source(self, source: DataSource, priority: DataPriority = DataPriority.SECONDARY):
        """Register a data source with priority"""
        self.sources[source.name] = {
            "instance": source,
            "priority": priority,
            "capabilities": source.capabilities
        }
        logger.info(f"Registered data source", source=source.name, priority=priority.value)

    def get_sources_by_capability(
        self,
        capability: DataSourceCapability,
        tier: PricingTier = PricingTier.FREE
    ) -> List[Dict[str, Any]]:
        """
        Get data sources that support a capability, filtered by user tier

        Returns sources sorted by priority
        """
        eligible_sources = []

        for name, source_info in self.sources.items():
            if capability not in source_info["capabilities"]:
                continue

            # Tier-based filtering
            if tier == PricingTier.FREE:
                # Free tier: only yfinance (free sources)
                if name not in ["YFINANCE"]:
                    continue
            elif tier == PricingTier.STARTER:
                # Starter: yfinance + Alpha Vantage (delayed data)
                if name not in ["YFINANCE", "ALPHA_VANTAGE", "FINNHUB"]:
                    continue
            elif tier == PricingTier.PROFESSIONAL:
                # Pro: All sources including real-time
                pass
            elif tier == PricingTier.ENTERPRISE:
                # Enterprise: All sources with highest priority
                pass

            eligible_sources.append({
                "name": name,
                "instance": source_info["instance"],
                "priority": source_info["priority"]
            })

        # Sort by priority (PRIMARY > SECONDARY > FALLBACK)
        priority_order = {
            DataPriority.PRIMARY: 0,
            DataPriority.SECONDARY: 1,
            DataPriority.FALLBACK: 2
        }
        eligible_sources.sort(key=lambda x: priority_order[x["priority"]])

        return eligible_sources

    async def get_cached(self, cache_key: str) -> Optional[Any]:
        """Get cached result"""
        if not self.redis_client:
            return None

        try:
            cached = await self.redis_client.get(cache_key)
            if cached:
                logger.debug("Cache hit", key=cache_key)
                try:
                    return json.loads(cached)
                except Exception:
                    # If data is not JSON, return raw string
                    return cached
        except Exception as e:
            logger.warning("Cache read failed", error=str(e))

        return None

    async def set_cached(self, cache_key: str, value: Any, ttl: int):
        """Set cached result"""
        if not self.redis_client:
            return

        try:
            payload = json.dumps(value, default=str)
            await self.redis_client.setex(cache_key, ttl, payload)
            logger.debug("Cache set", key=cache_key, ttl=ttl)
        except Exception as e:
            logger.warning("Cache write failed", error=str(e))

    async def get_real_time_quote(
        self,
        ticker: str,
        tier: PricingTier,
        include_fundamentals: bool = False
    ) -> Dict[str, Any]:
        """
        Get real-time quote with tier-based routing

        Routing logic:
        - Free/Starter: yfinance (15-min delay)
        - Professional+: Polygon.io (real-time)
        - Fallback: Alpha Vantage
        """
        cache_key = f"quote:{ticker}:{tier.value}"

        # Check cache
        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.REAL_TIME,
            tier
        )

        if not sources:
            raise Exception(f"No data sources available for tier {tier.value}")

        # Try each source in priority order
        for source_info in sources:
            source = source_info["instance"]

            try:
                logger.info(f"Fetching quote from {source.name}", ticker=ticker)

                if source.name == "POLYGON":
                    # Real-time from Polygon
                    result = await source.get_snapshot(ticker)
                elif source.name == "YFINANCE":
                    # Delayed from yfinance
                    from src.data_sources.market_data import get_real_time_quote
                    result = await get_real_time_quote(ticker)
                elif source.name == "ALPHA_VANTAGE":
                    # Intraday from Alpha Vantage
                    data = await source.get_intraday_prices(ticker, interval="5min", outputsize="compact")
                    if data:
                        latest = data[-1]
                        result = {
                            "ticker": ticker,
                            "price": latest["close"],
                            "timestamp": latest["timestamp"],
                            "source": "alpha_vantage_intraday"
                        }
                    else:
                        continue
                else:
                    continue

                # Add fundamentals if requested and available
                if include_fundamentals and tier in [PricingTier.PROFESSIONAL, PricingTier.ENTERPRISE]:
                    fundamentals = await self.get_fundamentals(ticker, tier)
                    result["fundamentals"] = fundamentals

                # Cache result
                await self.set_cached(cache_key, result, self.cache_ttl["quote"])

                return result

            except Exception as e:
                logger.warning(
                    f"Failed to fetch from {source.name}",
                    ticker=ticker,
                    error=str(e)
                )
                continue

        raise Exception(f"All data sources failed for {ticker}")

    async def get_historical_data(
        self,
        ticker: str,
        tier: PricingTier,
        period: str = "1y",
        interval: str = "1d"
    ) -> List[Dict[str, Any]]:
        """
        Get historical price data

        Routing:
        - All tiers: Alpha Vantage (20+ years daily)
        - Intraday: Polygon (Pro+) or Alpha Vantage
        """
        cache_key = f"historical:{ticker}:{period}:{interval}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.HISTORICAL_DATA,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                logger.info(f"Fetching historical from {source.name}", ticker=ticker)

                if source.name == "ALPHA_VANTAGE":
                    # Daily historical
                    if interval == "1d":
                        result = await source.get_daily_prices(ticker, outputsize="full")
                    else:
                        # Intraday
                        result = await source.get_intraday_prices(ticker, interval=interval)

                elif source.name == "POLYGON":
                    # Aggregates from Polygon
                    from_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
                    to_date = datetime.now().strftime("%Y-%m-%d")
                    result = await source.get_aggregates(ticker, timespan="day", from_date=from_date, to_date=to_date)

                elif source.name == "YFINANCE":
                    from src.data_sources.market_data import get_historical_data
                    result = await get_historical_data(ticker, period=period, interval=interval)

                else:
                    continue

                await self.set_cached(cache_key, result, self.cache_ttl["historical"])
                return result

            except Exception as e:
                logger.warning(f"Failed to fetch historical from {source.name}", error=str(e))
                continue

        raise Exception(f"All sources failed for historical data: {ticker}")

    async def get_fundamentals(
        self,
        ticker: str,
        tier: PricingTier
    ) -> Dict[str, Any]:
        """
        Get company fundamentals

        Routing:
        - Starter+: Alpha Vantage company overview
        - Pro+: Multi-source validation
        """
        cache_key = f"fundamentals:{ticker}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.FUNDAMENTALS,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                if source.name == "ALPHA_VANTAGE":
                    result = await source.get_company_overview(ticker)

                    if result:
                        await self.set_cached(cache_key, result, self.cache_ttl["fundamentals"])
                        return result

            except Exception as e:
                logger.warning(f"Failed to fetch fundamentals from {source.name}", error=str(e))
                continue

        return {}

    async def get_news_sentiment(
        self,
        ticker: str,
        tier: PricingTier,
        days: int = 7
    ) -> Dict[str, Any]:
        """
        Get news with sentiment analysis

        Routing:
        - Starter+: Finnhub news + sentiment
        - Pro+: Multi-source aggregation
        """
        if tier == PricingTier.FREE:
            raise Exception("News sentiment requires Starter tier or higher")

        cache_key = f"news:{ticker}:{days}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.NEWS,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                if source.name == "FINNHUB":
                    from_date = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
                    to_date = datetime.now().strftime("%Y-%m-%d")

                    news = await source.get_company_news(ticker, from_date=from_date, to_date=to_date)
                    social = await source.get_social_sentiment(ticker)

                    result = {
                        "ticker": ticker,
                        "news": news,
                        "social_sentiment": social,
                        "news_count": len(news),
                        "timestamp": datetime.now().isoformat()
                    }

                    await self.set_cached(cache_key, result, 3600)  # 1 hour cache
                    return result

            except Exception as e:
                logger.warning(f"Failed to fetch news from {source.name}", error=str(e))
                continue

        return {"ticker": ticker, "news": [], "social_sentiment": {}}

    async def get_earnings_calendar(
        self,
        ticker: Optional[str],
        tier: PricingTier,
        days_ahead: int = 30
    ) -> List[Dict[str, Any]]:
        """
        Get upcoming earnings events

        Routing:
        - Starter+: Finnhub earnings calendar
        """
        if tier == PricingTier.FREE:
            raise Exception("Earnings calendar requires Starter tier or higher")

        cache_key = f"earnings:{ticker or 'all'}:{days_ahead}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.EARNINGS,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                if source.name == "FINNHUB":
                    from_date = datetime.now().strftime("%Y-%m-%d")
                    to_date = (datetime.now() + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

                    result = await source.get_earnings_calendar(
                        from_date=from_date,
                        to_date=to_date,
                        ticker=ticker
                    )

                    await self.set_cached(cache_key, result, 3600)
                    return result

            except Exception as e:
                logger.warning(f"Failed to fetch earnings from {source.name}", error=str(e))
                continue

        return []

    async def get_analyst_recommendations(
        self,
        ticker: str,
        tier: PricingTier
    ) -> Dict[str, Any]:
        """Get analyst recommendations"""
        if tier == PricingTier.FREE:
            raise Exception("Analyst recommendations require Starter tier or higher")

        cache_key = f"analysts:{ticker}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.SENTIMENT,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                if source.name == "FINNHUB":
                    result = await source.get_analyst_recommendations(ticker)

                    await self.set_cached(cache_key, result, 86400)  # 24 hour cache
                    return result

            except Exception as e:
                logger.warning(f"Failed to fetch analysts from {source.name}", error=str(e))
                continue

        return {}

    async def get_options_chain(
        self,
        ticker: str,
        tier: PricingTier,
        expiration_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get options chain

        Routing:
        - Pro+: Polygon options data
        """
        if tier not in [PricingTier.PROFESSIONAL, PricingTier.ENTERPRISE]:
            raise Exception("Options data requires Professional tier or higher")

        cache_key = f"options:{ticker}:{expiration_date or 'all'}"

        cached = await self.get_cached(cache_key)
        if cached:
            return cached

        sources = self.get_sources_by_capability(
            DataSourceCapability.REAL_TIME,
            tier
        )

        for source_info in sources:
            source = source_info["instance"]

            try:
                if source.name == "POLYGON":
                    result = await source.get_options_chain(ticker, expiration_date=expiration_date)

                    await self.set_cached(cache_key, result, 3600)
                    return result

            except Exception as e:
                logger.warning(f"Failed to fetch options from {source.name}", error=str(e))
                continue

        return []

    async def get_multi_source_validation(
        self,
        ticker: str,
        concepts: List[str],
        tier: PricingTier
    ) -> Dict[str, Any]:
        """
        Get data from multiple sources and validate consistency

        Used for consistency_score in /api/v1/answers
        """
        results = {}

        # Get data from all available sources
        tasks = []
        for source_name, source_info in self.sources.items():
            source = source_info["instance"]
            tasks.append(self._fetch_from_source(source, ticker, concepts))

        source_results = await asyncio.gather(*tasks, return_exceptions=True)

        # Aggregate results by concept
        for concept in concepts:
            concept_values = []

            for source_result in source_results:
                if isinstance(source_result, Exception):
                    continue

                for data in source_result:
                    if data.concept == concept:
                        concept_values.append({
                            "value": data.value,
                            "source": data.source.name,
                            "timestamp": data.citation.get("timestamp")
                        })

            # Calculate consistency score
            if len(concept_values) == 0:
                consistency = 0.0
            elif len(concept_values) == 1:
                consistency = 0.85
            else:
                # Check variance
                values = [v["value"] for v in concept_values]
                avg = sum(values) / len(values)
                variance = sum((v - avg) ** 2 for v in values) / len(values)
                relative_variance = variance / (avg ** 2) if avg != 0 else 1.0

                # Lower variance = higher consistency
                consistency = max(0.0, min(1.0, 1.0 - relative_variance))

            results[concept] = {
                "values": concept_values,
                "consistency_score": consistency,
                "source_count": len(concept_values)
            }

        return results

    async def _fetch_from_source(
        self,
        source: DataSource,
        ticker: str,
        concepts: List[str]
    ) -> List[FinancialData]:
        """Fetch financial data from a single source"""
        try:
            return await source.get_financial_data(ticker, concepts)
        except Exception as e:
            logger.warning(f"Failed to fetch from {source.name}", error=str(e))
            return []


# Global aggregator instance
_aggregator: Optional[DataSourceAggregator] = None


def get_aggregator() -> DataSourceAggregator:
    """Get global aggregator instance"""
    global _aggregator
    if _aggregator is None:
        raise Exception("Aggregator not initialized. Call init_aggregator() first.")
    return _aggregator


def init_aggregator(redis_client=None) -> DataSourceAggregator:
    """Initialize global aggregator"""
    global _aggregator
    _aggregator = DataSourceAggregator(redis_client)
    return _aggregator
