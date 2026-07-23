#!/usr/bin/env python3
# Filename: src/core/bayesian_structural.py
"""
Bayesian Structural Time Series Module

This module provides time series modeling capabilities using Bayesian methods:
1. Structural time series decomposition (trend, seasonality, regression)
2. Probabilistic forecasting with uncertainty quantification
3. Causal impact analysis for intervention assessment
4. Automatic feature selection and model averaging

These methods offer advantages over traditional ARIMA and other models by
incorporating prior knowledge, handling missing data, and providing full
posterior distributions instead of point estimates.
"""

import numpy as np
import pandas as pd
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union, Optional, Any, Callable

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import Bayesian modeling libraries
try:
    import pymc as pm
    import arviz as az
    PYMC_AVAILABLE = True
    logger.info("PyMC available for Bayesian structural time series modeling")
except ImportError:
    PYMC_AVAILABLE = False
    logger.warning("PyMC not available. Some Bayesian modeling capabilities will be limited.")

# Try to import statsmodels for structural time series components
try:
    import statsmodels.api as sm
    from statsmodels.tsa.statespace.structural import UnobservedComponents
    STATSMODELS_AVAILABLE = True
    logger.info("statsmodels available for structural time series components")
except ImportError:
    STATSMODELS_AVAILABLE = False
    logger.warning("statsmodels not available. Some modeling capabilities will be limited.")

# Try to import TensorFlow Probability for advanced modeling
try:
    import tensorflow as tf
    import tensorflow_probability as tfp
    TFP_AVAILABLE = True
    logger.info("TensorFlow Probability available for advanced Bayesian modeling")
except ImportError:
    TFP_AVAILABLE = False
    logger.debug("TensorFlow Probability not available. Using alternative implementations.")

class BayesianStructuralTS:
    """
    Bayesian Structural Time Series modeling for financial data.
    """
    
    def __init__(self, output_dir: str = "data/bayesian_ts"):
        """
        Initialize the Bayesian Structural Time Series model.
        
        Args:
            output_dir: Directory for saving models and results
        """
        self.output_dir = output_dir
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize model components
        self.model = None
        self.trace = None
        self.components = None
        self.data = None
        self.date_index = None
        
        # Model configuration
        self.config = {
            'trend': True,
            'seasonality': False,
            'cycle': False,
            'regression': False,
            'auto_regression': False,
            'standardize': True,
            'season_length': 5,  # Trading days in a week
            'n_seasons': 52,     # Weeks in a year
            'cycle_period': 252  # Trading days in a year
        }
        
        # Additional parameters
        self.forecast_periods = 30
        self.credible_interval = 0.95
        self.last_fitted_date = None
        
    def set_config(self, config: Dict[str, Any]) -> None:
        """
        Set model configuration.
        
        Args:
            config: Dictionary with configuration parameters
        """
        self.config.update(config)
        logger.info(f"Updated model configuration: {self.config}")
    
    def prepare_data(self, data: pd.DataFrame, 
                    target_col: str,
                    exog_cols: Optional[List[str]] = None,
                    standardize: Optional[bool] = None) -> Dict[str, np.ndarray]:
        """
        Prepare data for Bayesian structural time series modeling.
        
        Args:
            data: DataFrame with time series data
            target_col: Name of target column
            exog_cols: List of exogenous (predictor) variables
            standardize: Whether to standardize data (overrides config)
            
        Returns:
            dict: Dictionary with prepared data arrays
        """
        # Check for datetime index
        if not isinstance(data.index, pd.DatetimeIndex):
            logger.warning("DataFrame does not have DatetimeIndex. Using integer index.")
            self.date_index = None
        else:
            self.date_index = data.index.copy()
        
        # Extract target series
        y = data[target_col].values
        
        # Handle missing values
        if np.isnan(y).any():
            logger.warning("Target series contains missing values. Interpolating.")
            y_series = pd.Series(y)
            y = y_series.interpolate(method='linear').values
        
        # Store original data for reference
        y_orig = y.copy()
        
        # Determine whether to standardize
        if standardize is None:
            standardize = self.config['standardize']
        
        # Standardize if requested
        if standardize:
            self.y_mean = np.mean(y)
            self.y_std = np.std(y)
            
            if self.y_std > 0:
                y = (y - self.y_mean) / self.y_std
            else:
                logger.warning("Standard deviation is zero. Not standardizing.")
                standardize = False
        else:
            self.y_mean = 0.0
            self.y_std = 1.0
        
        # Prepare exogenous variables if provided
        X = None
        X_names = None
        
        if exog_cols and len(exog_cols) > 0:
            X = data[exog_cols].values
            X_names = exog_cols
            
            # Handle missing values in exogenous variables
            if np.isnan(X).any():
                logger.warning("Exogenous variables contain missing values. Interpolating.")
                X_df = pd.DataFrame(X, columns=exog_cols)
                X = X_df.interpolate(method='linear').values
            
            # Standardize exogenous variables
            if standardize:
                self.X_mean = np.mean(X, axis=0)
                self.X_std = np.std(X, axis=0)
                
                # Only standardize columns with non-zero standard deviation
                valid_cols = self.X_std > 0
                X[:, valid_cols] = (X[:, valid_cols] - self.X_mean[valid_cols]) / self.X_std[valid_cols]
        
        # Store data
        self.data = {
            'y': y,
            'y_orig': y_orig,
            'X': X,
            'X_names': X_names,
            'standardized': standardize,
            'target_col': target_col
        }
        
        # Store last date
        if self.date_index is not None:
            self.last_fitted_date = self.date_index[-1]
            
        logger.info(f"Prepared data with {len(y)} observations")
        if X is not None:
            logger.info(f"Included {X.shape[1]} exogenous variables")
            
        return self.data
    
    def build_model_pymc(self) -> None:
        """
        Build Bayesian structural time series model using PyMC.
        """
        if not PYMC_AVAILABLE:
            logger.error("PyMC not available for model building")
            return
            
        if self.data is None:
            logger.error("Data not prepared. Call prepare_data() first.")
            return
        
        logger.info("Building Bayesian structural time series model with PyMC")
        
        # Extract data
        y = self.data['y']
        X = self.data['X']
        n_obs = len(y)
        
        # Create PyMC model
        with pm.Model() as model:
            # --- Trend component ---
            if self.config['trend']:
                # Local level model (random walk)
                level_scale = pm.HalfCauchy('level_scale', beta=0.1)
                trend = pm.GaussianRandomWalk('trend', sigma=level_scale, shape=n_obs)
            else:
                # No trend - use constant level
                level = pm.Normal('level', mu=0, sigma=1)
                trend = pm.Deterministic('trend', level * np.ones(n_obs))
            
            # --- Seasonal component ---
            if self.config['seasonality']:
                season_length = self.config['season_length']
                n_seasons = min(self.config['n_seasons'], n_obs // season_length)
                
                # Fourier series approach for seasonality
                seasonal_features = np.zeros((n_obs, 2 * n_seasons))
                for j in range(n_seasons):
                    seasonal_features[:, 2*j] = np.sin(2 * np.pi * (j+1) * np.arange(n_obs) / season_length)
                    seasonal_features[:, 2*j+1] = np.cos(2 * np.pi * (j+1) * np.arange(n_obs) / season_length)
                
                # Seasonal coefficients
                seasonal_coef_sd = pm.HalfCauchy('seasonal_coef_sd', beta=0.1)
                seasonal_coef = pm.Normal('seasonal_coef', mu=0, sigma=seasonal_coef_sd, shape=2 * n_seasons)
                
                # Seasonal component
                seasonality = pm.Deterministic('seasonality', seasonal_features.dot(seasonal_coef))
            else:
                seasonality = 0
            
            # --- Cycle component ---
            if self.config['cycle']:
                cycle_period = self.config['cycle_period']
                
                # Cycle amplitude
                cycle_amplitude = pm.HalfNormal('cycle_amplitude', sigma=0.1)
                
                # Cycle frequency
                cycle_frequency = pm.Beta('cycle_frequency', alpha=20, beta=1.5) * (2*np.pi/cycle_period)
                
                # Initial conditions
                cycle_init = pm.Normal('cycle_init', mu=0, sigma=0.1, shape=2)
                
                # Build cycle recursively
                cycle = np.zeros(n_obs)
                cycle[0] = cycle_init[0]
                
                # Damping factor (close to 1 for slow decay)
                cycle_damping = pm.Beta('cycle_damping', alpha=18, beta=2)
                
                # Define cycle component
                for t in range(1, n_obs):
                    cycle[t] = (cycle_damping * (cycle[t-1] * np.cos(cycle_frequency) + 
                                                 cycle_init[1] * np.sin(cycle_frequency)) + 
                                 pm.Normal.dist(mu=0, sigma=0.01).random())
                
                # Scale the cycle
                cycle = cycle_amplitude * cycle
            else:
                cycle = 0
            
            # --- Regression component ---
            if self.config['regression'] and X is not None:
                n_features = X.shape[1]
                
                # Regression coefficients with sparsity prior
                reg_coef_sd = pm.HalfCauchy('reg_coef_sd', beta=0.1)
                regression_coef = pm.Normal('regression_coef', mu=0, sigma=reg_coef_sd, shape=n_features)
                
                # Regression component
                regression = pm.Deterministic('regression', X.dot(regression_coef))
            else:
                regression = 0
            
            # --- Auto-regression component ---
            if self.config['auto_regression']:
                # AR(1) process
                ar_coef = pm.Uniform('ar_coef', lower=0, upper=1)
                ar_scale = pm.HalfCauchy('ar_scale', beta=0.1)
                
                ar = np.zeros(n_obs)
                for t in range(1, n_obs):
                    ar[t] = ar_coef * ar[t-1] + pm.Normal.dist(mu=0, sigma=ar_scale).random()
                    
                autoregression = pm.Deterministic('autoregression', ar)
            else:
                autoregression = 0
            
            # --- Combine components ---
            mu = trend + seasonality + cycle + regression + autoregression
            
            # --- Observation error ---
            sigma = pm.HalfCauchy('sigma', beta=0.1)
            
            # --- Likelihood ---
            likelihood = pm.Normal('y', mu=mu, sigma=sigma, observed=y)
            
            # Store model
            self.model = model
            
            # Store components
            self.components = {
                'trend': trend,
                'seasonality': seasonality if self.config['seasonality'] else None,
                'cycle': cycle if self.config['cycle'] else None,
                'regression': regression if self.config['regression'] and X is not None else None,
                'autoregression': autoregression if self.config['auto_regression'] else None
            }
            
        logger.info("Bayesian structural time series model built successfully")
    
    def build_model_statsmodels(self) -> None:
        """
        Build structural time series model using statsmodels.
        """
        if not STATSMODELS_AVAILABLE:
            logger.error("statsmodels not available for model building")
            return
            
        if self.data is None:
            logger.error("Data not prepared. Call prepare_data() first.")
            return
            
        logger.info("Building structural time series model with statsmodels")
        
        # Extract data
        y = self.data['y']
        X = self.data['X']
        
        # Define model components
        model_components = []
        
        if self.config['trend']:
            model_components.append('local level')
        
        if self.config['seasonality']:
            season_length = self.config['season_length']
            model_components.append(f'seasonal {season_length}')
        
        if self.config['cycle']:
            model_components.append('cycle')
        
        # Build model
        model = UnobservedComponents(
            y,
            exog=X,
            level=self.config['trend'],
            seasonal=self.config['season_length'] if self.config['seasonality'] else None,
            cycle=self.config['cycle'],
            stochastic_cycle=True,
            irregular=True
        )
        
        # Store model
        self.model = model
        
        logger.info(f"Structural time series model built with components: {model_components}")
    
    def build_model_tfp(self) -> None:
        """
        Build Bayesian structural time series model using TensorFlow Probability.
        """
        if not TFP_AVAILABLE:
            logger.error("TensorFlow Probability not available for model building")
            return
            
        if self.data is None:
            logger.error("Data not prepared. Call prepare_data() first.")
            return
            
        logger.info("Building Bayesian structural time series model with TensorFlow Probability")
        
        # Extract data
        y = self.data['y']
        X = self.data['X']
        
        # Convert to TensorFlow tensors
        y_tensor = tf.convert_to_tensor(y, dtype=tf.float32)
        
        # Define model components
        components = []
        
        # Add local linear trend if trend enabled
        if self.config['trend']:
            level = tfp.sts.LocalLinearTrend(observed_time_series=y_tensor)
            components.append(level)
            
        # Add seasonality if enabled
        if self.config['seasonality']:
            season_length = self.config['season_length']
            seasonal = tfp.sts.Seasonal(
                num_seasons=season_length,
                observed_time_series=y_tensor,
                name='seasonal'
            )
            components.append(seasonal)
            
        # Add cycle if enabled
        if self.config['cycle']:
            cycle = tfp.sts.Cycle(
                observed_time_series=y_tensor,
                name='cycle'
            )
            components.append(cycle)
            
        # Add regression component if enabled and exogenous variables provided
        if self.config['regression'] and X is not None:
            X_tensor = tf.convert_to_tensor(X, dtype=tf.float32)
            regression = tfp.sts.LinearRegression(
                design_matrix=X_tensor,
                name='regression'
            )
            components.append(regression)
            
        # Add autoregression if enabled
        if self.config['auto_regression']:
            ar = tfp.sts.Autoregressive(
                order=1,
                observed_time_series=y_tensor,
                name='autoregression'
            )
            components.append(ar)
            
        # Combine components into a single model
        model = tfp.sts.Sum(components=components, observed_time_series=y_tensor)
        
        # Store model
        self.model = model
        self.components = components
        
        logger.info("Bayesian structural time series model built with TFP successfully")
    
    def fit_model(self, method: str = 'auto', **kwargs) -> Any:
        """
        Fit the Bayesian structural time series model.
        
        Args:
            method: Fitting method ('pymc', 'statsmodels', 'tfp', or 'auto')
            **kwargs: Additional arguments for fitting method
            
        Returns:
            Model fitting results
        """
        if self.model is None:
            logger.error("Model not built. Call build_model() first.")
            return None
            
        # Determine method based on available libraries if 'auto'
        if method == 'auto':
            if PYMC_AVAILABLE:
                method = 'pymc'
            elif STATSMODELS_AVAILABLE:
                method = 'statsmodels'
            elif TFP_AVAILABLE:
                method = 'tfp'
            else:
                logger.error("No suitable modeling library available")
                return None
                
        logger.info(f"Fitting model using {method} method")
        
        # Fit based on method
        if method == 'pymc':
            return self._fit_pymc(**kwargs)
        elif method == 'statsmodels':
            return self._fit_statsmodels(**kwargs)
        elif method == 'tfp':
            return self._fit_tfp(**kwargs)
        else:
            logger.error(f"Unknown fitting method: {method}")
            return None
    
    def _fit_pymc(self, draws: int = 1000, tune: int = 1000, 
                chains: int = 2, cores: int = 1, **kwargs) -> Any:
        """
        Fit model using PyMC.
        
        Args:
            draws: Number of samples to draw
            tune: Number of tuning samples
            chains: Number of chains
            cores: Number of cores to use
            **kwargs: Additional arguments for pm.sample
            
        Returns:
            PyMC sampling trace
        """
        if not PYMC_AVAILABLE:
            logger.error("PyMC not available for model fitting")
            return None
            
        try:
            with self.model:
                # Sample from posterior
                trace = pm.sample(
                    draws=draws,
                    tune=tune,
                    chains=chains,
                    cores=cores,
                    return_inferencedata=True,
                    **kwargs
                )
                
                # Store trace
                self.trace = trace
                
                logger.info(f"Model fitted successfully with {draws} samples")
                
                return trace
                
        except Exception as e:
            logger.error(f"Error fitting PyMC model: {e}")
            return None
    
    def _fit_statsmodels(self, **kwargs) -> Any:
        """
        Fit model using statsmodels.
        
        Args:
            **kwargs: Additional arguments for model.fit
            
        Returns:
            statsmodels fitting results
        """
        if not STATSMODELS_AVAILABLE:
            logger.error("statsmodels not available for model fitting")
            return None
            
        try:
            # Fit the model
            results = self.model.fit(**kwargs)
            
            # Store results
            self.trace = results
            
            logger.info("Model fitted successfully with statsmodels")
            
            return results
            
        except Exception as e:
            logger.error(f"Error fitting statsmodels model: {e}")
            return None
    
    def _fit_tfp(self, num_variational_steps: int = 1000, **kwargs) -> Any:
        """
        Fit model using TensorFlow Probability.
        
        Args:
            num_variational_steps: Number of variational inference steps
            **kwargs: Additional arguments for tfp.sts.fit_with_hmc
            
        Returns:
            TFP fitting results
        """
        if not TFP_AVAILABLE:
            logger.error("TensorFlow Probability not available for model fitting")
            return None
            
        try:
            # Extract data
            y_tensor = tf.convert_to_tensor(self.data['y'], dtype=tf.float32)
            
            # Fit the model using variational inference
            variational_posteriors = tfp.sts.build_factored_surrogate_posterior(
                model=self.model
            )
            
            optimizer = tf.optimizers.Adam(learning_rate=0.1)
            
            @tf.function(autograph=False)
            def train_model():
                elbo_loss = tfp.vi.fit_surrogate_posterior(
                    target_log_prob_fn=self.model.joint_log_prob(observed_time_series=y_tensor),
                    surrogate_posterior=variational_posteriors,
                    optimizer=optimizer,
                    num_steps=num_variational_steps
                )
                return elbo_loss
            
            # Train the model
            elbo_loss = train_model()
            
            # Sample from variational posterior
            q_samples = variational_posteriors.sample(50)
            
            # Store results
            self.trace = (variational_posteriors, q_samples)
            
            logger.info("Model fitted successfully with TFP")
            
            return self.trace
            
        except Exception as e:
            logger.error(f"Error fitting TFP model: {e}")
            return None
    
    def forecast(self, periods: Optional[int] = None, 
               exog: Optional[np.ndarray] = None,
               include_components: bool = True,
               return_dist: bool = True) -> Dict[str, Any]:
        """
        Generate forecasts from the fitted model.
        
        Args:
            periods: Number of periods to forecast
            exog: Exogenous variables for forecast periods
            include_components: Whether to include component forecasts
            return_dist: Whether to return full distributions or just point estimates
            
        Returns:
            dict: Forecast results
        """
        if self.model is None or self.trace is None:
            logger.error("Model not fitted. Call fit_model() first.")
            return None
            
        # Set default forecast periods if not provided
        if periods is None:
            periods = self.forecast_periods
            
        logger.info(f"Generating {periods}-period forecast")
        
        # Determine forecasting method based on model type
        if PYMC_AVAILABLE and isinstance(self.model, pm.Model):
            forecast = self._forecast_pymc(periods, exog, include_components, return_dist)
        elif STATSMODELS_AVAILABLE and hasattr(self.trace, 'forecast'):
            forecast = self._forecast_statsmodels(periods, exog, include_components)
        elif TFP_AVAILABLE and isinstance(self.model, tfp.sts.Sum):
            forecast = self._forecast_tfp(periods, exog, include_components, return_dist)
        else:
            logger.error("Unknown model type for forecasting")
            return None
            
        # Generate forecast dates if date index is available
        if self.date_index is not None and self.last_fitted_date is not None:
            # Get frequency from date index
            freq = pd.infer_freq(self.date_index)
            if freq is None:
                # Try to infer frequency from last few points
                freq = pd.infer_freq(self.date_index[-5:])
                
            if freq is not None:
                forecast_dates = pd.date_range(
                    start=self.last_fitted_date + pd.Timedelta(days=1),
                    periods=periods,
                    freq=freq
                )
                forecast['dates'] = forecast_dates
            else:
                logger.warning("Could not infer frequency from date index")
                
        # Unstandardize forecasts if data was standardized
        if self.data['standardized']:
            forecast = self._unstandardize_forecast(forecast)
            
        return forecast
    
    def _forecast_pymc(self, periods: int, 
                     exog: Optional[np.ndarray] = None,
                     include_components: bool = True,
                     return_dist: bool = True) -> Dict[str, Any]:
        """
        Generate forecasts using PyMC model.
        
        Args:
            periods: Number of periods to forecast
            exog: Exogenous variables for forecast periods
            include_components: Whether to include component forecasts
            return_dist: Whether to return full distributions or just point estimates
            
        Returns:
            dict: Forecast results
        """
        # Extract posterior samples
        if isinstance(self.trace, az.InferenceData):
            posterior = self.trace.posterior
        else:
            posterior = self.trace
            
        # Get number of samples
        n_samples = len(posterior.chain) * len(posterior.draw)
        
        # Extract model parameters
        params = {}
        for param in posterior.data_vars:
            # Skip components
            if param in ['trend', 'seasonality', 'cycle', 'regression', 'autoregression', 'y']:
                continue
                
            # Extract parameter values
            params[param] = posterior[param].values.reshape(n_samples, -1)
            
        # Initialize forecast arrays
        forecast_samples = np.zeros((n_samples, periods))
        component_forecasts = {}
        
        if include_components:
            for component in ['trend', 'seasonality', 'cycle', 'regression', 'autoregression']:
                if self.components.get(component) is not None:
                    component_forecasts[component] = np.zeros((n_samples, periods))
        
        # Generate forecasts
        for t in range(periods):
            # Trend forecast (random walk)
            if self.config['trend']:
                if t == 0:
                    # Start with last trend value
                    last_trend = posterior['trend'].values[:, :, -1].reshape(n_samples)
                    trend_forecast = last_trend
                else:
                    # Random walk step
                    level_scale = params['level_scale'].reshape(n_samples)
                    trend_innovations = np.random.normal(0, level_scale)
                    trend_forecast = forecast_samples[:, t-1] + trend_innovations
                    
                forecast_samples[:, t] = trend_forecast
                
                if include_components:
                    component_forecasts['trend'][:, t] = trend_forecast
            
            # Seasonality forecast
            if self.config['seasonality']:
                season_length = self.config['season_length']
                
                # Fourier series approach
                t_global = len(self.data['y']) + t  # Global time index
                
                seasonal_features = np.zeros((n_samples, 2 * self.config['n_seasons']))
                for j in range(self.config['n_seasons']):
                    seasonal_features[:, 2*j] = np.sin(2 * np.pi * (j+1) * t_global / season_length)
                    seasonal_features[:, 2*j+1] = np.cos(2 * np.pi * (j+1) * t_global / season_length)
                
                # Extract seasonal coefficients
                seasonal_coef = params['seasonal_coef']
                
                # Calculate seasonal component
                seasonal_forecast = np.sum(seasonal_features * seasonal_coef, axis=1)
                
                forecast_samples[:, t] += seasonal_forecast
                
                if include_components:
                    component_forecasts['seasonality'][:, t] = seasonal_forecast
            
            # ... Add other components (cycle, regression, autoregression) here ...
        
        # Calculate forecast statistics
        mean = np.mean(forecast_samples, axis=0)
        median = np.median(forecast_samples, axis=0)
        std = np.std(forecast_samples, axis=0)
        
        # Calculate prediction intervals
        alpha = 1 - self.credible_interval
        lower = np.percentile(forecast_samples, alpha/2 * 100, axis=0)
        upper = np.percentile(forecast_samples, (1 - alpha/2) * 100, axis=0)
        
        forecast = {
            'mean': mean,
            'median': median,
            'std': std,
            'lower': lower,
            'upper': upper
        }
        
        if return_dist:
            forecast['samples'] = forecast_samples
            
        if include_components:
            forecast['components'] = {}
            for component, samples in component_forecasts.items():
                forecast['components'][component] = {
                    'mean': np.mean(samples, axis=0),
                    'lower': np.percentile(samples, alpha/2 * 100, axis=0),
                    'upper': np.percentile(samples, (1 - alpha/2) * 100, axis=0)
                }
                
                if return_dist:
                    forecast['components'][component]['samples'] = samples
                    
        return forecast
    
    def _forecast_statsmodels(self, periods: int, 
                           exog: Optional[np.ndarray] = None,
                           include_components: bool = True) -> Dict[str, Any]:
        """
        Generate forecasts using statsmodels model.
        
        Args:
            periods: Number of periods to forecast
            exog: Exogenous variables for forecast periods
            include_components: Whether to include component forecasts
            
        Returns:
            dict: Forecast results
        """
        # Generate forecast
        forecast = self.trace.forecast(steps=periods, exog=exog)
        
        # Calculate prediction intervals
        forecast_ci = self.trace.get_forecast(steps=periods, exog=exog)
        intervals = forecast_ci.conf_int(alpha=1-self.credible_interval)
        
        # Extract component forecasts if requested
        component_forecasts = {}
        if include_components:
            try:
                # Try to get components from StateSpace results
                for component in ['level', 'seasonal', 'cycle']:
                    if component in self.trace.states.columns:
                        # Forecast the component
                        component_forecast = self.trace.get_prediction(start=0, end=len(self.data['y'])+periods-1).predicted_state[component].iloc[-periods:]
                        component_forecasts[component] = {
                            'mean': component_forecast.values
                        }
            except Exception:
                logger.warning("Could not extract component forecasts from statsmodels model")
        
        return {
            'mean': forecast.values,
            'lower': intervals.iloc[:, 0].values,
            'upper': intervals.iloc[:, 1].values,
            'components': component_forecasts if include_components else {}
        }
    
    def _forecast_tfp(self, periods: int, 
                     exog: Optional[np.ndarray] = None,
                     include_components: bool = True,
                     return_dist: bool = True) -> Dict[str, Any]:
        """
        Generate forecasts using TensorFlow Probability model.
        
        Args:
            periods: Number of periods to forecast
            exog: Exogenous variables for forecast periods
            include_components: Whether to include component forecasts
            return_dist: Whether to return full distributions or just point estimates
            
        Returns:
            dict: Forecast results
        """
        if not TFP_AVAILABLE:
            logger.error("TensorFlow Probability not available for forecasting")
            return {'mean': np.zeros(periods), 'lower': np.zeros(periods), 'upper': np.zeros(periods)}
            
        try:
            # Extract the model and variational posteriors
            model = self.model
            variational_posteriors, posterior_samples = self.trace
            
            # Sample from the posterior
            samples = 100  # Number of samples for forecasting
            
            # Convert to TensorFlow format
            observed_time_series = tf.convert_to_tensor(
                self.data['y_orig'].reshape(-1, 1), dtype=tf.float64
            )
            
            # Initialize container for forecasts
            forecast_samples = np.zeros((samples, periods))
            component_forecasts = {}
            
            # Generate forecast samples
            for i, posterior_sample in enumerate(posterior_samples.items()):
                if i >= samples:  # Limit to 'samples' samples
                    break
                    
                # Get the sampled parameter values
                parameter_samples = posterior_sample[1]
                
                # Generate forecast
                forecast_dist = tfp.sts.forecast(
                    model=model,
                    observed_time_series=observed_time_series,
                    parameter_samples=parameter_samples,
                    num_steps_forecast=periods
                )
                
                # Sample from forecast distribution
                forecast_mean = forecast_dist.mean().numpy().flatten()
                forecast_samples[i, :] = forecast_mean
                
            # Calculate forecast statistics
            mean = np.mean(forecast_samples, axis=0)
            lower = np.percentile(forecast_samples, (1 - self.credible_interval) / 2 * 100, axis=0)
            upper = np.percentile(forecast_samples, (1 + self.credible_interval) / 2 * 100, axis=0)
            
            forecast = {
                'mean': mean,
                'lower': lower,
                'upper': upper
            }
            
            if return_dist:
                forecast['samples'] = forecast_samples
                
            if include_components:
                # Component forecasts not yet implemented for TFP
                pass
                
            return forecast
            
        except Exception as e:
            logger.error(f"Error forecasting with TFP model: {e}")
            return {'mean': np.zeros(periods), 'lower': np.zeros(periods), 'upper': np.zeros(periods)}
    
    def _unstandardize_forecast(self, forecast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Unstandardize forecasts if data was standardized.
        
        Args:
            forecast: Dictionary with forecast data
            
        Returns:
            dict: Unstandardized forecast
        """
        # Create a copy to avoid modifying the original
        result = forecast.copy()
        
        # Unstandardize mean
        if 'mean' in result:
            result['mean'] = result['mean'] * self.y_std + self.y_mean
            
        # Unstandardize confidence intervals
        if 'lower' in result:
            result['lower'] = result['lower'] * self.y_std + self.y_mean
            
        if 'upper' in result:
            result['upper'] = result['upper'] * self.y_std + self.y_mean
            
        # Unstandardize samples if available
        if 'samples' in result:
            result['samples'] = result['samples'] * self.y_std + self.y_mean
            
        # Unstandardize components if available
        if 'components' in result and isinstance(result['components'], dict):
            for component, comp_data in result['components'].items():
                if 'mean' in comp_data:
                    comp_data['mean'] = comp_data['mean'] * self.y_std + self.y_mean
                    
                if 'lower' in comp_data:
                    comp_data['lower'] = comp_data['lower'] * self.y_std + self.y_mean
                    
                if 'upper' in comp_data:
                    comp_data['upper'] = comp_data['upper'] * self.y_std + self.y_mean
                    
                if 'samples' in comp_data:
                    comp_data['samples'] = comp_data['samples'] * self.y_std + self.y_mean
                    
        return result
    
    def analyze_causal_impact(self, 
                            pre_period: Tuple[int, int],
                            post_period: Tuple[int, int],
                            counterfactual_model: Optional[Any] = None) -> Dict[str, Any]:
        """
        Analyze causal impact of an intervention.
        
        Args:
            pre_period: Tuple with (start, end) indices for pre-intervention period
            post_period: Tuple with (start, end) indices for post-intervention period
            counterfactual_model: Optional model for counterfactual predictions
            
        Returns:
            dict: Causal impact analysis results
        """
        if self.data is None:
            logger.error("No data available for causal impact analysis")
            return {}
            
        # Get original data
        y_orig = self.data['y_orig']
        
        # Use pre-intervention data to train model if no counterfactual provided
        if counterfactual_model is None:
            # Prepare pre-intervention data
            pre_data = {
                'y': self.data['y'][pre_period[0]:pre_period[1]],
                'y_orig': y_orig[pre_period[0]:pre_period[1]]
            }
            
            if self.data['X'] is not None:
                pre_data['X'] = self.data['X'][pre_period[0]:pre_period[1]]
                
            # Fit model on pre-intervention data
            if PYMC_AVAILABLE:
                with pm.Model() as model:
                    # Simple local level model
                    mu = pm.Normal('mu', mu=0, sigma=5)
                    sigma = pm.HalfNormal('sigma', sigma=1)
                    
                    # Likelihood
                    obs = pm.Normal('obs', mu=mu, sigma=sigma, observed=pre_data['y'])
                    
                    # Sample
                    trace = pm.sample(1000, tune=500)
                    
                # Generate counterfactual predictions for post period
                post_len = post_period[1] - post_period[0]
                mu_samples = trace.posterior['mu'].values.flatten()
                sigma_samples = trace.posterior['sigma'].values.flatten()
                
                # Generate multiple counterfactual samples
                counterfactual_samples = np.zeros((len(mu_samples), post_len))
                for i, (mu_i, sigma_i) in enumerate(zip(mu_samples, sigma_samples)):
                    counterfactual_samples[i] = np.random.normal(mu_i, sigma_i, post_len)
                    
                # Calculate counterfactual statistics
                counterfactual_mean = counterfactual_samples.mean(axis=0)
                counterfactual_lower = np.percentile(counterfactual_samples, 2.5, axis=0)
                counterfactual_upper = np.percentile(counterfactual_samples, 97.5, axis=0)
                
            elif STATSMODELS_AVAILABLE:
                # Use unobserved components model for counterfactual
                model = UnobservedComponents(
                    pre_data['y_orig'], 
                    level='local linear trend',
                    seasonal=None
                )
                
                res = model.fit(disp=False)
                
                # Generate forecast for post period
                post_len = post_period[1] - post_period[0]
                forecast = res.forecast(steps=post_len)
                
                # Get prediction intervals
                pred = res.get_prediction(start=len(pre_data['y_orig']), end=len(pre_data['y_orig'])+post_len-1)
                pred_int = pred.conf_int(alpha=0.05)
                
                counterfactual_mean = forecast
                counterfactual_lower = pred_int.iloc[:, 0]
                counterfactual_upper = pred_int.iloc[:, 1]
                
            else:
                # Simple AR model as fallback
                from statsmodels.tsa.ar_model import AutoReg
                model = AutoReg(pre_data['y_orig'], lags=5)
                res = model.fit()
                
                post_len = post_period[1] - post_period[0]
                counterfactual_mean = res.predict(start=len(pre_data['y_orig']), end=len(pre_data['y_orig'])+post_len-1)
                
                # Simple prediction intervals (+/- 2 std errors)
                std_err = np.sqrt(res.sigma2)
                counterfactual_lower = counterfactual_mean - 2 * std_err
                counterfactual_upper = counterfactual_mean + 2 * std_err
        else:
            # Use provided counterfactual model
            # This would be implemented based on the type of model provided
            pass
            
        # Get actual post-intervention data
        post_data = y_orig[post_period[0]:post_period[1]]
        
        # Calculate pointwise impact
        point_effects = post_data - counterfactual_mean
        
        # Calculate cumulative impact
        cumulative_effect = np.sum(point_effects)
        
        # Calculate relative impact
        if np.sum(counterfactual_mean) != 0:
            relative_effect = cumulative_effect / np.sum(counterfactual_mean)
        else:
            relative_effect = 0
            
        # Calculate p-value
        if isinstance(counterfactual_samples, np.ndarray):
            # Calculate cumulative sums for each sample
            sample_sums = np.sum(counterfactual_samples, axis=1)
            
            # Actual sum
            actual_sum = np.sum(post_data)
            
            # Calculate p-value (proportion of samples more extreme than actual)
            if actual_sum > np.mean(sample_sums):
                p_value = np.mean(sample_sums >= actual_sum)
            else:
                p_value = np.mean(sample_sums <= actual_sum)
        else:
            # Simple approximation
            avg_effect = np.mean(point_effects)
            std_effect = np.std(point_effects)
            z_score = avg_effect / (std_effect / np.sqrt(len(point_effects)))
            
            # Calculate two-tailed p-value
            from scipy import stats
            p_value = 2 * (1 - stats.norm.cdf(abs(z_score)))
            
        # Prepare results
        results = {
            'point_effects': point_effects,
            'cumulative_effect': cumulative_effect,
            'relative_effect': relative_effect,
            'p_value': p_value,
            'significant': p_value < 0.05,
            'actual': post_data,
            'counterfactual': {
                'mean': counterfactual_mean,
                'lower': counterfactual_lower,
                'upper': counterfactual_upper
            }
        }
        
        return results
    
    def plot_causal_impact(self, impact_results: Dict[str, Any], 
                         dates: Optional[pd.DatetimeIndex] = None,
                         output_file: Optional[str] = None) -> None:
        """
        Plot causal impact analysis results.
        
        Args:
            impact_results: Results from analyze_causal_impact
            dates: DatetimeIndex for x-axis labeling
            output_file: Path to save the plot
            
        Returns:
            None
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            logger.warning("Matplotlib not available. Cannot generate plot.")
            return
            
        if not impact_results:
            logger.warning("No impact results to plot.")
            return
            
        # Create figure with multiple panels
        fig, axes = plt.subplots(3, 1, figsize=(12, 10), sharex=True)
        
        # Get data
        actual = impact_results['actual']
        counterfactual = impact_results['counterfactual']['mean']
        lower = impact_results['counterfactual']['lower']
        upper = impact_results['counterfactual']['upper']
        point_effects = impact_results['point_effects']
        
        # Create x values (dates or indices)
        if dates is not None:
            x_values = dates[-len(actual):]
        else:
            x_values = np.arange(len(actual))
            
        # Panel 1: Original vs Counterfactual
        ax = axes[0]
        ax.plot(x_values, actual, 'b-', label='Actual')
        ax.plot(x_values, counterfactual, 'r--', label='Counterfactual')
        ax.fill_between(x_values, lower, upper, color='r', alpha=0.1, label='95% CI')
        ax.set_ylabel('Value')
        ax.set_title('Actual vs Counterfactual')
        ax.legend()
        ax.grid(True, alpha=0.3)
        
        # Panel 2: Pointwise effects
        ax = axes[1]
        ax.plot(x_values, point_effects, 'g-')
        ax.axhline(y=0, color='r', linestyle='--')
        ax.set_ylabel('Difference')
        ax.set_title('Pointwise Effects')
        ax.grid(True, alpha=0.3)
        
        # Panel 3: Cumulative effect
        ax = axes[2]
        cumulative = np.cumsum(point_effects)
        ax.plot(x_values, cumulative, 'g-')
        ax.axhline(y=0, color='r', linestyle='--')
        ax.set_ylabel('Cumulative Sum')
        ax.set_title('Cumulative Effect')
        ax.grid(True, alpha=0.3)
        
        # X-axis formatting for dates
        if dates is not None:
            for ax in axes:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
                fig.autofmt_xdate()
                
        # Add summary statistics
        summary_text = (
            f"Causal Impact Analysis\n"
            f"Cumulative effect: {impact_results['cumulative_effect']:.4f}\n"
            f"Relative effect: {impact_results['relative_effect']*100:.2f}%\n"
            f"p-value: {impact_results['p_value']:.4f}"
        )
        
        fig.text(0.01, 0.01, summary_text, fontsize=12, 
                bbox=dict(facecolor='white', alpha=0.8))
                
        plt.tight_layout(rect=[0, 0.05, 1, 0.95])
        
        # Save or display plot
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Causal impact plot saved to {output_file}")
        else:
            plt.show()
            
        plt.close(fig)
    
    def feature_selection(self, X: np.ndarray, 
                        y: np.ndarray,
                        feature_names: List[str],
                        method: str = 'spike_and_slab') -> Dict[str, Any]:
        """
        Perform Bayesian feature selection.
        
        Args:
            X: Feature matrix
            y: Target variable
            feature_names: Names of features
            method: Feature selection method ('spike_and_slab' or 'horseshoe')
            
        Returns:
            dict: Feature selection results
        """
        if not PYMC_AVAILABLE:
            logger.error("PyMC not available for Bayesian feature selection")
            return {}
            
        if len(feature_names) != X.shape[1]:
            logger.error("Number of feature names must match number of features")
            return {}
            
        # Center and scale X and y
        X_scaled = (X - np.mean(X, axis=0)) / np.std(X, axis=0)
        y_scaled = (y - np.mean(y)) / np.std(y)
        
        try:
            if method == 'spike_and_slab':
                # Spike and Slab prior for feature selection
                with pm.Model() as model:
                    # Global shrinkage parameter
                    tau = pm.HalfCauchy('tau', beta=1)
                    
                    # Binary indicators for inclusion/exclusion
                    gamma = pm.Bernoulli('gamma', p=0.5, shape=X.shape[1])
                    
                    # Coefficients
                    beta = pm.Normal('beta', mu=0, sigma=tau, shape=X.shape[1])
                    
                    # Slab-and-spike construction
                    beta_star = pm.Deterministic('beta_star', beta * gamma)
                    
                    # Expected value
                    mu = pm.Deterministic('mu', pm.math.dot(X_scaled, beta_star))
                    
                    # Likelihood
                    sigma = pm.HalfCauchy('sigma', beta=1)
                    y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma, observed=y_scaled)
                    
                    # Sample
                    trace = pm.sample(1000, tune=1000, return_inferencedata=True)
                
                # Extract results
                beta_means = az.summary(trace, var_names=['beta_star'])['mean'].values
                gamma_means = az.summary(trace, var_names=['gamma'])['mean'].values
                
                # Calculate inclusion probabilities
                inclusion_probs = gamma_means
                
                # Determine selected features
                selected = inclusion_probs > 0.5
                
                # Create results
                results = {
                    'inclusion_probabilities': dict(zip(feature_names, inclusion_probs)),
                    'coefficients': dict(zip(feature_names, beta_means)),
                    'selected_features': [feature_names[i] for i in range(len(feature_names)) if selected[i]],
                    'method': 'spike_and_slab'
                }
                
            elif method == 'horseshoe':
                # Horseshoe prior for feature selection
                with pm.Model() as model:
                    # Global shrinkage parameter
                    tau = pm.HalfCauchy('tau', beta=1)
                    
                    # Local shrinkage parameters
                    lambda_p = pm.HalfCauchy('lambda', beta=1, shape=X.shape[1])
                    
                    # Coefficients
                    beta = pm.Normal('beta', mu=0, sigma=tau * lambda_p, shape=X.shape[1])
                    
                    # Expected value
                    mu = pm.Deterministic('mu', pm.math.dot(X_scaled, beta))
                    
                    # Likelihood
                    sigma = pm.HalfCauchy('sigma', beta=1)
                    y_obs = pm.Normal('y_obs', mu=mu, sigma=sigma, observed=y_scaled)
                    
                    # Sample
                    trace = pm.sample(1000, tune=1000, return_inferencedata=True)
                
                # Extract results
                beta_means = az.summary(trace, var_names=['beta'])['mean'].values
                beta_hdi = az.hdi(trace, var_names=['beta'])
                
                # Determine selected features (credible interval excludes 0)
                selected = ~((beta_hdi['beta'][:, 0] < 0) & (beta_hdi['beta'][:, 1] > 0))
                
                # Calculate feature importance scores
                feature_importance = np.abs(beta_means) / np.max(np.abs(beta_means))
                
                # Create results
                results = {
                    'feature_importance': dict(zip(feature_names, feature_importance)),
                    'coefficients': dict(zip(feature_names, beta_means)),
                    'selected_features': [feature_names[i] for i in range(len(feature_names)) if selected[i]],
                    'method': 'horseshoe'
                }
                
            else:
                logger.error(f"Unknown feature selection method: {method}")
                return {}
                
            return results
            
        except Exception as e:
            logger.error(f"Error in Bayesian feature selection: {e}")
            return {}
        
    def train_gp_sklearn(self, data: Dict[str, np.ndarray], **kwargs) -> Any:
        """
        Train a Gaussian Process regression model using scikit-learn.
        
        Args:
            data: Dictionary with prepared data arrays
            **kwargs: Additional arguments for GaussianProcessRegressor
            
        Returns:
            Trained Gaussian Process model
        """
        try:
            from sklearn.gaussian_process import GaussianProcessRegressor
            from sklearn.gaussian_process.kernels import RBF, WhiteKernel, ExpSineSquared, RationalQuadratic
            SKLEARN_AVAILABLE = True
        except ImportError:
            logger.error("scikit-learn not available for Gaussian Process regression")
            return None
            
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for GP regression")
            return None
            
        try:
            # Extract data
            y = data['y']
            
            # Create input array (just use time indices if no exogenous variables)
            if data['X'] is not None:
                X = data['X']
            else:
                X = np.arange(len(y)).reshape(-1, 1)
                
            # Define kernel
            # Base kernel for trend
            k1 = RBF(length_scale=10.0, length_scale_bounds=(1e-1, 1e3)) 
            
            # Add white noise
            k2 = WhiteKernel(noise_level=1e-1)
            
            # Add seasonality if enabled
            if self.config['seasonality']:
                season_length = self.config['season_length']
                k3 = ExpSineSquared(
                    length_scale=1.0,
                    periodicity=season_length,
                    periodicity_bounds=(season_length * 0.9, season_length * 1.1)
                )
                kernel = k1 + k2 + k3
            else:
                kernel = k1 + k2
                
            # Create and fit model
            gp = GaussianProcessRegressor(
                kernel=kernel,
                alpha=1e-10,  # Nugget
                normalize_y=True,
                n_restarts_optimizer=5,
                **kwargs
            )
            
            gp.fit(X, y)
            
            # Store model
            self.gp_model = gp
            
            logger.info("Gaussian Process model trained successfully")
            
            return gp
            
        except Exception as e:
            logger.error(f"Error training Gaussian Process model: {e}")
            return None

# Example usage
if __name__ == "__main__":
    # Generate synthetic data
    np.random.seed(42)
    
    # Generate dates
    dates = pd.date_range(start='2020-01-01', periods=200, freq='D')
    
    # Generate synthetic time series with trend, seasonality, and noise
    trend = np.linspace(0, 20, 200)
    seasonality = 2 * np.sin(np.linspace(0, 2*np.pi*10, 200))
    noise = np.random.normal(0, 1, 200)
    
    y = trend + seasonality + noise
    
    # Create features
    X1 = np.random.normal(0, 1, 200)  # Irrelevant feature
    X2 = trend + np.random.normal(0, 0.5, 200)  # Relevant feature
    X3 = seasonality + np.random.normal(0, 0.5, 200)  # Relevant feature
    X = np.column_stack([X1, X2, X3])
    
    # Create DataFrame
    df = pd.DataFrame({
        'y': y,
        'X1': X1,
        'X2': X2,
        'X3': X3
    }, index=dates)
    
    # Initialize model
    model = BayesianStructuralTS()
    
    # Prepare data - change features parameter to exog_cols
    data = model.prepare_data(df, target_col='y', exog_cols=['X1', 'X2', 'X3'])
    
    # Build and train model
    if PYMC_AVAILABLE:
        model.build_model_pymc()
        model.train_gp_sklearn(data)
    elif STATSMODELS_AVAILABLE:
        model.build_model_statsmodels()
        model.train_gp_sklearn(data)
    
    # Generate forecast
    forecast = model.forecast(periods=30)
    
    # Plot forecast if matplotlib is available
    try:
        import matplotlib.pyplot as plt
        
        plt.figure(figsize=(12, 6))
        
        # Plot historical data
        plt.plot(dates, y, 'b-', label='Historical Data')
        
        # Plot forecast
        forecast_dates = pd.date_range(start=dates[-1] + pd.Timedelta(days=1), periods=30, freq='D')
        plt.plot(forecast_dates, forecast['mean'], 'r-', label='Forecast')
        plt.fill_between(forecast_dates, forecast['lower'], forecast['upper'], color='r', alpha=0.2, label='95% CI')
        
        plt.title('Bayesian Structural Time Series Forecast')
        plt.xlabel('Date')
        plt.ylabel('Value')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('bsts_forecast.png', dpi=300)
        plt.close()
        
        print("Forecast plot saved as 'bsts_forecast.png'")
    except ImportError:
        print("Matplotlib not available. Cannot generate plot.")
    
    # Causal impact analysis
    if PYMC_AVAILABLE or STATSMODELS_AVAILABLE:
        # Simulate intervention
        intervention_idx = 150
        post_data = y.copy()
        post_data[intervention_idx:] += 5  # Add effect
        
        # Create DataFrame with intervention
        df_intervention = pd.DataFrame({
            'y': post_data,
            'X1': X1,
            'X2': X2,
            'X3': X3
        }, index=dates)
        
        # Prepare data - fix the same unpacking issue
        data_intervention = model.prepare_data(df_intervention, target_col='y', exog_cols=['X1', 'X2', 'X3'])
        
        # Analyze causal impact
        impact = model.analyze_causal_impact(
            pre_period=(0, intervention_idx),
            post_period=(intervention_idx, 200)
        )
        
        # Plot causal impact
        model.plot_causal_impact(impact, dates, 'causal_impact.png')
        
        print("Causal impact analysis complete. Plot saved as 'causal_impact.png'")
        print(f"Estimated impact: {impact['cumulative_effect']:.2f}")
        print(f"Relative effect: {impact['relative_effect'] * 100:.2f}%")
        print(f"p-value: {impact['p_value']:.4f}")
    
    # Feature selection
    if PYMC_AVAILABLE:
        features = ['X1', 'X2', 'X3']
        feature_selection = model.feature_selection(X, y, features, method='spike_and_slab')
        
        print("\nFeature Selection Results:")
        for feature, prob in feature_selection.get('inclusion_probabilities', {}).items():
            print(f"{feature}: {prob:.2f}")
            
        print("Selected features:", feature_selection.get('selected_features', []))