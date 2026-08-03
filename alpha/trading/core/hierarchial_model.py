#!/usr/bin/env python3
# Filename: src/core/hierarchical_strategy.py
"""
Hierarchical Strategy Selection Module

This module provides a framework for selecting trading strategies with:
1. Nested statistical model comparison (AIC, BIC, etc.)
2. Regime-specific strategy selection
3. Feature engineering through systematic indicator combinations
4. Statistical significance testing with multiple hypothesis correction

This hierarchical approach ensures that strategies are selected based on 
objective statistical criteria rather than curve-fitting or intuition.
"""

import sqlite3
import pandas as pd
import numpy as np
import logging
from datetime import datetime, timedelta
import os
import json
import itertools
from tqdm import tqdm
import math

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import statsmodels for statistical modeling
try:
    import statsmodels.api as sm
    from statsmodels.stats.multitest import multipletests
    STATSMODELS_AVAILABLE = True
    logger.info("statsmodels available for advanced statistical modeling")
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available. Using simplified statistical methods.")

# Try to import scikit-learn for machine learning capabilities
try:
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.preprocessing import StandardScaler
    from sklearn.ensemble import RandomForestRegressor
    from sklearn.feature_selection import mutual_info_regression
    SKLEARN_AVAILABLE = True
    logger.info("scikit-learn available for machine learning capabilities")
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Some advanced features will be disabled.")

class HierarchicalStrategySelector:
    """
    Selects optimal trading strategies using hierarchical statistical modeling.
    """
    
    def __init__(self, hist_db='db/historical_data.db', 
                 benchmark_db='db/benchmark_result_final.db',
                 lookback_days=252):  # Default 1 year of data
        """
        Initialize the hierarchical strategy selector.
        
        Args:
            hist_db (str): Path to historical data database
            benchmark_db (str): Path to benchmark results database
            lookback_days (int): Number of days to look back for model training
        """
        self.hist_db = hist_db
        self.benchmark_db = benchmark_db
        self.lookback_days = lookback_days
        
        # Indicator pools for strategy generation
        self.base_indicators = ['sma', 'ema', 'macd', 'rsi', 'adx', 'cci', 'vwap', 'atr']
        self.extended_indicators = self.base_indicators + ['obv', 'roc', 'willr', 'aroon_up', 'aroon_down', 'cmo', 'mfi']
        
        # Statistical thresholds
        self.significance_threshold = 0.05
        self.aic_diff_threshold = 2.0  # AIC difference considered significant
        self.min_trades = 20          # Minimum trades for reliable statistics
        
        # Tracking of strategies by regime
        self.regime_strategies = {}
        
        # Function to calculate technical indicators (placeholder)
        try:
            from src.indicators.standard import calculate_technical_indicators
            self.calculate_indicators = calculate_technical_indicators
        except ImportError:
            logger.error("Failed to import calculate_technical_indicators")
            self.calculate_indicators = None
    
    def hierarchical_strategy_selection(self, market_regime, symbols=None, max_indicators=3):
        """
        Build strategy hierarchy based on nested statistical evidence for a given market regime.
        
        Args:
            market_regime (str): Current market regime
            symbols (list): List of symbols to analyze (if None, all available)
            max_indicators (int): Maximum number of indicators in combination
            
        Returns:
            dict: Dictionary of selected strategies with statistical metrics
        """
        logger.info(f"Starting hierarchical strategy selection for {market_regime} regime")
        
        # Get historical data for specified market regime periods
        regime_data = self.get_regime_historical_data(market_regime, symbols)
        
        if not regime_data:
            logger.warning(f"No historical data available for {market_regime} regime")
            return {}
        
        # Results container
        strategy_models = {}
        
        # First level: Test individual indicators
        level1_indicators = self.select_level1_indicators(regime_data)
        logger.info(f"Level 1 selected indicators: {level1_indicators}")
        
        if not level1_indicators:
            logger.warning("No significant level 1 indicators found")
            return {}
        
        # Second level: Combinations of top performing indicators
        level2_combinations = self.generate_indicator_combinations(level1_indicators, max_size=2)
        level2_models = self.evaluate_indicator_combinations(regime_data, level2_combinations)
        
        # Filter to combinations that outperform individual indicators
        level2_selected = self.select_superior_models(level2_models, [m for indicator, m in level1_indicators.items()])
        logger.info(f"Level 2 selected combinations: {list(level2_selected.keys())}")
        
        # Third level: Further combinations if beneficial
        if max_indicators > 2 and len(level2_selected) > 0:
            level3_combinations = self.generate_indicator_combinations(level1_indicators, max_size=3)
            level3_models = self.evaluate_indicator_combinations(regime_data, level3_combinations)
            
            # Filter to combinations that outperform level 2
            level3_selected = self.select_superior_models(level3_models, list(level2_selected.values()))
            logger.info(f"Level 3 selected combinations: {list(level3_selected.keys())}")
            
            # Combine all selected models
            strategy_models = {**level1_indicators, **level2_selected, **level3_selected}
        else:
            # Combine level 1 and 2 models
            strategy_models = {**level1_indicators, **level2_selected}
        
        # Apply multiple hypothesis testing correction
        strategy_models = self.apply_multiple_testing_correction(strategy_models)
        
        # Store in regime strategies dictionary
        self.regime_strategies[market_regime] = strategy_models
        
        return strategy_models
    
    def get_regime_historical_data(self, market_regime, symbols=None, min_periods=30):
        """
        Get historical data periods that match the specified market regime.
        
        Args:
            market_regime (str): Target market regime
            symbols (list): List of symbols to analyze
            min_periods (int): Minimum number of periods required
            
        Returns:
            dict: Dictionary of DataFrames with historical data
        """
        # Import market regime detector if available
        try:
            from src.core.market_regime import EnhancedMarketRegimeDetector
            regime_detector = EnhancedMarketRegimeDetector(self.hist_db)
        except ImportError:
            try:
                from src.core.market_regime import MarketRegimeDetector
                regime_detector = MarketRegimeDetector(self.hist_db)
            except ImportError:
                logger.error("No market regime detector available")
                return {}
        
        # Get all symbols if none specified
        if symbols is None:
            symbols = self.get_all_symbols()
            
        if not symbols:
            logger.warning("No symbols available for analysis")
            return {}
        
        # Sample only a subset of symbols if too many
        if len(symbols) > 20:
            np.random.seed(42)  # For reproducibility
            symbols = np.random.choice(symbols, 20, replace=False).tolist()
            logger.info(f"Sampling 20 symbols for regime data analysis: {symbols}")
        
        # Historical end date (slightly in the past to ensure data availability)
        end_date = datetime.now() - timedelta(days=5)
        start_date = end_date - timedelta(days=self.lookback_days * 2)  # Look back further to find enough samples
        
        # Container for regime-specific data
        regime_data = {}
        
        for symbol in tqdm(symbols, desc=f"Finding {market_regime} periods"):
            try:
                # Get historical data for this symbol
                data = self.get_historical_data(symbol, start_date, end_date)
                if data is None or len(data) < 60:  # Need enough data for regime detection
                    continue
                
                # Split into windows for regime analysis
                window_size = 20  # 20 trading days (approximately 1 month)
                step_size = 10    # 50% overlap between windows
                
                for i in range(0, len(data) - window_size, step_size):
                    window_data = data.iloc[i:i+window_size].copy()
                    
                    # Detect regime for this window
                    window_regime, _ = regime_detector.detect_regime_information_theory(window_data)
                    
                    # If window matches target regime, include it
                    if window_regime == market_regime:
                        window_key = f"{symbol}_{i}"
                        regime_data[window_key] = window_data
            except Exception as e:
                logger.warning(f"Error analyzing {symbol} for {market_regime} regime: {e}")
                continue
        
        logger.info(f"Found {len(regime_data)} {market_regime} regime periods across {len(symbols)} symbols")
        
        # Ensure we have enough data
        if len(regime_data) < min_periods:
            logger.warning(f"Insufficient {market_regime} regime data: only {len(regime_data)} periods found")
            return {}
            
        return regime_data
    
    def select_level1_indicators(self, regime_data):
        """
        Select individual indicators that show statistical significance.
        
        Args:
            regime_data (dict): Dictionary of regime-specific historical data
            
        Returns:
            dict: Dictionary of selected indicators with their models
        """
        logger.info("Evaluating individual indicators (Level 1)")
        
        indicator_models = {}
        
        # Process each data period
        for period_key, data in tqdm(regime_data.items(), desc="Evaluating indicators"):
            try:
                # Calculate indicators
                if self.calculate_indicators:
                    indicators = self.calculate_indicators(data)
                else:
                    continue
                
                # Calculate forward returns (target variable)
                forward_returns = self.calculate_forward_returns(data, days=5)  # 5-day returns
                if forward_returns is None or len(forward_returns) < 10:
                    continue
                
                # Evaluate each indicator
                for indicator in self.base_indicators:
                    if indicator not in indicators:
                        continue
                    
                    # Get indicator values
                    ind_values = indicators[indicator]
                    if isinstance(ind_values, pd.Series):
                        ind_values = ind_values.dropna()
                    
                    if len(ind_values) < 10:
                        continue
                    
                    # Align data
                    aligned_data = pd.DataFrame({
                        'indicator': ind_values,
                        'returns': forward_returns
                    }).dropna()
                    
                    if len(aligned_data) < 10:
                        continue
                    
                    # Build statistical model
                    if STATSMODELS_AVAILABLE:
                        X = sm.add_constant(aligned_data['indicator'])
                        y = aligned_data['returns']
                        
                        model = sm.OLS(y, X).fit()
                        
                        # Calculate key metrics
                        params = model.params.tolist()
                        pvalues = model.pvalues.tolist()[1]  # p-value for indicator (not constant)
                        rsquared = model.rsquared
                        aic = model.aic
                        
                        # Store if significant
                        if pvalues < self.significance_threshold:
                            if indicator not in indicator_models:
                                indicator_models[indicator] = []
                                
                            indicator_models[indicator].append({
                                'period': period_key,
                                'params': params,
                                'pvalue': pvalues,
                                'rsquared': rsquared,
                                'aic': aic,
                                'data_points': len(aligned_data)
                            })
                    else:
                        # Simplified model if statsmodels not available
                        X = aligned_data['indicator'].values
                        y = aligned_data['returns'].values
                        
                        # Calculate correlation and p-value
                        corr, pvalue = self.calculate_correlation_stats(X, y)
                        
                        # Store if significant
                        if pvalue < self.significance_threshold:
                            if indicator not in indicator_models:
                                indicator_models[indicator] = []
                                
                            indicator_models[indicator].append({
                                'period': period_key,
                                'params': [0, corr],  # Using correlation as coefficient
                                'pvalue': pvalue,
                                'rsquared': corr**2,
                                'data_points': len(aligned_data)
                            })
            except Exception as e:
                logger.warning(f"Error evaluating indicators for {period_key}: {e}")
                continue
        
        # Aggregate results across periods
        selected_indicators = {}
        
        for indicator, models in indicator_models.items():
            if len(models) < 3:  # Need at least 3 periods where indicator was significant
                continue
            
            # Calculate average metrics
            avg_pvalue = np.mean([m['pvalue'] for m in models])
            avg_rsquared = np.mean([m.get('rsquared', 0) for m in models])
            avg_coefficient = np.mean([m['params'][1] for m in models if len(m['params']) > 1])
            
            # Consistency check (coefficient should have consistent sign)
            coefficients = [m['params'][1] for m in models if len(m['params']) > 1]
            sign_consistency = np.mean([1 if c > 0 else -1 for c in coefficients])
            sign_consistency = abs(sign_consistency)  # 1 = perfect consistency, 0 = no consistency
            
            logger.debug(f"Indicator {indicator}: p={avg_pvalue:.4f}, r²={avg_rsquared:.4f}, coef={avg_coefficient:.4f}, consistency={sign_consistency:.2f}")
            
            # Select if significant and reasonably consistent
            if avg_pvalue < self.significance_threshold and sign_consistency > 0.6:
                selected_indicators[indicator] = {
                    'indicator': indicator,
                    'coef': avg_coefficient,
                    'pvalue': avg_pvalue,
                    'rsquared': avg_rsquared,
                    'consistency': sign_consistency,
                    'periods': len(models)
                }
                
        return selected_indicators
    
    def generate_indicator_combinations(self, base_indicators, max_size=2):
        """
        Generate combinations of indicators for testing.
        
        Args:
            base_indicators (dict): Dictionary of base indicators to combine
            max_size (int): Maximum combination size
            
        Returns:
            list: List of indicator combinations
        """
        indicators = list(base_indicators.keys())
        combinations = []
        
        for size in range(2, min(len(indicators) + 1, max_size + 1)):
            for combo in itertools.combinations(indicators, size):
                combinations.append(list(combo))
        
        return combinations
    
    def evaluate_indicator_combinations(self, regime_data, combinations):
        """
        Evaluate combinations of indicators on regime-specific data.
        
        Args:
            regime_data (dict): Dictionary of regime-specific historical data
            combinations (list): List of indicator combinations to evaluate
            
        Returns:
            dict: Dictionary of combination models with statistics
        """
        logger.info(f"Evaluating {len(combinations)} indicator combinations")
        
        combination_models = {}
        
        # Process each data period
        for period_key, data in tqdm(regime_data.items(), desc="Evaluating combinations"):
            try:
                # Calculate indicators
                if self.calculate_indicators:
                    indicators = self.calculate_indicators(data)
                else:
                    continue
                
                # Calculate forward returns (target variable)
                forward_returns = self.calculate_forward_returns(data, days=5)  # 5-day returns
                if forward_returns is None or len(forward_returns) < 10:
                    continue
                
                # Evaluate each combination
                for combo in combinations:
                    combo_key = ','.join(sorted(combo))
                    
                    # Check if all indicators in the combo are available
                    if not all(ind in indicators for ind in combo):
                        continue
                    
                    # Prepare aligned data
                    combo_data = pd.DataFrame({'returns': forward_returns})
                    
                    for ind in combo:
                        ind_values = indicators[ind]
                        if isinstance(ind_values, pd.Series):
                            combo_data[ind] = ind_values
                    
                    combo_data.dropna(inplace=True)
                    
                    if len(combo_data) < 10:
                        continue
                    
                    # Build statistical model
                    if STATSMODELS_AVAILABLE:
                        X = sm.add_constant(combo_data[combo])
                        y = combo_data['returns']
                        
                        try:
                            model = sm.OLS(y, X).fit()
                            
                            # Calculate key metrics
                            params = model.params.tolist()
                            pvalues = model.pvalues.tolist()[1:]  # p-values for indicators (not constant)
                            rsquared = model.rsquared
                            aic = model.aic
                            
                            # Store if at least one indicator is significant
                            if any(p < self.significance_threshold for p in pvalues):
                                if combo_key not in combination_models:
                                    combination_models[combo_key] = []
                                    
                                combination_models[combo_key].append({
                                    'period': period_key,
                                    'indicators': combo,
                                    'params': params,
                                    'pvalues': pvalues,
                                    'rsquared': rsquared,
                                    'aic': aic,
                                    'data_points': len(combo_data)
                                })
                        except Exception as e:
                            logger.debug(f"Error fitting model for combo {combo_key}: {e}")
                            continue
                    else:
                        # Simplified model using correlation if statsmodels not available
                        X = combo_data[combo].values
                        y = combo_data['returns'].values
                        
                        # Use simple correlation for each indicator
                        correlations = []
                        pvalues = []
                        
                        for i, ind in enumerate(combo):
                            corr, pvalue = self.calculate_correlation_stats(X[:, i], y)
                            correlations.append(corr)
                            pvalues.append(pvalue)
                        
                        # Store if at least one indicator is significant
                        if any(p < self.significance_threshold for p in pvalues):
                            if combo_key not in combination_models:
                                combination_models[combo_key] = []
                                
                            combination_models[combo_key].append({
                                'period': period_key,
                                'indicators': combo,
                                'params': [0] + correlations,  # Using correlations as coefficients
                                'pvalues': pvalues,
                                'rsquared': np.mean([c**2 for c in correlations]),
                                'data_points': len(combo_data)
                            })
            except Exception as e:
                logger.warning(f"Error evaluating combinations for {period_key}: {e}")
                continue
        
        # Aggregate results across periods
        selected_combinations = {}
        
        for combo_key, models in combination_models.items():
            if len(models) < 3:  # Need at least 3 periods where combination was significant
                continue
            
            # Calculate average metrics
            avg_pvalues = np.mean([np.mean(m['pvalues']) for m in models], axis=0)
            avg_rsquared = np.mean([m.get('rsquared', 0) for m in models])
            
            if 'aic' in models[0]:
                avg_aic = np.mean([m['aic'] for m in models if 'aic' in m])
            else:
                avg_aic = None
            
            # Get the indicators for this combo
            indicators = models[0]['indicators']
            
            # Calculate coefficient consistency
            coef_dict = {}
            for ind_idx, ind in enumerate(indicators):
                coefficients = [m['params'][ind_idx + 1] for m in models if len(m['params']) > ind_idx + 1]
                sign_consistency = np.mean([1 if c > 0 else -1 for c in coefficients])
                sign_consistency = abs(sign_consistency)  # 1 = perfect consistency, 0 = no consistency
                
                coef_dict[ind] = {
                    'mean': np.mean(coefficients),
                    'consistency': sign_consistency
                }
            
            # Overall consistency metric
            overall_consistency = np.mean([c['consistency'] for c in coef_dict.values()])
            
            logger.debug(f"Combo {combo_key}: p={avg_pvalues:.4f}, r²={avg_rsquared:.4f}, consistency={overall_consistency:.2f}")
            
            # Select if significant and reasonably consistent
            if avg_pvalues < self.significance_threshold and overall_consistency > 0.6:
                selected_combinations[combo_key] = {
                    'indicators': indicators,
                    'coefficients': coef_dict,
                    'pvalue': avg_pvalues,
                    'rsquared': avg_rsquared,
                    'aic': avg_aic,
                    'consistency': overall_consistency,
                    'periods': len(models)
                }
                
        return selected_combinations
    
    def select_superior_models(self, new_models, baseline_models, aic_diff_threshold=None):
        """
        Select models that significantly outperform baseline models.
        
        Args:
            new_models (dict): Dictionary of candidate models
            baseline_models (list): List of baseline models for comparison
            aic_diff_threshold (float): AIC difference threshold (default to self.aic_diff_threshold)
            
        Returns:
            dict: Dictionary of superior models
        """
        if aic_diff_threshold is None:
            aic_diff_threshold = self.aic_diff_threshold
            
        # Extract baseline metrics
        baseline_rsquared = np.mean([m.get('rsquared', 0) for m in baseline_models])
        
        if any('aic' in m for m in baseline_models):
            baseline_aic = np.mean([m.get('aic', float('inf')) for m in baseline_models if 'aic' in m])
        else:
            baseline_aic = None
        
        # Select superior models
        superior_models = {}
        
        for key, model in new_models.items():
            # Better R-squared is required
            rsquared_improvement = model['rsquared'] - baseline_rsquared
            
            # AIC comparison if available
            if baseline_aic is not None and 'aic' in model:
                aic_improvement = baseline_aic - model['aic']  # Lower AIC is better
            else:
                aic_improvement = None
            
            # Selection criteria
            if rsquared_improvement > 0.05:  # 5% improvement in R-squared
                superior_models[key] = model
            elif aic_improvement is not None and aic_improvement > aic_diff_threshold:
                superior_models[key] = model
        
        return superior_models
    
    def apply_multiple_testing_correction(self, models):
        """
        Apply multiple hypothesis testing correction to prevent false discoveries.
        
        Args:
            models (dict): Dictionary of models with p-values
            
        Returns:
            dict: Dictionary with corrected p-values and significance flags
        """
        if not STATSMODELS_AVAILABLE or not models:
            return models
            
        try:
            # Extract p-values and keys
            keys = []
            pvalues = []
            
            for key, model in models.items():
                if 'pvalue' in model:
                    keys.append(key)
                    pvalues.append(model['pvalue'])
            
            if not pvalues:
                return models
                
            # Apply correction
            rejected, corrected_pvalues, _, _ = multipletests(pvalues, method='fdr_bh')
            
            # Update models with corrected values
            corrected_models = models.copy()
            
            for i, key in enumerate(keys):
                corrected_models[key]['corrected_pvalue'] = corrected_pvalues[i]
                corrected_models[key]['significant_corrected'] = rejected[i]
            
            logger.info(f"Applied multiple testing correction to {len(pvalues)} models")
            logger.info(f"Models significant before correction: {sum(p < self.significance_threshold for p in pvalues)}")
            logger.info(f"Models significant after correction: {sum(rejected)}")
            
            return corrected_models
        except Exception as e:
            logger.warning(f"Error applying multiple testing correction: {e}")
            return models
    
    def get_best_strategies(self, market_regime=None, top_n=5):
        """
        Get the best strategies for a given market regime or overall.
        
        Args:
            market_regime (str): Market regime (if None, get best overall)
            top_n (int): Number of top strategies to return
            
        Returns:
            list: List of best strategy dictionaries
        """
        if market_regime and market_regime in self.regime_strategies:
            candidate_strategies = self.regime_strategies[market_regime]
        elif not market_regime:
            # Combine all regime strategies
            candidate_strategies = {}
            for regime, strategies in self.regime_strategies.items():
                for key, strategy in strategies.items():
                    if key not in candidate_strategies:
                        candidate_strategies[key] = strategy.copy()
                        candidate_strategies[key]['regimes'] = [regime]
                    else:
                        candidate_strategies[key]['regimes'].append(regime)
        else:
            logger.warning(f"No strategies found for regime: {market_regime}")
            return []
        
        # Sort by R-squared, then by consistency, then by corrected p-value
        sorted_strategies = sorted(
            candidate_strategies.values(),
            key=lambda x: (
                x.get('significant_corrected', False),
                x.get('rsquared', 0),
                x.get('consistency', 0),
                -x.get('corrected_pvalue', x.get('pvalue', 1))
            ),
            reverse=True
        )
        
        return sorted_strategies[:top_n]
    
    def get_historical_data(self, symbol, start_date, end_date):
        """
        Get historical data for a symbol from the database.
        
        Args:
            symbol (str): Stock symbol
            start_date (datetime): Start date
            end_date (datetime): End date
            
        Returns:
            pd.DataFrame: DataFrame with OHLCV data or None if unavailable
        """
        try:
            # Ensure symbol has .JK suffix for Indonesian stocks
            if not symbol.endswith('.JK'):
                symbol_with_suffix = f"{symbol}.JK"
            else:
                symbol_with_suffix = symbol
            
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
                    symbol_with_suffix, 
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
    
    def calculate_forward_returns(self, data, days=5):
        """
        Calculate forward returns from price data.
        
        Args:
            data (pd.DataFrame): Price data with 'close' column
            days (int): Forward return period in days
            
        Returns:
            pd.Series: Forward returns series or None if unavailable
        """
        if 'close' not in data.columns or len(data) <= days:
            return None
        
        try:
            forward_returns = data['close'].pct_change(days).shift(-days)
            return forward_returns
        except Exception as e:
            logger.error(f"Error calculating forward returns: {e}")
            return None
    
    def calculate_correlation_stats(self, x, y):
        """
        Calculate correlation and p-value between two series.
        
        Args:
            x (array): First series
            y (array): Second series
            
        Returns:
            tuple: (correlation coefficient, p-value)
        """
        if len(x) != len(y) or len(x) < 3:
            return 0, 1.0
            
        try:
            from scipy import stats
            return stats.pearsonr(x, y)
        except ImportError:
            # Simplified calculation if scipy not available
            correlation = np.corrcoef(x, y)[0, 1]
            
            # Simplified p-value calculation
            t_stat = correlation * np.sqrt((len(x) - 2) / (1 - correlation**2))
            p_value = 2 * (1 - self.simplified_t_cdf(abs(t_stat), len(x) - 2))
            
            return correlation, p_value
    
    def simplified_t_cdf(self, t, df):
        """
        Simplified t-distribution CDF for p-value calculation.
        
        Args:
            t (float): t-statistic
            df (int): Degrees of freedom
            
        Returns:
            float: Approximate cumulative probability
        """
        # Simple approximation of t-distribution CDF
        x = df / (df + t * t)
        if df >= 3:
            return 1.0 - 0.5 * x ** (df/2.0)
        else:
            return 0.5
    
    def get_all_symbols(self):
        """
        Get all available symbols from the historical database.
        
        Returns:
            list: List of stock symbols
        """
        try:
            conn = sqlite3.connect(self.hist_db)
            cursor = conn.cursor()
            cursor.execute("SELECT DISTINCT symbol FROM historical_data_daily")
            symbols = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            # Strip .JK suffix if present for consistent handling
            clean_symbols = []
            for symbol in symbols:
                if symbol.endswith('.JK'):
                    clean_symbols.append(symbol[:-3])
                else:
                    clean_symbols.append(symbol)
            
            logger.info(f"Found {len(clean_symbols)} symbols in historical database")
            return clean_symbols
        except Exception as e:
            logger.error(f"Error getting symbols from database: {e}")
            return []
    
    def create_strategy_parameters(self, strategy_key, market_regime="UNKNOWN"):
        """
        Create parameter dictionary for the given strategy to be used in production.
        
        Args:
            strategy_key (str): Strategy key (indicator or comma-separated combo)
            market_regime (str): Current market regime
            
        Returns:
            dict: Dictionary with strategy parameters for trading
        """
        # Get strategy information
        if market_regime in self.regime_strategies and strategy_key in self.regime_strategies[market_regime]:
            strategy = self.regime_strategies[market_regime][strategy_key]
        else:
            logger.warning(f"Strategy {strategy_key} not found for {market_regime} regime")
            return None
        
        # Parse indicators
        if 'indicators' in strategy:
            indicators = strategy['indicators']
        else:
            indicators = [strategy_key]  # Single indicator case
        
        # Get coefficients
        if 'coefficients' in strategy:
            # This is a combination case
            coefficients = {ind: coef_data['mean'] for ind, coef_data in strategy['coefficients'].items()}
        elif 'coef' in strategy:
            # Single indicator case
            coefficients = {strategy_key: strategy['coef']}
        else:
            coefficients = {ind: 1.0 for ind in indicators}  # Default coefficients
        
        # Create parameter dictionary
        params = {
            'indicators': indicators,
            'coefficients': coefficients,
            'lookback': 20,  # Default lookback period
            'threshold': 0.0,  # Default threshold for signal generation
            'regime': market_regime,
            'confidence': strategy.get('consistency', 0.8),
            'rsquared': strategy.get('rsquared', 0),
            'pvalue': strategy.get('pvalue', 1.0),
        }
        
        logger.info(f"Created strategy parameters for {strategy_key} in {market_regime} regime")
        return params
    
    def generate_signal(self, strategy_params, current_data):
        """
        Generate trading signal using the strategy parameters.
        
        Args:
            strategy_params (dict): Strategy parameters
            current_data (pd.DataFrame): Current market data
            
        Returns:
            tuple: (Signal ('buy', 'sell', or 'hold'), confidence)
        """
        if not strategy_params or not current_data or self.calculate_indicators is None:
            return 'hold', 0.0
        
        try:
            # Calculate indicators
            indicators = self.calculate_indicators(current_data)
            
            # Extract latest values
            latest_values = {}
            for ind in strategy_params['indicators']:
                if ind in indicators:
                    ind_value = indicators[ind]
                    if isinstance(ind_value, pd.Series):
                        ind_value = ind_value.dropna()
                        if len(ind_value) > 0:
                            latest_values[ind] = ind_value.iloc[-1]
                    elif ind_value is not None:
                        latest_values[ind] = ind_value
            
            # Check if we have all required indicators
            if len(latest_values) != len(strategy_params['indicators']):
                logger.warning(f"Missing indicators: {set(strategy_params['indicators']) - set(latest_values.keys())}")
                return 'hold', 0.0
            
            # Calculate signal value
            signal_value = 0.0
            for ind, value in latest_values.items():
                coefficient = strategy_params['coefficients'].get(ind, 1.0)
                signal_value += coefficient * value
            
            # Normalize by number of indicators
            signal_value /= len(latest_values)
            
            # Generate signal based on threshold and coefficient signs
            if signal_value > strategy_params['threshold']:
                # Check if positive or negative signal based on coefficient signs
                positive_coeffs = sum(1 for coef in strategy_params['coefficients'].values() if coef > 0)
                negative_coeffs = len(strategy_params['coefficients']) - positive_coeffs
                
                if positive_coeffs >= negative_coeffs:
                    signal = 'buy'
                else:
                    signal = 'sell'
            else:
                signal = 'hold'
            
            # Calculate confidence based on signal strength and strategy confidence
            confidence = abs(signal_value) * strategy_params.get('confidence', 0.8)
            confidence = min(confidence, 0.95)  # Cap at 95%
            
            logger.info(f"Generated {signal} signal with {confidence:.2f} confidence")
            return signal, confidence
            
        except Exception as e:
            logger.error(f"Error generating signal: {e}")
            return 'hold', 0.0
    
    def serialize_regime_strategies(self, file_path="data/regime_strategies.json"):
        """
        Serialize regime strategies to JSON for persistence.
        
        Args:
            file_path (str): Path to save the JSON file
            
        Returns:
            bool: Success flag
        """
        try:
            # Create output directory if it doesn't exist
            os.makedirs(os.path.dirname(file_path), exist_ok=True)
            
            # Convert numpy types and other non-serializable types
            def convert_for_json(obj):
                if isinstance(obj, (np.int64, np.int32, np.int16, np.int8)):
                    return int(obj)
                elif isinstance(obj, (np.float64, np.float32, np.float16)):
                    return float(obj)
                elif isinstance(obj, np.ndarray):
                    return obj.tolist()
                elif isinstance(obj, dict):
                    return {k: convert_for_json(v) for k, v in obj.items()}
                elif isinstance(obj, list):
                    return [convert_for_json(i) for i in obj]
                return obj
            
            # Convert strategies for serialization
            serializable_strategies = {
                regime: {
                    key: convert_for_json(strategy)
                    for key, strategy in strategies.items()
                }
                for regime, strategies in self.regime_strategies.items()
            }
            
            # Add metadata
            output_data = {
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                "strategy_count": sum(len(strategies) for strategies in self.regime_strategies.values()),
                "regime_strategies": serializable_strategies
            }
            
            # Write to file
            with open(file_path, 'w') as f:
                json.dump(output_data, f, indent=2)
                
            logger.info(f"Serialized {output_data['strategy_count']} regime strategies to {file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Error serializing regime strategies: {e}")
            return False
    
    def deserialize_regime_strategies(self, file_path="data/regime_strategies.json"):
        """
        Deserialize regime strategies from JSON.
        
        Args:
            file_path (str): Path to the JSON file
            
        Returns:
            bool: Success flag
        """
        try:
            if not os.path.exists(file_path):
                logger.warning(f"Strategies file not found: {file_path}")
                return False
                
            with open(file_path, 'r') as f:
                data = json.load(f)
                
            if 'regime_strategies' in data:
                self.regime_strategies = data['regime_strategies']
                logger.info(f"Loaded {data.get('strategy_count', 0)} regime strategies from {file_path}")
                return True
            else:
                logger.warning(f"Invalid regime strategies format in {file_path}")
                return False
                
        except Exception as e:
            logger.error(f"Error deserializing regime strategies: {e}")
            return False

# Example usage
if __name__ == "__main__":
    selector = HierarchicalStrategySelector()
    
    # Select strategies for each market regime
    regimes = ["BULL_TREND", "BEAR_TREND", "RANGE_BOUND", "HIGH_VOLATILITY"]
    
    for regime in regimes:
        print(f"\nSelecting strategies for {regime} regime...")
        strategies = selector.hierarchical_strategy_selection(regime)
        
        print(f"Selected {len(strategies)} strategies:")
        for key, strategy in strategies.items():
            if 'indicators' in strategy:
                indicators = strategy['indicators']
            else:
                indicators = [key]
                
            print(f"  {key}: r²={strategy.get('rsquared', 0):.3f}, p={strategy.get('pvalue', 1.0):.3f}, consistency={strategy.get('consistency', 0):.2f}")
    
    # Serialize strategies for later use
    selector.serialize_regime_strategies()
    
    # Show how to use for signal generation
    print("\nExample signal generation:")
    
    # Select a strategy
    if "BULL_TREND" in selector.regime_strategies and selector.regime_strategies["BULL_TREND"]:
        best_strategy_key = list(selector.regime_strategies["BULL_TREND"].keys())[0]
        strategy_params = selector.create_strategy_parameters(best_strategy_key, "BULL_TREND")
        
        print(f"Using strategy: {best_strategy_key}")
        print(f"Parameters: {strategy_params}")
        
        # Get some current data
        current_symbol = "BBCA"  # Example symbol
        end_date = datetime.now()
        start_date = end_date - timedelta(days=30)
        
        current_data = selector.get_historical_data(current_symbol, start_date, end_date)
        
        if current_data is not None:
            signal, confidence = selector.generate_signal(strategy_params, current_data)
            print(f"Signal: {signal}, Confidence: {confidence:.2f}")
        else:
            print("No data available for signal generation example")