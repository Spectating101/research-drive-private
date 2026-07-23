"""
Financial Metrics API Routes
Core revenue-generating endpoints
"""

import structlog
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

from src.data_sources import get_registry, DataSourceCapability
from src.models.user import User, APIKey, PricingTier, TIER_LIMITS

logger = structlog.get_logger(__name__)
router = APIRouter()


class MetricRequest(BaseModel):
    """Request model for metric queries"""
    ticker: str = Field(..., description="Company ticker symbol")
    metrics: List[str] = Field(..., description="Financial metrics to fetch (revenue, netIncome, etc.)")
    period: Optional[str] = Field(None, description="Period filter (e.g., 2023-Q4, ttm)")


class MetricResponse(BaseModel):
    """Response model for metric data"""
    ticker: str
    metric: str
    value: float
    unit: str
    period: str
    citation: Dict[str, Any]
    source: str


async def get_current_user(request: Request) -> User:
    """Dependency to get current authenticated user"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


async def check_feature_access(user: User, feature: str):
    """Check if user's tier has access to a feature"""
    features = TIER_LIMITS[user.tier]["features"]

    if features == ["all"] or feature in features:
        return True

    raise HTTPException(
        status_code=403,
        detail={
            "error": "feature_not_available",
            "message": f"Feature '{feature}' requires {PricingTier.PROFESSIONAL.value} tier or higher",
            "upgrade_url": "https://finsight.io/pricing"
        }
    )


@router.get("/metrics", response_model=List[MetricResponse])
async def get_metrics(
    ticker: str = Query(..., description="Company ticker symbol"),
    metrics: str = Query(..., description="Comma-separated list of metrics (revenue,netIncome,etc.)"),
    period: Optional[str] = Query(None, description="Period filter"),
    user: User = Depends(get_current_user)
):
    """
    Get financial metrics for a company

    **Required Tier:** Free+

    **Example:**
    ```
    GET /api/v1/metrics?ticker=AAPL&metrics=revenue,netIncome&period=2023-Q4
    ```

    **Returns:**
    List of metric values with SEC EDGAR citations
    """
    try:
        # Parse metrics
        metric_list = [m.strip() for m in metrics.split(",")]

        # Get data source registry
        registry = get_registry()
        sources = registry.get_by_capability(DataSourceCapability.FUNDAMENTALS)

        if not sources:
            raise HTTPException(
                status_code=503,
                detail="No data sources available"
            )

        # Use first available source (SEC EDGAR)
        source = sources[0]

        # Fetch data
        results = await source.get_financial_data(
            ticker=ticker,
            concepts=metric_list,
            period=period
        )

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {ticker}"
            )

        # Track usage (will be done by middleware in production)
        # await track_api_usage(user.user_id, "/metrics")

        # Format response
        response = [
            MetricResponse(
                ticker=r.ticker,
                metric=r.concept,
                value=r.value,
                unit=r.unit,
                period=r.period,
                citation=r.citation,
                source=r.source.value
            )
            for r in results
        ]

        logger.info(
            "Metrics fetched",
            user_id=user.user_id,
            ticker=ticker,
            metrics=len(response)
        )

        return response

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to fetch metrics", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to fetch financial metrics"
        )


@router.get("/metrics/available")
async def list_available_metrics():
    """
    List all available financial metrics

    **Required Tier:** Free+

    Returns list of metrics that can be queried via the API
    """
    return {
        "metrics": [
            {"name": "revenue", "description": "Total revenue", "unit": "USD"},
            {"name": "netIncome", "description": "Net income", "unit": "USD"},
            {"name": "totalAssets", "description": "Total assets", "unit": "USD"},
            {"name": "currentAssets", "description": "Current assets", "unit": "USD"},
            {"name": "currentLiabilities", "description": "Current liabilities", "unit": "USD"},
            {"name": "shareholdersEquity", "description": "Shareholders' equity", "unit": "USD"},
            {"name": "totalDebt", "description": "Total debt", "unit": "USD"},
            {"name": "cashAndEquivalents", "description": "Cash and equivalents", "unit": "USD"},
            {"name": "cfo", "description": "Cash from operations", "unit": "USD"},
            {"name": "cfi", "description": "Cash from investing", "unit": "USD"},
            {"name": "cff", "description": "Cash from financing", "unit": "USD"},
            {"name": "grossProfit", "description": "Gross profit", "unit": "USD"},
            {"name": "operatingIncome", "description": "Operating income", "unit": "USD"},
        ],
        "periods": [
            "Latest quarter",
            "Specific period (e.g., 2023-Q4)",
            "ttm (Trailing Twelve Months)"
        ]
    }
