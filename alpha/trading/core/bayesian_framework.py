#!/usr/bin/env python3
"""
Bayesian Framework Module

This module provides Bayesian methods for:
1. Strategy evaluation with proper uncertainty quantification
2. Indicator selection with false discovery rate control
3. Robust performance estimation with credible intervals
4. Principled parameter estimation under uncertainty

These methods enable more rigorous statistical validation of trading strategies
than traditional frequentist approaches, providing a clearer picture of what
actually works versus statistical flukes.
"""

import numpy as np
import pandas as pd
import logging
from datetime import datetime
import os
import time
import math
from scipy import stats

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import PyMC for Bayesian inference
try:
    import pymc as pm
    import arviz as az
    PYMC_AVAILABLE = True
    logger.info("PyMC available - using full Bayesian inference capabilities")
except ImportError:
    PYMC_AVAILABLE = False
    logger.warning("PyMC not available - using simplified Bayesian methods")


class BayesianFramework:
    """
    Provides Bayesian methods for trading strategy analysis and development.
    """
    
    def __init__(self, db_path=None):
        """
        Initialize the Bayesian framework.
        
        Args:
            db_path (str, optional): Path to historical database for data retrieval
        """
        self.db_path = db_path
        
        # Default parameters for MCMC sampling
        self.mcmc_samples = 2000
        self.mcmc_tune = 1000
        self.mcmc_chains = 2
        self.mcmc_cores = 1  # Using multiple cores can be unstable in some environments
        
        # Default significance threshold
        self.significance_threshold = 0.95  # 95% probability
        
        # Create output directory for inference results
        self.output_dir = "data/bayesian"
        os.makedirs(self.output_dir, exist_ok=True)
    
    def bayesian_strategy_test(self, returns, benchmark_returns=None, risk_free_rate=0.0):
        """
        Perform Bayesian hypothesis testing on strategy returns.
        
        Args:
            returns (array-like): Strategy returns (daily/weekly percentage returns)
            benchmark_returns (array-like, optional): Benchmark returns for comparison
            risk_free_rate (float): Risk-free rate for Sharpe ratio calculation
            
        Returns:
            dict: Dictionary with Bayesian inference results
        """
        if PYMC_AVAILABLE:
            return self._bayesian_test_pymc(returns, benchmark_returns, risk_free_rate)
        else:
            return self._bayesian_test_simplified(returns, benchmark_returns, risk_free_rate)
    
    def _bayesian_test_pymc(self, returns, benchmark_returns=None, risk_free_rate=0.0):
        """
        Perform full Bayesian inference using PyMC.
        
        Args:
            returns (array-like): Strategy returns
            benchmark_returns (array-like, optional): Benchmark returns for comparison
            risk_free_rate (float): Risk-free rate for Sharpe ratio calculation
            
        Returns:
            dict: Dictionary with Bayesian inference results
        """
        start_time = time.time()
        
        # For excess returns, we subtract benchmark or risk-free rate
        if benchmark_returns is not None:
            excess_returns = np.array(returns) - np.array(benchmark_returns)
        else:
            excess_returns = np.array(returns) - risk_free_rate
        
        try:
            with pm.Model() as model:
                # Prior for the mean return (weakly informative)
                mu = pm.Normal("mu", mu=0, sigma=0.05)
                
                # Prior for the standard deviation (half-normal to ensure positive)
                sigma = pm.HalfNormal("sigma", sigma=0.10)
                
                # Likelihood: returns are normally distributed
                returns_obs = pm.Normal("returns_obs", mu=mu, sigma=sigma, observed=excess_returns)
                
                # Sharpe ratio as a deterministic variable
                sharpe = pm.Deterministic("sharpe", mu / sigma)
                
                # Sample from the posterior using NUTS (No U-Turn Sampler)
                trace = pm.sample(
                    self.mcmc_samples, 
                    tune=self.mcmc_tune, 
                    chains=self.mcmc_chains,
                    cores=self.mcmc_cores
                )
            
            # Extract results
            mu_samples = trace['mu']
            sigma_samples = trace['sigma']
            sharpe_samples = trace['sharpe']
            
            # Calculate summary statistics
            mean_return = float(mu_samples.mean())
            std_return = float(sigma_samples.mean())
            sharpe_ratio = float(sharpe_samples.mean())
            
            # Calculate credible intervals (highest posterior density intervals)
            mu_hpdi = az.hdi(mu_samples, hdi_prob=0.95)
            sharpe_hpdi = az.hdi(sharpe_samples, hdi_prob=0.95)
            
            # Calculate probability of positive mean return
            prob_positive = (mu_samples > 0).mean()
            
            # Calculate probability of positive Sharpe ratio
            prob_positive_sharpe = (sharpe_samples > 0).mean()
            
            # Determine if result is "significant" based on threshold
            significant = prob_positive > self.significance_threshold
            
            computation_time = time.time() - start_time
            logger.info(f"Bayesian inference completed in {computation_time:.2f} seconds")
            
            # Return summary of inference
            return {
                'mean_estimate': mean_return,
                'mean_hpdi': (float(mu_hpdi[0]), float(mu_hpdi[1])),
                'sigma_estimate': std_return,
                'sharpe_estimate': sharpe_ratio,
                'sharpe_hpdi': (float(sharpe_hpdi[0]), float(sharpe_hpdi[1])),
                'prob_positive': prob_positive,
                'prob_positive_sharpe': prob_positive_sharpe,
                'significant': significant,
                'sample_size': len(returns),
                'computation_time': computation_time
            }
            
        except Exception as e:
            logger.error(f"Error in Bayesian inference: {e}")
            return self._bayesian_test_simplified(returns, benchmark_returns, risk_free_rate)
    
    def _bayesian_test_simplified(self, returns, benchmark_returns=None, risk_free_rate=0.0):
        """
        Perform simplified Bayesian inference when PyMC is not available.
        Uses analytical solutions for conjugate priors where possible.
        
        Args:
            returns (array-like): Strategy returns
            benchmark_returns (array-like, optional): Benchmark returns for comparison
            risk_free_rate (float): Risk-free rate for Sharpe ratio calculation
            
        Returns:
            dict: Dictionary with simplified Bayesian inference results
        """
        start_time = time.time()
        
        # For excess returns, we subtract benchmark or risk-free rate
        if benchmark_returns is not None:
            excess_returns = np.array(returns) - np.array(benchmark_returns)
        else:
            excess_returns = np.array(returns) - risk_free_rate
        
        # Sample statistics
        sample_mean = np.mean(excess_returns)
        sample_std = np.std(excess_returns, ddof=1)  # Using n-1 for unbiased estimation
        sample_size = len(excess_returns)
        
        # Prior parameters (weakly informative)
        prior_mean = 0.0
        prior_precision = 400.0  # Equivalent to prior_std = 0.05
        
        # Posterior parameters for mean (normal distribution)
        precision_data = sample_size / (sample_std**2) if sample_std > 0 else 0
        posterior_precision = prior_precision + precision_data
        posterior_mean = (prior_precision * prior_mean + precision_data * sample_mean) / posterior_precision
        posterior_std = 1.0 / np.sqrt(posterior_precision)
        
        # Calculate credible interval for mean
        ci_lower = stats.norm.ppf(0.025, loc=posterior_mean, scale=posterior_std)
        ci_upper = stats.norm.ppf(0.975, loc=posterior_mean, scale=posterior_std)
        
        # Calculate probability of positive mean return
        prob_positive = 1.0 - stats.norm.cdf(0, loc=posterior_mean, scale=posterior_std)
        
        # Approximate Sharpe ratio posterior
        # This is a rough approximation since the actual distribution is more complex
        sharpe_est = posterior_mean / sample_std if sample_std > 0 else 0
        sharpe_std = np.sqrt((1 + sharpe_est**2/2) / sample_size)  # Approximation
        
        # Calculate credible interval for Sharpe
        sharpe_ci_lower = stats.norm.ppf(0.025, loc=sharpe_est, scale=sharpe_std)
        sharpe_ci_upper = stats.norm.ppf(0.975, loc=sharpe_est, scale=sharpe_std)
        
        # Calculate probability of positive Sharpe ratio
        prob_positive_sharpe = 1.0 - stats.norm.cdf(0, loc=sharpe_est, scale=sharpe_std)
        
        # Determine if result is "significant" based on threshold
        significant = prob_positive > self.significance_threshold
        
        computation_time = time.time() - start_time
        
        return {
            'mean_estimate': float(posterior_mean),
            'mean_hpdi': (float(ci_lower), float(ci_upper)),
            'sigma_estimate': float(sample_std),  # Using sample std for simplicity
            'sharpe_estimate': float(sharpe_est),
            'sharpe_hpdi': (float(sharpe_ci_lower), float(sharpe_ci_upper)),
            'prob_positive': float(prob_positive),
            'prob_positive_sharpe': float(prob_positive_sharpe),
            'significant': significant,
            'sample_size': sample_size,
            'computation_time': computation_time,
            'note': 'Using simplified Bayesian inference (PyMC not available)'
        }
    
    def bayesian_indicator_evaluation(self, indicator_data, historical_returns):
        """
        Evaluate technical indicators using Bayesian methods.
        
        Args:
            indicator_data (dict): Dictionary of indicators with their values
            historical_returns (array-like): Corresponding historical returns
            
        Returns:
            dict: Dictionary of indicators with their Bayesian evaluation metrics
        """
        results = {}
        
        # Process each indicator
        for indicator, values in indicator_data.items():
            # Skip indicators with insufficient data
            if len(values) < 10:
                continue
                
            try:
                # Align indicator values with returns
                aligned_data = pd.DataFrame({
                    'indicator': values,
                    'returns': historical_returns
                }).dropna()
                
                if len(aligned_data) < 10:
                    continue
                
                # For classification indicators (e.g., buy/sell signals)
                if set(aligned_data['indicator'].unique()) == {0, 1}:
                    results[indicator] = self._evaluate_binary_indicator(
                        aligned_data['indicator'], aligned_data['returns'])
                # For continuous indicators
                else:
                    results[indicator] = self._evaluate_continuous_indicator(
                        aligned_data['indicator'], aligned_data['returns'])
            
            except Exception as e:
                logger.error(f"Error evaluating indicator {indicator}: {e}")
        
        return results
    
    def _evaluate_binary_indicator(self, signals, returns):
        """
        Evaluate a binary (0/1) indicator using Bayesian methods.
        
        Args:
            signals (array-like): Binary signals (0 or 1)
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        if PYMC_AVAILABLE:
            return self._evaluate_binary_pymc(signals, returns)
        else:
            return self._evaluate_binary_simplified(signals, returns)
    
    def _evaluate_binary_pymc(self, signals, returns):
        """
        Evaluate binary indicator using PyMC.
        
        Args:
            signals (array-like): Binary signals (0 or 1)
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        # Convert to numpy arrays
        signals = np.array(signals)
        returns = np.array(returns)
        
        # Split returns by signal
        signal_returns = returns[signals == 1]
        no_signal_returns = returns[signals == 0]
        
        try:
            with pm.Model() as model:
                # Priors for signal and no-signal returns
                mu_signal = pm.Normal("mu_signal", mu=0, sigma=0.05)
                sigma_signal = pm.HalfNormal("sigma_signal", sigma=0.10)
                
                mu_no_signal = pm.Normal("mu_no_signal", mu=0, sigma=0.05)
                sigma_no_signal = pm.HalfNormal("sigma_no_signal", sigma=0.10)
                
                # Likelihoods
                if len(signal_returns) > 0:
                    signal_obs = pm.Normal("signal_obs", mu=mu_signal, sigma=sigma_signal, 
                                         observed=signal_returns)
                
                if len(no_signal_returns) > 0:
                    no_signal_obs = pm.Normal("no_signal_obs", mu=mu_no_signal, sigma=sigma_no_signal, 
                                            observed=no_signal_returns)
                
                # Difference in means
                diff = pm.Deterministic("diff", mu_signal - mu_no_signal)
                
                # Sample
                trace = pm.sample(
                    self.mcmc_samples, 
                    tune=self.mcmc_tune, 
                    chains=self.mcmc_chains,
                    cores=self.mcmc_cores
                )
            
            # Extract results
            diff_samples = trace['diff']
            
            # Calculate probability that signal outperforms no-signal
            prob_outperformance = (diff_samples > 0).mean()
            
            # Calculate mean difference
            mean_diff = diff_samples.mean()
            
            # Calculate credible interval for difference
            diff_hpdi = az.hdi(diff_samples, hdi_prob=0.95)
            
            return {
                'prob_effectiveness': float(prob_outperformance),
                'mean_diff': float(mean_diff),
                'diff_hpdi': (float(diff_hpdi[0]), float(diff_hpdi[1])),
                'significant': prob_outperformance > self.significance_threshold,
                'signal_obs': len(signal_returns),
                'no_signal_obs': len(no_signal_returns)
            }
            
        except Exception as e:
            logger.error(f"Error in PyMC evaluation of binary indicator: {e}")
            return self._evaluate_binary_simplified(signals, returns)
    
    def _evaluate_binary_simplified(self, signals, returns):
        """
        Evaluate binary indicator using simplified Bayesian methods.
        
        Args:
            signals (array-like): Binary signals (0 or 1)
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        # Convert to numpy arrays
        signals = np.array(signals)
        returns = np.array(returns)
        
        # Split returns by signal
        signal_returns = returns[signals == 1]
        no_signal_returns = returns[signals == 0]
        
        # Skip if any group has no observations
        if len(signal_returns) == 0 or len(no_signal_returns) == 0:
            return {
                'prob_effectiveness': 0.5,
                'mean_diff': 0.0,
                'diff_hpdi': (0.0, 0.0),
                'significant': False,
                'signal_obs': len(signal_returns),
                'no_signal_obs': len(no_signal_returns),
                'error': 'Insufficient data in one or both groups'
            }
        
        # Calculate sample statistics
        signal_mean = np.mean(signal_returns)
        signal_std = np.std(signal_returns, ddof=1)
        signal_n = len(signal_returns)
        
        no_signal_mean = np.mean(no_signal_returns)
        no_signal_std = np.std(no_signal_returns, ddof=1)
        no_signal_n = len(no_signal_returns)
        
        # Calculate pooled standard deviation
        pooled_std = np.sqrt(((signal_n - 1) * signal_std**2 + 
                              (no_signal_n - 1) * no_signal_std**2) / 
                             (signal_n + no_signal_n - 2))
        
        # Calculate standard error of difference
        se_diff = pooled_std * np.sqrt(1/signal_n + 1/no_signal_n)
        
        # Calculate mean difference
        mean_diff = signal_mean - no_signal_mean
        
        # Calculate credible interval for difference
        diff_lower = mean_diff - 1.96 * se_diff
        diff_upper = mean_diff + 1.96 * se_diff
        
        # Calculate probability that signal outperforms no-signal
        prob_outperformance = 1.0 - stats.norm.cdf(0, loc=mean_diff, scale=se_diff)
        
        return {
            'prob_effectiveness': float(prob_outperformance),
            'mean_diff': float(mean_diff),
            'diff_hpdi': (float(diff_lower), float(diff_upper)),
            'significant': prob_outperformance > self.significance_threshold,
            'signal_obs': signal_n,
            'no_signal_obs': no_signal_n
        }
    
    def _evaluate_continuous_indicator(self, indicator_values, returns):
        """
        Evaluate a continuous indicator using Bayesian regression.
        
        Args:
            indicator_values (array-like): Continuous indicator values
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        if PYMC_AVAILABLE:
            return self._evaluate_continuous_pymc(indicator_values, returns)
        else:
            return self._evaluate_continuous_simplified(indicator_values, returns)
    
    def _evaluate_continuous_pymc(self, indicator_values, returns):
        """
        Evaluate continuous indicator using PyMC.
        
        Args:
            indicator_values (array-like): Continuous indicator values
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        # Normalize indicator values for better sampling
        indicator_mean = np.mean(indicator_values)
        indicator_std = np.std(indicator_values)
        if indicator_std > 0:
            indicator_norm = (indicator_values - indicator_mean) / indicator_std
        else:
            indicator_norm = indicator_values - indicator_mean
        
        try:
            with pm.Model() as model:
                # Priors for regression coefficients
                intercept = pm.Normal("intercept", mu=0, sigma=0.05)
                beta = pm.Normal("beta", mu=0, sigma=0.1)
                
                # Prior for observation error
                sigma = pm.HalfNormal("sigma", sigma=0.1)
                
                # Expected value
                mu = intercept + beta * indicator_norm
                
                # Likelihood
                returns_obs = pm.Normal("returns_obs", mu=mu, sigma=sigma, observed=returns)
                
                # Sample
                trace = pm.sample(
                    self.mcmc_samples, 
                    tune=self.mcmc_tune, 
                    chains=self.mcmc_chains,
                    cores=self.mcmc_cores
                )
            
            # Extract results
            beta_samples = trace['beta']
            
            # Calculate probability that indicator has positive effect
            prob_positive = (beta_samples > 0).mean()
            
            # Calculate mean effect
            mean_beta = beta_samples.mean()
            
            # Calculate credible interval for beta
            beta_hpdi = az.hdi(beta_samples, hdi_prob=0.95)
            
            # Calculate R-squared using mean parameters
            intercept_mean = trace['intercept'].mean()
            sigma_mean = trace['sigma'].mean()
            
            mu_pred = intercept_mean + mean_beta * indicator_norm
            ss_total = np.sum((returns - np.mean(returns))**2)
            ss_residual = np.sum((returns - mu_pred)**2)
            r_squared = 1 - (ss_residual / ss_total)
            
            return {
                'prob_positive_effect': float(prob_positive),
                'mean_effect': float(mean_beta),
                'effect_hpdi': (float(beta_hpdi[0]), float(beta_hpdi[1])),
                'r_squared': float(r_squared),
                'significant': prob_positive > self.significance_threshold or prob_positive < (1 - self.significance_threshold),
                'observations': len(returns)
            }
            
        except Exception as e:
            logger.error(f"Error in PyMC evaluation of continuous indicator: {e}")
            return self._evaluate_continuous_simplified(indicator_values, returns)
    
    def _evaluate_continuous_simplified(self, indicator_values, returns):
        """
        Evaluate continuous indicator using simplified Bayesian methods.
        
        Args:
            indicator_values (array-like): Continuous indicator values
            returns (array-like): Corresponding returns
            
        Returns:
            dict: Evaluation metrics
        """
        # Normalize indicator values
        indicator_mean = np.mean(indicator_values)
        indicator_std = np.std(indicator_values)
        if indicator_std > 0:
            indicator_norm = (indicator_values - indicator_mean) / indicator_std
        else:
            indicator_norm = indicator_values - indicator_mean
        
        # Fit OLS regression
        X = np.column_stack((np.ones_like(indicator_norm), indicator_norm))
        beta_hat, _, _, _ = np.linalg.lstsq(X, returns, rcond=None)
        
        # Extract intercept and slope
        intercept_hat, beta_hat = beta_hat
        
        # Calculate residuals and standard error
        y_pred = intercept_hat + beta_hat * indicator_norm
        residuals = returns - y_pred
        sigma_hat = np.sqrt(np.sum(residuals**2) / (len(returns) - 2))
        
        # Calculate standard error of beta
        se_beta = sigma_hat / np.sqrt(np.sum((indicator_norm - np.mean(indicator_norm))**2))
        
        # Calculate credible interval for beta
        beta_lower = beta_hat - 1.96 * se_beta
        beta_upper = beta_hat + 1.96 * se_beta
        
        # Calculate probability that beta is positive
        prob_positive = 1.0 - stats.norm.cdf(0, loc=beta_hat, scale=se_beta)
        
        # Calculate R-squared
        ss_total = np.sum((returns - np.mean(returns))**2)
        ss_residual = np.sum(residuals**2)
        r_squared = 1 - (ss_residual / ss_total)
        
        return {
            'prob_positive_effect': float(prob_positive),
            'mean_effect': float(beta_hat),
            'effect_hpdi': (float(beta_lower), float(beta_upper)),
            'r_squared': float(r_squared),
            'significant': prob_positive > self.significance_threshold or prob_positive < (1 - self.significance_threshold),
            'observations': len(returns)
        }
    
    def multiple_hypothesis_correction(self, strategy_results):
        """
        Apply false discovery rate control for multiple hypothesis testing.
        
        Args:
            strategy_results (dict): Dictionary of strategy test results
            
        Returns:
            dict: Corrected results dictionary
        """
        # Import here to avoid dependency issues
        try:
            from statsmodels.stats.multitest import multipletests
            
            # Extract strategy names and p-values
            strategies = []
            p_values = []
            
            for strategy_name, result in strategy_results.items():
                # Get p-value (1 - probability of positive effect)
                if 'prob_positive' in result:
                    p_value = 1.0 - result['prob_positive']
                elif 'prob_positive_effect' in result:
                    p_value = 1.0 - result['prob_positive_effect']
                elif 'prob_effectiveness' in result:
                    p_value = 1.0 - result['prob_effectiveness']
                else:
                    # Skip if no probability measure is available
                    continue
                
                strategies.append(strategy_name)
                p_values.append(p_value)
            
            if not p_values:
                logger.warning("No valid p-values found for multiple testing correction")
                return strategy_results
            
            # Apply Benjamini-Hochberg procedure
            rejected, corrected_p_values, _, _ = multipletests(p_values, method='fdr_bh')
            
            # Update results with corrected values
            corrected_results = strategy_results.copy()
            for i, strategy_name in enumerate(strategies):
                if 'prob_positive' in corrected_results[strategy_name]:
                    corrected_results[strategy_name]['prob_positive_corrected'] = 1.0 - corrected_p_values[i]
                    corrected_results[strategy_name]['significant_corrected'] = rejected[i]
                elif 'prob_positive_effect' in corrected_results[strategy_name]:
                    corrected_results[strategy_name]['prob_positive_effect_corrected'] = 1.0 - corrected_p_values[i]
                    corrected_results[strategy_name]['significant_corrected'] = rejected[i]
                elif 'prob_effectiveness' in corrected_results[strategy_name]:
                    corrected_results[strategy_name]['prob_effectiveness_corrected'] = 1.0 - corrected_p_values[i]
                    corrected_results[strategy_name]['significant_corrected'] = rejected[i]
            
            logger.info(f"Applied multiple hypothesis correction to {len(p_values)} tests")
            logger.info(f"Significant before correction: {sum(result.get('significant', False) for result in strategy_results.values())}")
            logger.info(f"Significant after correction: {sum(rejected)}")
            
            return corrected_results
            
        except ImportError:
            logger.warning("statsmodels not available for multiple testing correction")
            return strategy_results
        except Exception as e:
            logger.error(f"Error in multiple hypothesis correction: {e}")
            return strategy_results
    
    def kelly_criterion_with_uncertainty(self, win_rate, win_loss_ratio, sample_size, 
                                        market_regime='UNKNOWN', discount_factor=0.5):
        """
        Calculate the Kelly Criterion with statistical uncertainty adjustment.
        
        Args:
            win_rate (float): Win probability (0-1)
            win_loss_ratio (float): Ratio of average win to average loss
            sample_size (int): Number of trades used to estimate win_rate
            market_regime (str): Current market regime
            discount_factor (float): Conservative adjustment (e.g., Half-Kelly = 0.5)
            
        Returns:
            float: Optimal Kelly fraction adjusted for uncertainty
        """
        # Basic Kelly formula
        kelly_f = win_rate - ((1 - win_rate) / win_loss_ratio)
        
        # Uncertainty adjustment based on sample size
        # Using normal approximation to binomial confidence interval
        if sample_size > 0:
            z = stats.norm.ppf(0.95)  # 95% confidence
            uncertainty = z * math.sqrt((win_rate * (1 - win_rate)) / sample_size)
        else:
            uncertainty = 0.0
        
        # Apply market regime adjustment
        regime_factor = {
            'BULL_TREND': 1.0, 
            'BEAR_TREND': 0.7, 
            'HIGH_VOLATILITY': 0.5, 
            'RANGE_BOUND': 0.8,
            'UNKNOWN': 0.9
        }.get(market_regime, 0.9)
        
        # Apply conservative Kelly (half-Kelly by default) with uncertainty discount
        adjusted_kelly = max(0, (kelly_f - uncertainty) * discount_factor * regime_factor)
        
        logger.debug(f"Kelly calculation: basic={kelly_f:.4f}, uncertainty={uncertainty:.4f}, "
                    f"regime_factor={regime_factor}, adjusted={adjusted_kelly:.4f}")
        
        return adjusted_kelly

# Example usage for demonstration
if __name__ == "__main__":
    # Create a Bayesian Framework instance
    framework = BayesianFramework()
    
    # Generate some synthetic returns for testing
    np.random.seed(42)
    strategy_returns = np.random.normal(0.001, 0.01, 252)  # 1 year of daily returns
    benchmark_returns = np.random.normal(0.0005, 0.008, 252)  # Benchmark returns
    
    # Test Bayesian strategy evaluation
    result = framework.bayesian_strategy_test(strategy_returns, benchmark_returns)
    
    print("\nBayesian Strategy Evaluation Results:")
    print(f"Mean return estimate: {result['mean_estimate']:.5f}")
    print(f"95% credible interval: ({result['mean_hpdi'][0]:.5f}, {result['mean_hpdi'][1]:.5f})")
    print(f"Probability of positive return: {result['prob_positive']:.1%}")
    print(f"Significant: {result['significant']}")
    
    # Test Kelly criterion with uncertainty
    kelly = framework.kelly_criterion_with_uncertainty(0.55, 1.5, 100, 'BULL_TREND')
    print(f"\nKelly criterion with uncertainty: {kelly:.2%}")