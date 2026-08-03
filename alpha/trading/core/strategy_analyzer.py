#!/usr/bin/env python3
"""
Strategy Analyzer Module

This module provides functionality to analyze trading strategies through:
1. Backtesting on historical data
2. Performance visualization and metrics calculation
3. Strategy validation and comparison

Classes:
    StrategyAnalyzer: Main class for strategy analysis

Usage:
    analyzer = StrategyAnalyzer()
    performance = analyzer.analyze_strategy(strategy_name, indicator_combo, date_range)
    analyzer.generate_performance_chart(performance, "strategy_performance.png")
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os
import json
import random
from tqdm import tqdm

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import matplotlib for plotting
try:
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    MATPLOTLIB_AVAILABLE = True
except ImportError:
    MATPLOTLIB_AVAILABLE = False
    logger.warning("Matplotlib not available. Visualization features will be disabled.")

class StrategyAnalyzer:
    """
    Analyzes trading strategies through backtesting and performance measurement.
    """
    
    def __init__(self, hist_db='historical_data.db', 
                 benchmark_db='benchmark_result_final.db',
                 strategy_csv='Caveman - Sheet11.csv'):
        """
        Initialize the analyzer with database connections and settings.
        
        Args:
            hist_db (str): Path to historical data database
            benchmark_db (str): Path to benchmark results database
            strategy_csv (str): Path to strategy CSV file
        """
        self.hist_db = hist_db
        self.benchmark_db = benchmark_db
        self.strategy_csv = strategy_csv
        
        # Performance metrics to calculate
        self.metrics = [
            'total_return', 'win_rate', 'avg_gain', 'avg_loss',
            'max_drawdown', 'sharpe_ratio', 'profit_factor'
        ]
        
        # Strategy parameters
        self.lookback_days = 20
        self.forward_test_days = 10
        self.num_samples = 50
        self.risk_free_rate = 0.03  # 3% annualized for Sharpe ratio calculation
        
        # Load strategy CSV if it exists
        if os.path.exists(self.strategy_csv):
            try:
                self.strategy_df = pd.read_csv(self.strategy_csv)
                logger.info(f"Loaded {len(self.strategy_df)} strategy rows from {self.strategy_csv}")
            except Exception as e:
                logger.error(f"Error loading strategy CSV: {e}")
                self.strategy_df = None
        else:
            logger.warning(f"Strategy CSV not found at {self.strategy_csv}")
            self.strategy_df = None
            
        # Function to calculate technical indicators (reference to existing function)
        from src.indicators.standard import calculate_technical_indicators
        self.calculate_indicators = calculate_technical_indicators
    
    def scale_sub_indicator(self, sub_ind, raw_val, close_val):
        """
        Scale an indicator value to a factor.
        
        This replicates the scaling logic from operation_script.py to
        ensure consistency in signal generation.
        
        Args:
            sub_ind (str): Indicator name
            raw_val (float): Raw indicator value
            close_val (float): Current close price
            
        Returns:
            float: Scaled indicator value or None if scaling fails
        """
        if close_val <= 0:
            return None
        try:
            if sub_ind == 'ema':
                return close_val / raw_val if raw_val > 0 else None
            elif sub_ind == 'macd':
                return 1.0 + (raw_val / close_val)
            elif sub_ind == 'rsi':
                return 1.0 - ((raw_val - 50.0) / 50.0)
            elif sub_ind == 'adx':
                return 1.0 + ((raw_val - 20.0) / 80.0)
            elif sub_ind == 'atr':
                return 1.0 + (raw_val / close_val)
            elif sub_ind == 'vwap':
                return close_val / raw_val if raw_val > 0 else None
            elif sub_ind == 'cci':
                fac = 1.0 - (raw_val / 200.0)
                return fac if fac > 0 else None
            elif sub_ind == 'relvol':
                return min(raw_val, 3.0)
        except Exception as e:
            logger.error(f"Error scaling {sub_ind} with value {raw_val}: {e}")
            return None
        return None
    
    def calculate_combined_value(self, indicators, indicator_list, current_close):
        """
        Compute a combined value from the given indicators.
        Uses geometric mean of scaled indicator values.
        
        This replicates the logic from operation_script.py for consistency.
        
        Args:
            indicators (dict): Dictionary of indicator values
            indicator_list (list): List of indicators to combine
            current_close (float): Current close price
            
        Returns:
            float: Combined indicator value or None if calculation fails
        """
        try:
            factors = []
            for ind in indicator_list:
                if ind not in indicators:
                    logger.debug(f"Indicator {ind} missing.")
                    return None
                scaled = self.scale_sub_indicator(ind, indicators[ind], current_close)
                if scaled is None:
                    logger.debug(f"Scaling failed for {ind} (value: {indicators[ind]}).")
                    return None
                factors.append(scaled)
            if not factors:
                return None
            product = np.product(factors)
            combined = product ** (1.0 / len(factors))
            logger.debug(f"Combined value for {indicator_list}: {combined}")
            return combined
        except Exception as e:
            logger.error(f"Error computing combined value for {indicator_list}: {e}")
            return None
    
    def get_symbols(self):
        """
        Get all available symbols from historical database.
        
        Returns:
            list: List of stock symbols
        """
        conn = sqlite3.connect(self.hist_db)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM historical_data_daily")
        symbols = [row[0] for row in cursor.fetchall()]
        conn.close()
        return symbols
    
    def get_random_dates(self, n=30, min_days_ago=30, max_days_ago=365*2):
        """
        Generate random dates for testing.
        
        Args:
            n (int): Number of dates to generate
            min_days_ago (int): Minimum days from today
            max_days_ago (int): Maximum days from today
            
        Returns:
            list: List of datetime objects
        """
        today = datetime.now()
        return [
            today - timedelta(days=random.randint(min_days_ago, max_days_ago))
            for _ in range(n)
        ]
    
    def fetch_historical_data(self, symbol, start_date, end_date):
        """
        Fetch historical price data for a symbol within the date range.
        
        Args:
            symbol (str): Stock symbol
            start_date (datetime): Start date
            end_date (datetime): End date
            
        Returns:
            pd.DataFrame: DataFrame with OHLCV data or None if data unavailable
        """
        try:
            conn = sqlite3.connect(self.hist_db)
            
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
                params=(
                    symbol, 
                    start_date.strftime('%Y-%m-%d'), 
                    end_date.strftime('%Y-%m-%d')
                )
            )
            
            conn.close()
            
            if df.empty:
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
            logger.error(f"Error fetching historical data for {symbol}: {e}")
            return None
    
    def analyze_strategy(self, indicator_combo, num_samples=None, risk_threshold=10.0):
        """
        Analyze a trading strategy based on indicator combination.
        
        Args:
            indicator_combo (str): Comma-separated list of indicators
            num_samples (int): Number of random samples to test (uses self.num_samples if None)
            risk_threshold (float): Maximum allowed daily gain (%) before skipping a stock
            
        Returns:
            dict: Performance metrics and trade data
        """
        if num_samples is None:
            num_samples = self.num_samples
            
        # Parse indicator list
        indicators_to_use = [ind.strip() for ind in indicator_combo.split(',')]
        logger.info(f"Analyzing strategy with indicators: {indicators_to_use}")
        
        # Find matching strategy in CSV if available
        strategy_row = None
        if self.strategy_df is not None:
            mask = self.strategy_df['indicator'] == indicator_combo
            if mask.any():
                strategy_row = self.strategy_df[mask].iloc[0]
                logger.info(f"Found matching strategy in CSV: {strategy_row['indicator']} (Win Rate: {strategy_row['win_rate']}%)")
        
        # Get all symbols
        all_symbols = self.get_symbols()
        logger.info(f"Found {len(all_symbols)} symbols for testing")
        
        # Generate random test dates
        test_dates = self.get_random_dates(n=num_samples)
        
        # Store trade results
        trades = []
        
        # Run backtest on each sample date
        for test_date in tqdm(test_dates, desc="Testing strategy"):
            # Define data ranges
            lookback_start = test_date - timedelta(days=self.lookback_days * 1.5)  # Add margin for weekends
            lookback_end = test_date
            forward_end = test_date + timedelta(days=self.forward_test_days * 1.5)  # Add margin for weekends
            
            # Test random symbols for each date (limit to 10 symbols per date to keep runtime reasonable)
            test_symbols = random.sample(all_symbols, min(10, len(all_symbols)))
            
            for symbol in test_symbols:
                # Get lookback data for indicator calculation
                lookback_data = self.fetch_historical_data(symbol, lookback_start, lookback_end)
                if lookback_data is None or len(lookback_data) < self.lookback_days:
                    continue
                    
                # Get forward data for performance measurement
                forward_data = self.fetch_historical_data(symbol, lookback_end, forward_end)
                if forward_data is None or len(forward_data) < 5:  # Need at least 5 days of future data
                    continue
                
                # Skip if the daily gain is too high (risk management)
                current_close = float(lookback_data['close'].iloc[-1])
                previous_close = float(lookback_data['close'].iloc[-2]) if len(lookback_data) >= 2 else current_close
                daily_change = ((current_close - previous_close) / previous_close) * 100
                if daily_change > risk_threshold:
                    logger.debug(f"Skipping {symbol} due to high daily gain: {daily_change:.2f}%")
                    continue
                
                # Calculate indicators
                try:
                    calculated_indicators = self.calculate_indicators(lookback_data)
                    if not calculated_indicators:
                        continue
                        
                    # Calculate relative volume
                    last_bars = lookback_data.tail(20)
                    avg_vol = last_bars['volume'].mean()
                    if avg_vol <= 0:
                        continue
                    current_vol = float(lookback_data['volume'].iloc[-1])
                    relvol_val = current_vol / avg_vol
                    calculated_indicators['relvol'] = pd.Series([relvol_val], index=[lookback_data.index[-1]])
                    
                    # Simplify indicators dict for easier processing
                    simple_indicators = {}
                    for key, val in calculated_indicators.items():
                        if key not in indicators_to_use:
                            continue
                        try:
                            if isinstance(val, (pd.Series, np.ndarray)):
                                dropped = val.dropna()
                                if not dropped.empty:
                                    simple_indicators[key] = float(dropped.iloc[-1])
                            else:
                                simple_indicators[key] = float(val)
                        except Exception as e:
                            logger.debug(f"Error processing {key} for {symbol}: {e}")
                            continue
                    
                    # Skip if any required indicator is missing
                    if not all(key in simple_indicators for key in indicators_to_use):
                        continue
                        
                    # Calculate combined value
                    combined_val = self.calculate_combined_value(simple_indicators, indicators_to_use, current_close)
                    if combined_val is None:
                        continue
                    
                    # Determine if the signal should trigger (using value range if available)
                    trigger_signal = True
                    if strategy_row is not None and 'value_range' in strategy_row:
                        try:
                            value_range = strategy_row['value_range']
                            if isinstance(value_range, str) and '-' in value_range:
                                opt_min, opt_max = map(float, value_range.split('-'))
                                trigger_signal = opt_min <= combined_val <= opt_max
                        except Exception as e:
                            logger.debug(f"Error parsing value range: {e}")
                    
                    if not trigger_signal:
                        continue
                    
                    # Calculate entry price (using current close or next day open)
                    entry_price = current_close
                    entry_date = lookback_data.index[-1]
                    
                    # Calculate forward performance
                    max_price = forward_data['high'].max()
                    min_price = forward_data['low'].min()
                    exit_price = forward_data['close'].iloc[-1]
                    
                    # Calculate returns
                    max_return_pct = ((max_price - entry_price) / entry_price) * 100
                    min_return_pct = ((min_price - entry_price) / entry_price) * 100
                    exit_return_pct = ((exit_price - entry_price) / entry_price) * 100
                    
                    # Determine when the max price was reached
                    try:
                        max_idx = forward_data['high'].idxmax()
                        days_to_max = (max_idx - entry_date).days
                    except (ValueError, KeyError, TypeError):
                        days_to_max = None
                    
                    # Record trade
                    trade = {
                        'symbol': symbol,
                        'entry_date': entry_date.strftime('%Y-%m-%d'),
                        'entry_price': entry_price,
                        'combined_value': combined_val,
                        'max_price': max_price,
                        'min_price': min_price,
                        'exit_price': exit_price,
                        'max_return_pct': max_return_pct,
                        'min_return_pct': min_return_pct,
                        'exit_return_pct': exit_return_pct,
                        'days_to_max': days_to_max,
                        'result': 'Win' if exit_return_pct > 0 else 'Loss'
                    }
                    trades.append(trade)
                    
                except Exception as e:
                    logger.debug(f"Error analyzing {symbol}: {e}")
                    continue
        
        # Calculate overall performance metrics
        performance = self.calculate_performance_metrics(trades)
        
        return {
            'indicator_combo': indicator_combo,
            'num_trades': len(trades),
            'metrics': performance,
            'trades': trades
        }
    
    def calculate_performance_metrics(self, trades):
        """
        Calculate performance metrics from trade data.
        
        Args:
            trades (list): List of trade dictionaries
            
        Returns:
            dict: Performance metrics
        """
        if not trades:
            return {metric: None for metric in self.metrics}
            
        # Convert to DataFrame for easier analysis
        trades_df = pd.DataFrame(trades)
        
        # Calculate total return (compounded)
        total_return = (trades_df['exit_return_pct'] / 100 + 1).prod() - 1
        total_return_pct = total_return * 100
        
        # Calculate win rate
        wins = trades_df['result'] == 'Win'
        win_rate = wins.sum() / len(trades_df) * 100
        
        # Calculate average gain and loss
        avg_gain = trades_df.loc[wins, 'exit_return_pct'].mean() if wins.any() else 0
        avg_loss = trades_df.loc[~wins, 'exit_return_pct'].mean() if (~wins).any() else 0
        
        # Calculate profit factor
        gross_profit = trades_df.loc[wins, 'exit_return_pct'].sum() if wins.any() else 0
        gross_loss = abs(trades_df.loc[~wins, 'exit_return_pct'].sum()) if (~wins).any() else 0
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')
        
        # Calculate max drawdown
        returns = trades_df['exit_return_pct'] / 100
        cumulative = (1 + returns).cumprod()
        
        if len(cumulative) > 1:
            running_max = cumulative.cummax()
            drawdown = (cumulative / running_max - 1) * 100
            max_drawdown = abs(drawdown.min())
        else:
            max_drawdown = 0
        
        # Calculate annualized Sharpe ratio 
        # (assuming trades represent timeframe from first to last trade)
        if len(trades) > 1:
            try:
                first_date = datetime.strptime(trades[0]['entry_date'], '%Y-%m-%d')
                last_date = datetime.strptime(trades[-1]['entry_date'], '%Y-%m-%d')
                years = (last_date - first_date).days / 365.25
                
                if years > 0:
                    avg_return = trades_df['exit_return_pct'].mean()
                    std_return = trades_df['exit_return_pct'].std()
                    
                    if std_return > 0:
                        sharpe_ratio = (avg_return - self.risk_free_rate) / std_return * np.sqrt(252 / self.forward_test_days)
                    else:
                        sharpe_ratio = float('inf') if avg_return > self.risk_free_rate else float('-inf')
                else:
                    sharpe_ratio = None
            except (ValueError, TypeError, ZeroDivisionError):
                sharpe_ratio = None
        else:
            sharpe_ratio = None
        
        return {
            'total_return': total_return_pct,
            'win_rate': win_rate,
            'avg_gain': avg_gain,
            'avg_loss': avg_loss,
            'max_drawdown': max_drawdown,
            'sharpe_ratio': sharpe_ratio,
            'profit_factor': profit_factor
        }
    
    def generate_performance_chart(self, performance_data, output_file=None):
        """
        Generate performance chart for a strategy.
        
        Args:
            performance_data (dict): Strategy performance data
            output_file (str): Path to save the chart (if None, display only)
            
        Returns:
            bool: Success flag
        """
        if not MATPLOTLIB_AVAILABLE:
            logger.warning("Matplotlib not available. Cannot generate chart.")
            return False
            
        if not performance_data or 'trades' not in performance_data or not performance_data['trades']:
            logger.warning("No trade data available for chart generation.")
            return False
            
        try:
            trades = performance_data['trades']
            trades_df = pd.DataFrame(trades)
            
            # Sort by entry date
            trades_df['entry_date'] = pd.to_datetime(trades_df['entry_date'])
            trades_df.sort_values('entry_date', inplace=True)
            
            # Calculate cumulative returns
            returns = trades_df['exit_return_pct'] / 100
            equity_curve = (1 + returns).cumprod()
            
            # Create figure with two subplots
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10), gridspec_kw={'height_ratios': [3, 1]})
            
            # Plot equity curve
            ax1.plot(trades_df['entry_date'], equity_curve, 'b-', linewidth=2)
            ax1.set_title(f"Strategy Performance: {performance_data['indicator_combo']}", fontsize=14)
            ax1.set_ylabel('Account Value (Starting = 1)', fontsize=12)
            ax1.grid(True)
            
            # Format x-axis dates
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax1.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            
            # Calculate drawdown
            running_max = equity_curve.cummax()
            drawdown = (equity_curve / running_max - 1) * 100
            
            # Plot drawdown
            ax2.fill_between(trades_df['entry_date'], drawdown, 0, color='red', alpha=0.3)
            ax2.set_ylabel('Drawdown (%)', fontsize=12)
            ax2.set_xlabel('Date', fontsize=12)
            ax2.grid(True)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax2.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
            
            # Annotate with metrics
            metrics = performance_data['metrics']
            metrics_text = (
                f"Total Return: {metrics['total_return']:.2f}%\n"
                f"Win Rate: {metrics['win_rate']:.2f}%\n"
                f"Avg. Gain: {metrics['avg_gain']:.2f}%\n"
                f"Avg. Loss: {metrics['avg_loss']:.2f}%\n"
                f"Profit Factor: {metrics['profit_factor']:.2f}\n"
                f"Max Drawdown: {metrics['max_drawdown']:.2f}%\n"
                f"Trades: {performance_data['num_trades']}"
            )
            
            # Add metrics text box
            plt.figtext(0.15, 0.01, metrics_text, fontsize=12, 
                      bbox=dict(facecolor='white', alpha=0.8))
            
            # Adjust layout and display/save
            plt.tight_layout(rect=[0, 0.08, 1, 0.95])
            
            if output_file:
                plt.savefig(output_file, dpi=300, bbox_inches='tight')
                logger.info(f"Chart saved to {output_file}")
            else:
                plt.show()
                
            plt.close(fig)
            return True
            
        except Exception as e:
            logger.error(f"Error generating performance chart: {e}")
            return False
    
    def batch_analyze_strategies(self, indicator_combos=None, output_dir='strategy_reports'):
        """
        Run batch analysis on multiple strategies.
        
        Args:
            indicator_combos (list): List of indicator combinations to test
            output_dir (str): Directory to save reports and charts
            
        Returns:
            pd.DataFrame: Summary of strategies and performance
        """
        if not indicator_combos and self.strategy_df is not None:
            # Use strategy combinations from CSV
            indicator_combos = self.strategy_df['indicator'].unique().tolist()
        elif not indicator_combos:
            logger.error("No indicator combinations provided and no strategy CSV available.")
            return None
            
        # Ensure output directory exists
        if not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # Run analysis on each combination
        results = []
        
        for combo in tqdm(indicator_combos, desc="Analyzing strategies"):
            try:
                # Run analysis
                performance = self.analyze_strategy(combo)
                
                if not performance['trades']:
                    logger.warning(f"No trades for combo: {combo} - skipping")
                    continue
                    
                # Generate chart if matplotlib available
                if MATPLOTLIB_AVAILABLE:
                    chart_file = os.path.join(output_dir, f"{combo.replace(',', '_')}_chart.png")
                    self.generate_performance_chart(performance, chart_file)
                
                # Save detailed results to JSON
                results_file = os.path.join(output_dir, f"{combo.replace(',', '_')}_results.json")
                with open(results_file, 'w') as f:
                    # Convert float64/int64 types for JSON serialization
                    for trade in performance['trades']:
                        for k, v in trade.items():
                            if isinstance(v, (np.float64, np.int64)):
                                trade[k] = float(v)
                    
                    for metric, value in performance['metrics'].items():
                        if isinstance(value, (np.float64, np.int64)):
                            performance['metrics'][metric] = float(value)
                            
                    json.dump(performance, f, indent=2)
                
                # Add summary to results
                metrics = performance['metrics']
                result = {
                    'indicator_combo': combo,
                    'num_trades': performance['num_trades']
                }
                result.update(metrics)
                results.append(result)
                
            except Exception as e:
                logger.error(f"Error analyzing combo {combo}: {e}")
                continue
                
        # Convert results to DataFrame
        if results:
            results_df = pd.DataFrame(results)
            
            # Sort by win rate and profit factor
            results_df.sort_values(['win_rate', 'profit_factor'], ascending=False, inplace=True)
            
            # Save summary to CSV
            summary_file = os.path.join(output_dir, 'strategy_summary.csv')
            results_df.to_csv(summary_file, index=False)
            logger.info(f"Strategy summary saved to {summary_file}")
            
            return results_df
        else:
            logger.warning("No valid results to report.")
            return None

# Example usage
if __name__ == "__main__":
    analyzer = StrategyAnalyzer()
    
    # Example: Analyze a specific indicator combination
    performance = analyzer.analyze_strategy("ema,rsi,vwap", num_samples=10)
    print(f"Strategy performance metrics:")
    for metric, value in performance['metrics'].items():
        print(f"  {metric}: {value}")
        
    # Generate performance chart
    if MATPLOTLIB_AVAILABLE:
        analyzer.generate_performance_chart(performance)
    
    # Example: Batch analyze from strategy CSV
    # results_df = analyzer.batch_analyze_strategies()
    # print(results_df.head())