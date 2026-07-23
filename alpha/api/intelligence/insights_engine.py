"""
AI Insights Engine
Pre-computed financial intelligence for AI agents
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from enum import Enum
import structlog

from src.intelligence.technical_indicators import TechnicalIndicators, IndicatorType

logger = structlog.get_logger(__name__)


class InsightType(str, Enum):
    """Types of insights generated"""
    MOMENTUM = "momentum"
    ANOMALY = "anomaly"
    RISK = "risk"
    TREND = "trend"
    VOLATILITY = "volatility"
    VOLUME = "volume"


class SignalStrength(str, Enum):
    """Signal strength classification"""
    STRONG_BULLISH = "strong_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    STRONG_BEARISH = "strong_bearish"


@dataclass
class Insight:
    """
    Financial insight ready for AI agent consumption

    Designed to be actionable without additional computation
    """
    ticker: str
    insight_type: str
    signal: str  # bullish, bearish, neutral, warning
    confidence: float  # 0-1
    title: str  # Short summary
    reason: str  # Detailed explanation
    detected_at: str
    metadata: Dict[str, Any]
    risk_level: Optional[str] = None  # low, medium, high
    recommended_action: Optional[str] = None


class InsightsEngine:
    """
    Generate AI-ready financial insights

    Combines technical indicators, price action, volume analysis
    to produce actionable intelligence for AI agents
    """

    def __init__(self):
        self.indicators = TechnicalIndicators()

    async def generate_all_insights(
        self,
        ticker: str,
        price_data: List[Dict[str, Any]],
        quote_data: Optional[Dict[str, Any]] = None
    ) -> List[Insight]:
        """
        Generate all available insights for a ticker

        Args:
            ticker: Stock symbol
            price_data: Historical price records
            quote_data: Current quote (optional)

        Returns:
            List of insights
        """
        insights = []

        # Generate momentum insights
        momentum = await self.analyze_momentum(ticker, price_data)
        insights.extend(momentum)

        # Generate anomaly detections
        anomalies = await self.detect_anomalies(ticker, price_data, quote_data)
        insights.extend(anomalies)

        # Generate risk signals
        risks = await self.analyze_risk(ticker, price_data)
        insights.extend(risks)

        # Generate trend analysis
        trends = await self.analyze_trend(ticker, price_data)
        insights.extend(trends)

        # Sort by confidence (highest first)
        insights.sort(key=lambda x: x.confidence, reverse=True)

        logger.info(f"Generated {len(insights)} insights", ticker=ticker)
        return insights

    async def analyze_momentum(
        self,
        ticker: str,
        price_data: List[Dict[str, Any]]
    ) -> List[Insight]:
        """
        Analyze momentum using technical indicators

        Detects:
        - Golden/Death crosses
        - RSI extremes
        - MACD crossovers
        """
        insights = []

        # Get indicator signals
        signals = self.indicators.generate_signals(
            ticker,
            price_data,
            indicators=[IndicatorType.SMA, IndicatorType.RSI, IndicatorType.MACD]
        )

        for signal in signals:
            if signal.confidence < 0.5:
                continue

            if signal.indicator == "sma_crossover":
                if signal.signal == "bullish":
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.MOMENTUM.value,
                        signal="bullish",
                        confidence=signal.confidence,
                        title="Golden Cross Detected",
                        reason=f"50-day SMA crossed above 200-day SMA (${signal.metadata['sma_50']:.2f} > ${signal.metadata['sma_200']:.2f})",
                        detected_at=datetime.now().isoformat(),
                        metadata=signal.metadata,
                        recommended_action="Consider long positions"
                    ))
                elif signal.signal == "bearish":
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.MOMENTUM.value,
                        signal="bearish",
                        confidence=signal.confidence,
                        title="Death Cross Detected",
                        reason=f"50-day SMA crossed below 200-day SMA (${signal.metadata['sma_50']:.2f} < ${signal.metadata['sma_200']:.2f})",
                        detected_at=datetime.now().isoformat(),
                        metadata=signal.metadata,
                        recommended_action="Consider reducing exposure"
                    ))

            elif signal.indicator == "rsi":
                if signal.signal == "overbought":
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.MOMENTUM.value,
                        signal="warning",
                        confidence=signal.confidence,
                        title="Overbought Condition",
                        reason=f"RSI at {signal.value:.1f} (above 70) - potential pullback",
                        detected_at=datetime.now().isoformat(),
                        metadata={"rsi": signal.value},
                        risk_level="medium",
                        recommended_action="Watch for reversal signals"
                    ))
                elif signal.signal == "oversold":
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.MOMENTUM.value,
                        signal="bullish",
                        confidence=signal.confidence,
                        title="Oversold Condition",
                        reason=f"RSI at {signal.value:.1f} (below 30) - potential bounce",
                        detected_at=datetime.now().isoformat(),
                        metadata={"rsi": signal.value},
                        recommended_action="Watch for entry opportunities"
                    ))

            elif signal.indicator == "macd":
                if signal.signal == "bullish" and signal.confidence > 0.7:
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.MOMENTUM.value,
                        signal="bullish",
                        confidence=signal.confidence,
                        title="MACD Bullish Crossover",
                        reason=f"MACD line crossed above signal line (histogram: {signal.metadata['histogram']:.2f})",
                        detected_at=datetime.now().isoformat(),
                        metadata=signal.metadata,
                        recommended_action="Momentum building"
                    ))

        return insights

    async def detect_anomalies(
        self,
        ticker: str,
        price_data: List[Dict[str, Any]],
        quote_data: Optional[Dict[str, Any]] = None
    ) -> List[Insight]:
        """
        Detect anomalous market behavior

        Detects:
        - Volume spikes
        - Price gaps
        - Unusual price movements
        """
        insights = []

        if len(price_data) < 30:
            return insights

        df = pd.DataFrame(price_data).sort_values("date")

        # Volume anomaly detection
        volumes = df["volume"].dropna()
        if len(volumes) > 0:
            avg_volume = volumes.rolling(30).mean().iloc[-1]
            current_volume = volumes.iloc[-1]

            if current_volume > avg_volume * 2.5:
                ratio = current_volume / avg_volume
                insights.append(Insight(
                    ticker=ticker,
                    insight_type=InsightType.ANOMALY.value,
                    signal="warning",
                    confidence=min(ratio / 5.0, 1.0),
                    title="Unusual Volume Detected",
                    reason=f"Volume {ratio:.1f}x higher than 30-day average ({current_volume:,.0f} vs {avg_volume:,.0f})",
                    detected_at=datetime.now().isoformat(),
                    metadata={
                        "current_volume": int(current_volume),
                        "avg_volume": int(avg_volume),
                        "ratio": float(ratio)
                    },
                    risk_level="high",
                    recommended_action="Investigate news/events"
                ))

        # Price gap detection
        if len(df) >= 2:
            prev_close = df["close"].iloc[-2]
            current_open = df["open"].iloc[-1]
            gap_percent = ((current_open - prev_close) / prev_close) * 100

            if abs(gap_percent) > 3:
                insights.append(Insight(
                    ticker=ticker,
                    insight_type=InsightType.ANOMALY.value,
                    signal="bullish" if gap_percent > 0 else "bearish",
                    confidence=min(abs(gap_percent) / 10.0, 1.0),
                    title=f"{'Gap Up' if gap_percent > 0 else 'Gap Down'} Detected",
                    reason=f"Price gapped {gap_percent:+.1f}% from previous close (${prev_close:.2f} → ${current_open:.2f})",
                    detected_at=datetime.now().isoformat(),
                    metadata={
                        "gap_percent": float(gap_percent),
                        "prev_close": float(prev_close),
                        "current_open": float(current_open)
                    },
                    risk_level="high",
                    recommended_action="Check for news catalyst"
                ))

        # Price spike detection (intraday if quote available)
        if quote_data:
            current_price = quote_data.get("price")
            day_high = quote_data.get("day_high")
            day_low = quote_data.get("day_low")

            if current_price and day_high and day_low:
                day_range = day_high - day_low
                avg_range = df["high"] - df["low"]
                avg_range = avg_range.rolling(20).mean().iloc[-1]

                if day_range > avg_range * 2:
                    insights.append(Insight(
                        ticker=ticker,
                        insight_type=InsightType.VOLATILITY.value,
                        signal="warning",
                        confidence=min(day_range / avg_range / 3, 1.0),
                        title="High Intraday Volatility",
                        reason=f"Today's range ${day_range:.2f} is {day_range/avg_range:.1f}x the 20-day average",
                        detected_at=datetime.now().isoformat(),
                        metadata={
                            "day_range": float(day_range),
                            "avg_range": float(avg_range),
                            "day_high": float(day_high),
                            "day_low": float(day_low)
                        },
                        risk_level="high"
                    ))

        return insights

    async def analyze_risk(
        self,
        ticker: str,
        price_data: List[Dict[str, Any]]
    ) -> List[Insight]:
        """
        Analyze risk signals

        Calculates:
        - Volatility trends
        - Drawdown analysis
        - Support/resistance breaks
        """
        insights = []

        if len(price_data) < 30:
            return insights

        df = pd.DataFrame(price_data).sort_values("date")
        closes = df["close"]

        # Volatility analysis
        returns = closes.pct_change()
        volatility_20d = returns.rolling(20).std() * np.sqrt(252)  # Annualized
        current_vol = volatility_20d.iloc[-1]

        if current_vol > 0.3:  # >30% annualized volatility
            insights.append(Insight(
                ticker=ticker,
                insight_type=InsightType.RISK.value,
                signal="warning",
                confidence=min(current_vol / 0.5, 1.0),
                title="High Volatility Detected",
                reason=f"20-day volatility at {current_vol*100:.1f}% (annualized) - elevated risk",
                detected_at=datetime.now().isoformat(),
                metadata={"volatility": float(current_vol)},
                risk_level="high",
                recommended_action="Consider tighter stops"
            ))

        # Drawdown from peak
        rolling_max = closes.expanding().max()
        drawdown = (closes - rolling_max) / rolling_max
        current_drawdown = drawdown.iloc[-1]

        if current_drawdown < -0.15:  # >15% drawdown
            insights.append(Insight(
                ticker=ticker,
                insight_type=InsightType.RISK.value,
                signal="warning",
                confidence=min(abs(current_drawdown) / 0.3, 1.0),
                title="Significant Drawdown",
                reason=f"Price down {current_drawdown*100:.1f}% from recent peak (${rolling_max.iloc[-1]:.2f})",
                detected_at=datetime.now().isoformat(),
                metadata={
                    "drawdown_percent": float(current_drawdown * 100),
                    "peak_price": float(rolling_max.iloc[-1]),
                    "current_price": float(closes.iloc[-1])
                },
                risk_level="high",
                recommended_action="Assess recovery potential"
            ))

        return insights

    async def analyze_trend(
        self,
        ticker: str,
        price_data: List[Dict[str, Any]]
    ) -> List[Insight]:
        """
        Analyze price trends

        Identifies:
        - Short/medium/long-term trends
        - Trend strength
        - Potential reversals
        """
        insights = []

        if len(price_data) < 50:
            return insights

        df = pd.DataFrame(price_data).sort_values("date")
        closes = df["close"]

        # Calculate multiple timeframe trends
        sma_20 = closes.rolling(20).mean()
        sma_50 = closes.rolling(50).mean()
        sma_200 = closes.rolling(200).mean() if len(closes) >= 200 else None

        current_price = closes.iloc[-1]

        # Short-term trend (20-day)
        if current_price > sma_20.iloc[-1] * 1.02:  # >2% above SMA
            trend_strength = min((current_price / sma_20.iloc[-1] - 1) * 10, 1.0)
            insights.append(Insight(
                ticker=ticker,
                insight_type=InsightType.TREND.value,
                signal="bullish",
                confidence=trend_strength,
                title="Strong Short-Term Uptrend",
                reason=f"Price ${current_price:.2f} trading {((current_price/sma_20.iloc[-1]-1)*100):.1f}% above 20-day SMA",
                detected_at=datetime.now().isoformat(),
                metadata={
                    "price": float(current_price),
                    "sma_20": float(sma_20.iloc[-1]),
                    "distance_percent": float((current_price/sma_20.iloc[-1]-1)*100)
                },
                recommended_action="Momentum in place"
            ))

        # Trend alignment
        if sma_20.iloc[-1] > sma_50.iloc[-1] and current_price > sma_20.iloc[-1]:
            insights.append(Insight(
                ticker=ticker,
                insight_type=InsightType.TREND.value,
                signal="bullish",
                confidence=0.85,
                title="Multi-Timeframe Bullish Alignment",
                reason="Price > 20-day SMA > 50-day SMA - all trends aligned bullish",
                detected_at=datetime.now().isoformat(),
                metadata={
                    "price": float(current_price),
                    "sma_20": float(sma_20.iloc[-1]),
                    "sma_50": float(sma_50.iloc[-1])
                },
                recommended_action="Strong trend structure"
            ))

        return insights

    def get_overall_recommendation(self, insights: List[Insight]) -> Dict[str, Any]:
        """
        Aggregate insights into overall recommendation

        Returns:
            recommendation, confidence, reasoning
        """
        if not insights:
            return {
                "recommendation": "neutral",
                "confidence": 0.0,
                "reasoning": "Insufficient data for recommendation",
                "insights_analyzed": 0
            }

        # Weight by confidence
        bullish_score = sum(i.confidence for i in insights if i.signal == "bullish")
        bearish_score = sum(i.confidence for i in insights if i.signal == "bearish")
        warning_score = sum(i.confidence for i in insights if i.signal == "warning")

        total_score = bullish_score + bearish_score + warning_score

        if total_score == 0:
            return {
                "recommendation": "neutral",
                "confidence": 0.0,
                "reasoning": "Neutral signals",
                "insights_analyzed": len(insights)
            }

        # Determine recommendation
        if bullish_score > bearish_score * 1.5 and warning_score < total_score * 0.3:
            rec = "buy"
            conf = bullish_score / total_score
        elif bearish_score > bullish_score * 1.5 or warning_score > total_score * 0.5:
            rec = "sell"
            conf = (bearish_score + warning_score) / total_score
        else:
            rec = "hold"
            conf = 1.0 - abs(bullish_score - bearish_score) / total_score

        # Generate reasoning
        top_insights = sorted(insights, key=lambda x: x.confidence, reverse=True)[:3]
        reasoning = "; ".join([i.title for i in top_insights])

        return {
            "recommendation": rec,
            "confidence": conf,
            "reasoning": reasoning,
            "insights_analyzed": len(insights),
            "scores": {
                "bullish": float(bullish_score),
                "bearish": float(bearish_score),
                "warning": float(warning_score)
            }
        }
