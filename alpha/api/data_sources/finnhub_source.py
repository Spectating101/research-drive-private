"""
Finnhub Data Source Integration
News, sentiment, earnings, analyst recommendations
"""

import aiohttp
import structlog
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from enum import Enum

from src.data_sources.base import DataSource, DataSourceCapability, DataSourceType, FinancialData

logger = structlog.get_logger(__name__)


class FinnhubSource(DataSource):
    """
    Finnhub data source integration

    Provides:
    - Company news with sentiment
    - Earnings calendar
    - Analyst recommendations
    - Social sentiment (Reddit, Twitter)
    - Insider transactions
    - IPO calendar
    """

    def __init__(self, config: Dict[str, Any]):
        self.name = "FINNHUB"
        self.api_key = config.get("api_key")
        self.base_url = "https://finnhub.io/api/v1"
        self.capabilities = [
            DataSourceCapability.NEWS,
            DataSourceCapability.SENTIMENT,
            DataSourceCapability.EARNINGS,
        ]

    async def _make_request(self, endpoint: str, params: Dict[str, Any] = None) -> Dict[str, Any]:
        """Make authenticated request to Finnhub API"""
        if params is None:
            params = {}

        params["token"] = self.api_key

        async with aiohttp.ClientSession() as session:
            async with session.get(f"{self.base_url}/{endpoint}", params=params) as response:
                if response.status == 429:
                    raise Exception("Finnhub rate limit exceeded")
                elif response.status != 200:
                    raise Exception(f"Finnhub API error: {response.status}")

                return await response.json()

    async def get_company_news(
        self,
        ticker: str,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get company-specific news

        Args:
            ticker: Stock symbol
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)

        Returns:
            List of news articles with sentiment
        """
        try:
            # Default to last 7 days
            if not from_date:
                from_date = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")
            if not to_date:
                to_date = datetime.now().strftime("%Y-%m-%d")

            data = await self._make_request(
                "company-news",
                params={
                    "symbol": ticker.upper(),
                    "from": from_date,
                    "to": to_date
                }
            )

            # Parse and enrich news
            news = []
            for article in data:
                news.append({
                    "ticker": ticker.upper(),
                    "headline": article.get("headline"),
                    "summary": article.get("summary"),
                    "source": article.get("source"),
                    "url": article.get("url"),
                    "published_at": datetime.fromtimestamp(article.get("datetime", 0)).isoformat(),
                    "sentiment": self._analyze_headline_sentiment(article.get("headline", "")),
                    "category": article.get("category"),
                    "related_symbols": article.get("related", [])
                })

            logger.info(f"Fetched {len(news)} news articles", ticker=ticker)
            return news

        except Exception as e:
            logger.error("Failed to fetch company news", ticker=ticker, error=str(e))
            raise

    def _analyze_headline_sentiment(self, headline: str) -> Dict[str, Any]:
        """
        Simple sentiment analysis on headline

        Returns sentiment score and label
        """
        # Simple keyword-based sentiment (can be enhanced with ML)
        positive_words = ["surge", "gain", "beat", "exceed", "high", "growth", "profit", "success", "upgrade", "buy"]
        negative_words = ["fall", "drop", "miss", "low", "loss", "decline", "cut", "downgrade", "sell", "warning"]

        headline_lower = headline.lower()

        pos_count = sum(1 for word in positive_words if word in headline_lower)
        neg_count = sum(1 for word in negative_words if word in headline_lower)

        if pos_count > neg_count:
            return {"label": "positive", "score": min(pos_count / 10, 1.0)}
        elif neg_count > pos_count:
            return {"label": "negative", "score": min(neg_count / 10, 1.0)}
        else:
            return {"label": "neutral", "score": 0.5}

    async def get_social_sentiment(self, ticker: str) -> Dict[str, Any]:
        """
        Get social media sentiment (Reddit, Twitter)

        Returns aggregated sentiment from social platforms
        """
        try:
            data = await self._make_request(
                "stock/social-sentiment",
                params={"symbol": ticker.upper()}
            )

            if not data or "reddit" not in data:
                return {
                    "ticker": ticker.upper(),
                    "reddit": {"score": 0, "mention": 0},
                    "twitter": {"score": 0, "mention": 0},
                    "overall": "neutral",
                    "timestamp": datetime.now().isoformat()
                }

            reddit = data.get("reddit", [])
            twitter = data.get("twitter", [])

            # Calculate average sentiment
            reddit_sentiment = sum(r.get("score", 0) for r in reddit) / len(reddit) if reddit else 0
            twitter_sentiment = sum(t.get("score", 0) for t in twitter) / len(twitter) if twitter else 0

            reddit_mentions = sum(r.get("mention", 0) for r in reddit) if reddit else 0
            twitter_mentions = sum(t.get("mention", 0) for t in twitter) if twitter else 0

            # Overall sentiment
            overall_score = (reddit_sentiment + twitter_sentiment) / 2
            if overall_score > 0.2:
                overall = "positive"
            elif overall_score < -0.2:
                overall = "negative"
            else:
                overall = "neutral"

            return {
                "ticker": ticker.upper(),
                "reddit": {
                    "score": reddit_sentiment,
                    "mentions": reddit_mentions
                },
                "twitter": {
                    "score": twitter_sentiment,
                    "mentions": twitter_mentions
                },
                "overall": overall,
                "overall_score": overall_score,
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error("Failed to fetch social sentiment", ticker=ticker, error=str(e))
            return {
                "ticker": ticker.upper(),
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }

    async def get_earnings_calendar(
        self,
        from_date: Optional[str] = None,
        to_date: Optional[str] = None,
        ticker: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get earnings calendar

        Args:
            from_date: Start date (YYYY-MM-DD)
            to_date: End date (YYYY-MM-DD)
            ticker: Filter by specific ticker (optional)

        Returns:
            List of earnings events
        """
        try:
            # Default to next 30 days
            if not from_date:
                from_date = datetime.now().strftime("%Y-%m-%d")
            if not to_date:
                to_date = (datetime.now() + timedelta(days=30)).strftime("%Y-%m-%d")

            params = {
                "from": from_date,
                "to": to_date
            }

            if ticker:
                params["symbol"] = ticker.upper()

            data = await self._make_request("calendar/earnings", params=params)

            if not data or "earningsCalendar" not in data:
                return []

            earnings = []
            for event in data["earningsCalendar"]:
                earnings.append({
                    "ticker": event.get("symbol"),
                    "date": event.get("date"),
                    "eps_estimate": event.get("epsEstimate"),
                    "eps_actual": event.get("epsActual"),
                    "revenue_estimate": event.get("revenueEstimate"),
                    "revenue_actual": event.get("revenueActual"),
                    "quarter": event.get("quarter"),
                    "year": event.get("year"),
                    "surprise_percent": self._calculate_surprise(
                        event.get("epsActual"),
                        event.get("epsEstimate")
                    )
                })

            logger.info(f"Fetched {len(earnings)} earnings events")
            return earnings

        except Exception as e:
            logger.error("Failed to fetch earnings calendar", error=str(e))
            return []

    def _calculate_surprise(self, actual: Optional[float], estimate: Optional[float]) -> Optional[float]:
        """Calculate earnings surprise percentage"""
        if actual is None or estimate is None or estimate == 0:
            return None

        return ((actual - estimate) / abs(estimate)) * 100

    async def get_analyst_recommendations(self, ticker: str) -> Dict[str, Any]:
        """
        Get analyst recommendations summary

        Returns buy/hold/sell counts and consensus
        """
        try:
            data = await self._make_request(
                "stock/recommendation",
                params={"symbol": ticker.upper()}
            )

            if not data:
                return {}

            # Get most recent recommendation
            latest = data[0] if data else {}

            buy = latest.get("buy", 0) + latest.get("strongBuy", 0)
            hold = latest.get("hold", 0)
            sell = latest.get("sell", 0) + latest.get("strongSell", 0)

            total = buy + hold + sell

            if total == 0:
                consensus = "neutral"
            elif buy / total > 0.6:
                consensus = "buy"
            elif sell / total > 0.4:
                consensus = "sell"
            else:
                consensus = "hold"

            return {
                "ticker": ticker.upper(),
                "buy": buy,
                "hold": hold,
                "sell": sell,
                "consensus": consensus,
                "period": latest.get("period"),
                "timestamp": datetime.now().isoformat()
            }

        except Exception as e:
            logger.error("Failed to fetch analyst recommendations", ticker=ticker, error=str(e))
            return {}

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """
        Get financial data (implements DataSource interface)

        For Finnhub, this returns sentiment and news-based metrics
        """
        results = []

        try:
            # Get social sentiment
            if "sentiment" in concepts:
                sentiment = await self.get_social_sentiment(ticker)

                results.append(FinancialData(
                    ticker=ticker.upper(),
                    concept="sentiment_score",
                    value=sentiment.get("overall_score", 0),
                    unit="score",
                    period="current",
                    source=DataSourceType.FINNHUB,
                    citation={
                        "source": "Finnhub",
                        "type": "social_sentiment",
                        "timestamp": sentiment.get("timestamp"),
                        "reddit_mentions": sentiment.get("reddit", {}).get("mentions", 0),
                        "twitter_mentions": sentiment.get("twitter", {}).get("mentions", 0)
                    }
                ))

            # Get analyst recommendations
            if "analyst_rating" in concepts:
                recs = await self.get_analyst_recommendations(ticker)

                # Convert consensus to numeric score
                score_map = {"buy": 1.0, "hold": 0.0, "sell": -1.0, "neutral": 0.0}
                score = score_map.get(recs.get("consensus", "neutral"), 0.0)

                results.append(FinancialData(
                    ticker=ticker.upper(),
                    concept="analyst_consensus",
                    value=score,
                    unit="score",
                    period="current",
                    source=DataSourceType.FINNHUB,
                    citation={
                        "source": "Finnhub",
                        "type": "analyst_recommendations",
                        "buy": recs.get("buy", 0),
                        "hold": recs.get("hold", 0),
                        "sell": recs.get("sell", 0),
                        "timestamp": recs.get("timestamp")
                    }
                ))

        except Exception as e:
            logger.error("Failed to get financial data from Finnhub", ticker=ticker, error=str(e))

        return results
