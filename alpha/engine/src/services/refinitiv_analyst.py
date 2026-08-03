
import os
import pandas as pd
import json
import asyncio
from openai import AsyncOpenAI
from typing import Dict, Any, Optional

try:
    from config.settings import settings
except ImportError:
    settings = None

CEREBRAS_BASE_URL = "https://api.cerebras.ai/v1"
CEREBRAS_MODEL = "llama-3.3-70b"

class RefinitivAnalyst:
    """
    Autonomous Financial Analyst that consumes Refinitiv Data and produces Investment Memos.
    """
    def __init__(self):
        self.client = None
        api_key = None
        if settings is not None:
            api_key = getattr(settings, "CEREBRAS_API_KEY", None)
        if not api_key:
            api_key = os.getenv("CEREBRAS_API_KEY")
        if api_key:
            self.client = AsyncOpenAI(api_key=api_key, base_url=CEREBRAS_BASE_URL)
        self.data_cache = {}

    def load_mock_data(self, ticker: str) -> pd.DataFrame:
        """
        Simulates loading Parquet data from Refinitiv harvest.
        In production, this would read: ../finsight-api/data/{ticker}.parquet
        """
        # Create dummy fundamental data (Growing Revenue, High Margins)
        dates = pd.date_range(start='2020-01-01', periods=12, freq='Q')
        data = {
            'date': dates,
            'revenue': [100, 105, 112, 120, 125, 135, 142, 150, 160, 175, 190, 210], # Strong growth
            'gross_profit': [40, 42, 45, 50, 52, 58, 62, 68, 75, 82, 90, 105],       # Expanding margins
            'debt': [50, 50, 48, 45, 40, 35, 30, 25, 20, 15, 10, 5],                 # Deleveraging
            'eps': [1.2, 1.3, 1.4, 1.6, 1.8, 2.0, 2.2, 2.5, 2.8, 3.2, 3.6, 4.0]      # Exploding Earnings
        }
        df = pd.DataFrame(data)
        df.set_index('date', inplace=True)
        return df

    def calculate_metrics(self, df: pd.DataFrame) -> Dict[str, Any]:
        """Calculates key financial ratios."""
        latest = df.iloc[-1]
        start = df.iloc[0]
        
        cagr_rev = ((latest['revenue'] / start['revenue']) ** (1/3) - 1) * 100
        gross_margin = (latest['gross_profit'] / latest['revenue']) * 100
        debt_trend = "Decreasing" if df['debt'].is_monotonic_decreasing else "Increasing"
        
        return {
            "revenue_cagr_3y": f"{cagr_rev:.2f}%",
            "current_gross_margin": f"{gross_margin:.2f}%",
            "debt_trajectory": debt_trend,
            "latest_eps": latest['eps'],
            "eps_growth_total": f"{((latest['eps']/start['eps'])-1)*100:.2f}%"
        }

    async def generate_memo(self, ticker: str, metrics: Dict[str, Any]) -> str:
        """Uses Cerebras LLM to write the investment memo; falls back to mock if no key/client."""

        # Fast mock path when no client is configured
        if not self.client:
            return self._mock_memo(ticker, metrics)
        
        prompt = f"""You are a Senior Equity Research Analyst at a top Hedge Fund.
Write a concise, punchy Investment Memo for {ticker} based on these quantitative metrics:

{json.dumps(metrics, indent=2)}

Focus on:
1. The Growth Story (Revenue CAGR)
2. Profitability Quality (Margins)
3. Balance Sheet Health (Debt)
4. Verdict: BUY, HOLD, or SELL?

Style: Professional, data-driven, no fluff. Use bullet points."""

        try:
            completion = await self.client.chat.completions.create(
                model=CEREBRAS_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7
            )
            return completion.choices[0].message.content
        except Exception as e:
            return f"Error generating memo: {e}"

    def _mock_memo(self, ticker: str, metrics: Dict[str, Any]) -> str:
        """Return a deterministic mock memo for offline/mock runs."""
        return (
            f"**{ticker} Investment Memo (Mock)**\n"
            f"- Growth: {metrics.get('revenue_cagr_3y', 'N/A')} CAGR over 3y\n"
            f"- Margins: {metrics.get('current_gross_margin', 'N/A')} gross margin\n"
            f"- Balance Sheet: Debt trend {metrics.get('debt_trajectory', 'N/A')}\n"
            f"- EPS: Latest {metrics.get('latest_eps', 'N/A')} | Total growth {metrics.get('eps_growth_total', 'N/A')}\n"
            f"- Verdict (mock): HOLD while monitoring margin stability\n"
        )

    async def analyze_ticker(self, ticker: str):
        print(f"🔍 Analyzing {ticker}...")
        
        # 1. Load Data
        df = self.load_mock_data(ticker)
        print("   ✅ Data Loaded (Refinitiv Mock)")
        
        # 2. Compute Metrics
        metrics = self.calculate_metrics(df)
        print("   ✅ Metrics Calculated")
        
        # 3. Generate Insight
        print("   🧠 Generating Investment Memo via Cerebras...")
        memo = await self.generate_memo(ticker, metrics)
        
        print("\n" + "="*40)
        print(f"INVESTMENT MEMO: {ticker}")
        print("="*40)
        print(memo)
        print("="*40)

if __name__ == "__main__":
    analyst = RefinitivAnalyst()
    asyncio.run(analyst.analyze_ticker("NVDA"))
