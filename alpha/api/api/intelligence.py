"""
Intelligence API Routes
AI-ready financial insights for agents
"""

import structlog
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from src.models.user import User
from src.data_sources.market_data import MarketDataSource, MarketDataInterval
from src.intelligence.insights_engine import InsightsEngine, InsightType
from src.intelligence.technical_indicators import TechnicalIndicators, IndicatorType

logger = structlog.get_logger(__name__)
router = APIRouter()


class InsightResponse(BaseModel):
    """AI-ready insight response"""
    ticker: str
    insight_type: str
    signal: str
    confidence: float
    title: str
    reason: str
    detected_at: str
    metadata: dict
    risk_level: Optional[str] = None
    recommended_action: Optional[str] = None


class RecommendationResponse(BaseModel):
    """Overall recommendation with reasoning"""
    ticker: str
    recommendation: str  # buy, sell, hold
    confidence: float
    reasoning: str
    insights_analyzed: int
    scores: dict
    generated_at: str


async def get_current_user(request: Request) -> User:
    """Dependency to get current authenticated user"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


@router.get("/insights", response_model=List[InsightResponse])
async def get_insights(
    ticker: str = Query(..., description="Stock ticker symbol"),
    types: Optional[str] = Query(None, description="Comma-separated insight types (momentum,anomaly,risk,trend)"),
    min_confidence: float = Query(0.5, description="Minimum confidence threshold (0-1)", ge=0, le=1),
    user: User = Depends(get_current_user)
):
    """
    Get AI-ready financial insights

    **Required Tier:** Starter+

    **Returns:**
    - Momentum signals (golden crosses, RSI, MACD)
    - Anomaly detection (volume spikes, gaps, volatility)
    - Risk signals (drawdowns, volatility trends)
    - Trend analysis (multi-timeframe alignment)

    **Example:**
    ```
    GET /api/v1/insights?ticker=AAPL&types=momentum,anomaly&min_confidence=0.7
    ```

    **Response:**
    ```json
    [
      {
        "ticker": "AAPL",
        "insight_type": "momentum",
        "signal": "bullish",
        "confidence": 0.82,
        "title": "Golden Cross Detected",
        "reason": "50-day SMA crossed above 200-day SMA",
        "recommended_action": "Consider long positions"
      }
    ]
    ```
    """
    try:
        # Check tier access
        if user.tier.value == "free":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": "AI insights require Starter tier or higher",
                    "upgrade_url": "https://finsight.io/pricing"
                }
            )

        # Initialize data sources
        market_data = MarketDataSource({})
        insights_engine = InsightsEngine()

        # Fetch price data (last 90 days for analysis)
        price_data = await market_data.get_historical_prices(
            ticker=ticker,
            period="3mo",
            interval=MarketDataInterval.ONE_DAY
        )

        if not price_data:
            raise HTTPException(
                status_code=404,
                detail=f"No price data found for {ticker}"
            )

        # Get current quote
        try:
            quote_data = await market_data.get_realtime_quote(ticker)
        except Exception:
            quote_data = None

        # Generate insights
        insights = await insights_engine.generate_all_insights(
            ticker=ticker,
            price_data=price_data,
            quote_data=quote_data
        )

        # Filter by types if specified
        if types:
            requested_types = [t.strip() for t in types.split(",")]
            insights = [i for i in insights if i.insight_type in requested_types]

        # Filter by confidence
        insights = [i for i in insights if i.confidence >= min_confidence]

        logger.info(
            "Generated insights",
            user_id=user.user_id,
            ticker=ticker,
            count=len(insights)
        )

        # Convert to response model
        return [InsightResponse(**i.__dict__) for i in insights]

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate insights", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate financial insights"
        )


@router.get("/recommendation", response_model=RecommendationResponse)
async def get_recommendation(
    ticker: str = Query(..., description="Stock ticker symbol"),
    user: User = Depends(get_current_user)
):
    """
    Get overall AI recommendation (buy/sell/hold)

    **Required Tier:** Professional+

    **Returns:**
    Aggregated recommendation based on all available insights with
    confidence score and detailed reasoning.

    **Example:**
    ```
    GET /api/v1/recommendation?ticker=AAPL
    ```

    **Response:**
    ```json
    {
      "ticker": "AAPL",
      "recommendation": "buy",
      "confidence": 0.78,
      "reasoning": "Golden Cross Detected; Strong Short-Term Uptrend; Multi-Timeframe Bullish Alignment",
      "insights_analyzed": 8,
      "scores": {
        "bullish": 5.2,
        "bearish": 1.1,
        "warning": 0.3
      }
    }
    ```
    """
    try:
        # Check tier access
        if user.tier.value in ["free", "starter"]:
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": "Overall recommendations require Professional tier",
                    "upgrade_url": "https://finsight.io/pricing"
                }
            )

        # Initialize
        market_data = MarketDataSource({})
        insights_engine = InsightsEngine()

        # Fetch data
        price_data = await market_data.get_historical_prices(
            ticker=ticker,
            period="6mo",
            interval=MarketDataInterval.ONE_DAY
        )

        if not price_data:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {ticker}"
            )

        try:
            quote_data = await market_data.get_realtime_quote(ticker)
        except Exception:
            quote_data = None

        # Generate insights
        insights = await insights_engine.generate_all_insights(
            ticker=ticker,
            price_data=price_data,
            quote_data=quote_data
        )

        # Get overall recommendation
        recommendation = insights_engine.get_overall_recommendation(insights)

        logger.info(
            "Generated recommendation",
            user_id=user.user_id,
            ticker=ticker,
            recommendation=recommendation["recommendation"]
        )

        return RecommendationResponse(
            ticker=ticker.upper(),
            recommendation=recommendation["recommendation"],
            confidence=recommendation["confidence"],
            reasoning=recommendation["reasoning"],
            insights_analyzed=recommendation["insights_analyzed"],
            scores=recommendation["scores"],
            generated_at=datetime.now().isoformat()
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate recommendation", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate recommendation"
        )


@router.get("/indicators")
async def get_technical_indicators(
    ticker: str = Query(..., description="Stock ticker symbol"),
    indicators: str = Query("sma,rsi,macd", description="Comma-separated indicator list"),
    user: User = Depends(get_current_user)
):
    """
    Get pre-computed technical indicators

    **Required Tier:** Starter+

    **Available Indicators:**
    - sma: Simple Moving Average (50, 200)
    - ema: Exponential Moving Average
    - rsi: Relative Strength Index
    - macd: MACD with signal line
    - bollinger: Bollinger Bands
    - atr: Average True Range
    - adx: Average Directional Index

    **Example:**
    ```
    GET /api/v1/indicators?ticker=AAPL&indicators=sma,rsi,macd
    ```
    """
    try:
        # Check tier
        if user.tier.value == "free":
            raise HTTPException(
                status_code=403,
                detail="Technical indicators require Starter tier or higher"
            )

        # Fetch data
        market_data = MarketDataSource({})
        price_data = await market_data.get_historical_prices(
            ticker=ticker,
            period="6mo",
            interval=MarketDataInterval.ONE_DAY
        )

        if not price_data:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {ticker}"
            )

        # Parse indicators
        requested = [i.strip() for i in indicators.split(",")]
        indicator_types = []
        for ind in requested:
            try:
                indicator_types.append(IndicatorType(ind))
            except ValueError:
                continue

        # Calculate indicators
        tech_indicators = TechnicalIndicators()
        signals = tech_indicators.generate_signals(
            ticker=ticker,
            price_data=price_data,
            indicators=indicator_types
        )

        return {
            "ticker": ticker.upper(),
            "indicators": [
                {
                    "indicator": s.indicator,
                    "value": s.value,
                    "signal": s.signal,
                    "confidence": s.confidence,
                    "timestamp": s.timestamp,
                    "metadata": s.metadata
                }
                for s in signals
            ],
            "generated_at": datetime.now().isoformat()
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to calculate indicators", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to calculate technical indicators"
        )
