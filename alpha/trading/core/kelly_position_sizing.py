#!/usr/bin/env python3
# Filename: src/core/kelly_position_sizing.py
"""
Kelly Criterion with Uncertainty Module

This module provides advanced position sizing techniques using:
1. Kelly Criterion with statistical uncertainty adjustments
2. Regime-specific position sizing
3. Bayesian and frequentist approaches to win rate estimation
4. Correlation-aware portfolio-level Kelly allocation

These enhancements improve upon basic Kelly Criterion by accounting for
estimation errors and market conditions, leading to more robust risk management.
"""

import numpy as np
import pandas as pd
import logging
import math
from typing import Dict, List, Union, Optional, Tuple
from datetime import datetime

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import statistical libraries for enhanced estimation
try:
    from scipy import stats
    SCIPY_AVAILABLE = True
except ImportError:
    SCIPY_AVAILABLE = False
    logger.warning("SciPy not available. Using simplified statistical methods.")

# Try to import optional correlation modeling libraries
try:
    from sklearn.covariance import LedoitWolf, EmpiricalCovariance
    SKLEARN_AVAILABLE = True
    logger.info("scikit-learn available for robust correlation estimation")
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Using basic correlation estimation.")

class KellyPositionSizer:
    """
    Provides position sizing using Kelly Criterion with uncertainty adjustments.
    """
    
    def __init__(self, default_kelly_fraction: float = 0.5, 
                max_position_size: float = 0.25,
                correlation_method: str = 'ledoit_wolf',
                use_bayesian: bool = True):
        """
        Initialize the Kelly position sizer.
        
        Args:
            default_kelly_fraction: Default Kelly fraction for conservative sizing
            max_position_size: Maximum allowed position size as a fraction of portfolio
            correlation_method: Method for correlation estimation
            use_bayesian: Whether to use Bayesian methods for win rate estimation
        """
        self.default_kelly_fraction = default_kelly_fraction
        self.max_position_size = max_position_size
        self.correlation_method = correlation_method
        self.use_bayesian = use_bayesian
        
        # Market regime adjustments
        self.regime_factors = {
            'BULL_TREND': 1.0,
            'BEAR_TREND': 0.7,
            'HIGH_VOLATILITY': 0.5,
            'RANGE_BOUND': 0.8,
            'MEAN_REVERSION': 0.9,
            'UNKNOWN': 0.75
        }
        
        # Track historical allocations
        self.historical_allocations = []
        
    def calculate_kelly_fraction(self, win_rate: float, win_loss_ratio: float) -> float:
        """
        Calculate the basic Kelly fraction.
        
        Args:
            win_rate: Probability of winning (0-1)
            win_loss_ratio: Ratio of average win to average loss
            
        Returns:
            float: Kelly fraction
        """
        if win_loss_ratio <= 0:
            return 0.0
            
        kelly_f = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Kelly fraction cannot be negative
        return max(0, kelly_f)
        
    def estimate_win_rate_uncertainty(self, win_rate: float, sample_size: int, 
                                    confidence: float = 0.95) -> float:
        """
        Estimate uncertainty in win rate based on sample size.
        
        Args:
            win_rate: Observed win rate
            sample_size: Number of samples used to estimate win rate
            confidence: Confidence level for interval
            
        Returns:
            float: Uncertainty estimate
        """
        if sample_size <= 1:
            return 0.5  # Maximum uncertainty
            
        if SCIPY_AVAILABLE:
            # Calculate confidence interval using binomial distribution
            if self.use_bayesian:
                # Bayesian approach with Beta distribution
                alpha = 1 + win_rate * sample_size  # Add pseudo-observations as prior
                beta = 1 + sample_size - win_rate * sample_size
                
                lower, upper = stats.beta.interval(confidence, alpha, beta)
                
                # Calculate uncertainty as half the width of the interval
                uncertainty = (upper - lower) / 2
            else:
                # Frequentist approach with normal approximation to binomial
                z = stats.norm.ppf(1 - (1 - confidence) / 2)
                uncertainty = z * math.sqrt((win_rate * (1 - win_rate)) / sample_size)
        else:
            # Simplified approximation if scipy is not available
            uncertainty = math.sqrt((win_rate * (1 - win_rate)) / sample_size)
            
        return uncertainty
        
    def calculate_conservative_win_rate(self, win_rate: float, 
                                      sample_size: int, 
                                      confidence: float = 0.95) -> float:
        """
        Calculate a conservative win rate estimate accounting for uncertainty.
        
        Args:
            win_rate: Observed win rate
            sample_size: Number of samples used to estimate win rate
            confidence: Confidence level
            
        Returns:
            float: Conservative win rate estimate
        """
        # Calculate uncertainty
        uncertainty = self.estimate_win_rate_uncertainty(win_rate, sample_size, confidence)
        
        # Calculate lower bound of confidence interval
        conservative_win_rate = win_rate - uncertainty
        
        # Ensure win rate is between 0 and 1
        return max(0, min(1, conservative_win_rate))
        
    def kelly_position_sizing(self, strategy_results: Dict, 
                            market_regime: str = "UNKNOWN") -> Dict[str, float]:
        """
        Position sizing using empirical Kelly criterion with uncertainty adjustment.
        
        Args:
            strategy_results: Dictionary with strategy performance metrics
            market_regime: Current market regime
            
        Returns:
            dict: Dictionary of symbols with position sizes
        """
        positions = {}
        
        for symbol, result in strategy_results.items():
            # Extract metrics from result
            win_rate = result.get('win_rate', 0) / 100  # Convert from percentage
            avg_gain = result.get('avg_gain', 0)
            avg_loss = abs(result.get('avg_loss', 0))  # Ensure positive
            sample_size = result.get('sample_size', 10)
            
            # Calculate win/loss ratio
            win_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0
            
            # Get conservative win rate estimate
            conservative_win_rate = self.calculate_conservative_win_rate(win_rate, sample_size)
            
            # Calculate Kelly fraction
            kelly_f = self.calculate_kelly_fraction(conservative_win_rate, win_loss_ratio)
            
            # Apply market regime adjustment
            regime_factor = self.regime_factors.get(market_regime, 0.75)
            
            # Apply default Kelly fraction (typically 0.5 for "Half Kelly")
            adjusted_kelly = kelly_f * self.default_kelly_fraction * regime_factor
            
            # Cap at maximum position size
            position_size = min(adjusted_kelly, self.max_position_size)
            
            positions[symbol] = position_size
            
            logger.debug(f"Kelly sizing for {symbol}: original={kelly_f:.4f}, "
                        f"adjusted={adjusted_kelly:.4f}, final={position_size:.4f}")
            
        # Track allocation history
        self.historical_allocations.append({
            'timestamp': datetime.now(),
            'positions': positions.copy(),
            'market_regime': market_regime
        })
        
        return positions
        
    def estimate_covariance(self, returns: pd.DataFrame) -> np.ndarray:
        """
        Estimate covariance matrix using robust methods.
        
        Args:
            returns: DataFrame of asset returns
            
        Returns:
            np.ndarray: Covariance matrix
        """
        if returns.shape[1] <= 1:
            # Only one asset, return variance as a 1x1 matrix
            return np.array([[returns.var().iloc[0]]])
            
        if SKLEARN_AVAILABLE:
            if self.correlation_method == 'ledoit_wolf':
                # Ledoit-Wolf shrinkage estimator (more robust with limited data)
                cov_estimator = LedoitWolf().fit(returns)
                covariance = cov_estimator.covariance_
            else:
                # Standard empirical covariance
                cov_estimator = EmpiricalCovariance().fit(returns)
                covariance = cov_estimator.covariance_
        else:
            # Basic pandas covariance
            covariance = returns.cov().values
            
        return covariance
        
    def correlation_adjusted_kelly(self, strategy_results: Dict, 
                                 returns: pd.DataFrame,
                                 market_regime: str = "UNKNOWN") -> Dict[str, float]:
        """
        Calculate Kelly position sizes adjusted for asset correlations.
        
        Args:
            strategy_results: Dictionary of strategy results by symbol
            returns: DataFrame of historical returns for correlation calculation
            market_regime: Current market regime
            
        Returns:
            dict: Dictionary of symbols with position sizes
        """
        # Get individual Kelly fractions
        individual_kelly = self.kelly_position_sizing(strategy_results, market_regime)
        
        # Get symbols with positive Kelly fractions
        symbols = [s for s, k in individual_kelly.items() if k > 0]
        
        if len(symbols) <= 1:
            # No correlation adjustment needed for single asset
            return individual_kelly
            
        # Filter returns to include only the relevant symbols
        filtered_returns = returns[symbols]
        
        # Estimate covariance matrix
        try:
            covariance = self.estimate_covariance(filtered_returns)
            
            # Convert to correlation matrix
            std_devs = np.sqrt(np.diag(covariance))
            correlations = covariance / np.outer(std_devs, std_devs)
            
            # Create vector of individual Kelly fractions
            kelly_vector = np.array([individual_kelly[s] for s in symbols])
            
            # Adjust Kelly fractions based on correlation
            # This is a simplified approach - a full multivariate Kelly calculation
            # would involve solving a quadratic programming problem
            adjusted_kelly = {}
            
            for i, symbol in enumerate(symbols):
                # Calculate average correlation with other assets
                corrs = correlations[i, :]
                avg_corr = (np.sum(corrs) - 1) / (len(symbols) - 1) if len(symbols) > 1 else 0
                
                # Higher correlation -> lower allocation
                correlation_factor = 1 - 0.5 * avg_corr
                
                # Adjust Kelly fraction
                adjusted_kelly[symbol] = individual_kelly[symbol] * correlation_factor
                
            # Add symbols with zero allocation from individual Kelly
            for symbol in strategy_results:
                if symbol not in adjusted_kelly:
                    adjusted_kelly[symbol] = 0.0
                    
            # Track allocation history
            self.historical_allocations.append({
                'timestamp': datetime.now(),
                'positions': adjusted_kelly.copy(),
                'market_regime': market_regime,
                'correlation_adjusted': True
            })
                    
            return adjusted_kelly
            
        except Exception as e:
            logger.error(f"Error in correlation adjustment: {e}")
            logger.warning("Falling back to individual Kelly fractions")
            return individual_kelly
            
    def group_constraints_kelly(self, strategy_results: Dict,
                              returns: pd.DataFrame,
                              group_constraints: Dict[str, List[str]],
                              market_regime: str = "UNKNOWN") -> Dict[str, float]:
        """
        Calculate Kelly position sizes with group constraints.
        
        Args:
            strategy_results: Dictionary of strategy results by symbol
            returns: DataFrame of historical returns for correlation calculation
            group_constraints: Dictionary mapping group names to lists of symbols
            market_regime: Current market regime
            
        Returns:
            dict: Dictionary of symbols with position sizes
        """
        # Get correlation-adjusted Kelly fractions
        adjusted_kelly = self.correlation_adjusted_kelly(strategy_results, returns, market_regime)
        
        # Apply group constraints
        constrained_kelly = adjusted_kelly.copy()
        
        # Calculate group allocations
        group_allocations = {}
        for group_name, symbols in group_constraints.items():
            valid_symbols = [s for s in symbols if s in constrained_kelly]
            if not valid_symbols:
                continue
                
            group_allocation = sum(constrained_kelly[s] for s in valid_symbols)
            group_allocations[group_name] = {
                'symbols': valid_symbols,
                'allocation': group_allocation,
                'max_allocation': self.max_position_size
            }
            
        # Adjust allocations if any group exceeds its maximum
        for group_info in group_allocations.values():
            symbols = group_info['symbols']
            current_allocation = group_info['allocation']
            max_allocation = group_info['max_allocation']
            
            if current_allocation > max_allocation and symbols:
                # Scale down allocations proportionally
                scale_factor = max_allocation / current_allocation
                
                for symbol in symbols:
                    constrained_kelly[symbol] *= scale_factor
                    
        # Track allocation history
        self.historical_allocations.append({
            'timestamp': datetime.now(),
            'positions': constrained_kelly.copy(),
            'market_regime': market_regime,
            'group_constrained': True
        })
                    
        return constrained_kelly
        
    def multi_strategy_allocation(self, strategies: Dict[str, Dict], 
                                portfolio_max: float = 1.0,
                                returns: Optional[pd.DataFrame] = None,
                                market_regime: str = "UNKNOWN") -> Dict[str, Dict]:
        """
        Allocate capital across multiple strategies.
        
        Args:
            strategies: Dictionary of strategy results grouped by strategy name
            portfolio_max: Maximum total portfolio allocation
            returns: DataFrame of historical returns (optional)
            market_regime: Current market regime
            
        Returns:
            dict: Dictionary of strategies and symbols with position sizes
        """
        # Calculate Kelly allocation for each strategy
        strategy_allocations = {}
        
        for strategy_name, results in strategies.items():
            if returns is not None:
                # Use correlation-adjusted Kelly if returns data provided
                positions = self.correlation_adjusted_kelly(results, returns, market_regime)
            else:
                # Use individual Kelly if no returns data
                positions = self.kelly_position_sizing(results, market_regime)
                
            strategy_allocations[strategy_name] = positions
            
        # Calculate total allocation
        total_allocation = sum(sum(positions.values()) for positions in strategy_allocations.values())
        
        # Scale if total exceeds portfolio maximum
        if total_allocation > portfolio_max:
            scale_factor = portfolio_max / total_allocation
            
            for strategy_name in strategy_allocations:
                strategy_allocations[strategy_name] = {
                    symbol: position * scale_factor
                    for symbol, position in strategy_allocations[strategy_name].items()
                }
                
        # Calculate strategy-level metrics
        strategy_metrics = {}
        for strategy_name, positions in strategy_allocations.items():
            strategy_metrics[strategy_name] = {
                'total_allocation': sum(positions.values()),
                'max_position': max(positions.values()) if positions else 0,
                'positions': len(positions),
                'allocations': positions
            }
            
        # Track allocation history (simplified for multi-strategy)
        flat_allocations = {}
        for strategy_name, positions in strategy_allocations.items():
            for symbol, position in positions.items():
                flat_key = f"{strategy_name}:{symbol}"
                flat_allocations[flat_key] = position
                
        self.historical_allocations.append({
            'timestamp': datetime.now(),
            'positions': flat_allocations.copy(),
            'market_regime': market_regime,
            'multi_strategy': True
        })
            
        return strategy_metrics
        
    def kelly_from_strategy_series(self, returns_series: pd.Series, 
                                 lookback_period: int = 100,
                                 market_regime: str = "UNKNOWN") -> float:
        """
        Calculate Kelly fraction from historical strategy returns.
        
        Args:
            returns_series: Series of strategy returns (not asset returns)
            lookback_period: Number of recent periods to consider
            market_regime: Current market regime
            
        Returns:
            float: Kelly fraction
        """
        if len(returns_series) == 0:
            return 0.0
            
        # Use recent returns for estimation
        recent_returns = returns_series.iloc[-lookback_period:] if lookback_period < len(returns_series) else returns_series
        
        # Calculate win rate
        wins = (recent_returns > 0).sum()
        total_trades = (~recent_returns.isna()).sum()
        
        if total_trades == 0:
            return 0.0
            
        win_rate = wins / total_trades
        
        # Calculate average gain and loss
        avg_gain = recent_returns[recent_returns > 0].mean() if wins > 0 else 0
        avg_loss = abs(recent_returns[recent_returns < 0].mean()) if (total_trades - wins) > 0 else 0
        
        if avg_loss == 0:
            return 0.0  # Cannot calculate win/loss ratio
            
        win_loss_ratio = avg_gain / avg_loss
        
        # Get conservative win rate estimate
        conservative_win_rate = self.calculate_conservative_win_rate(win_rate, total_trades)
        
        # Calculate Kelly fraction
        kelly_f = self.calculate_kelly_fraction(conservative_win_rate, win_loss_ratio)
        
        # Apply market regime adjustment
        regime_factor = self.regime_factors.get(market_regime, 0.75)
        
        # Apply default Kelly fraction (typically 0.5 for "Half Kelly")
        adjusted_kelly = kelly_f * self.default_kelly_fraction * regime_factor
        
        # Cap at maximum position size
        position_size = min(adjusted_kelly, self.max_position_size)
        
        return position_size
        
    def robust_kelly_from_distributions(self, returns_model: Dict, 
                                      confidence: float = 0.95,
                                      market_regime: str = "UNKNOWN") -> float:
        """
        Calculate Kelly fraction using probabilistic return models (e.g., from Gaussian Process).
        
        Args:
            returns_model: Dictionary with return distribution parameters
            confidence: Confidence level for uncertainty estimation
            market_regime: Current market regime
            
        Returns:
            float: Kelly fraction
        """
        # Extract distribution parameters
        mean_return = returns_model.get('mean', 0)
        std_return = returns_model.get('std', 0)
        
        if std_return <= 0:
            return 0.0
            
        # Calculate probability of positive return (win rate)
        if SCIPY_AVAILABLE:
            win_rate = 1 - stats.norm.cdf(0, loc=mean_return, scale=std_return)
        else:
            # Simplified estimate if scipy not available
            z_score = mean_return / std_return
            win_rate = 0.5 + 0.5 * self.approx_erf(z_score / math.sqrt(2))
            
        # Calculate expected positive and negative returns
        if SCIPY_AVAILABLE:
            # Truncated normal distribution for positive and negative parts
            def expected_positive(mu, sigma):
                alpha = -mu / sigma
                pdf_alpha = stats.norm.pdf(alpha)
                cdf_alpha = stats.norm.cdf(alpha)
                
                if cdf_alpha == 1:  # Avoid division by zero
                    return 0
                    
                return mu + sigma * (pdf_alpha / (1 - cdf_alpha))
                
            def expected_negative(mu, sigma):
                alpha = -mu / sigma
                pdf_alpha = stats.norm.pdf(alpha)
                cdf_alpha = stats.norm.cdf(alpha)
                
                if cdf_alpha == 0:  # Avoid division by zero
                    return 0
                    
                return mu - sigma * (pdf_alpha / cdf_alpha)
                
            avg_gain = expected_positive(mean_return, std_return)
            avg_loss = abs(expected_negative(mean_return, std_return))
        else:
            # Simplified estimate if scipy not available
            avg_gain = mean_return + 0.8 * std_return
            avg_loss = abs(mean_return - 0.8 * std_return)
            
        if avg_loss <= 0:
            return 0.0
            
        win_loss_ratio = avg_gain / avg_loss
        
        # Use effective sample size based on confidence intervals
        if 'sample_size' in returns_model:
            sample_size = returns_model['sample_size']
        else:
            # Estimate effective sample size from confidence interval
            z = 1.96  # 95% confidence level
            margin_of_error = returns_model.get('margin_of_error', std_return * 0.2)
            sample_size = (z * std_return / margin_of_error) ** 2
            
        # Get conservative win rate estimate
        conservative_win_rate = self.calculate_conservative_win_rate(win_rate, sample_size, confidence)
        
        # Calculate Kelly fraction
        kelly_f = self.calculate_kelly_fraction(conservative_win_rate, win_loss_ratio)
        
        # Apply market regime adjustment
        regime_factor = self.regime_factors.get(market_regime, 0.75)
        
        # Apply default Kelly fraction (typically 0.5 for "Half Kelly")
        adjusted_kelly = kelly_f * self.default_kelly_fraction * regime_factor
        
        # Cap at maximum position size
        position_size = min(adjusted_kelly, self.max_position_size)
        
        return position_size
        
    def get_position_size_metrics(self, strategy_results: Dict, 
                               returns: Optional[pd.DataFrame] = None,
                               market_regime: str = "UNKNOWN") -> Dict:
        """
        Calculate position sizes with details on adjustments.
        
        Args:
            strategy_results: Dictionary of strategy results by symbol
            returns: DataFrame of historical returns (optional)
            market_regime: Current market regime
            
        Returns:
            dict: Dictionary with position sizes and adjustment details
        """
        metrics = {}
        
        for symbol, result in strategy_results.items():
            # Extract metrics from result
            win_rate = result.get('win_rate', 0) / 100  # Convert from percentage
            avg_gain = result.get('avg_gain', 0)
            avg_loss = abs(result.get('avg_loss', 0))  # Ensure positive
            sample_size = result.get('sample_size', 10)
            
            # Calculate win/loss ratio
            win_loss_ratio = avg_gain / avg_loss if avg_loss > 0 else 0
            
            # Calculate naive Kelly fraction
            naive_kelly = self.calculate_kelly_fraction(win_rate, win_loss_ratio)
            
            # Get conservative win rate estimate
            conservative_win_rate = self.calculate_conservative_win_rate(win_rate, sample_size)
            win_rate_uncertainty = self.estimate_win_rate_uncertainty(win_rate, sample_size)
            
            # Calculate Kelly with conservative win rate
            conservative_kelly = self.calculate_kelly_fraction(conservative_win_rate, win_loss_ratio)
            
            # Apply market regime adjustment
            regime_factor = self.regime_factors.get(market_regime, 0.75)
            regime_kelly = conservative_kelly * regime_factor
            
            # Apply default Kelly fraction (typically 0.5 for "Half Kelly")
            factored_kelly = regime_kelly * self.default_kelly_fraction
            
            # Calculate correlation adjustment if returns provided
            correlation_factor = 1.0
            if returns is not None and symbol in returns.columns:
                try:
                    # Calculate average correlation with other symbols
                    other_symbols = [s for s in returns.columns if s != symbol]
                    if other_symbols:
                        symbol_returns = returns[symbol]
                        corrs = [symbol_returns.corr(returns[s]) for s in other_symbols]
                        avg_corr = np.mean(corrs)
                        correlation_factor = 1 - 0.5 * avg_corr
                except Exception as e:
                    logger.warning(f"Error calculating correlation for {symbol}: {e}")
            
            correlation_kelly = factored_kelly * correlation_factor
            
            # Cap at maximum position size
            final_position = min(correlation_kelly, self.max_position_size)
            
            # Store all metrics
            metrics[symbol] = {
                'naive_kelly': naive_kelly,
                'win_rate': win_rate,
                'win_rate_uncertainty': win_rate_uncertainty,
                'conservative_win_rate': conservative_win_rate,
                'conservative_kelly': conservative_kelly,
                'regime_factor': regime_factor,
                'regime_kelly': regime_kelly,
                'default_fraction': self.default_kelly_fraction,
                'factored_kelly': factored_kelly,
                'correlation_factor': correlation_factor,
                'correlation_kelly': correlation_kelly,
                'max_position_size': self.max_position_size,
                'final_position': final_position
            }
        
        return metrics
    
    def approx_erf(self, x: float) -> float:
        """
        Approximate error function used when scipy is not available.
        
        Args:
            x: Input value
            
        Returns:
            float: Approximation of error function
        """
        # Abramowitz and Stegun approximation
        sign = 1 if x >= 0 else -1
        x = abs(x)
        
        a1 = 0.254829592
        a2 = -0.284496736
        a3 = 1.421413741
        a4 = -1.453152027
        a5 = 1.061405429
        p = 0.3275911
        
        t = 1.0 / (1.0 + p * x)
        y = 1.0 - (((((a5 * t + a4) * t) + a3) * t + a2) * t + a1) * t * math.exp(-x * x)
        
        return sign * y


# Example usage
if __name__ == "__main__":
    # Create position sizer
    sizer = KellyPositionSizer(default_kelly_fraction=0.5, max_position_size=0.2)
    
    # Example strategy results
    strategy_results = {
        'AAPL': {
            'win_rate': 65.0,  # 65%
            'avg_gain': 2.5,   # 2.5%
            'avg_loss': 1.5,   # -1.5%
            'sample_size': 100
        },
        'MSFT': {
            'win_rate': 55.0,  # 55%
            'avg_gain': 3.0,   # 3.0%
            'avg_loss': 1.8,   # -1.8%
            'sample_size': 80
        },
        'GOOGL': {
            'win_rate': 60.0,  # 60%
            'avg_gain': 2.2,   # 2.2%
            'avg_loss': 1.2,   # -1.2%
            'sample_size': 120
        }
    }
    
    # Create synthetic returns for correlation calculation
    np.random.seed(42)
    returns = pd.DataFrame(np.random.randn(100, 3) * 0.01, columns=['AAPL', 'MSFT', 'GOOGL'])
    
    # Add correlation between AAPL and MSFT
    returns['MSFT'] = returns['MSFT'] * 0.7 + returns['AAPL'] * 0.3
    
    # Calculate positions using different methods
    basic_kelly = sizer.kelly_position_sizing(strategy_results, market_regime="BULL_TREND")
    correlation_kelly = sizer.correlation_adjusted_kelly(strategy_results, returns, market_regime="BULL_TREND")
    
    # Group constraints example
    group_constraints = {
        'Technology': ['AAPL', 'MSFT', 'GOOGL'],
    }
    
    constrained_kelly = sizer.group_constraints_kelly(
        strategy_results, returns, group_constraints, market_regime="BULL_TREND"
    )
    
    # Print results
    print("\nBasic Kelly Position Sizing:")
    for symbol, allocation in basic_kelly.items():
        print(f"{symbol}: {allocation:.2%}")
        
    print("\nCorrelation-Adjusted Kelly Position Sizing:")
    for symbol, allocation in correlation_kelly.items():
        print(f"{symbol}: {allocation:.2%}")
        
    print("\nGroup-Constrained Kelly Position Sizing:")
    for symbol, allocation in constrained_kelly.items():
        print(f"{symbol}: {allocation:.2%}")
    
    # Calculate detailed position metrics
    metrics = sizer.get_position_size_metrics(strategy_results, returns, market_regime="BULL_TREND")
    
    print("\nDetailed Position Size Metrics for AAPL:")
    for metric, value in metrics['AAPL'].items():
        print(f"  {metric}: {value:.4f}")