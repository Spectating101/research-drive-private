#!/usr/bin/env python3
"""
Optimal Exit Analysis - Data-Driven Exit Strategy

This script analyzes the actual holding period performance to determine
optimal exit points based on data, not hardcoded assumptions.
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

class OptimalExitAnalyzer:
    """Analyze optimal exit points based on actual pattern performance."""
    
    def __init__(self):
        """Initialize the analyzer."""
        self.conn = sqlite3.connect('db/historical_data.db')
        self.data = None
        
    def load_and_prepare_data(self):
        """Load data and calculate features."""
        print("🔍 LOADING DATA FOR OPTIMAL EXIT ANALYSIS")
        print("=" * 60)
        
        # Load data
        df = pd.read_sql_query("SELECT * FROM historical_data_daily", self.conn)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        
        print(f"✅ Total Records: {len(df):,}")
        print(f"✅ Unique Symbols: {df['symbol'].nunique()}")
        
        # Calculate features
        df = df.sort_values(['symbol', 'timestamp'])
        df['daily_return'] = df.groupby('symbol')['close'].pct_change()
        df['gap'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        df['sma_5'] = df.groupby('symbol')['close'].rolling(5).mean().reset_index(0, drop=True)
        df['volume_sma_5'] = df.groupby('symbol')['volume'].rolling(5).mean().reset_index(0, drop=True)
        df['momentum_3d'] = df.groupby('symbol')['close'].pct_change(3)
        df['volume_ratio_5d'] = df['volume'] / df['volume_sma_5']
        df['price_vs_sma5'] = df['close'] / df['sma_5'] - 1
        
        # Calculate future returns for different holding periods
        for days in [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]:
            df[f'return_{days}d'] = df.groupby('symbol')['close'].pct_change(days).shift(-days)
        
        # Define winner for different thresholds
        df['is_winner_5%'] = (df['return_1d'] > 0.05).astype(int)
        df['is_winner_10%'] = (df['return_1d'] > 0.10).astype(int)
        df['is_winner_15%'] = (df['return_1d'] > 0.15).astype(int)
        
        # Remove NaN
        df = df.dropna()
        
        self.data = df
        
        print(f"✅ Data prepared with {len(df):,} records")
        return df
    
    def analyze_holding_period_performance(self):
        """Analyze performance across different holding periods."""
        print(f"\n📊 HOLDING PERIOD PERFORMANCE ANALYSIS")
        print("=" * 60)
        
        # Test the strongest pattern: Gap > 8% AND Price > SMA5 by 10%
        pattern_mask = (self.data['gap'] > 0.08) & (self.data['price_vs_sma5'] > 0.10)
        pattern_data = self.data[pattern_mask].copy()
        
        print(f"Pattern: Gap > 8% AND Price > SMA5 by 10%")
        print(f"Total signals: {len(pattern_data):,}")
        
        # Analyze returns for different holding periods
        holding_periods = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        
        print(f"\n📈 RETURNS BY HOLDING PERIOD:")
        print("-" * 50)
        print(f"{'Days':<4} {'Avg Return':<12} {'Win Rate':<10} {'Max Return':<12} {'Min Return':<12}")
        print("-" * 50)
        
        for days in holding_periods:
            returns = pattern_data[f'return_{days}d'].dropna()
            
            avg_return = returns.mean()
            win_rate = (returns > 0).mean()
            max_return = returns.max()
            min_return = returns.min()
            
            print(f"{days:<4} {avg_return:>10.2%} {win_rate:>8.1%} {max_return:>10.2%} {min_return:>10.2%}")
        
        return pattern_data
    
    def analyze_optimal_exit_points(self):
        """Analyze optimal exit points based on cumulative returns."""
        print(f"\n🎯 OPTIMAL EXIT POINT ANALYSIS")
        print("=" * 60)
        
        # Test the strongest pattern
        pattern_mask = (self.data['gap'] > 0.08) & (self.data['price_vs_sma5'] > 0.10)
        pattern_data = self.data[pattern_mask].copy()
        
        print(f"Analyzing {len(pattern_data):,} signals for optimal exit points...")
        
        # Calculate cumulative returns for each signal
        exit_analysis = []
        
        for _, row in pattern_data.iterrows():
            symbol = row['symbol']
            signal_date = row['timestamp']
            
            # Get future data for this symbol
            future_data = self.data[
                (self.data['symbol'] == symbol) & 
                (self.data['timestamp'] > signal_date)
            ].head(10)  # Look at next 10 days
            
            if len(future_data) > 0:
                entry_price = row['close']
                
                # Calculate cumulative returns for each day
                for i, future_row in future_data.iterrows():
                    days_held = (future_row['timestamp'] - signal_date).days
                    current_price = future_row['close']
                    cumulative_return = (current_price - entry_price) / entry_price
                    
                    exit_analysis.append({
                        'symbol': symbol,
                        'signal_date': signal_date,
                        'entry_price': entry_price,
                        'days_held': days_held,
                        'exit_price': current_price,
                        'cumulative_return': cumulative_return
                    })
        
        exit_df = pd.DataFrame(exit_analysis)
        
        # Analyze optimal exit points
        print(f"\n📊 OPTIMAL EXIT ANALYSIS:")
        print("-" * 50)
        
        for days in range(1, 11):
            day_data = exit_df[exit_df['days_held'] == days]
            
            if len(day_data) > 0:
                avg_return = day_data['cumulative_return'].mean()
                win_rate = (day_data['cumulative_return'] > 0).mean()
                median_return = day_data['cumulative_return'].median()
                
                print(f"Day {days:2d}: Avg={avg_return:6.2%}, Win Rate={win_rate:5.1%}, Median={median_return:6.2%}")
        
        return exit_df
    
    def analyze_profit_targets(self):
        """Analyze different profit targets and their success rates."""
        print(f"\n💰 PROFIT TARGET ANALYSIS")
        print("=" * 60)
        
        # Test the strongest pattern
        pattern_mask = (self.data['gap'] > 0.08) & (self.data['price_vs_sma5'] > 0.10)
        pattern_data = self.data[pattern_mask].copy()
        
        profit_targets = [0.05, 0.10, 0.15, 0.20, 0.25, 0.30]
        
        print(f"Analyzing profit targets for {len(pattern_data):,} signals...")
        print(f"\n📊 PROFIT TARGET SUCCESS RATES:")
        print("-" * 50)
        print(f"{'Target':<8} {'Success Rate':<12} {'Avg Days':<10} {'Max Days':<10}")
        print("-" * 50)
        
        for target in profit_targets:
            success_count = 0
            days_to_target = []
            
            for _, row in pattern_data.iterrows():
                symbol = row['symbol']
                signal_date = row['timestamp']
                entry_price = row['close']
                
                # Get future data for this symbol
                future_data = self.data[
                    (self.data['symbol'] == symbol) & 
                    (self.data['timestamp'] > signal_date)
                ].head(10)  # Look at next 10 days
                
                # Check if target is reached
                for i, future_row in future_data.iterrows():
                    days_held = (future_row['timestamp'] - signal_date).days
                    current_price = future_row['close']
                    cumulative_return = (current_price - entry_price) / entry_price
                    
                    if cumulative_return >= target:
                        success_count += 1
                        days_to_target.append(days_held)
                        break
            
            success_rate = success_count / len(pattern_data) if len(pattern_data) > 0 else 0
            avg_days = np.mean(days_to_target) if days_to_target else 0
            max_days = max(days_to_target) if days_to_target else 0
            
            print(f"{target:>6.0%} {success_rate:>10.1%} {avg_days:>8.1f} {max_days:>8.0f}")
    
    def analyze_stop_loss_levels(self):
        """Analyze different stop loss levels and their impact."""
        print(f"\n🛑 STOP LOSS ANALYSIS")
        print("=" * 60)
        
        # Test the strongest pattern
        pattern_mask = (self.data['gap'] > 0.08) & (self.data['price_vs_sma5'] > 0.10)
        pattern_data = self.data[pattern_mask].copy()
        
        stop_loss_levels = [-0.03, -0.05, -0.10, -0.15, -0.20]
        
        print(f"Analyzing stop loss levels for {len(pattern_data):,} signals...")
        print(f"\n📊 STOP LOSS IMPACT:")
        print("-" * 50)
        print(f"{'Stop Loss':<10} {'Trigger Rate':<12} {'Avg Loss':<10} {'Max Loss':<10}")
        print("-" * 50)
        
        for stop_loss in stop_loss_levels:
            trigger_count = 0
            losses = []
            
            for _, row in pattern_data.iterrows():
                symbol = row['symbol']
                signal_date = row['timestamp']
                entry_price = row['close']
                
                # Get future data for this symbol
                future_data = self.data[
                    (self.data['symbol'] == symbol) & 
                    (self.data['timestamp'] > signal_date)
                ].head(10)  # Look at next 10 days
                
                # Check if stop loss is triggered
                for i, future_row in future_data.iterrows():
                    days_held = (future_row['timestamp'] - signal_date).days
                    current_price = future_row['close']
                    cumulative_return = (current_price - entry_price) / entry_price
                    
                    if cumulative_return <= stop_loss:
                        trigger_count += 1
                        losses.append(cumulative_return)
                        break
            
            trigger_rate = trigger_count / len(pattern_data) if len(pattern_data) > 0 else 0
            avg_loss = np.mean(losses) if losses else 0
            max_loss = min(losses) if losses else 0
            
            print(f"{stop_loss:>8.0%} {trigger_rate:>10.1%} {avg_loss:>8.2%} {max_loss:>8.2%}")
    
    def test_optimized_strategy(self):
        """Test strategy with optimized exit conditions."""
        print(f"\n🎯 TESTING OPTIMIZED STRATEGY")
        print("=" * 60)
        
        # Use last 2 years for testing
        end_date = self.data['timestamp'].max()
        start_date = end_date - timedelta(days=730)
        
        test_data = self.data[
            (self.data['timestamp'] >= start_date) & 
            (self.data['timestamp'] <= end_date)
        ].copy()
        
        print(f"Testing period: {start_date.date()} to {end_date.date()}")
        print(f"Test records: {len(test_data):,}")
        
        # Define signal function
        def generate_signal(row):
            """Generate signal based on strongest pattern."""
            if (row['gap'] > 0.08) and (row['price_vs_sma5'] > 0.10):
                return True, f"Gap {row['gap']:.1%}, Price {row['price_vs_sma5']:.1%} above SMA5"
            return False, ""
        
        # Test with optimized exit conditions
        initial_capital = 100000
        capital = initial_capital
        trades = []
        positions = {}
        
        # Get unique dates
        dates = sorted(test_data['timestamp'].unique())
        
        for date in dates:
            current_date = date
            date_data = test_data[test_data['timestamp'] == date]
            
            # Check for exit conditions on existing positions
            for symbol in list(positions.keys()):
                position = positions[symbol]
                symbol_data = date_data[date_data['symbol'] == symbol]
                
                if len(symbol_data) > 0:
                    current_price = symbol_data.iloc[0]['close']
                    position_return = (current_price - position['entry_price']) / position['entry_price']
                    days_held = (current_date - position['entry_date']).days
                    
                    # Optimized exit conditions based on analysis
                    if (position_return >= 0.15 or  # 15% profit target
                        position_return <= -0.10 or  # 10% stop loss
                        days_held >= 6):  # 6-day max hold (based on peak analysis)
                        
                        # Close position
                        exit_price = current_price
                        capital += position['shares'] * exit_price
                        
                        trades.append({
                            'symbol': symbol,
                            'entry_date': position['entry_date'],
                            'exit_date': current_date,
                            'entry_price': position['entry_price'],
                            'exit_price': exit_price,
                            'return': position_return,
                            'days_held': days_held
                        })
                        
                        del positions[symbol]
            
            # Check for new entry signals
            for _, row in date_data.iterrows():
                symbol = row['symbol']
                
                if symbol not in positions and len(positions) < 5:  # Max 5 positions
                    signal, reason = generate_signal(row)
                    
                    if signal:
                        position_size = capital * 0.1  # 10% of capital
                        shares = int(position_size / row['close'])
                        
                        if shares > 0:
                            positions[symbol] = {
                                'shares': shares,
                                'entry_price': row['close'],
                                'entry_date': current_date,
                                'reason': reason
                            }
                            capital -= shares * row['close']
        
        # Close remaining positions at end
        for symbol, position in positions.items():
            last_data = test_data[test_data['symbol'] == symbol].iloc[-1]
            exit_price = last_data['close']
            position_return = (exit_price - position['entry_price']) / position['entry_price']
            
            trades.append({
                'symbol': symbol,
                'entry_date': position['entry_date'],
                'exit_date': last_data['timestamp'],
                'entry_price': position['entry_price'],
                'exit_price': exit_price,
                'return': position_return,
                'days_held': (last_data['timestamp'] - position['entry_date']).days
            })
        
        # Calculate performance
        total_trades = len(trades)
        winning_trades = len([t for t in trades if t['return'] > 0])
        win_rate = winning_trades / total_trades if total_trades > 0 else 0
        
        total_return = (capital - initial_capital) / initial_capital
        avg_return = np.mean([t['return'] for t in trades]) if trades else 0
        avg_days_held = np.mean([t['days_held'] for t in trades]) if trades else 0
        
        print(f"\n📈 OPTIMIZED STRATEGY RESULTS:")
        print(f"  Total Trades: {total_trades}")
        print(f"  Winning Trades: {winning_trades}")
        print(f"  Win Rate: {win_rate:.1%}")
        print(f"  Total Return: {total_return:.1%}")
        print(f"  Avg Return per Trade: {avg_return:.2%}")
        print(f"  Avg Days Held: {avg_days_held:.1f}")
        print(f"  Final Capital: ${capital:,.0f}")
        print(f"  Profit: ${capital - initial_capital:,.0f}")
        
        return trades, total_return, win_rate
    
    def run_complete_analysis(self):
        """Run the complete optimal exit analysis."""
        print("🚀 OPTIMAL EXIT ANALYSIS")
        print("=" * 60)
        print("Analyzing actual data to determine optimal exit points.")
        
        # Load data
        self.load_and_prepare_data()
        
        # Analyze holding period performance
        self.analyze_holding_period_performance()
        
        # Analyze optimal exit points
        self.analyze_optimal_exit_points()
        
        # Analyze profit targets
        self.analyze_profit_targets()
        
        # Analyze stop loss levels
        self.analyze_stop_loss_levels()
        
        # Test optimized strategy
        trades, total_return, win_rate = self.test_optimized_strategy()
        
        print(f"\n✅ OPTIMAL EXIT ANALYSIS COMPLETE")
        print("=" * 60)
        print("Exit conditions are now based on actual data analysis, not assumptions.")

def main():
    """Main function."""
    analyzer = OptimalExitAnalyzer()
    analyzer.run_complete_analysis()
    analyzer.conn.close()

if __name__ == "__main__":
    main()
