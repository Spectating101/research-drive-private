#!/usr/bin/env python3
"""
Enhanced Execution Module

This module implements sophisticated execution capabilities for the IDX pattern detection system.
It enhances the core pattern detection with advanced position sizing, risk management,
and timing optimization while maintaining the proven pattern detection logic.

Features:
- Kelly Criterion position sizing
- Dynamic stop losses based on volatility
- Multi-timeframe confirmation
- Correlation-based position limits
- Real-time performance monitoring
- Adaptive risk management
"""

import numpy as np
import pandas as pd
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass
import warnings
warnings.filterwarnings('ignore')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class ExecutionSignal:
    """Enhanced execution signal with position sizing and risk management."""
    symbol: str
    signal: str  # 'BUY', 'SELL', 'HOLD'
    confidence: float
    position_size: float
    stop_loss: float
    take_profit: float
    entry_price: float
    pattern_type: str
    market_regime: str
    volume_confirmation: bool
    multi_timeframe_confirmation: bool
    correlation_risk: float
    volatility_exposure: float
    timestamp: datetime

class EnhancedExecutor:
    """
    Enhanced execution system for IDX pattern detection.
    
    Integrates advanced position sizing, risk management, and timing optimization
    with the proven pattern detection system.
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db'):
        """
        Initialize the enhanced executor.
        
        Args:
            db_path: Path to historical data database
        """
        self.db_path = db_path
        
        # IDX-specific execution parameters
        self.execution_params = {
            'max_position_size': 0.25,        # Maximum 25% in single position
            'min_position_size': 0.01,        # Minimum 1% position
            'max_portfolio_allocation': 0.8,  # Maximum 80% portfolio allocation
            'target_volatility': 0.15,        # Target portfolio volatility
            'max_correlation': 0.75,          # Maximum correlation between positions
            'transaction_cost': 0.0025,       # 0.25% transaction cost
            'slippage': 0.001,               # 0.1% slippage
        }
        
        # Kelly Criterion parameters
        self.kelly_params = {
            'conservative_factor': 0.5,       # Use half Kelly for safety
            'max_kelly_fraction': 0.25,       # Maximum Kelly fraction
            'min_kelly_fraction': 0.01,       # Minimum Kelly fraction
        }
        
        # Risk management parameters
        self.risk_params = {
            'max_drawdown': 0.12,             # Maximum 12% drawdown
            'volatility_multiplier': 1.5,     # IDX volatility adjustment
            'correlation_decay': 0.95,        # Correlation decay factor
            'stop_loss_multiplier': 1.2,      # Stop loss adjustment
        }
        
        # Performance tracking
        self.performance_metrics = {
            'current_drawdown': 0.0,
            'daily_pnl': 0.0,
            'position_concentration': 0.0,
            'correlation_risk': 0.0,
            'volatility_exposure': 0.0,
        }
        
        logger.info("Enhanced Executor initialized for IDX trading")
    
    def get_historical_data(self, symbol: str, lookback_days: int = 252) -> pd.DataFrame:
        """Get historical data for analysis."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT * FROM historical_data_daily 
            WHERE symbol = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
            """
            df = pd.read_sql_query(query, conn, params=(symbol, lookback_days))
            conn.close()
            
            if df.empty:
                return pd.DataFrame()
            
            # Convert timestamp to datetime
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            
            return df
        except Exception as e:
            logger.error(f"Error getting historical data for {symbol}: {e}")
            return pd.DataFrame()
    
    def calculate_kelly_position_size(self, win_rate: float, avg_gain: float, 
                                    avg_loss: float) -> float:
        """
        Calculate optimal position size using Kelly Criterion.
        
        Args:
            win_rate: Win rate percentage (0-100)
            avg_gain: Average gain percentage
            avg_loss: Average loss percentage
            
        Returns:
            Optimal position size as fraction of capital
        """
        if avg_loss == 0 or win_rate <= 0:
            return self.kelly_params['min_kelly_fraction']
        
        # Kelly formula: f = (bp - q) / b
        # where: b = odds received, p = win probability, q = loss probability
        
        b = avg_gain / avg_loss  # Odds received
        p = win_rate / 100      # Win probability
        q = 1 - p              # Loss probability
        
        kelly_fraction = (b * p - q) / b
        
        # Apply conservative factor (half Kelly)
        conservative_kelly = kelly_fraction * self.kelly_params['conservative_factor']
        
        # Constrain to limits
        constrained_kelly = max(
            self.kelly_params['min_kelly_fraction'],
            min(conservative_kelly, self.kelly_params['max_kelly_fraction'])
        )
        
        return constrained_kelly
    
    def calculate_dynamic_stop_loss(self, symbol: str, pattern_type: str, 
                                  market_regime: str, entry_price: float) -> float:
        """
        Calculate dynamic stop loss based on volatility and market conditions.
        
        Args:
            symbol: Stock symbol
            pattern_type: Type of pattern detected
            market_regime: Current market regime
            entry_price: Entry price
            
        Returns:
            Stop loss price
        """
        # Get volatility data
        df = self.get_historical_data(symbol, 60)
        if df.empty:
            return entry_price * 0.95  # Default 5% stop loss
        
        # Calculate volatility
        returns = df['close'].pct_change().dropna()
        volatility = returns.std() * np.sqrt(252)  # Annualized volatility
        
        # Base stop loss percentages by pattern type
        base_stops = {
            'momentum_patterns': 0.05,    # 5% for momentum
            'reversal_patterns': 0.03,    # 3% for reversals
            'breakout_patterns': 0.07,    # 7% for breakouts
            'sentiment_patterns': 0.04,   # 4% for sentiment
            'volatility_patterns': 0.06,  # 6% for volatility
            'volume_patterns': 0.05,      # 5% for volume
        }
        
        # Adjust for volatility
        volatility_multiplier = volatility / 0.02  # Normalize to 2% volatility
        
        # Adjust for market regime
        regime_multipliers = {
            'BULL_TREND': 1.0,
            'RANGE_BOUND': 0.9,
            'BEAR_TREND': 0.8,
            'HIGH_VOLATILITY': 1.2
        }
        
        base_stop = base_stops.get(pattern_type, 0.05)
        adjusted_stop = (base_stop * volatility_multiplier * 
                        regime_multipliers.get(market_regime, 1.0) * 
                        self.risk_params['stop_loss_multiplier'])
        
        # Constrain stop loss
        constrained_stop = max(0.02, min(adjusted_stop, 0.10))  # Between 2% and 10%
        
        return entry_price * (1 - constrained_stop)
    
    def calculate_take_profit(self, entry_price: float, stop_loss: float, 
                            pattern_type: str) -> float:
        """
        Calculate take profit based on risk-reward ratio.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            pattern_type: Type of pattern detected
            
        Returns:
            Take profit price
        """
        # Risk-reward ratios by pattern type
        risk_reward_ratios = {
            'momentum_patterns': 2.0,     # 2:1 risk-reward
            'reversal_patterns': 1.5,     # 1.5:1 risk-reward
            'breakout_patterns': 2.5,     # 2.5:1 risk-reward
            'sentiment_patterns': 1.8,    # 1.8:1 risk-reward
            'volatility_patterns': 2.2,   # 2.2:1 risk-reward
            'volume_patterns': 2.0,       # 2:1 risk-reward
        }
        
        risk = entry_price - stop_loss
        reward = risk * risk_reward_ratios.get(pattern_type, 2.0)
        
        return entry_price + reward
    
    def check_volume_confirmation(self, symbol: str, pattern_type: str) -> bool:
        """
        Check if volume confirms the pattern.
        
        Args:
            symbol: Stock symbol
            pattern_type: Type of pattern detected
            
        Returns:
            True if volume confirms pattern
        """
        df = self.get_historical_data(symbol, 30)
        if df.empty or len(df) < 20:
            return True  # Default to True if insufficient data
        
        current_volume = df['volume'].iloc[-1]
        avg_volume = df['volume'].rolling(20).mean().iloc[-1]
        
        # Volume confirmation thresholds by pattern type
        volume_thresholds = {
            'breakout': 1.5,      # 150% of average volume
            'reversal': 2.0,      # 200% of average volume
            'momentum': 1.2,      # 120% of average volume
            'sentiment': 1.8,     # 180% of average volume
            'volatility': 1.3,    # 130% of average volume
            'volume': 1.5,        # 150% of average volume
        }
        
        threshold = volume_thresholds.get(pattern_type, 1.5)
        return current_volume > avg_volume * threshold
    
    def check_multi_timeframe_confirmation(self, symbol: str, pattern: Dict) -> bool:
        """
        Check pattern confirmation across multiple timeframes.
        
        Args:
            symbol: Stock symbol
            pattern: Pattern data
            
        Returns:
            True if pattern confirmed across timeframes
        """
        # For now, use daily data with different lookback periods
        # In production, this would use actual multi-timeframe data
        
        lookback_periods = [20, 60, 120]  # Short, medium, long term
        confirmations = []
        
        for period in lookback_periods:
            df = self.get_historical_data(symbol, period)
            if not df.empty and len(df) >= period * 0.8:
                # Simple confirmation check (can be enhanced)
                recent_trend = df['close'].iloc[-10:].pct_change().mean()
                confirmations.append(recent_trend > 0 if pattern.get('signal') == 'BUY' else recent_trend < 0)
        
        if not confirmations:
            return True  # Default to True if insufficient data
        
        # Weight confirmations (short = 50%, medium = 30%, long = 20%)
        weights = [0.5, 0.3, 0.2][:len(confirmations)]
        weighted_confirmation = sum(c * w for c, w in zip(confirmations, weights))
        
        return weighted_confirmation > 0.6  # 60% threshold
    
    def calculate_correlation_risk(self, portfolio: Dict, new_symbol: str) -> float:
        """
        Calculate correlation risk for new position.
        
        Args:
            portfolio: Current portfolio positions
            new_symbol: New symbol to add
            
        Returns:
            Correlation risk score (0-1)
        """
        if not portfolio:
            return 0.0
        
        # Get returns for portfolio symbols and new symbol
        symbols = list(portfolio.keys()) + [new_symbol]
        returns_data = {}
        
        for symbol in symbols:
            df = self.get_historical_data(symbol, 60)
            if not df.empty:
                returns_data[symbol] = df['close'].pct_change().dropna()
        
        if len(returns_data) < 2:
            return 0.0
        
        # Calculate correlation matrix
        returns_df = pd.DataFrame(returns_data)
        correlation_matrix = returns_df.corr()
        
        # Calculate average correlation with new symbol
        if new_symbol in correlation_matrix.index:
            correlations = correlation_matrix[new_symbol].drop(new_symbol)
            avg_correlation = correlations.abs().mean()
            return avg_correlation
        
        return 0.0
    
    def calculate_volatility_exposure(self, portfolio: Dict) -> float:
        """
        Calculate current portfolio volatility exposure.
        
        Args:
            portfolio: Current portfolio positions
            
        Returns:
            Portfolio volatility exposure
        """
        if not portfolio:
            return 0.0
        
        # Get returns for all portfolio symbols
        returns_data = {}
        for symbol in portfolio.keys():
            df = self.get_historical_data(symbol, 60)
            if not df.empty:
                returns_data[symbol] = df['close'].pct_change().dropna()
        
        if not returns_data:
            return 0.0
        
        # Calculate portfolio volatility
        returns_df = pd.DataFrame(returns_data)
        portfolio_vol = returns_df.std().mean() * np.sqrt(252)
        
        return portfolio_vol
    
    def generate_enhanced_signal(self, symbol: str, patterns: Dict, 
                               market_regime: str, portfolio: Dict = None) -> Optional[ExecutionSignal]:
        """
        Generate enhanced execution signal with position sizing and risk management.
        
        Args:
            symbol: Stock symbol
            patterns: Detected patterns
            market_regime: Current market regime
            portfolio: Current portfolio positions
            
        Returns:
            Enhanced execution signal
        """
        if not patterns or portfolio is None:
            portfolio = {}
        
        # Get current price
        df = self.get_historical_data(symbol, 5)
        if df.empty:
            return None
        
        current_price = df['close'].iloc[-1]
        
        # Determine signal and confidence
        signal = self._aggregate_patterns(patterns)
        if signal['signal'] == 'HOLD':
            return None
        
        confidence = signal['confidence']
        pattern_type = signal.get('pattern_type', 'general')
        
        # Check confirmations
        volume_confirmation = self.check_volume_confirmation(symbol, pattern_type)
        multi_timeframe_confirmation = self.check_multi_timeframe_confirmation(symbol, patterns)
        
        # Calculate position size using Kelly Criterion
        # Use historical performance data for Kelly calculation
        win_rate, avg_gain, avg_loss = self._get_historical_performance(symbol, pattern_type)
        position_size = self.calculate_kelly_position_size(win_rate, avg_gain, avg_loss)
        
        # Adjust position size based on confidence and confirmations
        position_size *= confidence
        if not volume_confirmation:
            position_size *= 0.8
        if not multi_timeframe_confirmation:
            position_size *= 0.7
        
        # Constrain position size
        position_size = max(
            self.execution_params['min_position_size'],
            min(position_size, self.execution_params['max_position_size'])
        )
        
        # Calculate stop loss and take profit
        stop_loss = self.calculate_dynamic_stop_loss(symbol, pattern_type, market_regime, current_price)
        take_profit = self.calculate_take_profit(current_price, stop_loss, pattern_type)
        
        # Calculate risk metrics
        correlation_risk = self.calculate_correlation_risk(portfolio, symbol)
        volatility_exposure = self.calculate_volatility_exposure(portfolio)
        
        # Apply correlation limits
        if correlation_risk > self.execution_params['max_correlation']:
            position_size *= 0.5  # Reduce position size
        
        # Apply volatility limits
        if volatility_exposure > self.execution_params['target_volatility']:
            position_size *= 0.8  # Reduce position size
        
        return ExecutionSignal(
            symbol=symbol,
            signal=signal['signal'],
            confidence=confidence,
            position_size=position_size,
            stop_loss=stop_loss,
            take_profit=take_profit,
            entry_price=current_price,
            pattern_type=pattern_type,
            market_regime=market_regime,
            volume_confirmation=volume_confirmation,
            multi_timeframe_confirmation=multi_timeframe_confirmation,
            correlation_risk=correlation_risk,
            volatility_exposure=volatility_exposure,
            timestamp=datetime.now()
        )
    
    def _aggregate_patterns(self, patterns: Dict) -> Dict:
        """Aggregate patterns into overall signal."""
        if not patterns:
            return {'signal': 'HOLD', 'confidence': 0.0}
        
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
        
        # Determine overall signal
        if buy_signals and not sell_signals:
            return {
                'signal': 'BUY',
                'confidence': np.mean(buy_signals),
                'pattern_type': 'momentum_patterns'
            }
        elif sell_signals and not buy_signals:
            return {
                'signal': 'SELL',
                'confidence': np.mean(sell_signals),
                'pattern_type': 'reversal_patterns'
            }
        elif buy_signals and sell_signals:
            # Mixed signals - use weighted approach
            buy_strength = np.mean(buy_signals) * len(buy_signals)
            sell_strength = np.mean(sell_signals) * len(sell_signals)
            
            if buy_strength > sell_strength:
                return {
                    'signal': 'BUY',
                    'confidence': buy_strength / (buy_strength + sell_strength),
                    'pattern_type': 'mixed_patterns'
                }
            else:
                return {
                    'signal': 'SELL',
                    'confidence': sell_strength / (buy_strength + sell_strength),
                    'pattern_type': 'mixed_patterns'
                }
        else:
            return {'signal': 'HOLD', 'confidence': 0.0}
    
    def _get_historical_performance(self, symbol: str, pattern_type: str) -> Tuple[float, float, float]:
        """
        Get historical performance for Kelly Criterion calculation.
        
        Args:
            symbol: Stock symbol
            pattern_type: Pattern type
            
        Returns:
            Tuple of (win_rate, avg_gain, avg_loss)
        """
        # For now, use default values based on pattern type
        # In production, this would use actual historical performance data
        
        default_performance = {
            'momentum_patterns': (65.0, 3.2, 2.1),
            'reversal_patterns': (58.0, 2.8, 2.3),
            'breakout_patterns': (62.0, 4.1, 2.5),
            'sentiment_patterns': (60.0, 2.9, 2.2),
            'volatility_patterns': (55.0, 3.5, 2.8),
            'volume_patterns': (63.0, 3.0, 2.0),
            'mixed_patterns': (61.0, 3.1, 2.2),
            'general': (60.0, 3.0, 2.2),
        }
        
        return default_performance.get(pattern_type, (60.0, 3.0, 2.2))
    
    def update_performance_metrics(self, portfolio: Dict) -> Dict:
        """
        Update real-time performance metrics.
        
        Args:
            portfolio: Current portfolio positions
            
        Returns:
            Updated performance metrics
        """
        if not portfolio:
            self.performance_metrics = {
                'current_drawdown': 0.0,
                'daily_pnl': 0.0,
                'position_concentration': 0.0,
                'correlation_risk': 0.0,
                'volatility_exposure': 0.0,
            }
            return self.performance_metrics
        
        # Calculate position concentration
        total_value = sum(portfolio.values())
        if total_value > 0:
            max_position = max(portfolio.values())
            self.performance_metrics['position_concentration'] = max_position / total_value
        
        # Calculate correlation risk
        if len(portfolio) > 1:
            symbols = list(portfolio.keys())
            correlations = []
            for i in range(len(symbols)):
                for j in range(i+1, len(symbols)):
                    corr = self.calculate_correlation_risk({symbols[i]: 1}, symbols[j])
                    correlations.append(corr)
            if correlations:
                self.performance_metrics['correlation_risk'] = np.mean(correlations)
        
        # Calculate volatility exposure
        self.performance_metrics['volatility_exposure'] = self.calculate_volatility_exposure(portfolio)
        
        return self.performance_metrics
    
    def check_risk_limits(self, portfolio: Dict, new_signal: ExecutionSignal) -> bool:
        """
        Check if new signal violates risk limits.
        
        Args:
            portfolio: Current portfolio
            new_signal: New execution signal
            
        Returns:
            True if signal is within risk limits
        """
        # Check drawdown limit
        if self.performance_metrics['current_drawdown'] > self.risk_params['max_drawdown']:
            logger.warning(f"Drawdown limit exceeded: {self.performance_metrics['current_drawdown']:.2%}")
            return False
        
        # Check position concentration
        if new_signal.position_size > self.execution_params['max_position_size']:
            logger.warning(f"Position size limit exceeded: {new_signal.position_size:.2%}")
            return False
        
        # Check correlation risk
        if new_signal.correlation_risk > self.execution_params['max_correlation']:
            logger.warning(f"Correlation risk too high: {new_signal.correlation_risk:.2%}")
            return False
        
        # Check volatility exposure
        if new_signal.volatility_exposure > self.execution_params['target_volatility'] * 1.5:
            logger.warning(f"Volatility exposure too high: {new_signal.volatility_exposure:.2%}")
            return False
        
        return True
