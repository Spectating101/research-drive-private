#!/usr/bin/env python3
"""
Enhanced IDX Pattern Detection System

This module implements fundamentally-driven pattern detection specifically
designed for Indonesian market inefficiencies and characteristics.
"""

import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging
from scipy import stats
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import TimeSeriesSplit
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class IDXEnhancedPatternDetector:
    """
    Enhanced pattern detector specifically designed for IDX market inefficiencies.
    
    Key IDX Characteristics:
    - Lower market efficiency → Patterns persist longer
    - Higher volatility → More exploitable swings
    - Retail-driven → Sentiment patterns matter
    - Sector rotation → Cross-sectional opportunities
    - Currency sensitivity → USD/IDR correlation patterns
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db'):
        self.db_path = db_path
        
        # IDX-specific parameters
        self.idx_params = {
            'volatility_threshold': 0.03,  # 3% daily volatility threshold
            'momentum_persistence': 0.7,   # Momentum effects persist longer
            'liquidity_threshold': 1000000, # Minimum volume for analysis
            'correlation_decay': 0.95,     # Faster correlation decay
            'sentiment_window': 5,         # Sentiment analysis window
            'regime_switching': True,      # Market regime detection
            'sector_rotation': True,       # Sector rotation analysis
            'currency_sensitivity': True   # USD/IDR correlation
        }
        
        # Pattern detection parameters
        self.pattern_params = {
            'short_window': 5,    # Short-term patterns
            'medium_window': 20,  # Medium-term patterns  
            'long_window': 50,    # Long-term patterns
            'volume_window': 10,  # Volume analysis
            'momentum_window': 14, # Momentum analysis
            'volatility_window': 20, # Volatility analysis
            'correlation_window': 30 # Correlation analysis
        }
        
        logger.info("IDX Enhanced Pattern Detector initialized")
    
    def detect_fundamental_patterns(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Detect fundamental patterns specific to IDX market inefficiencies.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            
        Returns:
            Dictionary of detected patterns with confidence scores
        """
        if df.empty or len(df) < 100:
            return {'error': 'Insufficient data'}
        
        patterns = {}
        
        # 1. Volatility Regime Patterns (IDX is more volatile)
        volatility_patterns = self._detect_volatility_regimes(df)
        patterns.update(volatility_patterns)
        
        # 2. Momentum Persistence Patterns (IDX momentum lasts longer)
        momentum_patterns = self._detect_momentum_persistence(df)
        patterns.update(momentum_patterns)
        
        # 3. Volume-Supported Patterns (Volume confirms trends in IDX)
        volume_patterns = self._detect_volume_support(df)
        patterns.update(volume_patterns)
        
        # 4. Sentiment-Driven Patterns (Retail-driven market)
        sentiment_patterns = self._detect_sentiment_patterns(df)
        patterns.update(sentiment_patterns)
        
        # 5. Liquidity Patterns (IDX liquidity constraints)
        liquidity_patterns = self._detect_liquidity_patterns(df)
        patterns.update(liquidity_patterns)
        
        # 6. Cross-Sectional Patterns (Sector rotation opportunities)
        cross_sectional = self._detect_cross_sectional_patterns(symbol)
        patterns.update(cross_sectional)
        
        return patterns
    
    def _detect_volatility_regimes(self, df: pd.DataFrame) -> Dict:
        """Detect volatility regime patterns specific to IDX."""
        patterns = {}
        
        # Calculate rolling volatility
        returns = df['close'].pct_change().dropna()
        vol_20 = returns.rolling(20).std()
        vol_50 = returns.rolling(50).std()
        
        # IDX-specific volatility patterns
        current_vol = vol_20.iloc[-1]
        avg_vol = vol_50.iloc[-1]
        
        # High volatility regime (IDX characteristic)
        if current_vol > avg_vol * 1.5:
            patterns['HIGH_VOLATILITY_REGIME'] = {
                'confidence': 0.8,
                'signal': 'SELL' if current_vol > avg_vol * 2 else 'HOLD',
                'description': 'High volatility regime - IDX characteristic'
            }
        
        # Volatility clustering (IDX shows strong clustering)
        vol_clustering = self._calculate_volatility_clustering(returns)
        if vol_clustering > 0.7:
            patterns['VOLATILITY_CLUSTERING'] = {
                'confidence': 0.75,
                'signal': 'HOLD',
                'description': 'Volatility clustering detected - expect continued volatility'
            }
        
        return patterns
    
    def _detect_momentum_persistence(self, df: pd.DataFrame) -> Dict:
        """Detect momentum persistence patterns (IDX momentum lasts longer)."""
        patterns = {}
        
        # Calculate momentum indicators
        returns = df['close'].pct_change().dropna()
        
        # Short-term momentum
        mom_5 = returns.rolling(5).mean()
        mom_10 = returns.rolling(10).mean()
        mom_20 = returns.rolling(20).mean()
        
        # IDX momentum persistence patterns
        current_mom_5 = mom_5.iloc[-1]
        current_mom_10 = mom_10.iloc[-1]
        current_mom_20 = mom_20.iloc[-1]
        
        # Strong momentum alignment (IDX characteristic)
        if (current_mom_5 > 0 and current_mom_10 > 0 and current_mom_20 > 0):
            patterns['STRONG_MOMENTUM_ALIGNMENT'] = {
                'confidence': 0.85,
                'signal': 'BUY',
                'description': 'Strong momentum alignment across timeframes - IDX momentum persistence'
            }
        elif (current_mom_5 < 0 and current_mom_10 < 0 and current_mom_20 < 0):
            patterns['STRONG_DOWNTURN_MOMENTUM'] = {
                'confidence': 0.85,
                'signal': 'SELL',
                'description': 'Strong downturn momentum - IDX momentum persistence'
            }
        
        # Momentum acceleration
        mom_acceleration = current_mom_5 - current_mom_20
        if mom_acceleration > 0.02:  # 2% acceleration
            patterns['MOMENTUM_ACCELERATION'] = {
                'confidence': 0.8,
                'signal': 'BUY',
                'description': 'Momentum acceleration detected'
            }
        
        return patterns
    
    def _detect_volume_support(self, df: pd.DataFrame) -> Dict:
        """Detect volume-supported patterns (Volume confirms trends in IDX)."""
        patterns = {}
        
        # Calculate volume metrics
        volume = df['volume']
        price_change = df['close'].pct_change()
        
        # Volume-weighted price change
        vwap = (df['close'] * volume).rolling(20).sum() / volume.rolling(20).sum()
        current_price = df['close'].iloc[-1]
        current_vwap = vwap.iloc[-1]
        
        # Volume surge patterns
        avg_volume = volume.rolling(20).mean()
        current_volume = volume.iloc[-1]
        
        if current_volume > avg_volume.iloc[-1] * 2:
            if current_price > current_vwap:
                patterns['HIGH_VOLUME_BREAKOUT'] = {
                    'confidence': 0.9,
                    'signal': 'BUY',
                    'description': 'High volume breakout above VWAP - strong signal'
                }
            else:
                patterns['HIGH_VOLUME_BREAKDOWN'] = {
                    'confidence': 0.9,
                    'signal': 'SELL',
                    'description': 'High volume breakdown below VWAP - strong signal'
                }
        
        # Volume trend alignment
        volume_trend = volume.rolling(10).mean().iloc[-1] - volume.rolling(30).mean().iloc[-1]
        price_trend = price_change.rolling(10).mean().iloc[-1]
        
        if volume_trend > 0 and price_trend > 0:
            patterns['VOLUME_PRICE_CONFIRMATION'] = {
                'confidence': 0.8,
                'signal': 'BUY',
                'description': 'Volume and price trend alignment'
            }
        
        return patterns
    
    def _detect_sentiment_patterns(self, df: pd.DataFrame) -> Dict:
        """Detect sentiment-driven patterns (Retail-driven IDX market)."""
        patterns = {}
        
        # Calculate sentiment indicators
        returns = df['close'].pct_change().dropna()
        
        # Price range analysis (retail sentiment)
        high_low_ratio = (df['high'] - df['low']) / df['close']
        avg_range = high_low_ratio.rolling(10).mean()
        current_range = high_low_ratio.iloc[-1]
        
        # Extreme sentiment patterns
        if current_range > avg_range.iloc[-1] * 1.5:
            if df['close'].iloc[-1] > df['open'].iloc[-1]:
                patterns['EXTREME_BULLISH_SENTIMENT'] = {
                    'confidence': 0.7,
                    'signal': 'BUY',
                    'description': 'Extreme bullish sentiment - retail buying'
                }
            else:
                patterns['EXTREME_BEARISH_SENTIMENT'] = {
                    'confidence': 0.7,
                    'signal': 'SELL',
                    'description': 'Extreme bearish sentiment - retail selling'
                }
        
        # Gap analysis (IDX shows significant gaps)
        gaps = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        gap_volatility = gaps.rolling(20).std()
        current_gap = gaps.iloc[-1]
        
        if abs(current_gap) > gap_volatility.iloc[-1] * 2:
            if current_gap > 0:
                patterns['BULLISH_GAP'] = {
                    'confidence': 0.75,
                    'signal': 'BUY',
                    'description': 'Significant bullish gap - strong opening'
                }
            else:
                patterns['BEARISH_GAP'] = {
                    'confidence': 0.75,
                    'signal': 'SELL',
                    'description': 'Significant bearish gap - weak opening'
                }
        
        return patterns
    
    def _detect_liquidity_patterns(self, df: pd.DataFrame) -> Dict:
        """Detect liquidity patterns (IDX liquidity constraints)."""
        patterns = {}
        
        volume = df['volume']
        price = df['close']
        
        # Amihud illiquidity measure
        returns = price.pct_change().abs()
        amihud = returns / volume
        avg_amihud = amihud.rolling(20).mean()
        current_amihud = amihud.iloc[-1]
        
        # Liquidity deterioration
        if current_amihud > avg_amihud.iloc[-1] * 1.5:
            patterns['LIQUIDITY_DETERIORATION'] = {
                'confidence': 0.8,
                'signal': 'SELL',
                'description': 'Liquidity deterioration - higher transaction costs'
            }
        
        # Volume drying up
        volume_ma = volume.rolling(20).mean()
        if volume.iloc[-1] < volume_ma.iloc[-1] * 0.5:
            patterns['VOLUME_DRYING_UP'] = {
                'confidence': 0.7,
                'signal': 'HOLD',
                'description': 'Volume drying up - reduced liquidity'
            }
        
        return patterns
    
    def _detect_cross_sectional_patterns(self, symbol: str) -> Dict:
        """Detect cross-sectional patterns (Sector rotation opportunities)."""
        patterns = {}
        
        # Get sector data (simplified - in practice would need sector mapping)
        try:
            # This would require sector classification data
            # For now, we'll use a simplified approach
            patterns['SECTOR_ROTATION_READY'] = {
                'confidence': 0.6,
                'signal': 'ANALYZE',
                'description': 'Cross-sectional analysis available for sector rotation'
            }
        except Exception as e:
            logger.warning(f"Cross-sectional analysis not available: {e}")
        
        return patterns
    
    def _calculate_volatility_clustering(self, returns: pd.Series) -> float:
        """Calculate volatility clustering coefficient."""
        if len(returns) < 50:
            return 0.0
        
        # Calculate squared returns (volatility proxy)
        squared_returns = returns ** 2
        
        # Calculate autocorrelation of squared returns
        autocorr = squared_returns.autocorr(lag=1)
        
        return abs(autocorr) if not pd.isna(autocorr) else 0.0
    
    def generate_enhanced_signals(self, symbol: str) -> Dict:
        """
        Generate enhanced trading signals for IDX market.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with enhanced signals and confidence scores
        """
        # Get data
        df = self._get_symbol_data(symbol)
        if df.empty:
            return {'error': f'No data available for {symbol}'}
        
        # Detect patterns
        patterns = self.detect_fundamental_patterns(df, symbol)
        
        # Generate signals
        signals = self._generate_signals_from_patterns(patterns)
        
        # Add market context
        market_context = self._get_market_context()
        signals['market_context'] = market_context
        
        return signals
    
    def _get_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Get symbol data from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = f"""
            SELECT * FROM historical_data_daily 
            WHERE symbol = '{symbol}' 
            ORDER BY timestamp
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()
    
    def _generate_signals_from_patterns(self, patterns: Dict) -> Dict:
        """Generate trading signals from detected patterns."""
        signals = {
            'patterns': patterns,
            'overall_signal': 'HOLD',
            'confidence': 0.0,
            'signal_strength': 0.0
        }
        
        if not patterns or 'error' in patterns:
            return signals
        
        # Calculate signal strength
        buy_signals = []
        sell_signals = []
        hold_signals = []
        
        for pattern_name, pattern_data in patterns.items():
            if 'signal' in pattern_data:
                signal = pattern_data['signal']
                confidence = pattern_data.get('confidence', 0.5)
                
                if signal == 'BUY':
                    buy_signals.append(confidence)
                elif signal == 'SELL':
                    sell_signals.append(confidence)
                else:
                    hold_signals.append(confidence)
        
        # Determine overall signal
        if buy_signals and not sell_signals:
            signals['overall_signal'] = 'BUY'
            signals['confidence'] = np.mean(buy_signals)
            signals['signal_strength'] = len(buy_signals)
        elif sell_signals and not buy_signals:
            signals['overall_signal'] = 'SELL'
            signals['confidence'] = np.mean(sell_signals)
            signals['signal_strength'] = len(sell_signals)
        elif buy_signals and sell_signals:
            # Mixed signals - use weighted approach
            buy_strength = np.mean(buy_signals) * len(buy_signals)
            sell_strength = np.mean(sell_signals) * len(sell_signals)
            
            if buy_strength > sell_strength:
                signals['overall_signal'] = 'BUY'
                signals['confidence'] = buy_strength / (buy_strength + sell_strength)
            else:
                signals['overall_signal'] = 'SELL'
                signals['confidence'] = sell_strength / (buy_strength + sell_strength)
            signals['signal_strength'] = abs(buy_strength - sell_strength)
        else:
            signals['overall_signal'] = 'HOLD'
            signals['confidence'] = np.mean(hold_signals) if hold_signals else 0.5
        
        return signals
    
    def _get_market_context(self) -> Dict:
        """Get current market context for IDX."""
        # This would integrate with broader market data
        # For now, return basic context
        return {
            'market_regime': 'UNKNOWN',
            'volatility_regime': 'NORMAL',
            'liquidity_conditions': 'NORMAL',
            'sector_rotation': 'NEUTRAL'
        }

if __name__ == "__main__":
    # Test the enhanced pattern detector
    detector = IDXEnhancedPatternDetector()
    signals = detector.generate_enhanced_signals('BBCA.JK')
    print("Enhanced IDX Pattern Detection Results:")
    print(signals)
