"""
Technical Indicators Module
Pre-computed indicators for AI agent consumption
"""

import pandas as pd
import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from enum import Enum
import structlog

logger = structlog.get_logger(__name__)


class IndicatorType(str, Enum):
    """Supported technical indicators"""
    SMA = "sma"  # Simple Moving Average
    EMA = "ema"  # Exponential Moving Average
    RSI = "rsi"  # Relative Strength Index
    MACD = "macd"  # Moving Average Convergence Divergence
    BOLLINGER = "bollinger"  # Bollinger Bands
    STOCHASTIC = "stochastic"  # Stochastic Oscillator
    ATR = "atr"  # Average True Range
    ADX = "adx"  # Average Directional Index


@dataclass
class IndicatorResult:
    """Result from technical indicator calculation"""
    indicator: str
    value: float
    timestamp: str
    signal: Optional[str] = None  # "bullish", "bearish", "neutral"
    confidence: Optional[float] = None  # 0-1
    metadata: Optional[Dict[str, Any]] = None


class TechnicalIndicators:
    """
    Calculate technical indicators from price data

    Designed for AI agent consumption with:
    - Pre-computed signals (not just values)
    - Confidence scores
    - Human-readable interpretations
    """

    @staticmethod
    def calculate_sma(prices: pd.Series, period: int = 50) -> pd.Series:
        """Calculate Simple Moving Average"""
        return prices.rolling(window=period).mean()

    @staticmethod
    def calculate_ema(prices: pd.Series, period: int = 50) -> pd.Series:
        """Calculate Exponential Moving Average"""
        return prices.ewm(span=period, adjust=False).mean()

    @staticmethod
    def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
        """
        Calculate Relative Strength Index

        RSI > 70: Overbought
        RSI < 30: Oversold
        """
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()

        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi

    @staticmethod
    def calculate_macd(
        prices: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> Dict[str, pd.Series]:
        """
        Calculate MACD (Moving Average Convergence Divergence)

        Returns:
            macd_line, signal_line, histogram
        """
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return {
            "macd": macd_line,
            "signal": signal_line,
            "histogram": histogram
        }

    @staticmethod
    def calculate_bollinger_bands(
        prices: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> Dict[str, pd.Series]:
        """
        Calculate Bollinger Bands

        Returns:
            upper_band, middle_band (SMA), lower_band
        """
        middle = prices.rolling(window=period).mean()
        std = prices.rolling(window=period).std()

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return {
            "upper": upper,
            "middle": middle,
            "lower": lower
        }

    @staticmethod
    def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 14) -> pd.Series:
        """Calculate Average True Range (volatility indicator)"""
        high_low = high - low
        high_close = abs(high - close.shift())
        low_close = abs(low - close.shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr

    @classmethod
    def generate_signals(
        cls,
        ticker: str,
        price_data: List[Dict[str, Any]],
        indicators: Optional[List[IndicatorType]] = None
    ) -> List[IndicatorResult]:
        """
        Generate AI-ready signals from price data

        Args:
            ticker: Stock symbol
            price_data: List of price records with OHLC data
            indicators: Which indicators to calculate (all if None)

        Returns:
            List of indicator results with signals
        """
        if not price_data:
            return []

        # Convert to DataFrame
        df = pd.DataFrame(price_data)
        df = df.sort_values("date")

        close = df["close"]
        high = df["high"]
        low = df["low"]

        results = []
        timestamp = df["date"].iloc[-1]

        # Calculate requested indicators (or all)
        if indicators is None:
            indicators = list(IndicatorType)

        for indicator in indicators:
            try:
                if indicator == IndicatorType.SMA:
                    sma_50 = cls.calculate_sma(close, 50)
                    sma_200 = cls.calculate_sma(close, 200)

                    if len(sma_50) > 0 and len(sma_200) > 0:
                        current_price = close.iloc[-1]
                        sma50_val = sma_50.iloc[-1]
                        sma200_val = sma_200.iloc[-1]

                        # Golden Cross / Death Cross detection
                        if sma50_val > sma200_val:
                            signal = "bullish"
                            confidence = min(((sma50_val - sma200_val) / sma200_val) * 10, 1.0)
                        else:
                            signal = "bearish"
                            confidence = min(((sma200_val - sma50_val) / sma200_val) * 10, 1.0)

                        results.append(IndicatorResult(
                            indicator="sma_crossover",
                            value=sma50_val,
                            timestamp=timestamp,
                            signal=signal,
                            confidence=confidence,
                            metadata={
                                "sma_50": float(sma50_val),
                                "sma_200": float(sma200_val),
                                "price": float(current_price)
                            }
                        ))

                elif indicator == IndicatorType.RSI:
                    rsi = cls.calculate_rsi(close)
                    if len(rsi) > 0:
                        rsi_val = rsi.iloc[-1]

                        if rsi_val > 70:
                            signal = "overbought"
                            confidence = min((rsi_val - 70) / 30, 1.0)
                        elif rsi_val < 30:
                            signal = "oversold"
                            confidence = min((30 - rsi_val) / 30, 1.0)
                        else:
                            signal = "neutral"
                            confidence = 1.0 - (abs(rsi_val - 50) / 50)

                        results.append(IndicatorResult(
                            indicator="rsi",
                            value=float(rsi_val),
                            timestamp=timestamp,
                            signal=signal,
                            confidence=confidence
                        ))

                elif indicator == IndicatorType.MACD:
                    macd_data = cls.calculate_macd(close)
                    if len(macd_data["macd"]) > 1:
                        macd_val = macd_data["macd"].iloc[-1]
                        signal_val = macd_data["signal"].iloc[-1]
                        histogram = macd_data["histogram"].iloc[-1]

                        # MACD crossover
                        if histogram > 0:
                            signal = "bullish"
                            confidence = min(abs(histogram) / abs(macd_val), 1.0)
                        else:
                            signal = "bearish"
                            confidence = min(abs(histogram) / abs(macd_val), 1.0)

                        results.append(IndicatorResult(
                            indicator="macd",
                            value=float(macd_val),
                            timestamp=timestamp,
                            signal=signal,
                            confidence=confidence,
                            metadata={
                                "macd": float(macd_val),
                                "signal": float(signal_val),
                                "histogram": float(histogram)
                            }
                        ))

                elif indicator == IndicatorType.BOLLINGER:
                    bb = cls.calculate_bollinger_bands(close)
                    if len(bb["upper"]) > 0:
                        current_price = close.iloc[-1]
                        upper = bb["upper"].iloc[-1]
                        lower = bb["lower"].iloc[-1]
                        middle = bb["middle"].iloc[-1]

                        # Price position relative to bands
                        if current_price > upper:
                            signal = "overbought"
                            confidence = min((current_price - upper) / upper, 1.0)
                        elif current_price < lower:
                            signal = "oversold"
                            confidence = min((lower - current_price) / lower, 1.0)
                        else:
                            signal = "neutral"
                            confidence = 1.0 - (abs(current_price - middle) / (upper - lower))

                        results.append(IndicatorResult(
                            indicator="bollinger_bands",
                            value=float(current_price),
                            timestamp=timestamp,
                            signal=signal,
                            confidence=confidence,
                            metadata={
                                "upper": float(upper),
                                "middle": float(middle),
                                "lower": float(lower),
                                "price": float(current_price)
                            }
                        ))

            except Exception as e:
                logger.warning(f"Failed to calculate {indicator}", ticker=ticker, error=str(e))
                continue

        return results

    @classmethod
    def get_momentum_score(cls, signals: List[IndicatorResult]) -> Dict[str, Any]:
        """
        Aggregate signals into overall momentum score

        Returns:
            overall_signal, confidence, reasoning
        """
        if not signals:
            return {
                "signal": "neutral",
                "confidence": 0.0,
                "reasoning": "No signals available"
            }

        bullish_count = sum(1 for s in signals if s.signal == "bullish")
        bearish_count = sum(1 for s in signals if s.signal == "bearish")
        total = len(signals)

        bullish_ratio = bullish_count / total
        bearish_ratio = bearish_count / total

        if bullish_ratio > 0.6:
            signal = "bullish"
            confidence = bullish_ratio
        elif bearish_ratio > 0.6:
            signal = "bearish"
            confidence = bearish_ratio
        else:
            signal = "neutral"
            confidence = 1.0 - abs(bullish_ratio - bearish_ratio)

        # Generate reasoning
        bullish_indicators = [s.indicator for s in signals if s.signal == "bullish"]
        bearish_indicators = [s.indicator for s in signals if s.signal == "bearish"]

        reasoning = f"{bullish_count} bullish signals ({', '.join(bullish_indicators[:3])}), "
        reasoning += f"{bearish_count} bearish signals ({', '.join(bearish_indicators[:3])})"

        return {
            "signal": signal,
            "confidence": confidence,
            "reasoning": reasoning,
            "indicators_analyzed": total
        }
