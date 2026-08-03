#!/usr/bin/env python3
"""
Portfolio Optimizer Module

This module provides functionality to optimize position allocation based on:
1. Correlation between assets
2. Market regime
3. Historical performance metrics

Classes:
    PortfolioOptimizer: Main class for position sizing and allocation

Usage:
    optimizer = PortfolioOptimizer()
    optimized_picks = optimizer.optimize_allocation(picks, current_regime)
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os
import json

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import PyPortfolioOpt if available
try:
    from pypfopt import efficient_frontier, risk_models, expected_returns
    PYPFOPT_AVAILABLE = True
except ImportError:
    PYPFOPT_AVAILABLE = False
    logger.warning("PyPortfolioOpt not available. Using simplified optimization methods.")

class PortfolioOptimizer:
    """
    Optimizes portfolio allocation based on correlation and market regime analysis.
    """
    
    def __init__(self, db_path='historical_data.db', lookback_days=90):
        """
        Initialize the optimizer with database connection and settings.
        
        Args:
            db_path (str): Path to the SQLite database containing historical data
            lookback_days (int): Number of days to look back for correlation calculation
        """
        self.db_path = db_path
        self.lookback_days = lookback_days
        
        # Define regime-based allocation multipliers
        self.regime_multipliers = {
            "BULL_TREND": 1.2,      # More aggressive in bull markets
            "BEAR_TREND": 0.8,      # Conservative in bear markets
            "HIGH_VOLATILITY": 0.7,  # Very conservative in volatile markets
            "RANGE_BOUND": 1.0,      # Normal in range-bound markets
            "UNKNOWN": 0.9          # Slightly conservative when regime is unknown
        }
        
        # Default risk parameters
        self.default_position_size = 0.02  # 2% per position default
        self.max_position_size = 0.05     # 5% maximum per position
        self.min_position_size = 0.005    # 0.5% minimum per position
        
    def get_correlation_matrix(self, symbols, days=None):
        """
        Calculate correlation matrix between the given symbols.
        
        Args:
            symbols (list): List of stock symbols
            days (int): Number of days to look back (uses self.lookback_days if None)
            
        Returns:
            pd.DataFrame: Correlation matrix or None if insufficient data
        """
        if not symbols:
            return None
            
        if days is None:
            days = self.lookback_days
            
        try:
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=days)
            
            # Connect to database
            conn = sqlite3.connect(self.db_path)
            
            # Prepare data container
            price_data = {}
            
            # Fetch data for each symbol
            for symbol in symbols:
                # Add .JK suffix if not present for Indonesian stocks
                query_symbol = symbol if symbol.endswith('.JK') else f"{symbol}.JK"
                
                query = """
                SELECT timestamp, close
                FROM historical_data_daily
                WHERE symbol = ? 
                AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """
                
                df = pd.read_sql_query(
                    query, 
                    conn, 
                    params=(query_symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                )
                
                if len(df) < 20:  # Require at least 20 data points
                    logger.warning(f"Insufficient data for {symbol}: {len(df)} rows")
                    # Try alternative symbol format if the current one didn't work
                    if query_symbol.endswith('.JK'):
                        query_symbol = query_symbol[:-3]
                    else:
                        query_symbol = f"{query_symbol}.JK"
                    
                    df = pd.read_sql_query(
                        query, 
                        conn, 
                        params=(query_symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                    )
                    
                    if len(df) < 20:
                        logger.warning(f"Still insufficient data for {symbol} after retry")
                        continue
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                df.dropna(inplace=True)
                
                # Store close prices with the original symbol name for consistency
                price_data[symbol] = df['close']
            
            conn.close()
            
            # Check if we have enough data
            if len(price_data) < 2:
                logger.warning("Insufficient symbols with data for correlation calculation")
                return None
                
            # Create a DataFrame with all close prices
            price_df = pd.DataFrame(price_data)
            
            # Calculate daily returns
            returns_df = price_df.pct_change().dropna()
            
            # Calculate correlation matrix
            correlation_matrix = returns_df.corr()
            
            logger.info(f"Calculated correlation matrix for {len(correlation_matrix)} symbols")
            return correlation_matrix
            
        except Exception as e:
            logger.error(f"Error calculating correlation matrix: {e}")
            return None
    
    def get_diversification_scores(self, correlation_matrix):
        """
        Calculate diversification scores based on correlation matrix.
        Lower correlation = higher diversification score.
        
        Args:
            correlation_matrix (pd.DataFrame): Correlation matrix
            
        Returns:
            dict: Dictionary of symbols with their diversification scores
        """
        if correlation_matrix is None or correlation_matrix.empty:
            return {}
            
        symbols = correlation_matrix.columns
        diversification_scores = {}
        
        for symbol in symbols:
            # Get correlations with other symbols
            correlations = [
                correlation_matrix.loc[symbol, other] 
                for other in symbols if other != symbol
            ]
            
            # Average correlation (excluding self-correlation which is 1.0)
            avg_correlation = sum(correlations) / len(correlations) if correlations else 0
            
            # Calculate diversification score (1 - avg_correlation)
            # Higher score = better diversification
            diversification_scores[symbol] = 1 - avg_correlation
        
        return diversification_scores
    
    def optimize_allocation(self, picks, market_regime="UNKNOWN"):
        """
        Optimize portfolio allocation using correlation-based diversification.
        
        Args:
            picks (dict): Dictionary of picks by category
            market_regime (str): Current market regime
            
        Returns:
            dict: Optimized picks with allocation percentages
        """
        if not picks:
            return picks
            
        # Extract symbols
        symbols = [pick['symbol'] for pick in picks.values()]
        if len(symbols) <= 1:
            # For single symbol, assign default allocation adjusted by regime
            regime_mult = self.regime_multipliers.get(market_regime, 1.0)
            for category, pick in picks.items():
                pick['allocation'] = self.default_position_size * regime_mult
                pick['allocation_pct'] = pick['allocation'] * 100  # For readability
            return picks
        
        # Calculate correlation matrix
        correlation_matrix = self.get_correlation_matrix(symbols)
        
        # If correlation calculation failed, use a simplified allocation method
        if correlation_matrix is None:
            logger.warning("Using simplified allocation due to correlation calculation failure")
            regime_mult = self.regime_multipliers.get(market_regime, 1.0)
            equal_weight = min(self.default_position_size * regime_mult, self.max_position_size)
            
            for category, pick in picks.items():
                pick['allocation'] = equal_weight
                pick['allocation_pct'] = equal_weight * 100  # For readability
            
            return picks
            
        # Get diversification scores based on correlation
        diversification_scores = self.get_diversification_scores(correlation_matrix)
        
        if not diversification_scores:
            logger.warning("No diversification scores available, using equal weights")
            regime_mult = self.regime_multipliers.get(market_regime, 1.0)
            equal_weight = min(self.default_position_size * regime_mult, self.max_position_size)
            
            for category, pick in picks.items():
                pick['allocation'] = equal_weight
                pick['allocation_pct'] = equal_weight * 100
            
            return picks
        
        # Calculate total diversification score for normalization
        total_div_score = sum(diversification_scores.values())
        
        # Get regime multiplier
        regime_mult = self.regime_multipliers.get(market_regime, 1.0)
        
        # Apply allocation adjustments to each pick
        for category, pick in picks.items():
            symbol = pick['symbol']
            
            if symbol in diversification_scores:
                # Normalize diversification score
                normalized_score = diversification_scores[symbol] / total_div_score
                
                # Calculate allocation based on diversification and regime
                allocation = self.default_position_size * normalized_score * regime_mult
                
                # Ensure allocation is within bounds
                allocation = max(min(allocation, self.max_position_size), self.min_position_size)
                
                # Store allocation in the pick
                pick['allocation'] = allocation
                pick['allocation_pct'] = allocation * 100  # For readability
                pick['diversification_score'] = diversification_scores[symbol]
            else:
                # Fallback for symbols missing from diversification scores
                pick['allocation'] = self.default_position_size * regime_mult
                pick['allocation_pct'] = pick['allocation'] * 100
        
        logger.info(f"Optimized allocations for {len(picks)} picks based on correlation and {market_regime} regime")
        return picks
    
    def optimize_allocation_advanced(self, picks, market_regime="UNKNOWN"):
        """
        Advanced portfolio optimization using PyPortfolioOpt's efficient frontier.
        Only used if PyPortfolioOpt is available.
        
        Args:
            picks (dict): Dictionary of picks by category
            market_regime (str): Current market regime
            
        Returns:
            dict: Optimized picks with allocation percentages
        """
        if not PYPFOPT_AVAILABLE or not picks:
            # Fall back to simple optimization if PyPortfolioOpt is not available
            return self.optimize_allocation(picks, market_regime)
            
        # Extract symbols
        symbols = [pick['symbol'] for pick in picks.values()]
        if len(symbols) <= 1:
            # For single symbol, assign default allocation adjusted by regime
            regime_mult = self.regime_multipliers.get(market_regime, 1.0)
            for category, pick in picks.items():
                pick['allocation'] = self.default_position_size * regime_mult
                pick['allocation_pct'] = pick['allocation'] * 100
            return picks
        
        try:
            # Connect to database
            conn = sqlite3.connect(self.db_path)
            
            # Calculate date range
            end_date = datetime.now()
            start_date = end_date - timedelta(days=self.lookback_days)
            
            # Get historical price data for all symbols
            price_data = {}
            for symbol in symbols:
                # Add .JK suffix if not present for Indonesian stocks
                query_symbol = symbol if symbol.endswith('.JK') else f"{symbol}.JK"
                
                query = """
                SELECT timestamp, close
                FROM historical_data_daily
                WHERE symbol = ? 
                AND timestamp BETWEEN ? AND ?
                ORDER BY timestamp ASC
                """
                
                df = pd.read_sql_query(
                    query, 
                    conn, 
                    params=(query_symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                )
                
                if len(df) < 20:  # Try alternative symbol format
                    if query_symbol.endswith('.JK'):
                        query_symbol = query_symbol[:-3]
                    else:
                        query_symbol = f"{query_symbol}.JK"
                    
                    df = pd.read_sql_query(
                        query, 
                        conn, 
                        params=(query_symbol, start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d'))
                    )
                
                df['timestamp'] = pd.to_datetime(df['timestamp'])
                df.set_index('timestamp', inplace=True)
                df['close'] = pd.to_numeric(df['close'], errors='coerce')
                price_data[symbol] = df['close'].dropna()
            
            conn.close()
            
            # Create price DataFrame
            price_df = pd.DataFrame(price_data)
            
            if price_df.empty or len(price_df.columns) < 2:
                logger.warning("Insufficient price data for advanced optimization")
                return self.optimize_allocation(picks, market_regime)
            
            # Calculate expected returns and sample covariance
            mu = expected_returns.mean_historical_return(price_df)
            S = risk_models.sample_cov(price_df)
            
            # Adjust risk aversion based on market regime
            risk_aversion = {
                "BULL_TREND": 0.01,
                "RANGE_BOUND": 0.02,
                "BEAR_TREND": 0.03,
                "HIGH_VOLATILITY": 0.05,
                "UNKNOWN": 0.025
            }.get(market_regime, 0.025)
            
            # Optimize portfolio with efficient frontier
            ef = efficient_frontier.EfficientFrontier(mu, S)
            weights = ef.max_sharpe()
            
            # Clean weights (removes tiny allocations)
            cleaned_weights = ef.clean_weights()
            
            # Apply weights to picks
            total_weight = sum(cleaned_weights.values())
            regime_mult = self.regime_multipliers.get(market_regime, 1.0)
            
            for category, pick in picks.items():
                symbol = pick['symbol']
                
                if symbol in cleaned_weights:
                    # Normalize weight and apply regime multiplier
                    normalized_weight = cleaned_weights[symbol] / total_weight if total_weight > 0 else 0
                    allocation = normalized_weight * regime_mult
                    
                    # Ensure allocation is within bounds
                    allocation = max(min(allocation, self.max_position_size), self.min_position_size)
                    
                    # Store allocation in the pick
                    pick['allocation'] = allocation
                    pick['allocation_pct'] = allocation * 100
                else:
                    # Fallback for symbols missing from optimization
                    pick['allocation'] = self.min_position_size
                    pick['allocation_pct'] = self.min_position_size * 100
            
            logger.info(f"Completed advanced optimization for {len(picks)} picks in {market_regime} regime")
            return picks
            
        except Exception as e:
            logger.error(f"Error in advanced optimization, falling back to simple method: {e}")
            return self.optimize_allocation(picks, market_regime)

# Example usage
if __name__ == "__main__":
    optimizer = PortfolioOptimizer()
    
    # Example picks
    example_picks = {
        "win_rate": {
            "symbol": "BBCA",
            "current_close": 9000,
            "target_price": 9500,
            "stop_loss": 8800
        },
        "reward/risk": {
            "symbol": "TLKM",
            "current_close": 4000,
            "target_price": 4300,
            "stop_loss": 3900
        }
    }
    
    optimized = optimizer.optimize_allocation(example_picks, "BULL_TREND")
    print("Optimized allocations:")
    for category, pick in optimized.items():
        print(f"{category} - {pick['symbol']}: {pick['allocation_pct']:.2f}%")