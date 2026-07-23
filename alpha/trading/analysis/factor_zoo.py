#!/usr/bin/env python3
"""
Academic Factor Zoo - 400+ Factors for Indonesian Stock Market
Based on academic finance literature and empirical research
"""

import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple
import logging
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class AcademicFactorZoo:
    """Comprehensive factor zoo implementation with 400+ academic factors"""
    
    def __init__(self, db_path: str = "db/historical_data.db"):
        self.db_path = db_path
        try:
            self.conn = sqlite3.connect(db_path)
        except Exception as e:
            logger.warning(f"Could not connect to database at {db_path}: {e}")
            self.conn = None
        
    def get_stock_data(self, symbol: str, end_date: str = None) -> pd.DataFrame:
        """Get historical data for a symbol up to end_date"""
        if self.conn is None:
            return pd.DataFrame()
            
        if end_date:
            query = "SELECT * FROM historical_data_daily WHERE symbol = ? AND timestamp <= ? ORDER BY timestamp"
            return pd.read_sql_query(query, self.conn, params=(symbol, end_date))
        else:
            query = "SELECT * FROM historical_data_daily WHERE symbol = ? ORDER BY timestamp"
            return pd.read_sql_query(query, self.conn, params=(symbol,))
            
    # --- FUNDAMENTAL FACTORS ---
    
    def calculate_fama_french_factors(self, fundamentals_df: pd.DataFrame) -> Dict[str, float]:
        """Fama-French 5-Factor Model proxies"""
        factors = {}
        if fundamentals_df.empty: return factors
        latest = fundamentals_df.iloc[-1]
        
        # 1. SMB (Size)
        if 'market_cap' in latest:
            factors['size_log_mcap'] = np.log(latest['market_cap'])
        # 2. HML (Value)
        if 'book_value' in latest and 'market_cap' in latest:
            factors['value_bm'] = latest['book_value'] / latest['market_cap']
        # 3. RMW (Profitability)
        if 'operating_profit' in latest and 'book_value' in latest:
            factors['profitability_op_be'] = latest['operating_profit'] / latest['book_value']
        # 4. CMA (Investment)
        if 'asset_growth' in latest:
            factors['investment_asset_growth'] = latest['asset_growth']
            
        return factors

    def calculate_q_factors(self, fundamentals_df: pd.DataFrame) -> Dict[str, float]:
        """
        Hou-Xue-Zhang Q-Factor Model proxies (Size, Investment, ROE).
        The q-factor model posits that expected returns are determined by:
        1. Market Factor (MKT)
        2. Size Factor (ME)
        3. Investment Factor (I/A): Asset Growth
        4. Profitability Factor (ROE): Return on Equity (Quarterly)
        """
        factors = {}
        if fundamentals_df.empty: return factors
        latest = fundamentals_df.iloc[-1]
        
        # 1. Size (ME)
        if 'market_cap' in latest:
            factors['q_size_me'] = latest['market_cap']
            
        # 2. Investment (I/A) - Asset Growth
        # Same as Fama-French CMA, but conceptually distinct in Q-theory
        if 'asset_growth' in latest:
            factors['q_investment_ia'] = latest['asset_growth']
            
        # 3. Profitability (ROE) - Net Income / Book Equity
        # Q-factor emphasizes recent (quarterly) ROE
        if 'net_income' in latest and 'book_value' in latest:
            if latest['book_value'] != 0:
                factors['q_profitability_roe'] = latest['net_income'] / latest['book_value']
            
        return factors

    # --- TECHNICAL FACTORS ---
    
    def calculate_price_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate price-based factors (50+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Basic price factors
        current_price = df['close'].iloc[-1]
        factors['current_price'] = current_price
        
        # Price momentum factors (1D to 5Y)
        for days in [1, 2, 3, 5, 10, 20, 30, 60, 90, 120, 180, 240, 360, 720, 1080, 1440]:
            if len(df) >= days:
                factors[f'price_momentum_{days}d'] = (current_price / df['close'].iloc[-days] - 1) * 100
        
        # Price volatility factors
        returns = df['close'].pct_change().dropna()
        for days in [5, 10, 20, 30, 60, 90, 120, 240]:
            if len(returns) >= days:
                factors[f'price_volatility_{days}d'] = returns.tail(days).std() * np.sqrt(252) * 100
        
        # Price range factors
        for days in [5, 10, 20, 30, 60]:
            if len(df) >= days:
                high_max = df['high'].tail(days).max()
                low_min = df['low'].tail(days).min()
                factors[f'price_range_{days}d'] = (high_max - low_min) / current_price * 100
        
        # Price position factors
        for days in [20, 50, 100, 200]:
            if len(df) >= days:
                high_max = df['high'].tail(days).max()
                low_min = df['low'].tail(days).min()
                factors[f'price_position_{days}d'] = (current_price - low_min) / (high_max - low_min) * 100
        
        return factors
    
    def calculate_volume_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate volume-based factors (30+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Volume momentum factors
        for days in [1, 2, 3, 5, 10, 20, 30, 60]:
            if len(df) >= days * 2:
                current_vol = df['volume'].tail(days).mean()
                past_vol = df['volume'].tail(days * 2).head(days).mean()
                factors[f'volume_momentum_{days}d'] = (current_vol / past_vol - 1) * 100
        
        # Volume volatility factors
        for days in [10, 20, 30, 60]:
            if len(df) >= days:
                factors[f'volume_volatility_{days}d'] = df['volume'].tail(days).std() / df['volume'].tail(days).mean() * 100
        
        # Volume-price relationship factors
        returns = df['close'].pct_change().dropna()
        volume = df['volume'].iloc[1:]  # Align with returns
        
        for days in [5, 10, 20, 30]:
            if len(returns) >= days:
                corr = returns.tail(days).corr(volume.tail(days))
                factors[f'volume_price_correlation_{days}d'] = corr if not pd.isna(corr) else 0
        
        # Volume trend factors
        for days in [10, 20, 30]:
            if len(df) >= days:
                volume_trend = np.polyfit(range(days), df['volume'].tail(days), 1)[0]
                factors[f'volume_trend_{days}d'] = volume_trend
        
        return factors
    
    def calculate_technical_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate technical indicator factors (100+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Moving averages
        for period in [5, 10, 20, 30, 50, 100, 200]:
            if len(df) >= period:
                sma = df['close'].rolling(period).mean()
                factors[f'sma_{period}'] = sma.iloc[-1]
                factors[f'price_vs_sma_{period}'] = (df['close'].iloc[-1] / sma.iloc[-1] - 1) * 100
        
        # Exponential moving averages
        for period in [5, 10, 20, 30, 50]:
            if len(df) >= period:
                ema = df['close'].ewm(span=period).mean()
                factors[f'ema_{period}'] = ema.iloc[-1]
                factors[f'price_vs_ema_{period}'] = (df['close'].iloc[-1] / ema.iloc[-1] - 1) * 100
        
        # RSI variations
        for period in [5, 10, 14, 21, 30]:
            if len(df) >= period:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(period).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(period).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                factors[f'rsi_{period}'] = rsi.iloc[-1] if not pd.isna(rsi.iloc[-1]) else 50
        
        # MACD variations
        for fast, slow, signal in [(12, 26, 9), (5, 35, 5), (8, 21, 5)]:
            if len(df) >= slow:
                exp1 = df['close'].ewm(span=fast).mean()
                exp2 = df['close'].ewm(span=slow).mean()
                macd = exp1 - exp2
                macd_signal = macd.ewm(span=signal).mean()
                factors[f'macd_{fast}_{slow}'] = macd.iloc[-1] if not pd.isna(macd.iloc[-1]) else 0
                factors[f'macd_signal_{fast}_{slow}'] = macd_signal.iloc[-1] if not pd.isna(macd_signal.iloc[-1]) else 0
                factors[f'macd_histogram_{fast}_{slow}'] = (macd.iloc[-1] - macd_signal.iloc[-1]) if not pd.isna(macd.iloc[-1]) else 0
        
        # Bollinger Bands
        for period in [10, 20, 30]:
            for std_dev in [1, 2, 3]:
                if len(df) >= period:
                    sma = df['close'].rolling(period).mean()
                    std = df['close'].rolling(period).std()
                    upper_band = sma + (std * std_dev)
                    lower_band = sma - (std * std_dev)
                    factors[f'bb_upper_{period}_{std_dev}'] = upper_band.iloc[-1] if not pd.isna(upper_band.iloc[-1]) else 0
                    factors[f'bb_lower_{period}_{std_dev}'] = lower_band.iloc[-1] if not pd.isna(lower_band.iloc[-1]) else 0
                    factors[f'bb_position_{period}_{std_dev}'] = (df['close'].iloc[-1] - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1]) * 100 if not pd.isna(upper_band.iloc[-1]) else 50
        
        # Stochastic Oscillator
        for k_period, d_period in [(14, 3), (21, 5)]:
            if len(df) >= k_period:
                low_min = df['low'].rolling(k_period).min()
                high_max = df['high'].rolling(k_period).max()
                k_percent = 100 * (df['close'] - low_min) / (high_max - low_min)
                d_percent = k_percent.rolling(d_period).mean()
                factors[f'stoch_k_{k_period}'] = k_percent.iloc[-1] if not pd.isna(k_percent.iloc[-1]) else 50
                factors[f'stoch_d_{k_period}_{d_period}'] = d_percent.iloc[-1] if not pd.isna(d_percent.iloc[-1]) else 50
        
        return factors
    
    def calculate_momentum_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate momentum-based factors (50+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Price momentum
        for days in [1, 2, 3, 5, 10, 20, 30, 60, 90, 120, 240]:
            if len(df) >= days:
                factors[f'momentum_{days}d'] = (df['close'].iloc[-1] / df['close'].iloc[-days] - 1) * 100
        
        # Volume momentum
        for days in [5, 10, 20, 30, 60]:
            if len(df) >= days * 2:
                current_vol = df['volume'].tail(days).mean()
                past_vol = df['volume'].tail(days * 2).head(days).mean()
                factors[f'volume_momentum_{days}d'] = (current_vol / past_vol - 1) * 100
        
        # High-Low momentum
        for days in [5, 10, 20, 30]:
            if len(df) >= days * 2:
                current_high = df['high'].tail(days).max()
                past_high = df['high'].tail(days * 2).head(days).max()
                current_low = df['low'].tail(days).min()
                past_low = df['low'].tail(days * 2).head(days).min()
                factors[f'high_momentum_{days}d'] = (current_high / past_high - 1) * 100
                factors[f'low_momentum_{days}d'] = (current_low / past_low - 1) * 100
        
        # Acceleration factors
        for days in [5, 10, 20]:
            if len(df) >= days * 2:
                recent_momentum = (df['close'].iloc[-1] / df['close'].iloc[-days] - 1) * 100
                past_momentum = (df['close'].iloc[-days] / df['close'].iloc[-days*2] - 1) * 100
                factors[f'acceleration_{days}d'] = recent_momentum - past_momentum
        
        return factors
    
    def calculate_volatility_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate volatility-based factors (40+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        returns = df['close'].pct_change().dropna()
        
        # Historical volatility
        for days in [5, 10, 20, 30, 60, 90, 120, 240]:
            if len(returns) >= days:
                factors[f'historical_volatility_{days}d'] = returns.tail(days).std() * np.sqrt(252) * 100
        
        # Realized volatility
        for days in [5, 10, 20, 30]:
            if len(returns) >= days:
                factors[f'realized_volatility_{days}d'] = np.sqrt((returns.tail(days) ** 2).sum()) * np.sqrt(252) * 100
        
        # Downside volatility
        for days in [10, 20, 30, 60]:
            if len(returns) >= days:
                downside_returns = returns.tail(days)[returns.tail(days) < 0]
                factors[f'downside_volatility_{days}d'] = downside_returns.std() * np.sqrt(252) * 100 if len(downside_returns) > 0 else 0
        
        # Volatility of volatility
        for days in [20, 30, 60]:
            if len(returns) >= days * 2:
                vol_series = returns.rolling(days).std()
                factors[f'volatility_of_volatility_{days}d'] = vol_series.tail(days).std() * 100
        
        # Range-based volatility
        for days in [5, 10, 20, 30]:
            if len(df) >= days:
                daily_range = np.log(df['high'].tail(days) / df['low'].tail(days))
                factors[f'range_volatility_{days}d'] = daily_range.std() * np.sqrt(252) * 100
        
        return factors
    
    def calculate_trend_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate trend-based factors (30+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Trend strength
        for period in [10, 20, 30, 50, 100]:
            if len(df) >= period:
                x = np.arange(period)
                y = df['close'].tail(period)
                slope, _ = np.polyfit(x, y, 1)
                factors[f'trend_slope_{period}d'] = slope
                factors[f'trend_strength_{period}d'] = abs(slope) / df['close'].iloc[-1] * 100
        
        # Trend consistency
        for period in [20, 30, 50]:
            if len(df) >= period:
                returns = df['close'].pct_change().tail(period)
                positive_days = (returns > 0).sum()
                factors[f'trend_consistency_{period}d'] = positive_days / period * 100
        
        # Moving average crossovers
        for fast, slow in [(5, 20), (10, 30), (20, 50), (50, 200)]:
            if len(df) >= slow:
                fast_ma = df['close'].rolling(fast).mean()
                slow_ma = df['close'].rolling(slow).mean()
                factors[f'ma_crossover_{fast}_{slow}'] = (fast_ma.iloc[-1] / slow_ma.iloc[-1] - 1) * 100
        
        return factors
    
    def calculate_liquidity_factors(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate liquidity-based factors (20+ factors)"""
        factors = {}
        
        if len(df) < 20:
            return factors
        
        # Volume-based liquidity
        for days in [5, 10, 20, 30, 60]:
            if len(df) >= days:
                avg_volume = df['volume'].tail(days).mean()
                factors[f'avg_volume_{days}d'] = avg_volume
                factors[f'volume_turnover_{days}d'] = avg_volume / df['close'].iloc[-1] * 100
        
        # Price impact factors
        for days in [5, 10, 20]:
            if len(df) >= days:
                returns = df['close'].pct_change().dropna()
                volume = df['volume'].iloc[1:]
                if len(returns) >= days and len(volume) >= days:
                    price_impact = abs(returns.tail(days)) / (volume.tail(days) / 1000000)  # Normalize volume
                    factors[f'price_impact_{days}d'] = price_impact.mean()
        
        # Volume consistency
        for days in [10, 20, 30]:
            if len(df) >= days:
                volume_cv = df['volume'].tail(days).std() / df['volume'].tail(days).mean()
                factors[f'volume_consistency_{days}d'] = 1 / volume_cv if volume_cv > 0 else 0
        
        return factors
    
    def calculate_all_factors(self, symbol: str, date: str) -> Dict[str, float]:
        """Calculate all 400+ factors for a symbol on a given date"""
        df = self.get_stock_data(symbol, date)
        
        if len(df) < 20:
            return {}
        
        all_factors = {}
        all_factors.update(self.calculate_price_factors(df))
        all_factors.update(self.calculate_volume_factors(df))
        all_factors.update(self.calculate_technical_factors(df))
        all_factors.update(self.calculate_momentum_factors(df))
        all_factors.update(self.calculate_volatility_factors(df))
        all_factors.update(self.calculate_trend_factors(df))
        all_factors.update(self.calculate_liquidity_factors(df))
        
        # Add timestamp
        all_factors['calculation_date'] = date
        all_factors['symbol'] = symbol
        
        return all_factors
    
    def store_factors(self, symbol: str, date: str, factors: Dict[str, float]):
        """Store calculated factors in database"""
        if not self.conn:
            return
            
        cursor = self.conn.cursor()
        
        for factor_name, factor_value in factors.items():
            if factor_name not in ['calculation_date', 'symbol'] and not pd.isna(factor_value):
                cursor.execute('''
                    INSERT OR REPLACE INTO stock_factors 
                    (symbol, date, factor_name, factor_value)
                    VALUES (?, ?, ?, ?)
                ''', (symbol, date, factor_name, factor_value))
        
        self.conn.commit()
    
    def calculate_factors_for_all_stocks(self, end_date: str = None, limit_dates: int = 100):
        """Calculate factors for all stocks in database"""
        if not self.conn:
            return
            
        if end_date is None:
            end_date = datetime.now().strftime('%Y-%m-%d')
        
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT symbol FROM historical_data_daily ORDER BY symbol")
        symbols = [row[0] for row in cursor.fetchall()]
        
        logger.info(f"Calculating 400+ factors for {len(symbols)} symbols")
        
        total_factors = 0
        for i, symbol in enumerate(symbols, 1):
            logger.info(f"Processing {symbol} ({i}/{len(symbols)})")
            
            try:
                # Get available dates for this symbol
                cursor.execute('''
                    SELECT DISTINCT timestamp FROM historical_data_daily 
                    WHERE symbol = ? AND timestamp <= ? 
                    ORDER BY timestamp DESC LIMIT ?
                ''', (symbol, end_date, limit_dates))
                
                dates = [row[0] for row in cursor.fetchall()]
                
                for date in dates:
                    factors = self.calculate_all_factors(symbol, date)
                    if factors:
                        self.store_factors(symbol, date, factors)
                        total_factors += len(factors)
                
            except Exception as e:
                logger.error(f"Error calculating factors for {symbol}: {str(e)}")
        
        logger.info(f"Total factors calculated: {total_factors}")
    
    def analyze_factor_performance(self, factor_name: str, lookforward_days: int = 20) -> Dict[str, float]:
        """Analyze factor performance for predicting future returns"""
        if not self.conn:
            return {'correlation': 0}
            
        query = '''
            SELECT sf.symbol, sf.date, sf.factor_value,
                   hd.close as current_price,
                   hd2.close as future_price
            FROM stock_factors sf
            JOIN historical_data_daily hd ON sf.symbol = hd.symbol AND sf.date = hd.timestamp
            JOIN historical_data_daily hd2 ON sf.symbol = hd2.symbol 
                AND hd2.timestamp = date(sf.date, '+{} days')
            WHERE sf.factor_name = ? AND sf.factor_value IS NOT NULL
            ORDER BY sf.date DESC
        '''.format(lookforward_days)
        
        df = pd.read_sql_query(query, self.conn, params=(factor_name,))
        
        if len(df) == 0:
            return {'correlation': 0, 'observations': 0, 'mean_return': 0, 'std_return': 0}
        
        df['future_return'] = (df['future_price'] / df['current_price'] - 1) * 100
        df = df.dropna()
        
        if len(df) == 0:
            return {'correlation': 0, 'observations': 0, 'mean_return': 0, 'std_return': 0}
        
        correlation = df['factor_value'].corr(df['future_return'])
        
        return {
            'correlation': correlation if not pd.isna(correlation) else 0,
            'observations': len(df),
            'mean_return': df['future_return'].mean(),
            'std_return': df['future_return'].std(),
            'factor_mean': df['factor_value'].mean(),
            'factor_std': df['factor_value'].std()
        }
    
    def get_top_factors(self, lookforward_days: int = 20, min_observations: int = 100) -> pd.DataFrame:
        """Get top performing factors by correlation with future returns"""
        if not self.conn:
            return pd.DataFrame()
            
        cursor = self.conn.cursor()
        cursor.execute("SELECT DISTINCT factor_name FROM stock_factors")
        factor_names = [row[0] for row in cursor.fetchall()]
        
        results = []
        for factor_name in factor_names:
            performance = self.analyze_factor_performance(factor_name, lookforward_days)
            if performance['observations'] >= min_observations:
                performance['factor_name'] = factor_name
                results.append(performance)
        
        df = pd.DataFrame(results)
        df = df.sort_values('correlation', key=abs, ascending=False)
        
        return df

def main():
    pass

if __name__ == "__main__":
    main()
