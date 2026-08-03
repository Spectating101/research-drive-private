"""
Market Data API Endpoints
Leverages multi-source aggregator for comprehensive data
"""

import structlog
from fastapi import APIRouter, HTTPException, Depends, Query
from typing import Optional, List
from datetime import datetime

from src.auth.dependencies import get_current_user, require_tier
from src.models.user import User, PricingTier
from src.data_sources.aggregator import get_aggregator

logger = structlog.get_logger(__name__)

router = APIRouter()


@router.get("/market/quote/{ticker}")
async def get_quote(
    ticker: str,
    include_fundamentals: bool = Query(False, description="Include fundamental data"),
    user: User = Depends(get_current_user)
):
    """
    Get real-time quote for a ticker

    **Tier Access:**
    - Free: 15-min delayed data
    - Starter: 15-min delayed data
    - Professional: Real-time data (<200ms latency)
    - Enterprise: Real-time data + priority routing

    **Response:**
    ```json
    {
        "ticker": "AAPL",
        "price": 175.43,
        "timestamp": "2025-01-26T14:30:00Z",
        "source": "polygon_realtime",
        "day": {
            "open": 174.20,
            "high": 176.10,
            "low": 173.80,
            "volume": 45678900
        }
    }
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_real_time_quote(
            ticker=ticker.upper(),
            tier=user.tier,
            include_fundamentals=include_fundamentals
        )

        return {
            "success": True,
            "data": result,
            "tier": user.tier.value,
            "timestamp": datetime.now().isoformat()
        }

    except Exception as e:
        logger.error("Failed to fetch quote", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/historical/{ticker}")
async def get_historical(
    ticker: str,
    period: str = Query("1y", description="Time period (1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, 10y, max)"),
    interval: str = Query("1d", description="Data interval (1m, 5m, 15m, 30m, 1h, 1d, 1wk, 1mo)"),
    user: User = Depends(get_current_user)
):
    """
    Get historical price data

    **Tier Access:**
    - Free: Daily data, max 1 year
    - Starter: Daily + intraday, max 5 years
    - Professional: All intervals, max 20 years
    - Enterprise: Unlimited historical depth

    **Response:**
    ```json
    {
        "ticker": "AAPL",
        "data": [
            {
                "date": "2024-01-26",
                "open": 174.20,
                "high": 176.10,
                "low": 173.80,
                "close": 175.43,
                "volume": 45678900
            }
        ],
        "count": 252
    }
    ```
    """
    try:
        # Tier-based restrictions
        if user.tier == PricingTier.FREE:
            if period not in ["1d", "5d", "1mo", "3mo", "6mo", "1y"]:
                raise HTTPException(
                    status_code=403,
                    detail="Free tier limited to max 1 year historical data. Upgrade to Starter for more."
                )
            if interval not in ["1d"]:
                raise HTTPException(
                    status_code=403,
                    detail="Free tier limited to daily data. Upgrade to Starter for intraday."
                )

        if user.tier == PricingTier.STARTER:
            if interval not in ["5m", "15m", "30m", "1h", "1d"]:
                raise HTTPException(
                    status_code=403,
                    detail="Starter tier limited to 5m+ intervals. Upgrade to Professional for 1-minute data."
                )

        aggregator = get_aggregator()

        result = await aggregator.get_historical_data(
            ticker=ticker.upper(),
            tier=user.tier,
            period=period,
            interval=interval
        )

        return {
            "success": True,
            "ticker": ticker.upper(),
            "period": period,
            "interval": interval,
            "data": result,
            "count": len(result),
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch historical data", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/fundamentals/{ticker}")
async def get_fundamentals(
    ticker: str,
    user: User = Depends(require_tier(PricingTier.STARTER))
):
    """
    Get company fundamentals

    **Tier Access:**
    - Starter+: Basic fundamentals
    - Professional+: Multi-source validation

    **Response:**
    ```json
    {
        "ticker": "AAPL",
        "market_cap": 2800000000000,
        "pe_ratio": 28.5,
        "eps": 6.15,
        "revenue_ttm": 394000000000,
        "dividend_yield": 0.0045,
        "beta": 1.25
    }
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_fundamentals(
            ticker=ticker.upper(),
            tier=user.tier
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"No fundamental data found for {ticker}")

        return {
            "success": True,
            "data": result,
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch fundamentals", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/news/{ticker}")
async def get_news(
    ticker: str,
    days: int = Query(7, ge=1, le=30, description="Number of days to look back"),
    user: User = Depends(require_tier(PricingTier.STARTER))
):
    """
    Get news with sentiment analysis

    **Tier Access:**
    - Starter+: Company news with sentiment
    - Professional+: Multi-source news aggregation

    **Response:**
    ```json
    {
        "ticker": "AAPL",
        "news": [
            {
                "headline": "Apple Reports Record Q4 Earnings",
                "summary": "...",
                "sentiment": {
                    "label": "positive",
                    "score": 0.85
                },
                "published_at": "2025-01-26T10:00:00Z"
            }
        ],
        "social_sentiment": {
            "overall": "positive",
            "reddit": {"score": 0.6, "mentions": 1500},
            "twitter": {"score": 0.7, "mentions": 8900}
        }
    }
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_news_sentiment(
            ticker=ticker.upper(),
            tier=user.tier,
            days=days
        )

        return {
            "success": True,
            "data": result,
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch news", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/earnings")
async def get_earnings_calendar(
    ticker: Optional[str] = Query(None, description="Filter by ticker (optional)"),
    days_ahead: int = Query(30, ge=1, le=90, description="Number of days ahead to look"),
    user: User = Depends(require_tier(PricingTier.STARTER))
):
    """
    Get upcoming earnings calendar

    **Tier Access:**
    - Starter+: Earnings calendar access

    **Response:**
    ```json
    [
        {
            "ticker": "AAPL",
            "date": "2025-02-15",
            "eps_estimate": 2.15,
            "revenue_estimate": 120000000000,
            "quarter": 1,
            "year": 2025
        }
    ]
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_earnings_calendar(
            ticker=ticker.upper() if ticker else None,
            tier=user.tier,
            days_ahead=days_ahead
        )

        return {
            "success": True,
            "data": result,
            "count": len(result),
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch earnings", error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/analysts/{ticker}")
async def get_analysts(
    ticker: str,
    user: User = Depends(require_tier(PricingTier.STARTER))
):
    """
    Get analyst recommendations

    **Tier Access:**
    - Starter+: Analyst consensus data

    **Response:**
    ```json
    {
        "ticker": "AAPL",
        "buy": 25,
        "hold": 8,
        "sell": 2,
        "consensus": "buy",
        "timestamp": "2025-01-26T14:30:00Z"
    }
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_analyst_recommendations(
            ticker=ticker.upper(),
            tier=user.tier
        )

        if not result:
            raise HTTPException(status_code=404, detail=f"No analyst data found for {ticker}")

        return {
            "success": True,
            "data": result,
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch analysts", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/options/{ticker}")
async def get_options(
    ticker: str,
    expiration_date: Optional[str] = Query(None, description="Filter by expiration date (YYYY-MM-DD)"),
    user: User = Depends(require_tier(PricingTier.PROFESSIONAL))
):
    """
    Get options chain

    **Tier Access:**
    - Professional+: Options chain data

    **Response:**
    ```json
    [
        {
            "contract_type": "call",
            "expiration_date": "2025-03-21",
            "strike_price": 180.0,
            "contract_ticker": "O:AAPL250321C00180000"
        }
    ]
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_options_chain(
            ticker=ticker.upper(),
            tier=user.tier,
            expiration_date=expiration_date
        )

        return {
            "success": True,
            "ticker": ticker.upper(),
            "data": result,
            "count": len(result),
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch options", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/market/multi-validate/{ticker}")
async def multi_source_validate(
    ticker: str,
    concepts: List[str] = Query(..., description="Concepts to validate across sources"),
    user: User = Depends(require_tier(PricingTier.PROFESSIONAL))
):
    """
    Get multi-source validation for data consistency

    **Tier Access:**
    - Professional+: Multi-source validation

    **Response:**
    ```json
    {
        "price": {
            "values": [
                {"value": 175.43, "source": "POLYGON", "timestamp": "..."},
                {"value": 175.45, "source": "ALPHA_VANTAGE", "timestamp": "..."}
            ],
            "consistency_score": 0.98,
            "source_count": 2
        }
    }
    ```
    """
    try:
        aggregator = get_aggregator()

        result = await aggregator.get_multi_source_validation(
            ticker=ticker.upper(),
            concepts=concepts,
            tier=user.tier
        )

        return {
            "success": True,
            "ticker": ticker.upper(),
            "data": result,
            "tier": user.tier.value
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed multi-source validation", ticker=ticker, error=str(e))
        raise HTTPException(status_code=500, detail=str(e))
