"""
SEC EDGAR Data Source Plugin
Adapted from Cite-Agent, cleaned for FinSight production use
"""

import aiohttp
import asyncio
import structlog
from typing import Dict, Any, List, Optional
from datetime import datetime

from src.data_sources.base import (
    DataSourcePlugin,
    DataSourceType,
    DataSourceCapability,
    FinancialData
)

logger = structlog.get_logger(__name__)


class SECEdgarSource(DataSourcePlugin):
    """SEC EDGAR data source plugin"""

    # XBRL concept mapping (GAAP + IFRS)
    CONCEPT_MAP = {
        "revenue": ["SalesRevenueNet", "RevenueFromContractWithCustomerExcludingAssessedTax", "Revenues", "Revenue"],
        "costOfRevenue": ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold", "CostOfSales"],
        "grossProfit": ["GrossProfit"],
        "operatingIncome": ["OperatingIncomeLoss", "ProfitLossFromOperatingActivities"],
        "netIncome": ["NetIncomeLoss", "ProfitLoss"],
        "totalAssets": ["Assets", "TotalAssets"],
        "currentAssets": ["AssetsCurrent", "CurrentAssets"],
        "currentLiabilities": ["LiabilitiesCurrent", "CurrentLiabilities"],
        "shareholdersEquity": ["StockholdersEquity", "ShareholdersEquity"],
        "totalDebt": ["DebtLongtermAndShorttermCombinedAmount", "LongTermDebt", "DebtCurrent"],
        "cashAndEquivalents": ["CashAndCashEquivalentsAtCarryingValue", "CashCashEquivalentsAndShortTermInvestments"],
        "cfo": ["NetCashProvidedByUsedInOperatingActivities", "NetCashFromOperatingActivities"],
        "cfi": ["NetCashProvidedByUsedInInvestingActivities", "NetCashFromInvestingActivities"],
        "cff": ["NetCashProvidedByUsedInFinancingActivities", "NetCashFromFinancingActivities"],
        "sharesDiluted": ["WeightedAverageNumberOfDilutedSharesOutstanding", "WeightedAverageNumberOfSharesOutstandingBasicAndDiluted"],
        "sharesBasic": ["WeightedAverageNumberOfSharesOutstandingBasic", "WeightedAverageNumberOfSharesOutstanding"],
        "interestExpense": ["InterestExpense", "InterestPaid"],
        "depreciationAndAmortization": ["DepreciationDepletionAndAmortization", "DepreciationAndAmortization"],
    }

    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.base_url = "https://data.sec.gov"
        self.user_agent = config.get("user_agent", "FinSight API/1.0 (contact@finsight.io)")
        self.session: Optional[aiohttp.ClientSession] = None
        self._session_loop = None
        self._ticker_cik_cache: Dict[str, str] = {}

    def get_source_type(self) -> DataSourceType:
        return DataSourceType.SEC_EDGAR

    def get_capabilities(self) -> List[DataSourceCapability]:
        return [
            DataSourceCapability.FUNDAMENTALS,
            DataSourceCapability.HISTORICAL,
            DataSourceCapability.FILINGS
        ]

    async def _get_session(self) -> aiohttp.ClientSession:
        """Get or create aiohttp session"""
        current_loop = asyncio.get_running_loop()

        if (
            self.session is None
            or self.session.closed
            or self._session_loop is not current_loop
        ):
            if self.session is not None and not self.session.closed:
                await self.session.close()

            self.session = aiohttp.ClientSession(
                headers={"User-Agent": self.user_agent},
                timeout=aiohttp.ClientTimeout(total=30)
            )
            self._session_loop = current_loop

        return self.session

    async def _resolve_ticker_to_cik(self, ticker: str) -> Optional[str]:
        """Resolve ticker to CIK using SEC company tickers JSON"""
        if ticker.upper() in self._ticker_cik_cache:
            return self._ticker_cik_cache[ticker.upper()]

        try:
            session = await self._get_session()
            url = "https://www.sec.gov/files/company_tickers.json"

            async with session.get(url) as response:
                if response.status == 200:
                    data = await response.json()

                    # Search for ticker
                    for entry in data.values():
                        if entry.get("ticker", "").upper() == ticker.upper():
                            cik = str(entry["cik_str"]).zfill(10)
                            self._ticker_cik_cache[ticker.upper()] = cik
                            logger.debug("Resolved ticker to CIK", ticker=ticker, cik=cik)
                            return cik

            logger.warning("Ticker not found in SEC database", ticker=ticker)
            return None

        except Exception as e:
            logger.error("Failed to resolve ticker", ticker=ticker, error=str(e))
            return None

    async def get_financial_data(
        self,
        ticker: str,
        concepts: List[str],
        period: Optional[str] = None
    ) -> List[FinancialData]:
        """Fetch financial data from SEC EDGAR"""
        try:
            # Resolve ticker to CIK
            cik = await self._resolve_ticker_to_cik(ticker)
            if not cik:
                logger.warning("Cannot fetch data without CIK", ticker=ticker)
                return []

            # Fetch companyfacts.json
            url = f"{self.base_url}/api/xbrl/companyfacts/CIK{cik}.json"
            session = await self._get_session()

            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning("Failed to fetch SEC data", ticker=ticker, status=response.status)
                    return []

                data = await response.json()

            # Extract facts for requested concepts
            results = []
            for concept in concepts:
                xbrl_concepts = self.CONCEPT_MAP.get(concept, [concept])

                for xbrl_concept in xbrl_concepts:
                    fact_data = self._extract_fact(data, xbrl_concept, period)
                    if fact_data:
                        results.append(
                            FinancialData(
                                source=DataSourceType.SEC_EDGAR,
                                ticker=ticker,
                                concept=concept,
                                value=fact_data["value"],
                                unit=fact_data["unit"],
                                period=fact_data["period"],
                                period_type=fact_data["period_type"],
                                citation=fact_data["citation"],
                                retrieved_at=datetime.utcnow(),
                                confidence=1.0  # SEC data is authoritative
                            )
                        )
                        break  # Found data for this concept

            return results

        except Exception as e:
            logger.error("Failed to fetch SEC data", ticker=ticker, error=str(e))
            return []

    def _extract_fact(
        self,
        companyfacts_data: Dict[str, Any],
        xbrl_concept: str,
        period_filter: Optional[str]
    ) -> Optional[Dict[str, Any]]:
        """Extract a single fact from companyfacts.json"""
        try:
            # Navigate through GAAP/IFRS taxonomy
            facts = companyfacts_data.get("facts", {})

            for taxonomy in ["us-gaap", "ifrs-full", "dei"]:
                if taxonomy in facts and xbrl_concept in facts[taxonomy]:
                    concept_data = facts[taxonomy][xbrl_concept]

                    # Get units (USD, shares, etc.)
                    units = concept_data.get("units", {})

                    for unit_key, unit_data in units.items():
                        if not unit_data:
                            continue

                        # Sort by filing date (most recent first)
                        sorted_data = sorted(
                            unit_data,
                            key=lambda x: x.get("filed", ""),
                            reverse=True
                        )

                        # Find matching period
                        for entry in sorted_data:
                            if period_filter and entry.get("end") != period_filter:
                                continue

                            # Build citation
                            citation = {
                                "source": "SEC EDGAR",
                                "accession": entry.get("accession"),
                                "filing_date": entry.get("filed"),
                                "form": entry.get("form"),
                                "url": f"https://www.sec.gov/cgi-bin/viewer?action=view&cik={companyfacts_data.get('cik')}&accession_number={entry.get('accession')}&xbrl_type=v"
                            }

                            return {
                                "value": entry.get("val"),
                                "unit": unit_key,
                                "period": entry.get("end"),
                                "period_type": "duration" if entry.get("start") else "instant",
                                "citation": citation
                            }

            return None

        except Exception as e:
            logger.error("Failed to extract fact", concept=xbrl_concept, error=str(e))
            return None

    async def search_companies(self, query: str) -> List[Dict[str, Any]]:
        """Search for companies in SEC database"""
        try:
            session = await self._get_session()
            url = "https://www.sec.gov/files/company_tickers.json"

            async with session.get(url) as response:
                if response.status != 200:
                    return []

                data = await response.json()

            # Filter by query
            query_lower = query.lower()
            results = []

            for entry in data.values():
                if (
                    query_lower in entry.get("title", "").lower()
                    or query_lower == entry.get("ticker", "").lower()
                ):
                    results.append({
                        "ticker": entry.get("ticker"),
                        "name": entry.get("title"),
                        "cik": str(entry.get("cik_str")).zfill(10)
                    })

            return results[:20]  # Limit to 20 results

        except Exception as e:
            logger.error("Company search failed", query=query, error=str(e))
            return []

    async def health_check(self) -> bool:
        """Check if SEC EDGAR API is accessible"""
        try:
            session = await self._get_session()
            url = f"{self.base_url}/api/xbrl/companyfacts/CIK0000320193.json"  # Apple

            async with session.get(url) as response:
                return response.status == 200

        except Exception:
            return False

    def get_rate_limit(self) -> Optional[int]:
        """SEC rate limit: 10 requests per second"""
        return 600  # 600 per minute

    async def __aenter__(self):
        """Context manager entry"""
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit - cleanup session"""
        if self.session and not self.session.closed:
            await self.session.close()
