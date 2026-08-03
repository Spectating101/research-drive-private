#!/usr/bin/env python3
# Filename: src/core/gaussian_process_forecasting.py
"""
Gaussian Process Forecasting Module

This module provides probabilistic forecasting for financial time series using:
1. Gaussian Process Regression (GPR) for probabilistic predictions with uncertainty
2. Bayesian optimization for hyperparameter tuning
3. Customized kernels for financial time series
4. Calibrated uncertainty estimates for risk management

Unlike traditional point forecasts, Gaussian Processes provide full probability
distributions, enabling more robust trading decisions with proper risk estimation.
"""

import numpy as np
import pandas as pd
import logging
import os
import json
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Union, Optional, Any

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Try to import scikit-learn for Gaussian Process implementation
try:
    from sklearn.gaussian_process import GaussianProcessRegressor
    from sklearn.gaussian_process.kernels import (
        RBF, Matern, WhiteKernel, ConstantKernel, ExpSineSquared, RationalQuadratic
    )
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split, GridSearchCV
    from sklearn.metrics import mean_squared_error, r2_score
    SKLEARN_AVAILABLE = True
    logger.info("scikit-learn available for Gaussian Process Regression")
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Gaussian Process functionality will be limited.")

# Try to import more advanced Gaussian Process libraries
try:
    import gpflow
    import tensorflow as tf
    GPFLOW_AVAILABLE = True
    logger.info("GPflow available for advanced Gaussian Process modeling")
except ImportError:
    GPFLOW_AVAILABLE = False
    logger.debug("GPflow not available. Using scikit-learn implementation.")

class GaussianProcessForecaster:
    """
    Provides probabilistic forecasting using Gaussian Process Regression.
    """
    
    def __init__(self, use_gpflow: bool = False, output_dir: str = "data/gp_models"):
        """
        Initialize the Gaussian Process forecasting model.
        
        Args:
            use_gpflow: Whether to use GPflow (if available) for improved performance
            output_dir: Directory to save trained models and results
        """
        self.use_gpflow = use_gpflow and GPFLOW_AVAILABLE
        self.output_dir = output_dir
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Default hyperparameters
        self.default_params = {
            'kernel': 'RBF+WhiteKernel',
            'alpha': 1e-10,
            'normalize_y': True,
            'n_restarts_optimizer': 5
        }
        
        # Tracking of model and data
        self.model = None
        self.scaler_X = StandardScaler()
        self.scaler_y = StandardScaler()
        self.feature_columns = None
        self.target_column = None
        self.trained = False
        
        # Prediction tracking
        self.last_prediction = None
        self.last_uncertainty = None
        
    def prepare_data(self, 
                    df: pd.DataFrame, 
                    features: List[str], 
                    target: str, 
                    test_size: float = 0.2, 
                    scale_data: bool = True) -> Tuple[Dict[str, np.ndarray], pd.DatetimeIndex]:
        """
        Prepare data for Gaussian Process modeling.
        
        Args:
            df: Input DataFrame with datetime index
            features: List of feature column names
            target: Target column name
            test_size: Proportion of data to use for testing
            scale_data: Whether to scale features and target
            
        Returns:
            dict: Dictionary with train/test data
            pd.DatetimeIndex: Index for the prepared data
        """
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("DataFrame must have a DatetimeIndex")
            
        # Store feature and target information
        self.feature_columns = features
        self.target_column = target
        
        # Extract features and target
        X = df[features].values
        y = df[target].values
        
        # Save the datetime index
        dates_index = df.index
        
        # Split data
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, shuffle=False
        )
        
        # Scale data if requested
        if scale_data:
            X_train = self.scaler_X.fit_transform(X_train)
            X_test = self.scaler_X.transform(X_test)
            
            # Reshape y to 2D for scaling
            y_train_2d = y_train.reshape(-1, 1)
            y_test_2d = y_test.reshape(-1, 1)
            
            y_train_scaled = self.scaler_y.fit_transform(y_train_2d).flatten()
            y_test_scaled = self.scaler_y.transform(y_test_2d).flatten()
        else:
            y_train_scaled = y_train
            y_test_scaled = y_test
        
        # Prepare data dictionary
        data = {
            'X_train': X_train,
            'X_test': X_test,
            'y_train': y_train_scaled,
            'y_test': y_test_scaled,
            'y_train_original': y_train,
            'y_test_original': y_test
        }
        
        return data, dates_index
        
    def create_kernel(self, kernel_type: str = 'RBF+WhiteKernel', length_scale: float = 1.0):
        """
        Create a kernel for Gaussian Process regression.
        
        Args:
            kernel_type: Type of kernel to use
            length_scale: Length scale parameter for RBF kernel
            
        Returns:
            Kernel object
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for kernel creation")
            return None
            
        if kernel_type == 'RBF':
            return RBF(length_scale=length_scale)
        elif kernel_type == 'Matern':
            return Matern(length_scale=length_scale, nu=1.5)
        elif kernel_type == 'RBF+WhiteKernel':
            return RBF(length_scale=length_scale) + WhiteKernel(noise_level=0.1)
        elif kernel_type == 'RationalQuadratic':
            return RationalQuadratic(length_scale=length_scale, alpha=1.0)
        elif kernel_type == 'FinancialKernel':
            # Custom kernel for financial time series
            # Combination of RBF (overall smoothness), RationalQuadratic (local patterns),
            # and WhiteKernel (noise)
            return (
                ConstantKernel(1.0) * 
                RBF(length_scale=length_scale) + 
                RationalQuadratic(length_scale=length_scale, alpha=0.5) + 
                WhiteKernel(noise_level=0.1)
            )
        elif kernel_type == 'SeasonalKernel':
            # Kernel for time series with seasonality
            return (
                RBF(length_scale=length_scale) +
                ExpSineSquared(length_scale=1.0, periodicity=252.0, periodicity_bounds=(200, 300)) +
                WhiteKernel(noise_level=0.1)
            )
        else:
            logger.warning(f"Unknown kernel type: {kernel_type}. Using RBF+WhiteKernel.")
            return RBF(length_scale=length_scale) + WhiteKernel(noise_level=0.1)
            
    def train_gp_sklearn(self, data: Dict[str, np.ndarray], params: Optional[Dict[str, Any]] = None):
        """
        Train a Gaussian Process model using scikit-learn implementation.
        
        Args:
            data: Dictionary with training data
            params: Hyperparameters for the model
            
        Returns:
            Trained Gaussian Process model
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for GP training")
            return None
            
        # Use default parameters if none provided
        if params is None:
            params = self.default_params.copy()
            
        # Create kernel
        kernel = self.create_kernel(params.get('kernel', 'RBF+WhiteKernel'))
        
        # Create and train GP model
        gp = GaussianProcessRegressor(
            kernel=kernel,
            alpha=params.get('alpha', 1e-10),
            normalize_y=params.get('normalize_y', True),
            n_restarts_optimizer=params.get('n_restarts_optimizer', 5),
            random_state=42
        )
        
        # Fit the model
        gp.fit(data['X_train'], data['y_train'])
        
        # Evaluate on test data
        y_pred, sigma = gp.predict(data['X_test'], return_std=True)
        
        # Calculate metrics
        mse = mean_squared_error(data['y_test'], y_pred)
        r2 = r2_score(data['y_test'], y_pred)
        
        # Calculate calibration score (percentage of true values within 2 standard deviations)
        within_2sigma = np.sum(np.abs(data['y_test'] - y_pred) < 2 * sigma) / len(y_pred)
        
        logger.info(f"GP Training Results (sklearn) - MSE: {mse:.6f}, R²: {r2:.4f}, Calibration (2σ): {within_2sigma:.2%}")
        
        self.model = gp
        self.trained = True
        
        return gp
        
    def train_gp_gpflow(self, data: Dict[str, np.ndarray], params: Optional[Dict[str, Any]] = None):
        """
        Train a Gaussian Process model using GPflow implementation.
        
        Args:
            data: Dictionary with training data
            params: Hyperparameters for the model
            
        Returns:
            Trained Gaussian Process model
        """
        if not GPFLOW_AVAILABLE:
            logger.error("GPflow not available for GP training")
            return None
            
        # Use default parameters if none provided
        if params is None:
            params = {
                'kernel': 'FinancialKernel',
                'learning_rate': 0.01,
                'n_iterations': 1000
            }
            
        # Convert data to TensorFlow format
        X_train = tf.convert_to_tensor(data['X_train'], dtype=tf.float64)
        y_train = tf.convert_to_tensor(data['y_train'].reshape(-1, 1), dtype=tf.float64)
        
        # Create kernel based on type
        kernel_type = params.get('kernel', 'FinancialKernel')
        
        if kernel_type == 'RBF':
            kernel = gpflow.kernels.SquaredExponential()
        elif kernel_type == 'Matern':
            kernel = gpflow.kernels.Matern32()
        elif kernel_type == 'FinancialKernel':
            # Custom kernel for financial time series
            kernel = (
                gpflow.kernels.SquaredExponential() + 
                gpflow.kernels.RationalQuadratic() + 
                gpflow.kernels.White()
            )
        else:
            kernel = gpflow.kernels.SquaredExponential()
            
        # Create the GP model
        gp_model = gpflow.models.GPR(
            (X_train, y_train),
            kernel=kernel,
            mean_function=None
        )
        
        # Set up optimizer
        optimizer = tf.optimizers.Adam(learning_rate=params.get('learning_rate', 0.01))
        
        # Training loop
        @tf.function
        def objective():
            return -gp_model.log_marginal_likelihood()
        
        n_iterations = params.get('n_iterations', 1000)
        
        for i in range(n_iterations):
            optimizer.minimize(objective, gp_model.trainable_variables)
            
            if i % 100 == 0:
                logger.debug(f"GPflow training iter {i}: log marginal likelihood = {gp_model.log_marginal_likelihood()}")
                
        # Evaluate on test data
        X_test = tf.convert_to_tensor(data['X_test'], dtype=tf.float64)
        mean, var = gp_model.predict_f(X_test)
        
        # Convert to numpy for metric calculation
        y_pred = mean.numpy().flatten()
        sigma = np.sqrt(var.numpy().flatten())
        
        # Calculate metrics
        mse = mean_squared_error(data['y_test'], y_pred)
        r2 = r2_score(data['y_test'], y_pred)
        
        # Calculate calibration score (percentage of true values within 2 standard deviations)
        within_2sigma = np.sum(np.abs(data['y_test'] - y_pred) < 2 * sigma) / len(y_pred)
        
        logger.info(f"GP Training Results (gpflow) - MSE: {mse:.6f}, R²: {r2:.4f}, Calibration (2σ): {within_2sigma:.2%}")
        
        self.model = gp_model
        self.trained = True
        
        return gp_model
        
    def train(self, df: pd.DataFrame, features: List[str], target: str, 
             params: Optional[Dict[str, Any]] = None, test_size: float = 0.2):
        """
        Train the Gaussian Process forecasting model.
        
        Args:
            df: Input DataFrame with datetime index
            features: List of feature column names
            target: Target column name
            params: Hyperparameters for the model
            test_size: Proportion of data to use for testing
            
        Returns:
            self
        """
        # Prepare data
        data, _ = self.prepare_data(df, features, target, test_size)
        
        # Train model based on availability
        if self.use_gpflow and GPFLOW_AVAILABLE:
            self.train_gp_gpflow(data, params)
        elif SKLEARN_AVAILABLE:
            self.train_gp_sklearn(data, params)
        else:
            logger.error("No Gaussian Process implementation available")
            
        return self
        
    def optimize_hyperparameters(self, df: pd.DataFrame, features: List[str], target: str, 
                               param_grid: Optional[Dict[str, List]] = None, cv: int = 3):
        """
        Optimize hyperparameters for the Gaussian Process model.
        
        Args:
            df: Input DataFrame with datetime index
            features: List of feature column names
            target: Target column name
            param_grid: Grid of hyperparameters to search
            cv: Number of cross-validation folds
            
        Returns:
            Best hyperparameters dictionary
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for hyperparameter optimization")
            return self.default_params.copy()
            
        # Prepare data
        X = df[features].values
        y = df[target].values
        
        # Scale features and target
        X_scaled = self.scaler_X.fit_transform(X)
        y_scaled = self.scaler_y.fit_transform(y.reshape(-1, 1)).flatten()
        
        # Define default parameter grid if none provided
        if param_grid is None:
            param_grid = {
                'kernel': [
                    RBF(length_scale=1.0) + WhiteKernel(noise_level=0.1),
                    Matern(length_scale=1.0, nu=1.5) + WhiteKernel(noise_level=0.1),
                    RationalQuadratic(length_scale=1.0, alpha=0.5) + WhiteKernel(noise_level=0.1)
                ],
                'alpha': [1e-10, 1e-8, 1e-6],
                'n_restarts_optimizer': [5]
            }
            
        # Create base GP model
        gp = GaussianProcessRegressor(random_state=42)
        
        # Use GridSearchCV to find best parameters
        grid_search = GridSearchCV(
            gp, param_grid, cv=cv, scoring='neg_mean_squared_error',
            verbose=1, n_jobs=-1
        )
        
        # Fit the grid search
        grid_search.fit(X_scaled, y_scaled)
        
        # Get best parameters
        best_params = grid_search.best_params_
        
        logger.info(f"Best hyperparameters: {best_params}")
        logger.info(f"Best score: {-grid_search.best_score_:.6f} MSE")
        
        # Train the model with best parameters
        self.train_gp_sklearn({
            'X_train': X_scaled,
            'y_train': y_scaled,
            'X_test': X_scaled,
            'y_test': y_scaled
        }, best_params)
        
        return best_params
        
    def predict(self, X: Union[pd.DataFrame, np.ndarray], return_std: bool = True) -> Tuple[np.ndarray, np.ndarray]:
        """
        Make predictions with uncertainty estimates.
        
        Args:
            X: Input features (DataFrame or array)
            return_std: Whether to return standard deviations
            
        Returns:
            tuple: (Predictions, Standard deviations)
        """
        if not self.trained or self.model is None:
            raise ValueError("Model not trained. Call train() first.")
            
        # Handle DataFrame input
        if isinstance(X, pd.DataFrame):
            if self.feature_columns is not None:
                X = X[self.feature_columns].values
            else:
                X = X.values
                
        # Scale features
        X_scaled = self.scaler_X.transform(X)
        
        # Make prediction based on model type
        if self.use_gpflow and GPFLOW_AVAILABLE:
            # GPflow prediction
            X_tf = tf.convert_to_tensor(X_scaled, dtype=tf.float64)
            mean, var = self.model.predict_f(X_tf)
            
            # Convert to numpy
            y_pred = mean.numpy().flatten()
            sigma = np.sqrt(var.numpy().flatten()) if return_std else None
        else:
            # scikit-learn prediction
            y_pred, sigma = self.model.predict(X_scaled, return_std=return_std)
            
        # Inverse scale the predictions
        y_pred_original_scale = self.scaler_y.inverse_transform(y_pred.reshape(-1, 1)).flatten()
        
        # Scale the standard deviations
        if return_std and sigma is not None:
            # Apply the same scaler standard deviation
            sigma_original_scale = sigma * self.scaler_y.scale_
        else:
            sigma_original_scale = None
            
        # Store last prediction and uncertainty
        self.last_prediction = y_pred_original_scale
        self.last_uncertainty = sigma_original_scale
        
        if return_std:
            return y_pred_original_scale, sigma_original_scale
        else:
            return y_pred_original_scale
            
    def generate_confidence_intervals(self, X: Union[pd.DataFrame, np.ndarray], 
                                     confidence: float = 0.95) -> Dict[str, np.ndarray]:
        """
        Generate prediction intervals at the specified confidence level.
        
        Args:
            X: Input features (DataFrame or array)
            confidence: Confidence level (e.g., 0.95 for 95% intervals)
            
        Returns:
            dict: Dictionary with predictions and intervals
        """
        # Get predictions with uncertainty
        y_pred, sigma = self.predict(X, return_std=True)
        
        # Calculate z-score for the given confidence level
        alpha = 1.0 - confidence
        z = abs(np.percentile(np.random.normal(0, 1, 10000), [alpha/2, 1-alpha/2]))
        
        # Calculate confidence intervals
        lower_bound = y_pred - z[1] * sigma
        upper_bound = y_pred + z[1] * sigma
        
        return {
            'prediction': y_pred,
            'lower_bound': lower_bound,
            'upper_bound': upper_bound,
            'uncertainty': sigma
        }
        
    def forecast_ahead(self, last_X: Union[pd.DataFrame, np.ndarray], 
                      steps: int = 5, 
                      uncertainty_factor: float = 1.0) -> Dict[str, np.ndarray]:
        """
        Generate multi-step forecast with increasing uncertainty.
        
        Args:
            last_X: Last known feature values
            steps: Number of steps to forecast ahead
            uncertainty_factor: Factor to increase uncertainty with each step
            
        Returns:
            dict: Dictionary with forecast and confidence intervals
        """
        if not self.trained or self.model is None:
            raise ValueError("Model not trained. Call train() first.")
            
        # Handle DataFrame input for last known features
        if isinstance(last_X, pd.DataFrame):
            if self.feature_columns is not None:
                last_X = last_X[self.feature_columns].values
            else:
                last_X = last_X.values
                
        # Initialize with the last known features
        current_X = last_X.copy()
        
        # Containers for results
        forecasts = []
        lower_bounds = []
        upper_bounds = []
        uncertainties = []
        
        for step in range(steps):
            # Make prediction for current step
            forecast, sigma = self.predict(current_X, return_std=True)
            
            # Increase uncertainty with each step
            adjusted_sigma = sigma * (1.0 + step * uncertainty_factor)
            
            # Calculate confidence intervals (95%)
            lower_bound = forecast - 1.96 * adjusted_sigma
            upper_bound = forecast + 1.96 * adjusted_sigma
            
            # Store results
            forecasts.append(forecast[0])
            lower_bounds.append(lower_bound[0])
            upper_bounds.append(upper_bound[0])
            uncertainties.append(adjusted_sigma[0])
            
            # Update features for next step based on prediction
            # This is simplified and would need customization for real features
            # For now, we'll just use the prediction as one feature and keep others constant
            if self.feature_columns is not None and self.target_column in self.feature_columns:
                # Find index of target in features
                target_idx = self.feature_columns.index(self.target_column)
                # Update that feature with the prediction
                current_X[0, target_idx] = forecast[0]
            
        return {
            'forecast': np.array(forecasts),
            'lower_bound': np.array(lower_bounds),
            'upper_bound': np.array(upper_bounds),
            'uncertainty': np.array(uncertainties)
        }
        
    def calculate_decision_confidence(self, prediction: float, uncertainty: float, 
                                    threshold: float = 0.0) -> float:
        """
        Calculate confidence in a trading decision.
        
        Args:
            prediction: Predicted value
            uncertainty: Uncertainty (standard deviation)
            threshold: Decision threshold (e.g., 0 for positive/negative)
            
        Returns:
            float: Confidence score (0-1)
        """
        if uncertainty <= 0:
            # Avoid division by zero
            return 1.0 if prediction > threshold else 0.0
            
        # Calculate probability that the true value is above threshold
        z_score = (prediction - threshold) / uncertainty
        probability = 1.0 - 0.5 * (1.0 + np.math.erf(z_score / np.sqrt(2)))
        
        # Transform to confidence (0.5-1.0)
        confidence = 0.5 + 0.5 * abs(2 * probability - 1)
        
        return confidence
        
    def generate_trading_signals(self, X: Union[pd.DataFrame, np.ndarray], 
                               threshold: float = 0.0, 
                               confidence_threshold: float = 0.7) -> Dict[str, np.ndarray]:
        """
        Generate trading signals with confidence scores.
        
        Args:
            X: Input features
            threshold: Decision threshold for prediction
            confidence_threshold: Minimum confidence to generate a signal
            
        Returns:
            dict: Dictionary with signals and confidence scores
        """
        # Make predictions with uncertainty
        predictions, uncertainties = self.predict(X, return_std=True)
        
        # Initialize signals array (0 = no signal)
        signals = np.zeros_like(predictions)
        confidences = np.zeros_like(predictions)
        
        # Generate signals based on predictions and confidence
        for i in range(len(predictions)):
            pred = predictions[i]
            uncertainty = uncertainties[i]
            
            # Calculate confidence in the decision
            confidence = self.calculate_decision_confidence(pred, uncertainty, threshold)
            
            # Assign signal if confidence is high enough
            if confidence >= confidence_threshold:
                signals[i] = 1 if pred > threshold else -1
                confidences[i] = confidence
            else:
                signals[i] = 0
                confidences[i] = confidence
                
        return {
            'predictions': predictions,
            'uncertainties': uncertainties,
            'signals': signals,
            'confidences': confidences
        }
        
    def save_model(self, filename: Optional[str] = None):
        """
        Save the trained model.
        
        Args:
            filename: Output file path (default: uses timestamp)
            
        Returns:
            str: Path to saved model file
        """
        if not self.trained or self.model is None:
            logger.warning("No trained model to save.")
            return None
            
        # Default filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.output_dir, f"gp_model_{timestamp}.pkl")
            
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        # Save model based on type
        if self.use_gpflow and GPFLOW_AVAILABLE:
            # Save GPflow model
            try:
                checkpoint_path = f"{filename}_gpflow_ckpt"
                ckpt = tf.train.Checkpoint(model=self.model)
                manager = tf.train.CheckpointManager(ckpt, checkpoint_path, max_to_keep=1)
                manager.save()
                
                # Save metadata
                metadata = {
                    'feature_columns': self.feature_columns,
                    'target_column': self.target_column,
                    'model_type': 'gpflow',
                    'checkpoint_path': checkpoint_path,
                    'timestamp': datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                
                with open(f"{filename}_metadata.json", 'w') as f:
                    json.dump(metadata, f, indent=2)
                    
                logger.info(f"GPflow model saved to {checkpoint_path}")
                return checkpoint_path
                
            except Exception as e:
                logger.error(f"Error saving GPflow model: {e}")
                return None
        else:
            # Save scikit-learn model
            try:
                import joblib
                
                # Create model package with model and scalers
                model_package = {
                    'model': self.model,
                    'scaler_X': self.scaler_X,
                    'scaler_y': self.scaler_y,
                    'feature_columns': self.feature_columns,
                    'target_column': self.target_column,
                    'model_type': 'sklearn'
                }
                
                joblib.dump(model_package, filename)
                logger.info(f"Model saved to {filename}")
                return filename
                
            except Exception as e:
                logger.error(f"Error saving model: {e}")
                return None
                
    def load_model(self, filename: str):
        """
        Load a trained model.
        
        Args:
            filename: Path to model file
            
        Returns:
            self
        """
        # Check if file exists
        if not os.path.exists(filename):
            logger.error(f"Model file not found: {filename}")
            return self
            
        # Check if it's a GPflow model
        if os.path.exists(f"{filename}_metadata.json"):
            # Load GPflow model
            if not GPFLOW_AVAILABLE:
                logger.error("Cannot load GPflow model: GPflow not available")
                return self
                
            try:
                # Load metadata
                with open(f"{filename}_metadata.json", 'r') as f:
                    metadata = json.load(f)
                    
                self.feature_columns = metadata['feature_columns']
                self.target_column = metadata['target_column']
                checkpoint_path = metadata.get('checkpoint_path', filename)
                
                # Create empty model
                kernel = gpflow.kernels.SquaredExponential()
                dummy_data = np.zeros((2, len(self.feature_columns)))
                dummy_y = np.zeros((2, 1))
                
                self.model = gpflow.models.GPR(
                    (dummy_data, dummy_y),
                    kernel=kernel
                )
                
                # Restore checkpoint
                ckpt = tf.train.Checkpoint(model=self.model)
                ckpt.restore(tf.train.latest_checkpoint(checkpoint_path))
                
                self.use_gpflow = True
                self.trained = True
                
                logger.info(f"GPflow model loaded from {checkpoint_path}")
                
            except Exception as e:
                logger.error(f"Error loading GPflow model: {e}")
                return self
        else:
            # Load scikit-learn model
            try:
                import joblib
                
                model_package = joblib.load(filename)
                
                self.model = model_package['model']
                self.scaler_X = model_package['scaler_X']
                self.scaler_y = model_package['scaler_y']
                self.feature_columns = model_package['feature_columns']
                self.target_column = model_package['target_column']
                
                self.use_gpflow = False
                self.trained = True
                
                logger.info(f"scikit-learn model loaded from {filename}")
                
            except Exception as e:
                logger.error(f"Error loading model: {e}")
                return self
                
        return self
        
    def plot_predictions(self, X: Union[pd.DataFrame, np.ndarray], 
                       y_true: Optional[np.ndarray] = None,
                       dates: Optional[pd.DatetimeIndex] = None,
                       title: str = 'Gaussian Process Predictions',
                       output_file: Optional[str] = None):
        """
        Plot predictions with uncertainty intervals.
        
        Args:
            X: Input features
            y_true: True target values (if available)
            dates: DatetimeIndex for x-axis (if available)
            title: Plot title
            output_file: Path to save the plot (if None, display only)
            
        Returns:
            None
        """
        try:
            import matplotlib.pyplot as plt
            import matplotlib.dates as mdates
        except ImportError:
            logger.warning("Matplotlib not available. Cannot generate plot.")
            return
            
        # Get predictions with uncertainty
        predictions, uncertainties = self.predict(X, return_std=True)
        
        # Calculate confidence intervals (95%)
        lower_bound = predictions - 1.96 * uncertainties
        upper_bound = predictions + 1.96 * uncertainties
        
        # Create x-axis values
        if dates is not None:
            x_values = dates
            x_label = 'Date'
        else:
            x_values = np.arange(len(predictions))
            x_label = 'Index'
            
        # Create figure
        plt.figure(figsize=(12, 6))
        
        # Plot predictions with confidence intervals
        plt.plot(x_values, predictions, 'b-', label='Prediction')
        plt.fill_between(x_values, lower_bound, upper_bound, color='b', alpha=0.2, label='95% Confidence')
        
        # Plot true values if available
        if y_true is not None:
            plt.plot(x_values, y_true, 'r.', label='True Value')
            
        # Set labels and title
        plt.xlabel(x_label)
        plt.ylabel('Value')
        plt.title(title)
        plt.legend(loc='best')
        
        # Format date axis if using dates
        if dates is not None:
            plt.gcf().autofmt_xdate()
            plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            
        # Add grid
        plt.grid(True, alpha=0.3)
        
        # Save or display
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Plot saved to {output_file}")
        else:
            plt.tight_layout()
            plt.show()
            
        plt.close()
        
    def plot_forecast(self, forecast_results: Dict[str, np.ndarray], 
                     historical_data: Optional[pd.Series] = None,
                     start_date: Optional[datetime] = None,
                     freq: str = 'D',
                     title: str = 'Gaussian Process Forecast',
                     output_file: Optional[str] = None):
        """
        Plot multi-step forecast with confidence intervals.
        
        Args:
            forecast_results: Results from forecast_ahead method
            historical_data: Historical data to show before forecast
            start_date: Date to start forecasting from
            freq: Frequency for date range
            title: Plot title
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
            
        # Extract forecast data
        forecast = forecast_results['forecast']
        lower_bound = forecast_results['lower_bound']
        upper_bound = forecast_results['upper_bound']
        
        # Create forecast dates
        if start_date is None:
            start_date = datetime.now()
            
        forecast_dates = pd.date_range(start=start_date, periods=len(forecast), freq=freq)
        
        # Create figure
        plt.figure(figsize=(12, 6))
        
        # Plot historical data if available
        if historical_data is not None:
            hist_dates = historical_data.index
            plt.plot(hist_dates, historical_data.values, 'b-', label='Historical')
            
            # Add vertical line to separate historical from forecast
            plt.axvline(x=hist_dates[-1], color='k', linestyle='--', alpha=0.5)
            
        # Plot forecast with confidence intervals
        plt.plot(forecast_dates, forecast, 'r-', label='Forecast')
        plt.fill_between(forecast_dates, lower_bound, upper_bound, color='r', alpha=0.2, label='95% Confidence')
        
        # Set labels and title
        plt.xlabel('Date')
        plt.ylabel('Value')
        plt.title(title)
        plt.legend(loc='best')
        
        # Format date axis
        plt.gcf().autofmt_xdate()
        plt.gca().xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
        
        # Add grid
        plt.grid(True, alpha=0.3)
        
        # Save or display
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Forecast plot saved to {output_file}")
        else:
            plt.tight_layout()
            plt.show()
            
        plt.close()
        
    def plot_calibration(self, X: Union[pd.DataFrame, np.ndarray], y_true: np.ndarray, 
                        output_file: Optional[str] = None):
        """
        Plot calibration curve to evaluate uncertainty estimates.
        
        Args:
            X: Input features
            y_true: True target values
            output_file: Path to save the plot
            
        Returns:
            None
        """
        try:
            import matplotlib.pyplot as plt
        except ImportError:
            logger.warning("Matplotlib not available. Cannot generate plot.")
            return
            
        # Get predictions with uncertainty
        predictions, uncertainties = self.predict(X, return_std=True)
        
        # Calculate z-scores
        z_scores = (y_true - predictions) / uncertainties
        
        # Create figure with two subplots
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 5))
        
        # Plot z-score histogram
        ax1.hist(z_scores, bins=20, density=True, alpha=0.6, color='b')
        
        # Plot standard normal distribution for comparison
        x = np.linspace(-4, 4, 100)
        ax1.plot(x, np.exp(-x**2/2) / np.sqrt(2*np.pi), 'r-', linewidth=2)
        
        ax1.set_title('Z-score Distribution')
        ax1.set_xlabel('Z-score')
        ax1.set_ylabel('Density')
        ax1.legend(['Standard Normal', 'Model Z-scores'])
        ax1.grid(True, alpha=0.3)
        
        # Plot calibration curve
        coverage_levels = np.linspace(0.1, 0.95, 9)
        theoretical_quantiles = []
        observed_quantiles = []
        
        for p in coverage_levels:
            theoretical_quantiles.append(p)
            
            # Calculate observed coverage
            z_threshold = np.percentile(np.random.normal(0, 1, 10000), [p * 100])[0]
            observed_coverage = np.mean(np.abs(z_scores) <= z_threshold)
            observed_quantiles.append(observed_coverage)
            
        # Plot calibration line
        ax2.plot([0, 1], [0, 1], 'k--', label='Ideal')
        ax2.plot(theoretical_quantiles, observed_quantiles, 'bo-', label='Model')
        
        ax2.set_title('Calibration Curve')
        ax2.set_xlabel('Theoretical Coverage')
        ax2.set_ylabel('Observed Coverage')
        ax2.legend()
        ax2.grid(True, alpha=0.3)
        
        # Add overall assessment
        mse = np.mean((np.array(theoretical_quantiles) - np.array(observed_quantiles))**2)
        calibration_error = np.sqrt(mse)
        
        fig.suptitle(f'Uncertainty Calibration Assessment (Error: {calibration_error:.4f})', fontsize=14)
        
        # Save or display
        plt.tight_layout(rect=[0, 0, 1, 0.95])  # Make room for the suptitle
        
        if output_file:
            plt.savefig(output_file, dpi=300, bbox_inches='tight')
            logger.info(f"Calibration plot saved to {output_file}")
        else:
            plt.show()
            
        plt.close()
        
        return calibration_error


# Example usage
if __name__ == "__main__":
    # Generate synthetic financial data for demonstration
    np.random.seed(42)
    
    # Generate dates
    dates = pd.date_range(start='2020-01-01', periods=500, freq='D')
    
    # Create synthetic price series with trend, noise, and some seasonality
    trend = np.linspace(0, 10, 500)
    noise = np.random.normal(0, 1, 500)
    seasonality = 0.5 * np.sin(np.linspace(0, 15, 500))
    
    # Combine components
    price = 100 + trend + noise + seasonality
    
    # Create features
    # - Lagged prices
    # - Moving averages
    # - Volatility
    df = pd.DataFrame({
        'price': price
    }, index=dates)
    
    # Add lagged features
    for lag in [1, 2, 3, 5, 10]:
        df[f'price_lag_{lag}'] = df['price'].shift(lag)
        
    # Add moving averages
    for window in [5, 10, 20]:
        df[f'ma_{window}'] = df['price'].rolling(window=window).mean()
        
    # Add volatility
    df['volatility'] = df['price'].rolling(window=20).std()
    
    # Drop rows with NaN values
    df = df.dropna()
    
    # Define target (next day's return)
    df['next_return'] = df['price'].pct_change(1).shift(-1)
    
    # Define features
    features = [col for col in df.columns if col not in ['price', 'next_return']]
    target = 'next_return'
    
    # Split data for demonstration
    train_size = int(0.8 * len(df))
    df_train = df.iloc[:train_size]
    df_test = df.iloc[train_size:]
    
    print(f"Training data: {len(df_train)} rows")
    print(f"Test data: {len(df_test)} rows")
    
    # Create and train Gaussian Process forecaster
    gp = GaussianProcessForecaster(use_gpflow=False)
    
    # Train the model
    gp.train(df_train, features, target)
    
    # Make predictions on test set
    predictions, uncertainties = gp.predict(df_test[features], return_std=True)
    
    # Generate confidence intervals
    confidence_intervals = gp.generate_confidence_intervals(df_test[features])
    
    # Generate multi-step forecast
    last_X = df_test[features].iloc[-1:].values
    forecast = gp.forecast_ahead(last_X, steps=30, uncertainty_factor=0.1)
    
    # Generate trading signals
    signals = gp.generate_trading_signals(df_test[features], threshold=0, confidence_threshold=0.6)
    
    # Calculate strategy returns
    strategy_returns = signals['signals'] * df_test['next_return'].values
    cumulative_return = (1 + strategy_returns).cumprod()[-1] - 1
    
    print(f"Strategy cumulative return: {cumulative_return:.2%}")
    
    # Plot predictions
    gp.plot_predictions(df_test[features], df_test['next_return'].values, df_test.index,
                      title='GP Predictions with Uncertainty', output_file='gp_predictions.png')
    
    # Plot forecast
    gp.plot_forecast(forecast, df['price'].iloc[-60:], df.index[-1],
                   title='GP Price Forecast', output_file='gp_forecast.png')
    
    # Plot calibration
    gp.plot_calibration(df_test[features], df_test['next_return'].values, output_file='gp_calibration.png')
    
    # Save the model
    model_file = gp.save_model()
    
    print(f"Model saved to {model_file}")
    print("Example complete - see output plots for visualization of results")