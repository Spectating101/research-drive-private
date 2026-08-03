#!/usr/bin/env python3
"""
Market Regime Detection Module

This module provides functionality to detect market regimes (bull, bear, volatile, range-bound)
based on historical price data and statistical analysis.

Classes:
    MarketRegimeDetector: Main class for regime detection

Usage:
    detector = MarketRegimeDetector()
    regime = detector.detect_regime()
    print(f"Current market regime: {regime}")
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MarketRegimeDetector:
    """
    Detects market regimes based on price action, volatility, and trend analysis.
    
    Market regimes include:
    - BULL_TREND: Strong upward trend with moderate volatility
    - BEAR_TREND: Strong downward trend with moderate to high volatility
    - RANGE_BOUND: No clear trend with low volatility
    - HIGH_VOLATILITY: Any trend with abnormally high volatility
    """
    
    def __init__(self, db_path='historical_data.db'):
        """
        Initialize the detector with database connection and market indices.
        
        Args:
            db_path (str): Path to the SQLite database containing historical data
        """
        self.db_path = db_path
        
        # Define market indices for different markets
        self.market_indices = {
            'indo': '^JKSE',  # Jakarta Composite Index
            'taiwan': '^TWII',  # Taiwan Weighted Index
            'us': '^GSPC'     # S&P 500 (for global market reference)
        }
        
        # Define regime parameters
        self.volatility_threshold = 1.3  # Ratio of current to historical volatility
        self.trend_threshold = 5.0      # % change threshold for trend detection
        self.min_data_points = 50       # Minimum required data points
    
    def get_market_data(self, symbol, lookback=90):
        """
        Retrieve market data for the specified symbol and lookback period.
        
        Args:
            symbol (str): Market index symbol
            lookback (int): Number of days to look back
            
        Returns:
            pd.DataFrame: DataFrame with OHLCV data or None if data unavailable
        """
        try:
            # Calculate start date based on lookback
            end_date = datetime.now()
            start_date = end_date - timedelta(days=lookback * 1.5)  # Add margin for weekends/holidays
            
            # Connect to database
            if not os.path.exists(self.db_path):
                logger.error(f"Database not found at {self.db_path}")
                return None
                
            conn = sqlite3.connect(self.db_path)
            
            # Query historical data
            query = """
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data_daily
            WHERE symbol = ? 
            AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp ASC
            """
            
            df = pd.read_sql_query(
                query, 
                conn, 
                params=(symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
            )
            
            conn.close()
            
            # Check if we got enough data
            if len(df) < self.min_data_points:
                logger.warning(f"Insufficient data for {symbol}: {len(df)} rows")
                # Try without .JK suffix as fallback
                if symbol.endswith('.JK'):
                    return self.get_market_data(symbol[:-3], lookback)
                return None
                
            # Process data
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
            # Ensure numeric types
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
                
            df.dropna(inplace=True)
            
            return df
            
        except Exception as e:
            logger.error(f"Error retrieving market data for {symbol}: {e}")
            return None
    
    def detect_regime(self, market_code='indo', lookback=90):
        """
        Detect the current market regime based on multiple factors.
        
        Args:
            market_code (str): Market to analyze ('indo', 'taiwan', 'us')
            lookback (int): Days to analyze
            
        Returns:
            str: Market regime classification
        """
        # Get proxy symbol for the market
        symbol = self.market_indices.get(market_code)
        if not symbol:
            logger.warning(f"Unknown market code: {market_code}")
            return "UNKNOWN"
            
        # Add .JK suffix for Indonesian symbols if needed
        if market_code == 'indo' and not symbol.endswith('.JK'):
            symbol = f"{symbol}.JK"
            
        # Get market data
        data = self.get_market_data(symbol, lookback)
        if data is None or len(data) < self.min_data_points:
            logger.warning(f"Insufficient data for market regime detection: {market_code}")
            return "UNKNOWN"
            
        # Calculate trend indicators
        sma20 = data['close'].rolling(20).mean()
        sma50 = data['close'].rolling(50).mean()
        
        # Calculate volatility indicators
        returns = data['close'].pct_change().dropna()
        current_vol = returns.tail(20).std() * 100  # Convert to percentage
        historical_vol = returns.std() * 100        # Convert to percentage
        vol_ratio = current_vol / historical_vol if historical_vol > 0 else 1.0
        
        # Calculate momentum
        price_momentum = (data['close'].iloc[-1] / data['close'].iloc[-20] - 1) * 100
        
        logger.info(f"Market stats - Momentum: {price_momentum:.2f}%, Vol Ratio: {vol_ratio:.2f}, "
                   f"Current Vol: {current_vol:.2f}%, Historical Vol: {historical_vol:.2f}%")
        
        # Determine regime based on indicators
        if vol_ratio > self.volatility_threshold:
            regime = "HIGH_VOLATILITY"
        elif price_momentum > self.trend_threshold and data['close'].iloc[-1] > sma50.iloc[-1]:
            regime = "BULL_TREND"
        elif price_momentum < -self.trend_threshold and data['close'].iloc[-1] < sma50.iloc[-1]:
            regime = "BEAR_TREND"
        else:
            regime = "RANGE_BOUND"
            
        logger.info(f"Detected market regime for {market_code}: {regime}")
        return regime
        
    def get_regime_parameters(self, regime="UNKNOWN"):
        """
        Get recommended parameters for the detected regime.
        
        Args:
            regime (str): Detected market regime
            
        Returns:
            dict: Dictionary with recommended parameters for the given regime
        """
        # Default parameters
        params = {
            "risk_multiplier": 1.0,
            "gain_multiplier": 1.0,
            "loss_multiplier": 1.0,
            "win_rate_threshold": 70.0,
            "position_size_pct": 2.0
        }
        
        # Adjust based on regime
        if regime == "BULL_TREND":
            params.update({
                "risk_multiplier": 1.2,
                "gain_multiplier": 1.2,
                "loss_multiplier": 1.0,
                "win_rate_threshold": 65.0,
                "position_size_pct": 2.5
            })
        elif regime == "BEAR_TREND":
            params.update({
                "risk_multiplier": 0.8,
                "gain_multiplier": 0.9,
                "loss_multiplier": 0.8,
                "win_rate_threshold": 75.0,
                "position_size_pct": 1.5
            })
        elif regime == "HIGH_VOLATILITY":
            params.update({
                "risk_multiplier": 0.7,
                "gain_multiplier": 1.1,
                "loss_multiplier": 0.7,
                "win_rate_threshold": 80.0,
                "position_size_pct": 1.0
            })
        elif regime == "RANGE_BOUND":
            params.update({
                "risk_multiplier": 1.0,
                "gain_multiplier": 0.9,
                "loss_multiplier": 0.9,
                "win_rate_threshold": 70.0,
                "position_size_pct": 2.0
            })
            
        logger.info(f"Parameters for {regime} regime: {params}")
        return params

# Example usage
if __name__ == "__main__":
    detector = MarketRegimeDetector()
    regime = detector.detect_regime(market_code='indo')
    print(f"Current market regime: {regime}")
    
    # Get recommended parameters for the regime
    params = detector.get_regime_parameters(regime)
    print("Recommended parameters:")
    for key, value in params.items():
        print(f"  {key}: {value}")