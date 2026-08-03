#!/usr/bin/env python3
"""
Aggressive IDX Pattern Detection System

This module implements aggressive pattern detection specifically designed for 
Indonesian market high volatility and the patterns we observed in the data.
"""

import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class IDXAggressivePatternDetector:
    """
    Aggressive pattern detector for IDX market high volatility opportunities.
    
    Based on data analysis showing:
    - Stocks with 100%+ daily gains
    - High volatility patterns
    - Momentum persistence
    - Volume breakouts
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db'):
        self.db_path = db_path
        
        # Aggressive parameters for IDX high volatility
        self.aggressive_params = {
            'volatility_threshold': 0.05,  # 5% daily volatility (lower threshold)
            'momentum_threshold': 0.03,    # 3% momentum threshold
            'volume_threshold': 0.5,       # 50% volume increase
            'price_threshold': 0.05,       # 5% price movement
            'confidence_threshold': 0.4,   # Lower confidence threshold (40%)
            'max_hold_days': 5,           # Short holding period
            'stop_loss': 0.10,            # 10% stop loss
            'take_profit': 0.20           # 20% take profit
        }
        
        logger.info("IDX Aggressive Pattern Detector initialized")
    
    def detect_aggressive_patterns(self, df: pd.DataFrame, symbol: str) -> Dict:
        """
        Detect aggressive patterns for high volatility IDX opportunities.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            
        Returns:
            Dictionary of detected patterns with confidence scores
        """
        if df.empty or len(df) < 20:
            return {'error': 'Insufficient data'}
        
        patterns = {}
        
        # 1. High Volatility Breakout Pattern
        volatility_patterns = self._detect_volatility_breakouts(df)
        patterns.update(volatility_patterns)
        
        # 2. Volume Explosion Pattern
        volume_patterns = self._detect_volume_explosions(df)
        patterns.update(volume_patterns)
        
        # 3. Momentum Acceleration Pattern
        momentum_patterns = self._detect_momentum_acceleration(df)
        patterns.update(momentum_patterns)
        
        # 4. Gap and Go Pattern
        gap_patterns = self._detect_gap_patterns(df)
        patterns.update(gap_patterns)
        
        # 5. Price Breakout Pattern
        breakout_patterns = self._detect_price_breakouts(df)
        patterns.update(breakout_patterns)
        
        # 6. Multi-timeframe Confirmation
        mtf_patterns = self._detect_mtf_confirmation(df)
        patterns.update(mtf_patterns)
        
        # Generate final signals from patterns
        signals = self._generate_signals_from_patterns(patterns)
        return signals
    
    def _detect_volatility_breakouts(self, df: pd.DataFrame) -> Dict:
        """Detect high volatility breakout patterns."""
        patterns = {}
        
        # Calculate volatility
        returns = df['close'].pct_change().dropna()
        current_vol = returns.rolling(5).std().iloc[-1]
        avg_vol = returns.rolling(20).std().iloc[-1]
        
        # High volatility breakout
        if current_vol > avg_vol * 1.5 and current_vol > self.aggressive_params['volatility_threshold']:
            if returns.iloc[-1] > 0:
                patterns['HIGH_VOL_BULLISH_BREAKOUT'] = {
                    'confidence': 0.6,
                    'signal': 'BUY',
                    'description': f'High volatility bullish breakout - Vol: {current_vol:.3f}'
                }
            else:
                patterns['HIGH_VOL_BEARISH_BREAKOUT'] = {
                    'confidence': 0.6,
                    'signal': 'SELL',
                    'description': f'High volatility bearish breakout - Vol: {current_vol:.3f}'
                }
        
        return patterns
    
    def _detect_volume_explosions(self, df: pd.DataFrame) -> Dict:
        """Detect volume explosion patterns."""
        patterns = {}
        
        volume = df['volume']
        current_volume = volume.iloc[-1]
        avg_volume = volume.rolling(20).mean().iloc[-1]
        
        # Volume explosion
        if current_volume > avg_volume * 2:  # 200% volume increase
            price_change = (df['close'].iloc[-1] - df['open'].iloc[-1]) / df['open'].iloc[-1]
            
            if price_change > self.aggressive_params['price_threshold']:
                patterns['VOLUME_EXPLOSION_BULLISH'] = {
                    'confidence': 0.7,
                    'signal': 'BUY',
                    'description': f'Volume explosion with price gain - Vol: {current_volume/avg_volume:.1f}x'
                }
            elif price_change < -self.aggressive_params['price_threshold']:
                patterns['VOLUME_EXPLOSION_BEARISH'] = {
                    'confidence': 0.7,
                    'signal': 'SELL',
                    'description': f'Volume explosion with price drop - Vol: {current_volume/avg_volume:.1f}x'
                }
        
        return patterns
    
    def _detect_momentum_acceleration(self, df: pd.DataFrame) -> Dict:
        """Detect momentum acceleration patterns."""
        patterns = {}
        
        returns = df['close'].pct_change().dropna()
        
        # Short-term momentum
        short_momentum = returns.rolling(3).mean().iloc[-1]
        medium_momentum = returns.rolling(10).mean().iloc[-1]
        
        # Momentum acceleration
        if short_momentum > medium_momentum and short_momentum > self.aggressive_params['momentum_threshold']:
            patterns['MOMENTUM_ACCELERATION_BULLISH'] = {
                'confidence': 0.65,
                'signal': 'BUY',
                'description': f'Momentum acceleration - Short: {short_momentum:.3f}, Medium: {medium_momentum:.3f}'
            }
        elif short_momentum < medium_momentum and short_momentum < -self.aggressive_params['momentum_threshold']:
            patterns['MOMENTUM_ACCELERATION_BEARISH'] = {
                'confidence': 0.65,
                'signal': 'SELL',
                'description': f'Momentum deceleration - Short: {short_momentum:.3f}, Medium: {medium_momentum:.3f}'
            }
        
        return patterns
    
    def _detect_gap_patterns(self, df: pd.DataFrame) -> Dict:
        """Detect gap patterns."""
        patterns = {}
        
        # Calculate gaps
        gaps = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        current_gap = gaps.iloc[-1]
        gap_volatility = gaps.rolling(20).std().iloc[-1]
        
        # Significant gap
        if abs(current_gap) > gap_volatility * 2:
            if current_gap > 0:
                patterns['BULLISH_GAP'] = {
                    'confidence': 0.6,
                    'signal': 'BUY',
                    'description': f'Bullish gap: {current_gap:.3f}'
                }
            else:
                patterns['BEARISH_GAP'] = {
                    'confidence': 0.6,
                    'signal': 'SELL',
                    'description': f'Bearish gap: {current_gap:.3f}'
                }
        
        return patterns
    
    def _detect_price_breakouts(self, df: pd.DataFrame) -> Dict:
        """Detect price breakout patterns."""
        patterns = {}
        
        # Calculate moving averages
        ma5 = df['close'].rolling(5).mean()
        ma20 = df['close'].rolling(20).mean()
        
        current_price = df['close'].iloc[-1]
        current_ma5 = ma5.iloc[-1]
        current_ma20 = ma20.iloc[-1]
        
        # Breakout above moving averages
        if current_price > current_ma5 > current_ma20:
            price_change = (current_price - current_ma20) / current_ma20
            if price_change > self.aggressive_params['price_threshold']:
                patterns['PRICE_BREAKOUT_BULLISH'] = {
                    'confidence': 0.6,
                    'signal': 'BUY',
                    'description': f'Price breakout above MAs - {price_change:.3f}'
                }
        
        # Breakdown below moving averages
        elif current_price < current_ma5 < current_ma20:
            price_change = (current_ma20 - current_price) / current_ma20
            if price_change > self.aggressive_params['price_threshold']:
                patterns['PRICE_BREAKDOWN_BEARISH'] = {
                    'confidence': 0.6,
                    'signal': 'SELL',
                    'description': f'Price breakdown below MAs - {price_change:.3f}'
                }
        
        return patterns
    
    def _detect_mtf_confirmation(self, df: pd.DataFrame) -> Dict:
        """Detect multi-timeframe confirmation patterns."""
        patterns = {}
        
        # Multiple timeframe analysis
        returns = df['close'].pct_change().dropna()
        
        # 1-day, 3-day, and 5-day momentum
        momentum_1d = returns.iloc[-1]
        momentum_3d = returns.rolling(3).sum().iloc[-1]
        momentum_5d = returns.rolling(5).sum().iloc[-1]
        
        # All timeframes bullish
        if momentum_1d > 0 and momentum_3d > 0 and momentum_5d > 0:
            patterns['MTF_BULLISH_CONFIRMATION'] = {
                'confidence': 0.7,
                'signal': 'BUY',
                'description': f'Multi-timeframe bullish - 1d: {momentum_1d:.3f}, 3d: {momentum_3d:.3f}, 5d: {momentum_5d:.3f}'
            }
        # All timeframes bearish
        elif momentum_1d < 0 and momentum_3d < 0 and momentum_5d < 0:
            patterns['MTF_BEARISH_CONFIRMATION'] = {
                'confidence': 0.7,
                'signal': 'SELL',
                'description': f'Multi-timeframe bearish - 1d: {momentum_1d:.3f}, 3d: {momentum_3d:.3f}, 5d: {momentum_5d:.3f}'
            }
        
        return patterns
    
    def generate_aggressive_signals(self, symbol: str) -> Dict:
        """Generate aggressive trading signals for a symbol."""
        try:
            # Get symbol data
            df = self._get_symbol_data(symbol)
            if df.empty:
                return {'error': 'No data available'}
            
            # Detect patterns
            patterns = self.detect_aggressive_patterns(df, symbol)
            
            # Generate signals
            signals = self._generate_signals_from_patterns(patterns)
            
            return signals
            
        except Exception as e:
            logger.error(f"Error generating signals for {symbol}: {e}")
            return {'error': str(e)}
    
    def _get_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Get symbol data from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = f"""
            SELECT * FROM historical_data_daily 
            WHERE symbol = '{symbol}' 
            ORDER BY timestamp DESC
            LIMIT 100
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df.sort_values('timestamp').reset_index(drop=True)
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
        
        for pattern_name, pattern_data in patterns.items():
            if 'signal' in pattern_data:
                signal = pattern_data['signal']
                confidence = pattern_data.get('confidence', 0.5)
                
                if signal == 'BUY':
                    buy_signals.append(confidence)
                elif signal == 'SELL':
                    sell_signals.append(confidence)
        
        # Determine overall signal with lower threshold
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
        
        return signals

if __name__ == "__main__":
    # Test the aggressive pattern detector
    detector = IDXAggressivePatternDetector()
    signals = detector.generate_aggressive_signals('BBCA.JK')
    print("Aggressive IDX Pattern Detection Results:")
    print(signals)
