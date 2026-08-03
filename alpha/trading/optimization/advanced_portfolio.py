#!/usr/bin/env python3
"""
Advanced Portfolio Optimization Module

This module implements sophisticated portfolio optimization techniques,
specifically designed for Indonesian market characteristics and inefficiencies.

Features:
- Risk Parity optimization
- Hierarchical Risk Parity (HRP)
- Black-Litterman model integration
- Regime-dependent optimization
- Conditional Value at Risk (CVaR)
- Maximum Diversification Ratio
- Kelly Criterion for position sizing
- Dynamic rebalancing strategies
"""

import numpy as np
import pandas as pd
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
from scipy.optimize import minimize, differential_evolution
from scipy.cluster.hierarchy import dendrogram, linkage, fcluster
from scipy.spatial.distance import squareform
import warnings
warnings.filterwarnings('ignore')

# Try to import Rust backend
try:
    import sharpe_rust
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    print("Warning: Rust backend not available, using Python implementation")

# Try to import PyPortfolioOpt
try:
    from pypfopt import risk_models, expected_returns, EfficientFrontier
    from pypfopt.risk_models import CovarianceShrinkage
    from pypfopt.objective_functions import negative_sharpe, portfolio_volatility
    PYPFOPT_AVAILABLE = True
except ImportError:
    PYPFOPT_AVAILABLE = False
    logging.warning("PyPortfolioOpt not available. Using custom optimization.")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedPortfolioOptimizer:
    """
    Advanced portfolio optimizer for Indonesian markets.
    
    Implements multiple optimization techniques:
    - Risk Parity
    - Hierarchical Risk Parity (HRP)
    - Black-Litterman model
    - Regime-dependent optimization
    - Kelly Criterion
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db', 
                 lookback_days: int = 252,
                 risk_free_rate: float = 0.05):
        """
        Initialize the advanced portfolio optimizer.
        
        Args:
            db_path: Path to historical data database
            lookback_days: Number of days for historical analysis
            risk_free_rate: Risk-free rate for calculations
        """
        self.db_path = db_path
        self.lookback_days = lookback_days
        self.risk_free_rate = risk_free_rate
        
        # Indonesian market specific parameters
        self.idx_params = {
            'volatility_multiplier': 1.5,     # IDX typically more volatile
            'correlation_decay': 0.95,        # Faster correlation decay
            'liquidity_constraint': 0.1,      # Maximum 10% in illiquid assets
            'concentration_limit': 0.15,      # Maximum 15% in single asset
            'min_position_size': 0.01,        # Minimum 1% position
            'max_position_size': 0.25,        # Maximum 25% position
            'transaction_cost': 0.0025,       # 0.25% transaction cost
            'slippage': 0.001                 # 0.1% slippage
        }
        
        # Optimization parameters
        self.optimization_params = {
            'max_iterations': 1000,
            'tolerance': 1e-6,
            'population_size': 50,
            'mutation_rate': 0.1,
            'crossover_rate': 0.7
        }
        
        logger.info("Advanced Portfolio Optimizer initialized for Indonesian markets")
    
    def get_returns_data(self, symbols: List[str]) -> pd.DataFrame:
        """
        Get historical returns data for optimization.
        
        Args:
            symbols: List of stock symbols
            
        Returns:
            DataFrame with returns data
        """
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Get data for all symbols
            returns_data = {}
            for symbol in symbols:
                # Add .JK suffix if not present
                query_symbol = symbol if symbol.endswith('.JK') else f"{symbol}.JK"
                
                query = """
                SELECT timestamp, close
                FROM historical_data_daily
                WHERE symbol = ?
                ORDER BY timestamp DESC
                LIMIT ?
                """
                
                df = pd.read_sql_query(query, conn, params=(query_symbol, self.lookback_days))
                
                if not df.empty:
                    df['timestamp'] = pd.to_datetime(df['timestamp'])
                    df.set_index('timestamp', inplace=True)
                    df = df.sort_index()
                    
                    # Calculate returns
                    returns = df['close'].pct_change().dropna()
                    returns_data[symbol] = returns
            
            conn.close()
            
            if len(returns_data) < 2:
                return pd.DataFrame()
            
            # Align all returns data
            aligned_returns = pd.DataFrame(returns_data)
            aligned_returns = aligned_returns.dropna()
            
            return aligned_returns
            
        except Exception as e:
            logger.error(f"Error fetching returns data: {e}")
            return pd.DataFrame()
    
    def calculate_risk_metrics(self, returns: pd.DataFrame) -> Dict:
        """
        Calculate comprehensive risk metrics.
        
        Args:
            returns: DataFrame with returns data
            
        Returns:
            Dictionary with risk metrics
        """
        if returns.empty or len(returns) < 50:
            return {}
        
        metrics = {}
        
        # Basic risk metrics
        metrics['volatility'] = returns.std() * np.sqrt(252)
        metrics['annualized_returns'] = returns.mean() * 252
        metrics['sharpe_ratio'] = (metrics['annualized_returns'] - self.risk_free_rate) / metrics['volatility']
        
        # Downside risk metrics
        downside_returns = returns[returns < 0]
        metrics['downside_deviation'] = downside_returns.std() * np.sqrt(252)
        metrics['sortino_ratio'] = (metrics['annualized_returns'] - self.risk_free_rate) / metrics['downside_deviation']
        
        # Maximum drawdown
        cumulative_returns = (1 + returns).cumprod()
        rolling_max = cumulative_returns.expanding().max()
        drawdown = (cumulative_returns - rolling_max) / rolling_max
        metrics['max_drawdown'] = drawdown.min()
        
        # Value at Risk (VaR)
        metrics['var_95'] = np.percentile(returns, 5)
        metrics['var_99'] = np.percentile(returns, 1)
        
        # Conditional Value at Risk (CVaR)
        metrics['cvar_95'] = returns[returns <= metrics['var_95']].mean()
        metrics['cvar_99'] = returns[returns <= metrics['var_99']].mean()
        
        # Skewness and kurtosis
        metrics['skewness'] = returns.skew()
        metrics['kurtosis'] = returns.kurtosis()
        
        # Tail risk measures
        metrics['tail_risk'] = self._calculate_tail_risk(returns)
        
        return metrics
    
    def _calculate_tail_risk(self, returns: pd.DataFrame) -> pd.Series:
        """Calculate tail risk measures."""
        tail_risk = {}
        
        for col in returns.columns:
            # Calculate extreme negative returns
            extreme_returns = returns[col][returns[col] < returns[col].quantile(0.05)]
            
            if len(extreme_returns) > 0:
                # Expected shortfall
                tail_risk[col] = extreme_returns.mean()
            else:
                tail_risk[col] = returns[col].min()
        
        return pd.Series(tail_risk)
    
    def risk_parity_optimization(self, returns: pd.DataFrame, target_vol: float = 0.10) -> Dict:
        """
        Implement Risk Parity optimization.
        
        Args:
            returns: DataFrame with returns data
            target_vol: Target portfolio volatility
            
        Returns:
            Dictionary with optimization results
        """
        if returns.empty or len(returns) < 50:
            return {'error': 'Insufficient data for optimization'}
        
        # Try to use Rust backend for performance
        if RUST_AVAILABLE:
            try:
                returns_array = returns.values
                
                rust_weights = sharpe_rust.risk_parity_optimization_rust(returns_array, target_vol)
                weights_array = np.array(rust_weights)
                
                # Calculate portfolio metrics
                portfolio_metrics = self._calculate_portfolio_metrics(returns, weights_array)
                
                return {
                    'weights': dict(zip(returns.columns, weights_array)),
                    'portfolio_metrics': portfolio_metrics,
                    'optimization_success': True,
                    'method': 'rust_risk_parity'
                }
            except Exception as e:
                logger.warning(f"Rust backend failed, falling back to Python: {e}")
        
        # Python fallback implementation
        try:
            # Calculate covariance matrix
            cov_matrix = returns.cov() * 252
            
            # Risk parity objective function
            def risk_parity_objective(weights):
                weights = np.array(weights)
                weights = weights / np.sum(weights)  # Normalize
                
                # Calculate portfolio risk contributions
                portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)
                risk_contributions = (weights * (cov_matrix @ weights)) / portfolio_vol
                
                # Objective: minimize variance of risk contributions
                target_contribution = portfolio_vol / len(weights)
                variance = np.var(risk_contributions - target_contribution)
                
                return variance
            
            # Constraints
            n_assets = len(returns.columns)
            
            # Bounds for weights
            bounds = [(self.idx_params['min_position_size'], 
                      self.idx_params['max_position_size'])] * n_assets
            
            # Initial weights (equal weight)
            initial_weights = np.array([1/n_assets] * n_assets)
            
            # Optimize
            result = minimize(
                risk_parity_objective,
                initial_weights,
                method='SLSQP',
                bounds=bounds,
                constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                options={'maxiter': self.optimization_params['max_iterations']}
            )
            
            if result.success:
                optimal_weights = result.x / np.sum(result.x)
                
                # Calculate portfolio metrics
                portfolio_metrics = self._calculate_portfolio_metrics(returns, optimal_weights)
                
                return {
                    'weights': dict(zip(returns.columns, optimal_weights)),
                    'portfolio_metrics': portfolio_metrics,
                    'optimization_success': True,
                    'objective_value': result.fun,
                    'method': 'python_risk_parity'
                }
            else:
                return {'error': f'Optimization failed: {result.message}'}
                
        except Exception as e:
            logger.error(f"Risk parity optimization error: {e}")
            return {'error': f'Optimization error: {str(e)}'}
    
    def hierarchical_risk_parity(self, returns: pd.DataFrame) -> Dict:
        """
        Implement Hierarchical Risk Parity (HRP) optimization.
        
        Args:
            returns: DataFrame with returns data
            
        Returns:
            Dictionary with HRP results
        """
        if returns.empty or len(returns) < 50:
            return {'error': 'Insufficient data for HRP optimization'}
        
        try:
            # Calculate correlation matrix
            corr_matrix = returns.corr()
            
            # Convert correlation to distance matrix
            distance_matrix = np.sqrt(0.5 * (1 - corr_matrix))
            
            # Hierarchical clustering
            condensed_dist = squareform(distance_matrix)
            linkage_matrix = linkage(condensed_dist, method='single')
            
            # Get cluster assignments
            n_clusters = len(returns.columns)
            cluster_assignments = fcluster(linkage_matrix, n_clusters, criterion='maxclust')
            
            # Calculate weights using HRP algorithm
            weights = self._hrp_weights(returns, cluster_assignments)
            
            # Calculate portfolio metrics
            portfolio_metrics = self._calculate_portfolio_metrics(returns, weights)
            
            return {
                'weights': dict(zip(returns.columns, weights)),
                'portfolio_metrics': portfolio_metrics,
                'cluster_assignments': dict(zip(returns.columns, cluster_assignments)),
                'optimization_success': True
            }
            
        except Exception as e:
            logger.error(f"HRP optimization error: {e}")
            return {'error': f'HRP optimization error: {str(e)}'}
    
    def _hrp_weights(self, returns: pd.DataFrame, cluster_assignments: np.ndarray) -> np.ndarray:
        """Calculate HRP weights using hierarchical clustering."""
        n_assets = len(returns.columns)
        weights = np.zeros(n_assets)
        
        # Calculate variance for each asset
        variances = returns.var() * 252
        
        # Sort assets by cluster assignment
        sorted_indices = np.argsort(cluster_assignments)
        sorted_variances = variances.iloc[sorted_indices]
        
        # Initialize weights
        weights[sorted_indices[0]] = 1.0
        
        # Recursively calculate weights
        for i in range(1, n_assets):
            if cluster_assignments[sorted_indices[i]] == cluster_assignments[sorted_indices[i-1]]:
                # Same cluster: equal weight
                cluster_size = np.sum(cluster_assignments == cluster_assignments[sorted_indices[i]])
                cluster_weight = 1.0 / cluster_size
                cluster_indices = np.where(cluster_assignments == cluster_assignments[sorted_indices[i]])[0]
                weights[cluster_indices] = cluster_weight
            else:
                # Different cluster: weight by inverse variance
                weights[sorted_indices[i]] = 1.0 / sorted_variances.iloc[i]
        
        # Normalize weights
        weights = weights / np.sum(weights)
        
        return weights
    
    def black_litterman_optimization(self, returns: pd.DataFrame, 
                                   market_caps: Dict[str, float] = None,
                                   views: Dict[str, float] = None) -> Dict:
        """
        Implement Black-Litterman model optimization.
        
        Args:
            returns: DataFrame with returns data
            market_caps: Dictionary of market capitalizations
            views: Dictionary of return views
            
        Returns:
            Dictionary with Black-Litterman results
        """
        if returns.empty or len(returns) < 50:
            return {'error': 'Insufficient data for Black-Litterman optimization'}
        
        try:
            # Calculate market equilibrium returns
            if market_caps is None:
                # Use equal market cap if not provided
                market_caps = {col: 1.0 for col in returns.columns}
            
            market_cap_weights = np.array([market_caps.get(col, 1.0) for col in returns.columns])
            market_cap_weights = market_cap_weights / np.sum(market_cap_weights)
            
            # Calculate covariance matrix
            cov_matrix = returns.cov() * 252
            
            # Market equilibrium returns (reverse optimization)
            risk_aversion = 2.5  # Typical risk aversion parameter
            pi = risk_aversion * cov_matrix @ market_cap_weights
            
            # Incorporate views
            if views is not None:
                # Create view matrix
                view_matrix = np.zeros((len(views), len(returns.columns)))
                view_returns = np.zeros(len(views))
                
                for i, (asset, view_return) in enumerate(views.items()):
                    if asset in returns.columns:
                        asset_idx = returns.columns.get_loc(asset)
                        view_matrix[i, asset_idx] = 1.0
                        view_returns[i] = view_return
                
                # View confidence matrix (diagonal)
                omega = np.diag([0.1] * len(views))  # 10% confidence
                
                # Black-Litterman formula
                tau = 0.05  # Scaling parameter
                pi_bl = pi + tau * cov_matrix @ view_matrix.T @ np.linalg.inv(
                    omega + tau * view_matrix @ cov_matrix @ view_matrix.T
                ) @ (view_returns - view_matrix @ pi)
                
                # Updated covariance matrix
                cov_bl = cov_matrix + tau * cov_matrix @ view_matrix.T @ np.linalg.inv(
                    omega + tau * view_matrix @ cov_matrix @ view_matrix.T
                ) @ view_matrix @ cov_matrix
            else:
                pi_bl = pi
                cov_bl = cov_matrix
            
            # Optimize portfolio
            optimal_weights = self._optimize_with_constraints(pi_bl, cov_bl)
            
            # Calculate portfolio metrics
            portfolio_metrics = self._calculate_portfolio_metrics(returns, optimal_weights)
            
            return {
                'weights': dict(zip(returns.columns, optimal_weights)),
                'portfolio_metrics': portfolio_metrics,
                'equilibrium_returns': dict(zip(returns.columns, pi)),
                'bl_returns': dict(zip(returns.columns, pi_bl)),
                'optimization_success': True
            }
            
        except Exception as e:
            logger.error(f"Black-Litterman optimization error: {e}")
            return {'error': f'Black-Litterman optimization error: {str(e)}'}
    
    def _optimize_with_constraints(self, expected_returns: np.ndarray, 
                                 cov_matrix: np.ndarray) -> np.ndarray:
        """Optimize portfolio with constraints."""
        n_assets = len(expected_returns)
        
        # Objective function: maximize Sharpe ratio
        def objective(weights):
            weights = np.array(weights)
            portfolio_return = np.sum(weights * expected_returns)
            portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)
            sharpe = (portfolio_return - self.risk_free_rate) / portfolio_vol
            return -sharpe  # Minimize negative Sharpe
        
        # Constraints
        bounds = [(self.idx_params['min_position_size'], 
                  self.idx_params['max_position_size'])] * n_assets
        
        # Initial weights
        initial_weights = np.array([1/n_assets] * n_assets)
        
        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints={'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
            options={'maxiter': self.optimization_params['max_iterations']}
        )
        
        if result.success:
            return result.x / np.sum(result.x)
        else:
            # Fallback to equal weights
            return np.array([1/n_assets] * n_assets)
    
    def kelly_criterion_optimization(self, returns: pd.DataFrame) -> Dict:
        """
        Implement Kelly Criterion for position sizing.
        
        Args:
            returns: DataFrame with returns data
            
        Returns:
            Dictionary with Kelly Criterion results
        """
        if returns.empty or len(returns) < 50:
            return {'error': 'Insufficient data for Kelly Criterion optimization'}
        
        try:
            kelly_weights = {}
            
            for col in returns.columns:
                asset_returns = returns[col].dropna()
                
                # Calculate Kelly fraction
                mean_return = asset_returns.mean() * 252
                variance = asset_returns.var() * 252
                
                if variance > 0:
                    kelly_fraction = (mean_return - self.risk_free_rate) / variance
                else:
                    kelly_fraction = 0
                
                # Apply constraints
                kelly_fraction = max(
                    self.idx_params['min_position_size'],
                    min(kelly_fraction, self.idx_params['max_position_size'])
                )
                
                kelly_weights[col] = kelly_fraction
            
            # Normalize weights
            total_weight = sum(kelly_weights.values())
            if total_weight > 0:
                normalized_weights = {k: v/total_weight for k, v in kelly_weights.items()}
            else:
                # Fallback to equal weights
                n_assets = len(returns.columns)
                normalized_weights = {col: 1/n_assets for col in returns.columns}
            
            # Convert to array
            weights_array = np.array([normalized_weights[col] for col in returns.columns])
            
            # Calculate portfolio metrics
            portfolio_metrics = self._calculate_portfolio_metrics(returns, weights_array)
            
            return {
                'weights': normalized_weights,
                'portfolio_metrics': portfolio_metrics,
                'raw_kelly_fractions': kelly_weights,
                'optimization_success': True
            }
            
        except Exception as e:
            logger.error(f"Kelly Criterion optimization error: {e}")
            return {'error': f'Kelly Criterion optimization error: {str(e)}'}
    
    def regime_dependent_optimization(self, returns: pd.DataFrame, 
                                    regime: str = 'UNKNOWN') -> Dict:
        """
        Implement regime-dependent portfolio optimization.
        
        Args:
            returns: DataFrame with returns data
            regime: Current market regime
            
        Returns:
            Dictionary with regime-dependent optimization results
        """
        if returns.empty or len(returns) < 50:
            return {'error': 'Insufficient data for regime-dependent optimization'}
        
        try:
            # Regime-specific parameters
            regime_params = {
                'BULL_TREND': {
                    'risk_aversion': 2.0,
                    'target_vol': 0.15,
                    'momentum_weight': 0.3
                },
                'BEAR_TREND': {
                    'risk_aversion': 4.0,
                    'target_vol': 0.08,
                    'momentum_weight': -0.2
                },
                'HIGH_VOLATILITY': {
                    'risk_aversion': 5.0,
                    'target_vol': 0.06,
                    'momentum_weight': 0.0
                },
                'RANGE_BOUND': {
                    'risk_aversion': 3.0,
                    'target_vol': 0.10,
                    'momentum_weight': 0.1
                }
            }
            
            params = regime_params.get(regime, regime_params['RANGE_BOUND'])
            
            # Calculate momentum signals
            momentum_signals = self._calculate_momentum_signals(returns)
            
            # Adjust expected returns based on regime
            expected_returns = returns.mean() * 252
            adjusted_returns = expected_returns + params['momentum_weight'] * momentum_signals
            
            # Calculate covariance matrix with regime adjustment
            cov_matrix = returns.cov() * 252
            if regime == 'HIGH_VOLATILITY':
                cov_matrix = cov_matrix * self.idx_params['volatility_multiplier']
            
            # Optimize with regime-specific constraints
            optimal_weights = self._optimize_with_regime_constraints(
                adjusted_returns, cov_matrix, params
            )
            
            # Calculate portfolio metrics
            portfolio_metrics = self._calculate_portfolio_metrics(returns, optimal_weights)
            
            return {
                'weights': dict(zip(returns.columns, optimal_weights)),
                'portfolio_metrics': portfolio_metrics,
                'regime': regime,
                'regime_params': params,
                'optimization_success': True
            }
            
        except Exception as e:
            logger.error(f"Regime-dependent optimization error: {e}")
            return {'error': f'Regime-dependent optimization error: {str(e)}'}
    
    def _calculate_momentum_signals(self, returns: pd.DataFrame) -> pd.Series:
        """Calculate momentum signals for each asset."""
        momentum_signals = {}
        
        for col in returns.columns:
            # Calculate momentum over different periods
            momentum_5 = returns[col].rolling(5).mean()
            momentum_20 = returns[col].rolling(20).mean()
            momentum_60 = returns[col].rolling(60).mean()
            
            # Combined momentum signal
            combined_momentum = (
                0.5 * momentum_5.iloc[-1] +
                0.3 * momentum_20.iloc[-1] +
                0.2 * momentum_60.iloc[-1]
            )
            
            momentum_signals[col] = combined_momentum
        
        return pd.Series(momentum_signals)
    
    def _optimize_with_regime_constraints(self, expected_returns: np.ndarray,
                                        cov_matrix: np.ndarray,
                                        regime_params: Dict) -> np.ndarray:
        """Optimize with regime-specific constraints."""
        n_assets = len(expected_returns)
        
        # Objective function: maximize utility
        def objective(weights):
            weights = np.array(weights)
            portfolio_return = np.sum(weights * expected_returns)
            portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)
            
            # Utility function with regime-specific risk aversion
            utility = portfolio_return - 0.5 * regime_params['risk_aversion'] * portfolio_vol**2
            return -utility  # Minimize negative utility
        
        # Constraints
        bounds = [(self.idx_params['min_position_size'], 
                  self.idx_params['max_position_size'])] * n_assets
        
        # Volatility constraint
        def volatility_constraint(weights):
            portfolio_vol = np.sqrt(weights.T @ cov_matrix @ weights)
            return regime_params['target_vol'] - portfolio_vol
        
        # Initial weights
        initial_weights = np.array([1/n_assets] * n_assets)
        
        # Optimize
        result = minimize(
            objective,
            initial_weights,
            method='SLSQP',
            bounds=bounds,
            constraints=[
                {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                {'type': 'ineq', 'fun': volatility_constraint}
            ],
            options={'maxiter': self.optimization_params['max_iterations']}
        )
        
        if result.success:
            return result.x / np.sum(result.x)
        else:
            # Fallback to equal weights
            return np.array([1/n_assets] * n_assets)
    
    def _calculate_portfolio_metrics(self, returns: pd.DataFrame, 
                                   weights: np.ndarray) -> Dict:
        """Calculate comprehensive portfolio metrics."""
        try:
            # Portfolio returns
            portfolio_returns = (returns * weights).sum(axis=1)
            
            # Basic metrics
            annualized_return = portfolio_returns.mean() * 252
            annualized_vol = portfolio_returns.std() * np.sqrt(252)
            sharpe_ratio = (annualized_return - self.risk_free_rate) / annualized_vol
            
            # Downside metrics
            downside_returns = portfolio_returns[portfolio_returns < 0]
            downside_deviation = downside_returns.std() * np.sqrt(252)
            sortino_ratio = (annualized_return - self.risk_free_rate) / downside_deviation
            
            # Maximum drawdown
            cumulative_returns = (1 + portfolio_returns).cumprod()
            rolling_max = cumulative_returns.expanding().max()
            drawdown = (cumulative_returns - rolling_max) / rolling_max
            max_drawdown = drawdown.min()
            
            # Value at Risk
            var_95 = np.percentile(portfolio_returns, 5)
            var_99 = np.percentile(portfolio_returns, 1)
            
            # Conditional Value at Risk
            cvar_95 = portfolio_returns[portfolio_returns <= var_95].mean()
            cvar_99 = portfolio_returns[portfolio_returns <= var_99].mean()
            
            # Diversification ratio
            individual_vols = returns.std() * np.sqrt(252)
            portfolio_vol_naive = np.sum(weights * individual_vols)
            diversification_ratio = portfolio_vol_naive / annualized_vol
            
            return {
                'annualized_return': annualized_return,
                'annualized_volatility': annualized_vol,
                'sharpe_ratio': sharpe_ratio,
                'sortino_ratio': sortino_ratio,
                'max_drawdown': max_drawdown,
                'var_95': var_95,
                'var_99': var_99,
                'cvar_95': cvar_95,
                'cvar_99': cvar_99,
                'diversification_ratio': diversification_ratio,
                'weights': dict(zip(returns.columns, weights))
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            return {}
    
    def compare_optimization_methods(self, symbols: List[str], 
                                   market_caps: Dict[str, float] = None,
                                   views: Dict[str, float] = None,
                                   regime: str = 'UNKNOWN') -> Dict:
        """
        Compare different optimization methods.
        
        Args:
            symbols: List of stock symbols
            market_caps: Market capitalizations for Black-Litterman
            views: Return views for Black-Litterman
            regime: Current market regime
            
        Returns:
            Dictionary with comparison results
        """
        # Get returns data
        returns = self.get_returns_data(symbols)
        if returns.empty:
            return {'error': 'No returns data available'}
        
        comparison = {}
        
        # Run different optimization methods
        methods = {
            'risk_parity': self.risk_parity_optimization,
            'hierarchical_risk_parity': self.hierarchical_risk_parity,
            'kelly_criterion': self.kelly_criterion_optimization,
            'regime_dependent': lambda r: self.regime_dependent_optimization(r, regime)
        }
        
        # Add Black-Litterman if market caps provided
        if market_caps is not None:
            methods['black_litterman'] = lambda r: self.black_litterman_optimization(r, market_caps, views)
        
        # Run optimizations
        for method_name, method_func in methods.items():
            try:
                result = method_func(returns)
                if 'error' not in result:
                    comparison[method_name] = result
                else:
                    comparison[method_name] = {'error': result['error']}
            except Exception as e:
                comparison[method_name] = {'error': str(e)}
        
        # Compare performance
        if len(comparison) > 1:
            comparison['performance_comparison'] = self._compare_performance(comparison)
        
        return comparison
    
    def _compare_performance(self, results: Dict) -> Dict:
        """Compare performance across optimization methods."""
        comparison = {}
        
        for method, result in results.items():
            if 'error' not in result and 'portfolio_metrics' in result:
                metrics = result['portfolio_metrics']
                comparison[method] = {
                    'sharpe_ratio': metrics.get('sharpe_ratio', 0),
                    'sortino_ratio': metrics.get('sortino_ratio', 0),
                    'max_drawdown': metrics.get('max_drawdown', 0),
                    'diversification_ratio': metrics.get('diversification_ratio', 0),
                    'annualized_return': metrics.get('annualized_return', 0),
                    'annualized_volatility': metrics.get('annualized_volatility', 0)
                }
        
        return comparison
