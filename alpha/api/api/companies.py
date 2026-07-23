"""
Company Search and Information Routes
"""

import structlog
from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel
from typing import List, Optional

from src.data_sources import get_registry
from src.models.user import User, APIKey

logger = structlog.get_logger(__name__)
router = APIRouter()


class CompanyResult(BaseModel):
    """Company search result"""
    ticker: str
    name: str
    cik: str


class CompanySearchResponse(BaseModel):
    """Response for company search"""
    results: List[CompanyResult]
    count: int


async def get_current_user_from_request(request) -> tuple[User, APIKey]:
    """Get authenticated user from request state"""
    user = getattr(request.state, "user", None)
    api_key = getattr(request.state, "api_key", None)

    if not user or not api_key:
        raise HTTPException(
            status_code=401,
            detail="Authentication required"
        )

    return user, api_key


@router.get("/companies/search", response_model=CompanySearchResponse)
async def search_companies(
    q: str = Query(..., description="Search query (company name or ticker)", min_length=1)
):
    """
    Search for companies by name or ticker

    **Required Tier:** Free+

    **Example:**
    ```
    GET /api/v1/companies/search?q=apple
    GET /api/v1/companies/search?q=AAPL
    ```

    **Returns:**
    List of matching companies with ticker, name, and CIK
    """
    try:
        # Get data source registry
        registry = get_registry()
        sources = registry.list_all()

        if not sources:
            raise HTTPException(
                status_code=503,
                detail="No data sources available"
            )

        # Use first available source (SEC EDGAR)
        source = sources[0]

        # Search companies
        results = await source.search_companies(q)

        if not results:
            return CompanySearchResponse(results=[], count=0)

        # Format response
        formatted_results = [
            CompanyResult(
                ticker=r["ticker"],
                name=r["name"],
                cik=r["cik"]
            )
            for r in results
        ]

        logger.info(
            "Company search",
            query=q,
            results=len(formatted_results)
        )

        return CompanySearchResponse(
            results=formatted_results,
            count=len(formatted_results)
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Company search failed", query=q, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Company search failed"
        )


@router.get("/companies/{ticker}")
async def get_company_info(
    ticker: str
):
    """
    Get company information by ticker

    **Required Tier:** Free+

    **Example:**
    ```
    GET /api/v1/companies/AAPL
    ```

    **Returns:**
    Company details including name, CIK, and available data sources
    """
    try:
        # Get data source registry
        registry = get_registry()
        sources = registry.list_all()

        if not sources:
            raise HTTPException(
                status_code=503,
                detail="No data sources available"
            )

        # Search for exact ticker match
        source = sources[0]
        results = await source.search_companies(ticker)

        # Find exact match
        company = None
        for r in results:
            if r["ticker"].upper() == ticker.upper():
                company = r
                break

        if not company:
            raise HTTPException(
                status_code=404,
                detail=f"Company {ticker} not found"
            )

        logger.info(
            "Company info retrieved",
            ticker=ticker
        )

        return {
            "ticker": company["ticker"],
            "name": company["name"],
            "cik": company["cik"],
            "data_sources": ["sec_edgar"],
            "available_metrics": [
                "revenue", "netIncome", "totalAssets", "currentAssets",
                "currentLiabilities", "shareholdersEquity", "totalDebt",
                "cashAndEquivalents", "cfo", "cfi", "cff", "grossProfit",
                "operatingIncome"
            ]
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get company info", ticker=ticker, error=str(e))
        raise HTTPException(
            status_code=500,
            detail="Failed to get company information"
        )
