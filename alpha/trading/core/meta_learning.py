#!/usr/bin/env python3
# Filename: src/core/meta_learning.py
"""
Meta-Learning System Module

This module provides a meta-learning framework for:
1. Predicting which strategies work best in different market conditions
2. Learning strategy performance patterns across market regimes
3. Adapting strategy selection based on historical performance
4. Managing strategy allocation through a learning feedback loop

This system enables the trading framework to improve over time by
systematically learning which strategies work in different conditions.
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

# Try to import machine learning libraries
try:
    from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
    from sklearn.preprocessing import StandardScaler
    from sklearn.pipeline import Pipeline
    from sklearn.model_selection import train_test_split, GridSearchCV
    from sklearn.metrics import mean_squared_error, r2_score
    from sklearn.feature_extraction import DictVectorizer
    SKLEARN_AVAILABLE = True
    logger.info("scikit-learn available for meta-learning capabilities")
except ImportError:
    SKLEARN_AVAILABLE = False
    logger.warning("scikit-learn not available. Meta-learning capabilities will be limited.")

# Try to import additional ML libraries for more advanced methods
try:
    import xgboost as xgb
    XGBOOST_AVAILABLE = True
    logger.info("XGBoost available for enhanced meta-learning models")
except ImportError:
    XGBOOST_AVAILABLE = False

class MetaLearningSystem:
    """
    A system that learns which strategies work best in different market conditions.
    """
    
    def __init__(self, db_path: Optional[str] = None, 
                output_dir: str = "data/meta_learning",
                model_type: str = "random_forest"):
        """
        Initialize the meta-learning system.
        
        Args:
            db_path: Path to database with historical strategy performance
            output_dir: Directory for saving models and results
            model_type: Type of model to use ('random_forest', 'gradient_boosting', 'xgboost')
        """
        self.db_path = db_path
        self.output_dir = output_dir
        self.model_type = model_type
        
        # Create output directory
        os.makedirs(output_dir, exist_ok=True)
        
        # Initialize models dictionary (one per strategy or metric)
        self.models = {}
        
        # Track performance data
        self.performance_history = []
        self.market_condition_history = []
        
        # Tracking of feature importance
        self.feature_importance = {}
        
        # Default parameters for different model types
        self.default_params = {
            'random_forest': {
                'n_estimators': 100,
                'max_depth': 10,
                'min_samples_split': 5,
                'min_samples_leaf': 2,
                'random_state': 42
            },
            'gradient_boosting': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'min_samples_split': 5,
                'random_state': 42
            },
            'xgboost': {
                'n_estimators': 100,
                'learning_rate': 0.1,
                'max_depth': 5,
                'colsample_bytree': 0.8,
                'subsample': 0.8,
                'random_state': 42
            }
        }
    
    def extract_strategy_features(self, strategy: str) -> Dict[str, Any]:
        """
        Extract features from a strategy specification.
        
        Args:
            strategy: Strategy identifier or specification
            
        Returns:
            dict: Dictionary of strategy features
        """
        features = {}
        
        # If strategy is just an identifier string
        if isinstance(strategy, str):
            # Extract indicator components if it's a comma-separated list
            if ',' in strategy:
                indicators = strategy.split(',')
                features['num_indicators'] = len(indicators)
                
                # Track which indicators are used
                indicator_types = ['ema', 'macd', 'rsi', 'adx', 'cci', 'vwap', 'atr', 'obv', 'bbands', 'stoch']
                for ind_type in indicator_types:
                    features[f'uses_{ind_type}'] = any(ind_type in ind.lower() for ind in indicators)
                    
                # Categorize by indicator types
                momentum_indicators = ['macd', 'rsi', 'cci', 'stoch']
                trend_indicators = ['ema', 'adx', 'vwap']
                volatility_indicators = ['atr', 'bbands']
                
                features['pct_momentum'] = sum(any(mi in ind.lower() for mi in momentum_indicators) for ind in indicators) / len(indicators)
                features['pct_trend'] = sum(any(ti in ind.lower() for ti in trend_indicators) for ind in indicators) / len(indicators)
                features['pct_volatility'] = sum(any(vi in ind.lower() for vi in volatility_indicators) for ind in indicators) / len(indicators)
            else:
                # Single indicator strategy
                features['num_indicators'] = 1
                features['is_single_indicator'] = True
                
                # Try to categorize the indicator
                indicator = strategy.lower()
                features['is_momentum'] = any(mi in indicator for mi in ['macd', 'rsi', 'cci', 'stoch'])
                features['is_trend'] = any(ti in indicator for ti in ['ema', 'adx', 'vwap'])
                features['is_volatility'] = any(vi in indicator for vi in ['atr', 'bbands'])
        
        # If strategy is a dictionary with more information
        elif isinstance(strategy, dict):
            # Extract basic properties
            strategy_id = strategy.get('id', '')
            features['strategy_id'] = strategy_id
            
            # Extract indicators if available
            if 'indicators' in strategy:
                indicators = strategy['indicators']
                if isinstance(indicators, list):
                    features['num_indicators'] = len(indicators)
                    # Add more indicator-based features as above
                elif isinstance(indicators, str) and ',' in indicators:
                    indicators_list = indicators.split(',')
                    features['num_indicators'] = len(indicators_list)
                    # Add more indicator-based features as above
                
            # Extract parameters if available
            if 'parameters' in strategy:
                params = strategy['parameters']
                if isinstance(params, dict):
                    for key, value in params.items():
                        if isinstance(value, (int, float, bool)):
                            features[f'param_{key}'] = value
            
            # Extract complexity metrics if available
            features['complexity'] = strategy.get('complexity', 1.0)
            features['lookback_period'] = strategy.get('lookback', 20)
        
        return features
    
    def extract_market_condition_features(self, market_state: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract features from market condition data.
        
        Args:
            market_state: Dictionary with market condition information
            
        Returns:
            dict: Dictionary of market condition features
        """
        features = {}
        
        # Extract regime label
        if 'regime' in market_state:
            regime = market_state['regime']
            features['regime'] = regime
            
            # One-hot encode regime
            regimes = ['BULL_TREND', 'BEAR_TREND', 'HIGH_VOLATILITY', 'RANGE_BOUND', 'MEAN_REVERSION']
            for r in regimes:
                features[f'regime_{r}'] = int(regime == r)
        
        # Extract numeric metrics
        numeric_metrics = [
            'volatility', 'trend_strength', 'momentum', 'volume', 'price_momentum',
            'current_vol', 'historical_vol', 'vol_ratio', 'directional_bias',
            'entropy', 'complexity'
        ]
        
        for metric in numeric_metrics:
            if metric in market_state:
                features[metric] = market_state[metric]
        
        # Extract derived features
        if 'current_vol' in market_state and 'historical_vol' in market_state:
            if market_state['historical_vol'] > 0:
                features['vol_ratio'] = market_state['current_vol'] / market_state['historical_vol']
                
        # Extract market breadth indicators if available
        breadth_metrics = ['advance_decline_ratio', 'pct_above_sma50', 'pct_above_sma200', 'new_highs_new_lows']
        for metric in breadth_metrics:
            if metric in market_state:
                features[metric] = market_state[metric]
                
        return features
    
    def prepare_training_data(self, strategy_performance: List[Dict], 
                            market_conditions: List[Dict]) -> Tuple[pd.DataFrame, pd.Series]:
        """
        Prepare training data from strategy performance and market conditions.
        
        Args:
            strategy_performance: List of strategy performance records
            market_conditions: List of market condition records
            
        Returns:
            tuple: (X_features DataFrame, y_target Series)
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for preparing training data")
            return pd.DataFrame(), pd.Series()
            
        if not strategy_performance or not market_conditions:
            logger.warning("No performance data or market conditions provided")
            return pd.DataFrame(), pd.Series()
            
        # Align strategy performance with market conditions by date
        aligned_data = []
        
        for perf in strategy_performance:
            # Extract performance date
            perf_date = perf.get('date')
            if not perf_date:
                continue
                
            # Find matching market condition
            matching_condition = None
            for condition in market_conditions:
                if condition.get('date') == perf_date:
                    matching_condition = condition
                    break
                    
            if not matching_condition:
                continue
                
            # Extract strategy features
            strategy_features = self.extract_strategy_features(perf.get('strategy', ''))
            
            # Extract market condition features
            market_features = self.extract_market_condition_features(matching_condition)
            
            # Combine features
            combined_features = {**strategy_features, **market_features}
            
            # Get target variable (e.g., strategy return)
            target = perf.get('return', perf.get('performance', 0))
            
            # Store aligned data
            aligned_data.append((combined_features, target))
            
        if not aligned_data:
            logger.warning("No aligned data found after matching")
            return pd.DataFrame(), pd.Series()
            
        # Extract features and targets
        features_list, targets = zip(*aligned_data)
        
        # Convert to DataFrame
        dvec = DictVectorizer(sparse=False)
        X = dvec.fit_transform(features_list)
        feature_names = dvec.get_feature_names_out()
        
        # Store feature names for later interpretation
        self.feature_names = feature_names
        
        X_df = pd.DataFrame(X, columns=feature_names)
        y_series = pd.Series(targets)
        
        logger.info(f"Prepared training data with {X_df.shape[1]} features and {len(y_series)} samples")
        
        return X_df, y_series
    
    def train_meta_model(self, X: pd.DataFrame, y: pd.Series, 
                       target_name: str = 'performance',
                       params: Optional[Dict] = None) -> Any:
        """
        Train a meta-learning model.
        
        Args:
            X: Feature DataFrame
            y: Target Series
            target_name: Name of the target metric
            params: Model parameters (optional)
            
        Returns:
            Trained model object
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for training models")
            return None
            
        if X.empty or y.empty:
            logger.warning("Empty training data")
            return None
            
        # Select model type
        if self.model_type == 'random_forest':
            base_model = RandomForestRegressor
            default_params = self.default_params['random_forest']
        elif self.model_type == 'gradient_boosting':
            base_model = GradientBoostingRegressor
            default_params = self.default_params['gradient_boosting']
        elif self.model_type == 'xgboost' and XGBOOST_AVAILABLE:
            base_model = xgb.XGBRegressor
            default_params = self.default_params['xgboost']
        else:
            logger.warning(f"Model type {self.model_type} not available. Using random forest.")
            base_model = RandomForestRegressor
            default_params = self.default_params['random_forest']
            
        # Use provided parameters or defaults
        model_params = params or default_params
        
        # Create preprocessing pipeline with scaling
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('model', base_model(**model_params))
        ])
        
        # Train the model
        try:
            pipeline.fit(X, y)
            
            # Extract model from pipeline for feature importance
            model = pipeline.named_steps['model']
            
            # Store feature importance (if available)
            if hasattr(model, 'feature_importances_'):
                importance = model.feature_importances_
                feature_names = X.columns
                
                importances = dict(zip(feature_names, importance))
                importances = {k: v for k, v in sorted(importances.items(), key=lambda item: item[1], reverse=True)}
                
                self.feature_importance[target_name] = importances
                
                # Log top features
                top_features = list(importances.items())[:10]
                logger.info(f"Top features for {target_name}: {top_features}")
                
            # Calculate training metrics
            y_pred = pipeline.predict(X)
            mse = mean_squared_error(y, y_pred)
            r2 = r2_score(y, y_pred)
            
            logger.info(f"Trained {self.model_type} model for {target_name} - MSE: {mse:.6f}, R²: {r2:.4f}")
            
            # Store the model
            self.models[target_name] = pipeline
            
            return pipeline
            
        except Exception as e:
            logger.error(f"Error training meta-model: {e}")
            return None
    
    def optimize_hyperparameters(self, X: pd.DataFrame, y: pd.Series,
                               target_name: str = 'performance',
                               cv: int = 3) -> Dict:
        """
        Optimize model hyperparameters using grid search.
        
        Args:
            X: Feature DataFrame
            y: Target Series
            target_name: Name of the target metric
            cv: Number of cross-validation folds
            
        Returns:
            dict: Best parameters
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for hyperparameter optimization")
            return self.default_params[self.model_type]
            
        if X.empty or y.empty:
            logger.warning("Empty training data")
            return self.default_params[self.model_type]
            
        # Select parameter grid based on model type
        if self.model_type == 'random_forest':
            base_model = RandomForestRegressor
            param_grid = {
                'model__n_estimators': [50, 100, 200],
                'model__max_depth': [5, 10, 15, None],
                'model__min_samples_split': [2, 5, 10],
                'model__min_samples_leaf': [1, 2, 4]
            }
        elif self.model_type == 'gradient_boosting':
            base_model = GradientBoostingRegressor
            param_grid = {
                'model__n_estimators': [50, 100, 200],
                'model__learning_rate': [0.01, 0.05, 0.1, 0.2],
                'model__max_depth': [3, 5, 7],
                'model__min_samples_split': [2, 5, 10]
            }
        elif self.model_type == 'xgboost' and XGBOOST_AVAILABLE:
            base_model = xgb.XGBRegressor
            param_grid = {
                'model__n_estimators': [50, 100, 200],
                'model__learning_rate': [0.01, 0.05, 0.1, 0.2],
                'model__max_depth': [3, 5, 7],
                'model__colsample_bytree': [0.6, 0.8, 1.0],
                'model__subsample': [0.6, 0.8, 1.0]
            }
        else:
            logger.warning(f"Model type {self.model_type} not available. Using random forest.")
            base_model = RandomForestRegressor
            param_grid = {
                'model__n_estimators': [50, 100, 200],
                'model__max_depth': [5, 10, 15, None],
                'model__min_samples_split': [2, 5, 10],
                'model__min_samples_leaf': [1, 2, 4]
            }
            
        # Create preprocessing pipeline with scaling
        pipeline = Pipeline([
            ('scaler', StandardScaler()),
            ('model', base_model())
        ])
        
        # Run grid search
        try:
            grid_search = GridSearchCV(
                pipeline, param_grid, cv=cv, scoring='neg_mean_squared_error',
                verbose=1, n_jobs=-1
            )
            
            grid_search.fit(X, y)
            
            # Get best parameters
            best_params = grid_search.best_params_
            
            # Convert from model__ prefix to regular parameters
            processed_params = {}
            for key, value in best_params.items():
                processed_params[key.replace('model__', '')] = value
                
            logger.info(f"Best hyperparameters for {target_name}: {processed_params}")
            
            # Train model with best parameters
            best_model = grid_search.best_estimator_
            self.models[target_name] = best_model
            
            # Calculate metrics
            y_pred = best_model.predict(X)
            mse = mean_squared_error(y, y_pred)
            r2 = r2_score(y, y_pred)
            
            logger.info(f"Optimized {self.model_type} model for {target_name} - MSE: {mse:.6f}, R²: {r2:.4f}")
            
            return processed_params
            
        except Exception as e:
            logger.error(f"Error optimizing hyperparameters: {e}")
            return self.default_params[self.model_type]
    
    def predict_strategy_performance(self, strategies: List[Union[str, Dict]], 
                                  market_condition: Dict) -> Dict[str, float]:
        """
        Predict performance of strategies under given market conditions.
        
        Args:
            strategies: List of strategy specifications
            market_condition: Current market condition
            
        Returns:
            dict: Dictionary of predicted performance for each strategy
        """
        if not SKLEARN_AVAILABLE or 'performance' not in self.models:
            logger.warning("No trained model available for performance prediction")
            return {}
            
        # Extract features for each strategy
        feature_rows = []
        strategy_ids = []
        
        for strategy in strategies:
            # Extract strategy features
            strategy_features = self.extract_strategy_features(strategy)
            
            # Extract market condition features
            market_features = self.extract_market_condition_features(market_condition)
            
            # Combine features
            combined_features = {**strategy_features, **market_features}
            
            # Store for prediction
            feature_rows.append(combined_features)
            
            # Store strategy ID
            if isinstance(strategy, dict) and 'id' in strategy:
                strategy_ids.append(strategy['id'])
            elif isinstance(strategy, str):
                strategy_ids.append(strategy)
            else:
                strategy_ids.append(f"strategy_{len(strategy_ids)}")
                
        if not feature_rows:
            return {}
            
        # Convert features to DataFrame
        dvec = DictVectorizer(sparse=False)
        X = dvec.fit_transform(feature_rows)
        feature_names = dvec.get_feature_names_out()
        
        # Ensure feature alignment with model
        model = self.models['performance']
        
        try:
            # Make predictions
            predictions = model.predict(X)
            
            # Combine predictions with strategy IDs
            performance_predictions = dict(zip(strategy_ids, predictions))
            
            return performance_predictions
            
        except Exception as e:
            logger.error(f"Error making predictions: {e}")
            return {}
    
    def rank_strategies(self, strategies: List[Union[str, Dict]], 
                       market_condition: Dict,
                       min_performance: float = 0.0) -> List[Tuple[str, float]]:
        """
        Rank strategies by predicted performance.
        
        Args:
            strategies: List of strategy specifications
            market_condition: Current market condition
            min_performance: Minimum performance threshold
            
        Returns:
            list: Ranked list of (strategy_id, predicted_performance) tuples
        """
        # Get performance predictions
        predictions = self.predict_strategy_performance(strategies, market_condition)
        
        if not predictions:
            return []
            
        # Filter by minimum performance
        filtered_predictions = {k: v for k, v in predictions.items() if v >= min_performance}
        
        # Sort by performance (descending)
        ranked_strategies = sorted(filtered_predictions.items(), key=lambda x: x[1], reverse=True)
        
        return ranked_strategies
    
    def add_performance_record(self, strategy: Union[str, Dict], 
                             market_condition: Dict,
                             performance: float,
                             date: Optional[str] = None) -> None:
        """
        Add a performance record for a strategy under given market conditions.
        
        Args:
            strategy: Strategy specification
            market_condition: Market condition
            performance: Observed performance
            date: Date of observation (default: current date)
        """
        if date is None:
            date = datetime.now().strftime('%Y-%m-%d')
            
        # Create performance record
        record = {
            'date': date,
            'strategy': strategy,
            'performance': performance
        }
        
        # Create market condition record with same date
        condition_record = {
            'date': date,
            **market_condition
        }
        
        # Add to history
        self.performance_history.append(record)
        self.market_condition_history.append(condition_record)
        
        logger.debug(f"Added performance record for {date}: {performance:.4f}")
    
    def update_models(self, retrain_all: bool = False) -> bool:
        """
        Update meta-learning models with latest performance data.
        
        Args:
            retrain_all: Whether to retrain all models from scratch
            
        Returns:
            bool: Success flag
        """
        if not SKLEARN_AVAILABLE:
            logger.error("scikit-learn not available for updating models")
            return False
            
        if not self.performance_history or not self.market_condition_history:
            logger.warning("No performance data available for training")
            return False
            
        # Prepare training data
        X, y = self.prepare_training_data(self.performance_history, self.market_condition_history)
        
        if X.empty or y.empty:
            logger.warning("Could not prepare training data")
            return False
            
        # Train or update models
        if retrain_all or 'performance' not in self.models:
            logger.info("Training new meta-learning model")
            model = self.train_meta_model(X, y, 'performance')
        else:
            logger.info("Updating existing meta-learning model")
            # For simplistic update, we'll just retrain - in a more sophisticated system
            # we could implement incremental learning here
            model = self.train_meta_model(X, y, 'performance')
            
        return model is not None
    
    def export_model_insights(self, filename: Optional[str] = None) -> None:
        """
        Export model insights for visualization and interpretation.
        
        Args:
            filename: Output file path (default: uses timestamp)
        """
        if not self.feature_importance:
            logger.warning("No feature importance data available")
            return
            
        # Default filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.output_dir, f"meta_model_insights_{timestamp}.json")
            
        # Create insights object
        insights = {
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'model_type': self.model_type,
            'feature_importance': self.feature_importance,
            'training_samples': len(self.performance_history),
            'models': list(self.models.keys())
        }
        
        # Add additional insights
        if hasattr(self, 'feature_names'):
            insights['feature_names'] = self.feature_names.tolist()
            
        # Convert any NumPy or non-serializable types
        def convert_for_json(obj):
            if isinstance(obj, np.integer):
                return int(obj)
            elif isinstance(obj, np.floating):
                return float(obj)
            elif isinstance(obj, np.ndarray):
                return obj.tolist()
            elif isinstance(obj, (pd.DataFrame, pd.Series)):
                return obj.to_dict()
            return obj
            
        # Export as JSON
        try:
            with open(filename, 'w') as f:
                json.dump(insights, f, default=convert_for_json, indent=2)
                
            logger.info(f"Model insights exported to {filename}")
        except Exception as e:
            logger.error(f"Error exporting model insights: {e}")
    
    def save_models(self, filename: Optional[str] = None) -> str:
        """
        Save trained meta-learning models.
        
        Args:
            filename: Output file path (default: uses timestamp)
            
        Returns:
            str: Path to saved model
        """
        if not self.models:
            logger.warning("No models to save")
            return ""
            
        # Default filename
        if filename is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = os.path.join(self.output_dir, f"meta_learning_models_{timestamp}.pkl")
            
        # Ensure directory exists
        os.makedirs(os.path.dirname(filename), exist_ok=True)
        
        try:
            import joblib
            
            # Save models dictionary
            joblib.dump(self.models, filename)
            
            # Save feature importance separately
            if self.feature_importance:
                insights_file = filename.replace('.pkl', '_insights.json')
                self.export_model_insights(insights_file)
                
            logger.info(f"Meta-learning models saved to {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error saving models: {e}")
            return ""
    
    def load_models(self, filename: str) -> bool:
        """
        Load trained meta-learning models.
        
        Args:
            filename: Path to saved models
            
        Returns:
            bool: Success flag
        """
        if not os.path.exists(filename):
            logger.error(f"Model file not found: {filename}")
            return False
            
        try:
            import joblib
            
            # Load models dictionary
            self.models = joblib.load(filename)
            
            # Try to load insights file
            insights_file = filename.replace('.pkl', '_insights.json')
            if os.path.exists(insights_file):
                with open(insights_file, 'r') as f:
                    insights = json.load(f)
                    
                if 'feature_importance' in insights:
                    self.feature_importance = insights['feature_importance']
                    
                if 'feature_names' in insights:
                    self.feature_names = np.array(insights['feature_names'])
                    
            logger.info(f"Meta-learning models loaded from {filename}")
            return True
            
        except Exception as e:
            logger.error(f"Error loading models: {e}")
            return False
    
    def plot_feature_importance(self, target_name: str = 'performance', top_n: int = 20, 
                              output_file: Optional[str] = None) -> None:
        """
        Plot feature importance for a given target metric.
        
        Args:
            target_name: Name of the target metric
            top_n: Number of top features to plot
            output_file: Path to save the plot
        """
        if target_name not in self.feature_importance:
            logger.warning(f"No feature importance data for {target_name}")
            return
            
        try:
            import matplotlib.pyplot as plt
            
            # Get feature importance
            importance = self.feature_importance[target_name]
            
            # Sort and get top N
            sorted_importance = dict(sorted(importance.items(), key=lambda x: x[1], reverse=True)[:top_n])
            
            # Create figure
            plt.figure(figsize=(12, 8))
            
            # Plot horizontal bar chart
            features = list(sorted_importance.keys())
            values = list(sorted_importance.values())
            
            plt.barh(range(len(features)), values, align='center')
            plt.yticks(range(len(features)), features)
            
            # Add labels and title
            plt.xlabel('Importance')
            plt.ylabel('Feature')
            plt.title(f'Top {top_n} Features for {target_name}')
            
            # Add grid
            plt.grid(True, alpha=0.3)
            
            # Color code by feature type
            colors = []
            for feature in features:
                if 'regime' in feature:
                    colors.append('darkred')
                elif any(m in feature for m in ['volatility', 'vol_ratio']):
                    colors.append('darkorange')
                elif any(m in feature for m in ['trend', 'momentum']):
                    colors.append('darkgreen')
                elif 'uses_' in feature:
                    colors.append('darkblue')
                else:
                    colors.append('darkgrey')
                    
            # Update bar colors
            for i, patch in enumerate(plt.gca().patches):
                patch.set_facecolor(colors[i])
                
            # Add legend
            from matplotlib.patches import Patch
            legend_elements = [
                Patch(facecolor='darkred', label='Market Regime'),
                Patch(facecolor='darkorange', label='Volatility'),
                Patch(facecolor='darkgreen', label='Trend/Momentum'),
                Patch(facecolor='darkblue', label='Indicator Type'),
                Patch(facecolor='darkgrey', label='Other')
            ]
            plt.legend(handles=legend_elements, loc='lower right')
            
            # Save or display
            if output_file:
                plt.tight_layout()
                plt.savefig(output_file, dpi=300, bbox_inches='tight')
                logger.info(f"Feature importance plot saved to {output_file}")
            else:
                plt.tight_layout()
                plt.show()
                
            plt.close()
            
        except ImportError:
            logger.warning("Matplotlib not available. Cannot generate plot.")
        except Exception as e:
            logger.error(f"Error plotting feature importance: {e}")
    
    def plot_strategy_performance_matrix(self, strategies: List[str], 
                                       market_conditions: List[Dict],
                                       output_file: Optional[str] = None) -> None:
        """
        Plot a matrix of predicted strategy performance across market conditions.
        
        Args:
            strategies: List of strategy identifiers
            market_conditions: List of market condition dictionaries
            output_file: Path to save the plot
        """
        if not strategies or not market_conditions:
            logger.warning("No strategies or market conditions provided")
            return
            
        try:
            import matplotlib.pyplot as plt
            import seaborn as sns
            
            # Generate performance predictions for each strategy and market condition
            performance_matrix = []
            
            for condition in market_conditions:
                predictions = self.predict_strategy_performance(strategies, condition)
                performance_matrix.append([predictions.get(s, 0) for s in strategies])
                
            # Create matrix
            performance_df = pd.DataFrame(performance_matrix, 
                                         columns=strategies,
                                         index=[m.get('regime', f"Condition_{i}") for i, m in enumerate(market_conditions)])
            
            # Create figure
            plt.figure(figsize=(12, 8))
            
            # Create heatmap
            sns.heatmap(performance_df, annot=True, cmap='RdYlGn', center=0, 
                      linewidths=.5, cbar_kws={'label': 'Predicted Performance'})
            
            # Add labels and title
            plt.xlabel('Strategy')
            plt.ylabel('Market Regime')
            plt.title('Predicted Strategy Performance by Market Regime')
            
            # Rotate x-axis labels for readability
            plt.xticks(rotation=45, ha='right')
            
            # Save or display
            if output_file:
                plt.tight_layout()
                plt.savefig(output_file, dpi=300, bbox_inches='tight')
                logger.info(f"Strategy performance matrix saved to {output_file}")
            else:
                plt.tight_layout()
                plt.show()
                
            plt.close()
            
        except ImportError:
            logger.warning("Matplotlib or seaborn not available. Cannot generate plot.")
        except Exception as e:
            logger.error(f"Error plotting strategy performance matrix: {e}")
    
    def analyze_market_regime_transitions(self) -> Dict[str, Any]:
        """
        Analyze strategy performance during market regime transitions.
        
        Returns:
            dict: Analysis of strategy performance during transitions
        """
        if not self.performance_history or not self.market_condition_history:
            logger.warning("No performance data available for transition analysis")
            return {}
            
        # Extract regime sequences
        regime_sequence = []
        for condition in self.market_condition_history:
            regime = condition.get('regime', 'UNKNOWN')
            regime_sequence.append(regime)
            
        # Find regime transitions
        transitions = []
        for i in range(1, len(regime_sequence)):
            if regime_sequence[i] != regime_sequence[i-1]:
                transitions.append((i-1, regime_sequence[i-1], regime_sequence[i]))
                
        if not transitions:
            return {"transitions": 0, "message": "No regime transitions found in data"}
            
        # Analyze strategy performance during transitions
        transition_performance = {}
        
        for trans_idx, from_regime, to_regime in transitions:
            transition_key = f"{from_regime}_to_{to_regime}"
            
            # Get performance records around transition
            pre_transition = self.performance_history[max(0, trans_idx-2):trans_idx+1]
            post_transition = self.performance_history[trans_idx+1:min(len(self.performance_history), trans_idx+4)]
            
            # Group by strategy
            strategies = {}
            
            for record in pre_transition + post_transition:
                strategy = record.get('strategy', '')
                if isinstance(strategy, dict) and 'id' in strategy:
                    strategy_id = strategy['id']
                elif isinstance(strategy, str):
                    strategy_id = strategy
                else:
                    continue
                    
                if strategy_id not in strategies:
                    strategies[strategy_id] = {
                        'pre': [],
                        'post': []
                    }
                    
                if record in pre_transition:
                    strategies[strategy_id]['pre'].append(record.get('performance', 0))
                else:
                    strategies[strategy_id]['post'].append(record.get('performance', 0))
                    
            # Calculate average performance
            for strategy_id, data in strategies.items():
                data['pre_avg'] = sum(data['pre']) / len(data['pre']) if data['pre'] else 0
                data['post_avg'] = sum(data['post']) / len(data['post']) if data['post'] else 0
                data['change'] = data['post_avg'] - data['pre_avg']
                
            # Store transition analysis
            transition_performance[transition_key] = {
                'from_regime': from_regime,
                'to_regime': to_regime,
                'strategies': strategies,
                'best_strategy': max(strategies.items(), key=lambda x: x[1]['change'])[0] if strategies else None,
                'date': self.market_condition_history[trans_idx].get('date', 'unknown')
            }
            
        # Overall analysis
        num_transitions = len(transitions)
        regime_pairs = {}
        
        for transition_key, data in transition_performance.items():
            from_regime = data['from_regime']
            to_regime = data['to_regime']
            pair = (from_regime, to_regime)
            
            if pair not in regime_pairs:
                regime_pairs[pair] = []
                
            regime_pairs[pair].append(data)
            
        # Calculate statistics by transition type
        transition_stats = {}
        
        for pair, instances in regime_pairs.items():
            from_regime, to_regime = pair
            key = f"{from_regime}_to_{to_regime}"
            
            best_strategies = {}
            for instance in instances:
                for strategy_id, perf in instance['strategies'].items():
                    if strategy_id not in best_strategies:
                        best_strategies[strategy_id] = []
                        
                    best_strategies[strategy_id].append(perf['change'])
                    
            # Calculate average performance change by strategy
            avg_performance = {}
            for strategy_id, changes in best_strategies.items():
                avg_performance[strategy_id] = sum(changes) / len(changes)
                
            # Find best strategy for this transition type
            if avg_performance:
                best_strategy = max(avg_performance.items(), key=lambda x: x[1])
            else:
                best_strategy = (None, 0)
                
            transition_stats[key] = {
                'from_regime': from_regime,
                'to_regime': to_regime,
                'count': len(instances),
                'best_strategy': best_strategy[0],
                'avg_performance_change': best_strategy[1],
                'all_strategies': avg_performance
            }
            
        return {
            'transitions': num_transitions,
            'transition_types': len(regime_pairs),
            'transition_performance': transition_performance,
            'transition_stats': transition_stats
        }
    
    def get_regime_specific_strategies(self, market_regime: str, top_n: int = 3) -> List[str]:
        """
        Get strategies that work best in a specific market regime.
        
        Args:
            market_regime: Target market regime
            top_n: Number of top strategies to return
            
        Returns:
            list: List of best strategy identifiers for the regime
        """
        # Find all unique strategies
        all_strategies = set()
        
        for record in self.performance_history:
            strategy = record.get('strategy', '')
            if isinstance(strategy, dict) and 'id' in strategy:
                all_strategies.add(strategy['id'])
            elif isinstance(strategy, str):
                all_strategies.add(strategy)
                
        # Create sample market condition with target regime
        market_condition = {'regime': market_regime}
        
        # Rank strategies
        ranked = self.rank_strategies(list(all_strategies), market_condition)
        
        # Return top N
        return [strategy for strategy, _ in ranked[:top_n]]
    
    def recommend_strategy_allocation(self, current_market_condition: Dict, 
                                    available_strategies: List[Union[str, Dict]],
                                    min_allocation: float = 0.05,
                                    max_total: float = 1.0) -> Dict[str, float]:
        """
        Recommend allocation across strategies based on predicted performance.
        
        Args:
            current_market_condition: Current market condition
            available_strategies: List of available strategies
            min_allocation: Minimum allocation per strategy
            max_total: Maximum total allocation
            
        Returns:
            dict: Recommended allocation by strategy
        """
        # Get ranked strategies
        ranked = self.rank_strategies(available_strategies, current_market_condition)
        
        if not ranked:
            return {}
            
        # Extract performance scores
        strategies, scores = zip(*ranked)
        
        # Convert to numpy array
        scores = np.array(scores)
        
        # Ensure positive scores
        positive_scores = np.maximum(scores, 0)
        
        # If all strategies have zero or negative expected performance
        if np.sum(positive_scores) == 0:
            logger.warning("All strategies have zero or negative expected performance")
            return {}
            
        # Calculate raw allocations based on relative performance
        raw_allocations = positive_scores / np.sum(positive_scores) * max_total
        
        # Apply minimum allocation threshold
        allocations = np.maximum(raw_allocations, min_allocation)
        
        # Scale down if total exceeds maximum
        total_allocation = np.sum(allocations)
        if total_allocation > max_total:
            allocations = allocations * (max_total / total_allocation)
            
        # Create allocation dictionary
        return dict(zip(strategies, allocations))
    
    def update_from_feedback(self, strategy: Union[str, Dict], 
                           market_condition: Dict,
                           actual_performance: float,
                           expected_performance: float,
                           learning_rate: float = 0.1) -> None:
        """
        Update model based on feedback from actual vs. expected performance.
        
        Args:
            strategy: Strategy specification
            market_condition: Market condition
            actual_performance: Actual observed performance
            expected_performance: Expected performance from model
            learning_rate: Learning rate for update (0-1)
        """
        # Calculate prediction error
        error = actual_performance - expected_performance
        
        # Add performance record
        self.add_performance_record(strategy, market_condition, actual_performance)
        
        # Simple update mechanism - retrain if error is large
        if abs(error) > 0.1:
            logger.info(f"Large prediction error detected ({error:.4f}). Updating models.")
            self.update_models()
            
        logger.debug(f"Updated model with feedback: error={error:.4f}")


# Example usage
if __name__ == "__main__":
    # Create meta-learning system
    meta_learner = MetaLearningSystem(model_type='random_forest')
    
    # Generate synthetic data for demonstration
    np.random.seed(42)
    
    # Define sample strategies
    strategies = [
        "ema,rsi",
        "macd,adx",
        "vwap,atr,cci",
        "rsi,cci,atr",
        "ema,macd,bbands"
    ]
    
    # Define market regimes
    regimes = ["BULL_TREND", "BEAR_TREND", "HIGH_VOLATILITY", "RANGE_BOUND"]
    
    # Generate synthetic performance data
    performance_history = []
    market_condition_history = []
    
    # Define synthetic performance characteristics by regime
    regime_performance = {
        "BULL_TREND": {
            "ema,rsi": (0.05, 0.02),         # (mean, std) for normal distribution
            "macd,adx": (0.03, 0.015),
            "vwap,atr,cci": (0.02, 0.01),
            "rsi,cci,atr": (0.035, 0.015),
            "ema,macd,bbands": (0.04, 0.02)
        },
        "BEAR_TREND": {
            "ema,rsi": (-0.02, 0.015),
            "macd,adx": (-0.01, 0.01),
            "vwap,atr,cci": (0.01, 0.01),
            "rsi,cci,atr": (0.02, 0.015),
            "ema,macd,bbands": (-0.03, 0.02)
        },
        "HIGH_VOLATILITY": {
            "ema,rsi": (-0.01, 0.03),
            "macd,adx": (0.0, 0.025),
            "vwap,atr,cci": (0.03, 0.02),
            "rsi,cci,atr": (0.025, 0.02),
            "ema,macd,bbands": (0.01, 0.025)
        },
        "RANGE_BOUND": {
            "ema,rsi": (0.01, 0.01),
            "macd,adx": (0.015, 0.01),
            "vwap,atr,cci": (0.005, 0.005),
            "rsi,cci,atr": (0.01, 0.01),
            "ema,macd,bbands": (0.005, 0.01)
        }
    }
    
    # Generate synthetic data
    for _ in range(500):
        # Select random regime
        regime = np.random.choice(regimes)
        
        # Generate date
        days_ago = np.random.randint(1, 365)
        date = (datetime.now() - timedelta(days=days_ago)).strftime('%Y-%m-%d')
        
        # Create market condition
        market_condition = {
            'regime': regime,
            'volatility': np.random.uniform(0.01, 0.05),
            'trend_strength': np.random.uniform(0, 1),
            'price_momentum': np.random.uniform(-0.1, 0.1),
            'vol_ratio': np.random.uniform(0.5, 2.0),
            'date': date
        }
        
        # For each strategy, generate performance
        for strategy in strategies:
            if regime in regime_performance and strategy in regime_performance[regime]:
                mean, std = regime_performance[regime][strategy]
                performance = np.random.normal(mean, std)
                
                # Add performance record
                meta_learner.add_performance_record(strategy, market_condition, performance, date)
    
    # Train meta-learning model
    meta_learner.update_models()
    
    # Export model insights
    meta_learner.export_model_insights()
    
    # Plot feature importance
    meta_learner.plot_feature_importance(output_file='feature_importance.png')
    
    # Test prediction on new market condition
    current_condition = {
        'regime': 'BULL_TREND',
        'volatility': 0.02,
        'trend_strength': 0.7,
        'price_momentum': 0.05,
        'vol_ratio': 1.2
    }
    
    predictions = meta_learner.predict_strategy_performance(strategies, current_condition)
    
    print("\nPredicted Strategy Performance:")
    for strategy, performance in sorted(predictions.items(), key=lambda x: x[1], reverse=True):
        print(f"{strategy}: {performance:.4f}")
        
    # Get recommended allocation
    allocation = meta_learner.recommend_strategy_allocation(
        current_condition, strategies, min_allocation=0.05, max_total=1.0)
    
    print("\nRecommended Strategy Allocation:")
    for strategy, alloc in allocation.items():
        print(f"{strategy}: {alloc:.2%}")
        
    # Analyze regime transitions
    transition_analysis = meta_learner.analyze_market_regime_transitions()
    
    print("\nRegime Transition Analysis:")
    for transition, stats in transition_analysis.get('transition_stats', {}).items():
        print(f"{transition}: Best strategy: {stats['best_strategy']} "
             f"(Avg performance change: {stats['avg_performance_change']:.4f})")
        
    # Save the trained model
    model_file = meta_learner.save_models()
    print(f"\nMeta-learning models saved to {model_file}")