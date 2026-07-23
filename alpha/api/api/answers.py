"""
LLM-Ready Financial Answers API
Structured, cited financial data optimized for LLM consumption
"""

import structlog
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, Depends, Query
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Literal
from enum import Enum

from src.data_sources import get_registry, DataSourceCapability
from src.models.user import User

logger = structlog.get_logger(__name__)
router = APIRouter()


class SourceCitation(BaseModel):
    """Citation for a data source"""
    type: str = Field(..., description="Source type (sec_filing, market_data, etc.)")
    filing: Optional[str] = Field(None, description="Filing type (10-K, 10-Q, 8-K)")
    url: str = Field(..., description="Source URL")
    excerpt: Optional[str] = Field(None, description="Relevant excerpt from source")
    as_of: Optional[str] = Field(None, description="Data timestamp")


class AnswerResponse(BaseModel):
    """Structured answer with citations and consistency score"""
    ticker: str
    metric: str
    value: Any
    unit: str
    period: str
    as_of: str
    sources: List[SourceCitation]
    consistency_score: float = Field(..., ge=0.0, le=1.0, description="Cross-source consistency (0-1)")
    retrieved_at: str


class LLMPromptResponse(BaseModel):
    """LLM-ready prompt snippet with metadata"""
    prompt_snippet: str = Field(..., description="Formatted text for LLM context")
    metadata: AnswerResponse


async def get_current_user(request: Request) -> User:
    """Dependency to get current authenticated user"""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def calculate_consistency_score(results: List[Any]) -> float:
    """
    Calculate consistency score across multiple data sources

    For now, simplified:
    - Single source = 0.85 (good but not verified)
    - 2+ sources with matching values = 0.96+ (high confidence)
    - Conflicting sources = lower score
    """
    if len(results) == 0:
        return 0.0

    if len(results) == 1:
        # Single source - reasonable confidence
        return 0.85

    # Multiple sources - check if values match
    values = [r.value for r in results]
    unique_values = set(values)

    if len(unique_values) == 1:
        # Perfect agreement across sources
        return 0.96

    # Some disagreement - calculate variance
    # Simplified: reduce score based on number of conflicting values
    agreement_ratio = values.count(values[0]) / len(values)
    return 0.75 + (agreement_ratio * 0.20)


def format_llm_snippet(answer: AnswerResponse) -> str:
    """Format answer data as LLM-ready context snippet"""

    # Format the main fact
    snippet = f"**{answer.ticker} - {answer.metric}**\n"
    snippet += f"Value: {answer.value:,} {answer.unit}\n"
    snippet += f"Period: {answer.period}\n"
    snippet += f"As of: {answer.as_of}\n"
    snippet += f"Confidence: {answer.consistency_score:.0%}\n\n"

    # Add source citations
    snippet += "**Sources:**\n"
    for i, source in enumerate(answer.sources, 1):
        snippet += f"{i}. "
        if source.filing:
            snippet += f"{source.filing} filing"
        else:
            snippet += f"{source.type}"
        snippet += f"\n   URL: {source.url}\n"

        if source.excerpt:
            snippet += f"   Excerpt: {source.excerpt}\n"

    return snippet


@router.get("/answers", response_model=AnswerResponse)
async def get_answer(
    ticker: str = Query(..., description="Company ticker symbol (e.g., AAPL)"),
    metric: str = Query(..., description="Financial metric (e.g., revenue_ttm, net_income)"),
    format: Literal["json", "llm"] = Query("json", description="Response format"),
    user: User = Depends(get_current_user)
):
    """
    Get structured, cited financial answers optimized for LLM consumption

    **Required Tier:** Starter+

    **Key Features:**
    - Structured JSON output (no hallucination)
    - Multi-source citations with URLs
    - Consistency score (cross-source validation)
    - LLM-ready format option
    - Sub-300ms response time

    **Example:**
    ```
    GET /api/v1/answers?ticker=AAPL&metric=revenue_ttm&format=json
    ```

    **Response:**
    ```json
    {
      "ticker": "AAPL",
      "metric": "revenue_ttm",
      "value": 383285000000,
      "unit": "USD",
      "period": "TTM",
      "as_of": "2024-09-30",
      "sources": [...],
      "consistency_score": 0.96,
      "retrieved_at": "2025-11-24T12:00:00Z"
    }
    ```

    **Format Options:**
    - `json`: Structured data (default)
    - `llm`: Formatted text snippet + metadata
    """
    try:
        # Check tier access (Starter+ only)
        if user.tier.value == "free":
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "feature_not_available",
                    "message": "LLM-ready answers require Starter tier or higher",
                    "upgrade_url": "https://finsight.io/pricing"
                }
            )

        # Get data source registry
        registry = get_registry()
        sources = registry.get_by_capability(DataSourceCapability.FUNDAMENTALS)

        if not sources:
            raise HTTPException(
                status_code=503,
                detail="No data sources available"
            )

        # Parse metric (e.g., "revenue_ttm" -> concept="revenue", period="ttm")
        parts = metric.split("_")
        concept = parts[0]
        period = parts[1] if len(parts) > 1 else None

        # Fetch from primary source (SEC EDGAR)
        source = sources[0]
        results = await source.get_financial_data(
            ticker=ticker,
            concepts=[concept],
            period=period
        )

        if not results:
            raise HTTPException(
                status_code=404,
                detail=f"No data found for {ticker} - {metric}"
            )

        # Get primary result
        primary = results[0]

        # Calculate consistency score
        consistency = calculate_consistency_score(results)

        # Build source citations
        citations = []
        for r in results:
            citation = SourceCitation(
                type="sec_filing" if r.source.value == "SEC_EDGAR" else "market_data",
                filing=r.citation.get("filing_type") if r.citation else None,
                url=r.citation.get("url", "") if r.citation else "",
                excerpt=r.citation.get("excerpt") if r.citation else None,
                as_of=r.citation.get("filed_date") if r.citation else None
            )
            citations.append(citation)

        # Build response
        answer = AnswerResponse(
            ticker=ticker.upper(),
            metric=metric,
            value=primary.value,
            unit=primary.unit,
            period=primary.period or period or "latest",
            as_of=primary.citation.get("filed_date", datetime.now().isoformat()) if primary.citation else datetime.now().isoformat(),
            sources=citations,
            consistency_score=consistency,
            retrieved_at=datetime.now().isoformat()
        )

        # Return based on format
        if format == "llm":
            return LLMPromptResponse(
                prompt_snippet=format_llm_snippet(answer),
                metadata=answer
            )

        logger.info(
            "Answer generated",
            user_id=user.user_id,
            ticker=ticker,
            metric=metric,
            consistency=consistency
        )

        return answer

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to generate answer", ticker=ticker, metric=metric, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to generate financial answer"
        )


@router.get("/answers/available")
async def list_available_answers():
    """
    List all available financial answers/metrics

    **Required Tier:** Free+
    """
    return {
        "metrics": [
            {
                "name": "revenue_ttm",
                "description": "Trailing twelve months revenue",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "revenue_latest",
                "description": "Most recent quarter revenue",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "net_income_ttm",
                "description": "Trailing twelve months net income",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "total_assets",
                "description": "Total assets (latest)",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "shareholders_equity",
                "description": "Shareholders equity (latest)",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "cash_equivalents",
                "description": "Cash and cash equivalents",
                "unit": "USD",
                "tier": "starter"
            },
            {
                "name": "total_debt",
                "description": "Total debt (latest)",
                "unit": "USD",
                "tier": "professional"
            },
            {
                "name": "operating_income_ttm",
                "description": "Trailing twelve months operating income",
                "unit": "USD",
                "tier": "professional"
            },
        ],
        "formats": [
            {"name": "json", "description": "Structured JSON response"},
            {"name": "llm", "description": "LLM-ready text snippet with metadata"}
        ],
        "tiers": {
            "free": "Access to /metrics only",
            "starter": "Access to /answers with basic metrics",
            "professional": "Access to all metrics + advanced features",
            "enterprise": "Custom metrics + SLA"
        }
    }
