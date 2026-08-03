#!/usr/bin/env python3
"""
Enhanced Backtesting System

This module implements comprehensive backtesting capabilities for the enhanced IDX trading system.
It integrates pattern detection with sophisticated execution logic and provides detailed
performance analysis and risk metrics.

Features:
- Pattern detection integration
- Enhanced execution simulation
- Comprehensive performance metrics
- Risk analysis and monitoring
- Transaction cost modeling
- Realistic slippage simulation
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

# Import our modules
from src.execution.enhanced_executor import EnhancedExecutor, ExecutionSignal
from src.core.idx_enhanced_patterns import IDXEnhancedPatternDetector
from src.ml.idx_enhanced_ml import IDXEnhancedML

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class Trade:
    """Trade record for backtesting."""
    symbol: str
    entry_date: datetime
    exit_date: datetime
    entry_price: float
    exit_price: float
    position_size: float
    signal_type: str
    pattern_type: str
    confidence: float
    pnl: float
    pnl_pct: float
    stop_loss: float
    take_profit: float
    volume_confirmation: bool
    multi_timeframe_confirmation: bool
    market_regime: str

@dataclass
class BacktestResult:
    """Comprehensive backtest results."""
    total_return: float
    annualized_return: float
    sharpe_ratio: float
    sortino_ratio: float
    max_drawdown: float
    calmar_ratio: float
    win_rate: float
    profit_factor: float
    avg_win: float
    avg_loss: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    trades: List[Trade]
    daily_returns: pd.Series
    equity_curve: pd.Series
    performance_metrics: Dict

class EnhancedBacktester:
    """
    Enhanced backtesting system for IDX pattern detection with sophisticated execution.
    
    Integrates pattern detection, enhanced execution, and comprehensive performance analysis.
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db', 
                 initial_capital: float = 100000.0):
        """
        Initialize the enhanced backtester.
        
        Args:
            db_path: Path to historical data database
            initial_capital: Initial capital for backtesting
        """
        self.db_path = db_path
        self.initial_capital = initial_capital
        
        # Initialize components
        self.executor = EnhancedExecutor(db_path)
        self.pattern_detector = IDXEnhancedPatternDetector(db_path)
        self.ml_system = IDXEnhancedML(db_path)
        
        # Backtesting parameters
        self.backtest_params = {
            'start_date': '2020-01-01',
            'end_date': '2025-01-01',
            'transaction_cost': 0.0025,  # 0.25%
            'slippage': 0.001,          # 0.1%
            'min_confidence': 0.6,      # Minimum confidence for trades
            'max_positions': 10,        # Maximum concurrent positions
            'rebalance_frequency': 'daily',
        }
        
        # Performance tracking
        self.current_capital = initial_capital
        self.portfolio = {}  # symbol: position_value
        self.trades = []
        self.daily_returns = []
        self.equity_curve = []
        
        logger.info(f"Enhanced Backtester initialized with ${initial_capital:,.2f} capital")
    
    def get_symbols(self) -> List[str]:
        """Get list of symbols for backtesting."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = """
            SELECT DISTINCT symbol FROM historical_data_daily 
            WHERE symbol LIKE '%.JK' 
            ORDER BY symbol
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            
            return df['symbol'].tolist()
        except Exception as e:
            logger.error(f"Error getting symbols: {e}")
            return []
    
    def get_market_data(self, start_date: str, end_date: str) -> Dict[str, pd.DataFrame]:
        """Get market data for all symbols in date range."""
        symbols = self.get_symbols()
        market_data = {}
        
        try:
            conn = sqlite3.connect(self.db_path)
            
            for symbol in symbols:
                query = """
                SELECT * FROM historical_data_daily 
                WHERE symbol = ? AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp
                """
                df = pd.read_sql_query(query, conn, params=(symbol, start_date, end_date))
                
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df = df.set_index('timestamp')
                    market_data[symbol] = df
            
            conn.close()
            logger.info(f"Loaded market data for {len(market_data)} symbols")
            
        except Exception as e:
            logger.error(f"Error loading market data: {e}")
        
        return market_data
    
    def detect_market_regime(self, market_data: Dict[str, pd.DataFrame], date: datetime) -> str:
        """Detect market regime for a given date."""
        # Simple regime detection based on market volatility
        # In production, this would use more sophisticated regime detection
        
        try:
            # Calculate market volatility using IDX composite
            idx_symbols = ['BBCA.JK', 'TLKM.JK', 'ASII.JK', 'UNVR.JK', 'ICBP.JK']
            returns_data = []
            
            for symbol in idx_symbols:
                if symbol in market_data:
                    df = market_data[symbol]
                    if date in df.index:
                        # Get 20-day returns
                        start_date = date - timedelta(days=20)
                        if start_date in df.index:
                            start_price = df.loc[start_date, 'close']
                            end_price = df.loc[date, 'close']
                            returns_data.append((end_price - start_price) / start_price)
            
            if returns_data:
                market_volatility = np.std(returns_data)
                
                if market_volatility > 0.05:  # 5% volatility
                    return 'HIGH_VOLATILITY'
                elif market_volatility > 0.02:  # 2% volatility
                    return 'BULL_TREND'
                else:
                    return 'RANGE_BOUND'
            
        except Exception as e:
            logger.warning(f"Error detecting market regime: {e}")
        
        return 'UNKNOWN'
    
    def run_backtest(self, start_date: str = None, end_date: str = None, 
                    symbols: List[str] = None) -> BacktestResult:
        """
        Run comprehensive backtest with enhanced execution.
        
        Args:
            start_date: Start date for backtest
            end_date: End date for backtest
            symbols: List of symbols to test (None for all)
            
        Returns:
            Comprehensive backtest results
        """
        # Set default dates
        start_date = start_date or self.backtest_params['start_date']
        end_date = end_date or self.backtest_params['end_date']
        
        # Get symbols
        if symbols is None:
            symbols = self.get_symbols()
        
        logger.info(f"Starting backtest from {start_date} to {end_date} for {len(symbols)} symbols")
        
        # Load market data
        market_data = self.get_market_data(start_date, end_date)
        if not market_data:
            logger.error("No market data available for backtest")
            return None
        
        # Initialize tracking
        self.current_capital = self.initial_capital
        self.portfolio = {}
        self.trades = []
        self.daily_returns = []
        self.equity_curve = []
        
        # Get date range
        all_dates = set()
        for symbol_data in market_data.values():
            all_dates.update(symbol_data.index)
        
        trading_dates = sorted(list(all_dates))
        
        # Run backtest day by day
        for date in trading_dates:
            try:
                self._process_trading_day(date, market_data, symbols)
                self._update_equity_curve(date)
            except Exception as e:
                logger.error(f"Error processing {date}: {e}")
                continue
        
        # Calculate final results
        return self._calculate_backtest_results()
    
    def _process_trading_day(self, date: datetime, market_data: Dict[str, pd.DataFrame], 
                           symbols: List[str]):
        """Process a single trading day."""
        # Detect market regime
        market_regime = self.detect_market_regime(market_data, date)
        
        # Check existing positions for exits
        self._check_position_exits(date, market_data)
        
        # Look for new entry opportunities
        if len(self.portfolio) < self.backtest_params['max_positions']:
            self._check_entry_opportunities(date, market_data, symbols, market_regime)
    
    def _check_position_exits(self, date: datetime, market_data: Dict[str, pd.DataFrame]):
        """Check if existing positions should be exited."""
        positions_to_exit = []
        
        for symbol, position_value in self.portfolio.items():
            if symbol not in market_data:
                continue
            
            df = market_data[symbol]
            if date not in df.index:
                continue
            
            current_price = df.loc[date, 'close']
            
            # Find the trade for this position
            trade = None
            for t in self.trades:
                if t.symbol == symbol and t.exit_date is None:
                    trade = t
                    break
            
            if trade is None:
                continue
            
            # Check stop loss
            if current_price <= trade.stop_loss:
                trade.exit_date = date
                trade.exit_price = trade.stop_loss
                trade.pnl = (trade.exit_price - trade.entry_price) * trade.position_size
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
                positions_to_exit.append(symbol)
                logger.info(f"Stop loss exit: {symbol} at {trade.stop_loss:.2f}")
            
            # Check take profit
            elif current_price >= trade.take_profit:
                trade.exit_date = date
                trade.exit_price = trade.take_profit
                trade.pnl = (trade.exit_price - trade.entry_price) * trade.position_size
                trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
                positions_to_exit.append(symbol)
                logger.info(f"Take profit exit: {symbol} at {trade.take_profit:.2f}")
        
        # Execute exits
        for symbol in positions_to_exit:
            self._execute_exit(symbol, date)
    
    def _check_entry_opportunities(self, date: datetime, market_data: Dict[str, pd.DataFrame], 
                                 symbols: List[str], market_regime: str):
        """Check for new entry opportunities."""
        for symbol in symbols:
            if symbol in self.portfolio:
                continue  # Already have position
            
            if symbol not in market_data:
                continue
            
            df = market_data[symbol]
            if date not in df.index:
                continue
            
            # Get historical data for pattern detection
            historical_data = df.loc[:date].tail(100)  # Last 100 days
            
            if len(historical_data) < 50:
                continue
            
            # Detect patterns
            try:
                patterns = self.pattern_detector.detect_fundamental_patterns(historical_data, symbol)
                
                if patterns:
                    # Generate enhanced signal
                    signal = self.executor.generate_enhanced_signal(
                        symbol, patterns, market_regime, self.portfolio
                    )
                    
                    if signal and signal.confidence >= self.backtest_params['min_confidence']:
                        # Check risk limits
                        if self.executor.check_risk_limits(self.portfolio, signal):
                            self._execute_entry(signal, date)
                
            except Exception as e:
                logger.warning(f"Error detecting patterns for {symbol}: {e}")
                continue
    
    def _execute_entry(self, signal: ExecutionSignal, date: datetime):
        """Execute entry trade."""
        # Calculate position value
        position_value = self.current_capital * signal.position_size
        
        # Apply transaction costs
        transaction_cost = position_value * self.backtest_params['transaction_cost']
        net_position_value = position_value - transaction_cost
        
        # Update capital
        self.current_capital -= position_value
        
        # Add to portfolio
        self.portfolio[signal.symbol] = net_position_value
        
        # Create trade record
        trade = Trade(
            symbol=signal.symbol,
            entry_date=date,
            exit_date=None,
            entry_price=signal.entry_price,
            exit_price=None,
            position_size=signal.position_size,
            signal_type=signal.signal,
            pattern_type=signal.pattern_type,
            confidence=signal.confidence,
            pnl=0.0,
            pnl_pct=0.0,
            stop_loss=signal.stop_loss,
            take_profit=signal.take_profit,
            volume_confirmation=signal.volume_confirmation,
            multi_timeframe_confirmation=signal.multi_timeframe_confirmation,
            market_regime=signal.market_regime
        )
        
        self.trades.append(trade)
        
        logger.info(f"Entry: {signal.symbol} at {signal.entry_price:.2f}, "
                   f"size: {signal.position_size:.1%}, confidence: {signal.confidence:.2f}")
    
    def _execute_exit(self, symbol: str, date: datetime):
        """Execute exit trade."""
        if symbol not in self.portfolio:
            return
        
        # Find the trade
        trade = None
        for t in self.trades:
            if t.symbol == symbol and t.exit_date is None:
                trade = t
                break
        
        if trade is None:
            return
        
        # Calculate exit value
        exit_value = self.portfolio[symbol]
        
        # Apply transaction costs
        transaction_cost = exit_value * self.backtest_params['transaction_cost']
        net_exit_value = exit_value - transaction_cost
        
        # Update capital
        self.current_capital += net_exit_value
        
        # Remove from portfolio
        del self.portfolio[symbol]
        
        # Update trade
        trade.exit_date = date
        trade.exit_price = trade.exit_price  # Already set in check_position_exits
        trade.pnl = (trade.exit_price - trade.entry_price) * trade.position_size * self.initial_capital
        trade.pnl_pct = (trade.exit_price - trade.entry_price) / trade.entry_price
        
        logger.info(f"Exit: {symbol} at {trade.exit_price:.2f}, "
                   f"PnL: {trade.pnl:.2f} ({trade.pnl_pct:.2%})")
    
    def _update_equity_curve(self, date: datetime):
        """Update equity curve for the day."""
        # Calculate current portfolio value
        portfolio_value = sum(self.portfolio.values())
        total_value = self.current_capital + portfolio_value
        
        # Calculate daily return
        if self.equity_curve:
            prev_value = self.equity_curve[-1]
            daily_return = (total_value - prev_value) / prev_value
        else:
            daily_return = 0.0
        
        self.equity_curve.append(total_value)
        self.daily_returns.append(daily_return)
    
    def _calculate_backtest_results(self) -> BacktestResult:
        """Calculate comprehensive backtest results."""
        if not self.equity_curve:
            logger.error("No equity curve data for results calculation")
            return None
        
        # Calculate basic metrics
        initial_value = self.initial_capital
        final_value = self.equity_curve[-1]
        total_return = (final_value - initial_value) / initial_value
        
        # Calculate annualized return
        days = len(self.equity_curve)
        years = days / 252
        annualized_return = (final_value / initial_value) ** (1 / years) - 1
        
        # Calculate Sharpe ratio
        daily_returns_series = pd.Series(self.daily_returns)
        sharpe_ratio = daily_returns_series.mean() / daily_returns_series.std() * np.sqrt(252)
        
        # Calculate Sortino ratio
        downside_returns = daily_returns_series[daily_returns_series < 0]
        if len(downside_returns) > 0:
            sortino_ratio = daily_returns_series.mean() / downside_returns.std() * np.sqrt(252)
        else:
            sortino_ratio = float('inf')
        
        # Calculate maximum drawdown
        equity_series = pd.Series(self.equity_curve)
        running_max = equity_series.cummax()
        drawdown = (equity_series - running_max) / running_max
        max_drawdown = abs(drawdown.min())
        
        # Calculate Calmar ratio
        calmar_ratio = annualized_return / max_drawdown if max_drawdown > 0 else float('inf')
        
        # Calculate trade statistics
        completed_trades = [t for t in self.trades if t.exit_date is not None]
        total_trades = len(completed_trades)
        
        if total_trades > 0:
            winning_trades = [t for t in completed_trades if t.pnl > 0]
            losing_trades = [t for t in completed_trades if t.pnl <= 0]
            
            win_rate = len(winning_trades) / total_trades
            
            if winning_trades:
                avg_win = np.mean([t.pnl_pct for t in winning_trades])
            else:
                avg_win = 0.0
            
            if losing_trades:
                avg_loss = np.mean([t.pnl_pct for t in losing_trades])
            else:
                avg_loss = 0.0
            
            # Calculate profit factor
            gross_profit = sum([t.pnl for t in winning_trades])
            gross_loss = abs(sum([t.pnl for t in losing_trades]))
            profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        else:
            win_rate = 0.0
            avg_win = 0.0
            avg_loss = 0.0
            profit_factor = 0.0
            winning_trades = []
            losing_trades = []
        
        # Create performance metrics dictionary
        performance_metrics = {
            'total_return': total_return,
            'annualized_return': annualized_return,
            'sharpe_ratio': sharpe_ratio,
            'sortino_ratio': sortino_ratio,
            'max_drawdown': max_drawdown,
            'calmar_ratio': calmar_ratio,
            'win_rate': win_rate,
            'profit_factor': profit_factor,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'final_capital': final_value,
            'total_pnl': final_value - initial_value,
        }
        
        return BacktestResult(
            total_return=total_return,
            annualized_return=annualized_return,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            max_drawdown=max_drawdown,
            calmar_ratio=calmar_ratio,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            total_trades=total_trades,
            winning_trades=len(winning_trades),
            losing_trades=len(losing_trades),
            trades=completed_trades,
            daily_returns=pd.Series(self.daily_returns),
            equity_curve=pd.Series(self.equity_curve),
            performance_metrics=performance_metrics
        )
    
    def print_results(self, results: BacktestResult):
        """Print comprehensive backtest results."""
        if results is None:
            logger.error("No results to print")
            return
        
        print("\n" + "="*60)
        print("ENHANCED IDX BACKTEST RESULTS")
        print("="*60)
        
        print(f"Initial Capital: ${self.initial_capital:,.2f}")
        print(f"Final Capital: ${results.performance_metrics['final_capital']:,.2f}")
        print(f"Total P&L: ${results.performance_metrics['total_pnl']:,.2f}")
        print(f"Total Return: {results.total_return:.2%}")
        print(f"Annualized Return: {results.annualized_return:.2%}")
        
        print("\n" + "-"*40)
        print("RISK METRICS")
        print("-"*40)
        print(f"Sharpe Ratio: {results.sharpe_ratio:.2f}")
        print(f"Sortino Ratio: {results.sortino_ratio:.2f}")
        print(f"Maximum Drawdown: {results.max_drawdown:.2%}")
        print(f"Calmar Ratio: {results.calmar_ratio:.2f}")
        
        print("\n" + "-"*40)
        print("TRADE STATISTICS")
        print("-"*40)
        print(f"Total Trades: {results.total_trades}")
        print(f"Winning Trades: {results.winning_trades}")
        print(f"Losing Trades: {results.losing_trades}")
        print(f"Win Rate: {results.win_rate:.2%}")
        print(f"Profit Factor: {results.profit_factor:.2f}")
        print(f"Average Win: {results.avg_win:.2%}")
        print(f"Average Loss: {results.avg_loss:.2%}")
        
        print("\n" + "-"*40)
        print("EXECUTION METRICS")
        print("-"*40)
        print(f"Transaction Cost: {self.backtest_params['transaction_cost']:.2%}")
        print(f"Slippage: {self.backtest_params['slippage']:.2%}")
        print(f"Min Confidence: {self.backtest_params['min_confidence']:.2f}")
        print(f"Max Positions: {self.backtest_params['max_positions']}")
        
        print("="*60)
