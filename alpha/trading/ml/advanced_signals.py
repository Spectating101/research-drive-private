#!/usr/bin/env python3
"""
Advanced Machine Learning Signal Generation Module

This module implements sophisticated ML techniques for signal generation,
specifically designed for Indonesian market inefficiencies and characteristics.

Features:
- Ensemble learning with multiple base models
- Deep learning with LSTM/GRU for time series
- Reinforcement learning for dynamic strategy adaptation
- Market microstructure-aware feature engineering
- Cross-validation with time series splits
- Feature importance analysis
- Model interpretability tools
"""

import numpy as np
import pandas as pd
import sqlite3
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple, Optional
import warnings
warnings.filterwarnings('ignore')

# Try to import Rust backend
try:
    import sharpe_rust
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False
    print("Warning: Rust backend not available, using Python implementation")

# ML Libraries
try:
    from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
    from sklearn.linear_model import LogisticRegression
    from sklearn.svm import SVC
    from sklearn.preprocessing import StandardScaler, RobustScaler
    from sklearn.model_selection import TimeSeriesSplit
    from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
    from sklearn.feature_selection import SelectKBest, f_classif, RFE
    from sklearn.decomposition import PCA
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False
    logging.warning("Scikit-learn not available. ML features disabled.")

try:
    import tensorflow as tf
    from tensorflow.keras.models import Sequential
    from tensorflow.keras.layers import LSTM, Dense, Dropout, GRU, Bidirectional
    from tensorflow.keras.optimizers import Adam
    from tensorflow.keras.callbacks import EarlyStopping, ReduceLROnPlateau
    TENSORFLOW_AVAILABLE = True
except ImportError:
    TENSORFLOW_AVAILABLE = False
    logging.warning("TensorFlow not available. Deep learning features disabled.")

try:
    import optuna
    from optuna.integration import OptunaSearchCV
    OPTUNA_AVAILABLE = True
except ImportError:
    OPTUNA_AVAILABLE = False
    logging.warning("Optuna not available. Hyperparameter optimization disabled.")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class AdvancedSignalGenerator:
    """
    Advanced ML-based signal generator for Indonesian markets.
    
    Incorporates multiple ML techniques and market-specific adaptations:
    - Ensemble learning for robust predictions
    - Deep learning for complex pattern recognition
    - Feature engineering for market microstructure
    - Cross-validation with proper time series splits
    - Model interpretability and feature importance
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db', 
                 lookback_days: int = 60,
                 prediction_horizon: int = 5):
        """
        Initialize the advanced signal generator.
        
        Args:
            db_path: Path to historical data database
            lookback_days: Number of days to look back for features
            prediction_horizon: Days ahead to predict
        """
        self.db_path = db_path
        self.lookback_days = lookback_days
        self.prediction_horizon = prediction_horizon
        
        # Model storage
        self.models = {}
        self.scalers = {}
        self.feature_importance = {}
        
        # Indonesian market specific parameters
        self.idx_characteristics = {
            'min_volume_threshold': 1000000,  # Minimum volume for liquidity
            'price_impact_threshold': 0.02,   # 2% price impact threshold
            'volatility_multiplier': 1.5,     # IDX typically more volatile
            'correlation_decay': 0.95,        # Faster correlation decay in emerging markets
            'momentum_persistence': 0.7       # Momentum effects persist longer
        }
        
        # Feature engineering parameters
        self.feature_params = {
            'technical_windows': [5, 10, 20, 50],
            'volume_windows': [5, 10, 20],
            'volatility_windows': [10, 20, 50],
            'momentum_windows': [5, 10, 20],
            'correlation_windows': [20, 50]
        }
        
        logger.info("Advanced Signal Generator initialized for Indonesian markets")
    
    def engineer_features(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Advanced feature engineering for Indonesian markets.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            
        Returns:
            DataFrame with engineered features
        """
        if df.empty or len(df) < max(self.feature_params['technical_windows']):
            return pd.DataFrame()
        
        # Try to use Rust backend for technical indicators
        if RUST_AVAILABLE:
            try:
                prices = df[['open', 'high', 'low', 'close']].values
                volumes = df['volume'].values
                
                # Get Rust-calculated indicators
                rust_indicators = sharpe_rust.calculate_technical_indicators_rust(prices, volumes)
                
                # Create features DataFrame
                features = df.copy()
                
                # Add Rust-calculated indicators
                for indicator_name, values in rust_indicators.items():
                    if len(values) == len(features):
                        features[f'rust_{indicator_name}'] = values
                
                # Continue with Python-specific features
                features = self._add_python_features(features, symbol)
                
                return features
            except Exception as e:
                logger.warning(f"Rust backend failed, falling back to Python: {e}")
        
        # Python fallback implementation
        features = df.copy()
        features = self._add_python_features(features, symbol)
        return features
    
    def _add_python_features(self, features: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Add Python-specific features to the DataFrame."""
        # Price-based features
        features['returns'] = features['close'].pct_change()
        features['log_returns'] = np.log(features['close'] / features['close'].shift(1))
        features['price_position'] = (features['close'] - features['low']) / (features['high'] - features['low'])
        
        # Volume-based features (critical for IDX)
        features['volume_ma'] = features['volume'].rolling(20).mean()
        features['volume_ratio'] = features['volume'] / features['volume_ma']
        features['volume_price_trend'] = (features['volume'] * features['returns']).rolling(10).sum()
        
        # Volatility features (IDX specific)
        for window in self.feature_params['volatility_windows']:
            features[f'volatility_{window}'] = features['returns'].rolling(window).std() * np.sqrt(252)
            features[f'parkinson_vol_{window}'] = np.sqrt(
                (1 / (4 * np.log(2))) * 
                ((np.log(features['high'] / features['low']) ** 2).rolling(window).mean())
            )
        
        # Technical indicators with multiple timeframes (if not already calculated by Rust)
        for window in self.feature_params['technical_windows']:
            # Moving averages
            if f'rust_sma_{window}' not in features.columns:
                features[f'sma_{window}'] = features['close'].rolling(window).mean()
            if f'rust_ema_{window}' not in features.columns:
                features[f'ema_{window}'] = features['close'].ewm(span=window).mean()
            features[f'price_to_sma_{window}'] = features['close'] / features[f'sma_{window}']
            
            # RSI (if not already calculated by Rust)
            if f'rust_rsi_{window}' not in features.columns:
                delta = features['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=window).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=window).mean()
                rs = gain / loss
                features[f'rsi_{window}'] = 100 - (100 / (1 + rs))
            
            # MACD (if not already calculated by Rust)
            if f'rust_macd_{window}' not in features.columns:
                ema12 = features['close'].ewm(span=12).mean()
                ema26 = features['close'].ewm(span=26).mean()
                features[f'macd_{window}'] = ema12 - ema26
                features[f'macd_signal_{window}'] = features[f'macd_{window}'].ewm(span=9).mean()
                features[f'macd_histogram_{window}'] = features[f'macd_{window}'] - features[f'macd_signal_{window}']
        
        # Market microstructure features (IDX specific)
        features['bid_ask_spread_proxy'] = (features['high'] - features['low']) / features['close']
        features['price_efficiency'] = features['returns'].rolling(20).apply(
            lambda x: np.corrcoef(x[:-1], x[1:])[0, 1] if len(x) > 1 else 0
        )
        
        # Momentum features with IDX persistence
        for window in self.feature_params['momentum_windows']:
            features[f'momentum_{window}'] = features['close'] / features['close'].shift(window) - 1
            features[f'momentum_ma_{window}'] = features[f'momentum_{window}'].rolling(window).mean()
        
        # Correlation features (market-wide effects)
        features['market_correlation'] = self._calculate_market_correlation(features, symbol)
        
        # Liquidity features (critical for IDX)
        features['amihud_illiquidity'] = abs(features['returns']) / (features['volume'] / 1000000)
        features['turnover_ratio'] = features['volume'] / features['volume'].rolling(50).mean()
        
        # Remove infinite and NaN values
        features = features.replace([np.inf, -np.inf], np.nan)
        features = features.dropna()
        
        return features
    
    def _calculate_market_correlation(self, df: pd.DataFrame, symbol: str) -> pd.Series:
        """Calculate correlation with market index (JKSE)."""
        try:
            # Get JKSE data
            conn = sqlite3.connect(self.db_path)
            jkse_query = """
            SELECT timestamp, close FROM historical_data_daily 
            WHERE symbol = '^JKSE' AND timestamp BETWEEN ? AND ?
            ORDER BY timestamp
            """
            jkse_data = pd.read_sql_query(
                jkse_query, conn, 
                params=(df.index.min(), df.index.max())
            )
            conn.close()
            
            if jkse_data.empty:
                return pd.Series(0, index=df.index)
            
            jkse_data['timestamp'] = pd.to_datetime(jkse_data['timestamp'])
            jkse_data.set_index('timestamp', inplace=True)
            jkse_data['returns'] = jkse_data['close'].pct_change()
            
            # Calculate rolling correlation
            merged = pd.merge(df['returns'], jkse_data['returns'], 
                            left_index=True, right_index=True, how='left')
            
            correlation = merged['returns_x'].rolling(50).corr(merged['returns_y'])
            return correlation.fillna(0)
            
        except Exception as e:
            logger.warning(f"Error calculating market correlation: {e}")
            return pd.Series(0, index=df.index)
    
    def create_target_variable(self, df: pd.DataFrame, threshold: float = 0.02) -> pd.Series:
        """
        Create target variable for classification.
        
        Args:
            df: Feature DataFrame
            threshold: Minimum return threshold for positive signal
            
        Returns:
            Target series (1 for positive, 0 for negative)
        """
        # Forward-looking returns
        future_returns = df['returns'].shift(-self.prediction_horizon)
        
        # Create binary target
        target = (future_returns > threshold).astype(int)
        
        # Remove NaN values
        target = target.dropna()
        
        return target
    
    def build_ensemble_model(self) -> VotingClassifier:
        """Build ensemble model with multiple base classifiers."""
        if not SKLEARN_AVAILABLE:
            raise ImportError("Scikit-learn required for ensemble models")
        
        # Base models
        rf = RandomForestClassifier(
            n_estimators=200,
            max_depth=10,
            min_samples_split=10,
            min_samples_leaf=5,
            random_state=42,
            n_jobs=-1
        )
        
        gb = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=6,
            random_state=42
        )
        
        lr = LogisticRegression(
            C=1.0,
            random_state=42,
            max_iter=1000
        )
        
        svm = SVC(
            C=1.0,
            kernel='rbf',
            probability=True,
            random_state=42
        )
        
        # Ensemble
        ensemble = VotingClassifier(
            estimators=[
                ('rf', rf),
                ('gb', gb),
                ('lr', lr),
                ('svm', svm)
            ],
            voting='soft'
        )
        
        return ensemble
    
    def build_deep_learning_model(self, input_shape: Tuple[int, int]):
        """Build LSTM-based deep learning model."""
        if not TENSORFLOW_AVAILABLE:
            raise ImportError("TensorFlow required for deep learning models")
        
        model = Sequential([
            Bidirectional(LSTM(128, return_sequences=True), input_shape=input_shape),
            Dropout(0.3),
            Bidirectional(LSTM(64, return_sequences=False)),
            Dropout(0.3),
            Dense(32, activation='relu'),
            Dropout(0.2),
            Dense(1, activation='sigmoid')
        ])
        
        model.compile(
            optimizer=Adam(learning_rate=0.001),
            loss='binary_crossentropy',
            metrics=['accuracy', 'auc']
        )
        
        return model
    
    def prepare_sequences(self, features: pd.DataFrame, target: pd.Series, 
                         sequence_length: int = 20) -> Tuple[np.ndarray, np.ndarray]:
        """Prepare sequences for LSTM model."""
        if not TENSORFLOW_AVAILABLE:
            raise ValueError("TensorFlow required for sequence preparation")
        
        # Align features and target
        aligned_data = pd.concat([features, target], axis=1).dropna()
        feature_cols = [col for col in aligned_data.columns if col != target.name]
        
        X, y = [], []
        
        for i in range(sequence_length, len(aligned_data)):
            X.append(aligned_data[feature_cols].iloc[i-sequence_length:i].values)
            y.append(aligned_data[target.name].iloc[i])
        
        return np.array(X), np.array(y)
    
    def train_models(self, symbol: str, test_size: float = 0.2) -> Dict:
        """
        Train multiple models for a given symbol.
        
        Args:
            symbol: Stock symbol
            test_size: Proportion of data for testing
            
        Returns:
            Dictionary with training results
        """
        # Get data
        df = self._get_symbol_data(symbol)
        if df.empty:
            return {'error': f'No data available for {symbol}'}
        
        # Engineer features
        features = self.engineer_features(df, symbol)
        if features.empty:
            return {'error': f'Feature engineering failed for {symbol}'}
        
        # Create target
        target = self.create_target_variable(features)
        
        # Align features and target
        aligned_data = pd.concat([features, target], axis=1).dropna()
        feature_cols = [col for col in aligned_data.columns if col != target.name]
        
        X = aligned_data[feature_cols]
        y = aligned_data[target.name]
        
        # Time series split
        tscv = TimeSeriesSplit(n_splits=5)
        
        results = {}
        
        # Train ensemble model
        if SKLEARN_AVAILABLE:
            ensemble = self.build_ensemble_model()
            
            # Cross-validation
            cv_scores = []
            for train_idx, val_idx in tscv.split(X):
                X_train, X_val = X.iloc[train_idx], X.iloc[val_idx]
                y_train, y_val = y.iloc[train_idx], y.iloc[val_idx]
                
                # Scale features
                scaler = StandardScaler()
                X_train_scaled = scaler.fit_transform(X_train)
                X_val_scaled = scaler.transform(X_val)
                
                # Train and predict
                ensemble.fit(X_train_scaled, y_train)
                y_pred = ensemble.predict(X_val_scaled)
                y_pred_proba = ensemble.predict_proba(X_val_scaled)[:, 1]
                
                # Calculate metrics
                auc = roc_auc_score(y_val, y_pred_proba)
                cv_scores.append(auc)
            
            # Final training on full dataset
            scaler = StandardScaler()
            X_scaled = scaler.fit_transform(X)
            ensemble.fit(X_scaled, y)
            
            # Store models and results
            self.models[f'{symbol}_ensemble'] = ensemble
            self.scalers[f'{symbol}_ensemble'] = scaler
            
            results['ensemble'] = {
                'cv_auc_mean': np.mean(cv_scores),
                'cv_auc_std': np.std(cv_scores),
                'feature_importance': self._get_feature_importance(ensemble, feature_cols)
            }
        
        # Train deep learning model
        if TENSORFLOW_AVAILABLE:
            try:
                # Prepare sequences
                sequence_length = 20
                X_seq, y_seq = self.prepare_sequences(features, target, sequence_length)
                
                if len(X_seq) > 100:  # Ensure enough data
                    # Split for deep learning
                    split_idx = int(len(X_seq) * (1 - test_size))
                    X_train_seq, X_test_seq = X_seq[:split_idx], X_seq[split_idx:]
                    y_train_seq, y_test_seq = y_seq[:split_idx], y_seq[split_idx:]
                    
                    # Build and train model
                    dl_model = self.build_deep_learning_model((sequence_length, X_seq.shape[2]))
                    
                    callbacks = [
                        EarlyStopping(patience=10, restore_best_weights=True),
                        ReduceLROnPlateau(patience=5, factor=0.5)
                    ]
                    
                    history = dl_model.fit(
                        X_train_seq, y_train_seq,
                        validation_data=(X_test_seq, y_test_seq),
                        epochs=100,
                        batch_size=32,
                        callbacks=callbacks,
                        verbose=0
                    )
                    
                    # Evaluate
                    y_pred_dl = dl_model.predict(X_test_seq)
                    auc_dl = roc_auc_score(y_test_seq, y_pred_dl)
                    
                    self.models[f'{symbol}_deep_learning'] = dl_model
                    
                    results['deep_learning'] = {
                        'auc': auc_dl,
                        'history': history.history
                    }
                    
            except Exception as e:
                logger.warning(f"Deep learning training failed for {symbol}: {e}")
        
        return results
    
    def generate_signals(self, symbol: str, confidence_threshold: float = 0.6) -> Dict:
        """
        Generate trading signals using trained models.
        
        Args:
            symbol: Stock symbol
            confidence_threshold: Minimum confidence for signal generation
            
        Returns:
            Dictionary with signal information
        """
        # Get latest data
        df = self._get_symbol_data(symbol)
        if df.empty:
            return {'error': f'No data available for {symbol}'}
        
        features = self.engineer_features(df, symbol)
        if features.empty:
            return {'error': f'Feature engineering failed for {symbol}'}
        
        signals = {}
        
        # Ensemble model signals
        if f'{symbol}_ensemble' in self.models:
            ensemble = self.models[f'{symbol}_ensemble']
            scaler = self.scalers[f'{symbol}_ensemble']
            
            # Get latest features
            latest_features = features.iloc[-1:]
            feature_cols = [col for col in latest_features.columns 
                          if col not in ['open', 'high', 'low', 'close', 'volume', 'returns']]
            
            X_latest = latest_features[feature_cols]
            X_scaled = scaler.transform(X_latest)
            
            # Predict
            proba = ensemble.predict_proba(X_scaled)[0]
            prediction = ensemble.predict(X_scaled)[0]
            
            signals['ensemble'] = {
                'prediction': int(prediction),
                'confidence': max(proba),
                'probabilities': proba.tolist(),
                'signal': 'BUY' if prediction == 1 and max(proba) > confidence_threshold else 'HOLD'
            }
        
        # Deep learning signals
        if f'{symbol}_deep_learning' in self.models and TENSORFLOW_AVAILABLE:
            try:
                dl_model = self.models[f'{symbol}_deep_learning']
                
                # Prepare sequence
                sequence_length = 20
                if len(features) >= sequence_length:
                    feature_cols = [col for col in features.columns 
                                  if col not in ['open', 'high', 'low', 'close', 'volume', 'returns']]
                    
                    latest_sequence = features[feature_cols].iloc[-sequence_length:].values
                    latest_sequence = latest_sequence.reshape(1, sequence_length, -1)
                    
                    # Predict
                    dl_proba = dl_model.predict(latest_sequence)[0][0]
                    dl_prediction = int(dl_proba > 0.5)
                    
                    signals['deep_learning'] = {
                        'prediction': dl_prediction,
                        'confidence': dl_proba if dl_prediction == 1 else 1 - dl_proba,
                        'probability': float(dl_proba),
                        'signal': 'BUY' if dl_prediction == 1 and dl_proba > confidence_threshold else 'HOLD'
                    }
                    
            except Exception as e:
                logger.warning(f"Deep learning prediction failed for {symbol}: {e}")
        
        # Combine signals
        if 'ensemble' in signals and 'deep_learning' in signals:
            # Weighted average of predictions
            ensemble_weight = 0.6
            dl_weight = 0.4
            
            combined_confidence = (
                signals['ensemble']['confidence'] * ensemble_weight +
                signals['deep_learning']['confidence'] * dl_weight
            )
            
            combined_prediction = int(
                (signals['ensemble']['prediction'] * ensemble_weight +
                 signals['deep_learning']['prediction'] * dl_weight) > 0.5
            )
            
            signals['combined'] = {
                'prediction': combined_prediction,
                'confidence': combined_confidence,
                'signal': 'BUY' if combined_prediction == 1 and combined_confidence > confidence_threshold else 'HOLD'
            }
        
        return signals
    
    def _get_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Get historical data for a symbol."""
        try:
            conn = sqlite3.connect(self.db_path)
            
            # Add .JK suffix if not present
            query_symbol = symbol if symbol.endswith('.JK') else f"{symbol}.JK"
            
            query = """
            SELECT timestamp, open, high, low, close, volume
            FROM historical_data_daily
            WHERE symbol = ?
            ORDER BY timestamp DESC
            LIMIT ?
            """
            
            df = pd.read_sql_query(query, conn, params=(query_symbol, self.lookback_days * 2))
            conn.close()
            
            if df.empty:
                return pd.DataFrame()
            
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            df = df.sort_index()
            
            return df
            
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()
    
    def _get_feature_importance(self, model, feature_names: List[str]) -> Dict[str, float]:
        """Extract feature importance from ensemble model."""
        try:
            if hasattr(model, 'named_estimators_'):
                # Voting classifier
                importance_dict = {}
                for name, estimator in model.named_estimators_.items():
                    if hasattr(estimator, 'feature_importances_'):
                        for i, importance in enumerate(estimator.feature_importances_):
                            feature_name = feature_names[i]
                            if feature_name not in importance_dict:
                                importance_dict[feature_name] = []
                            importance_dict[feature_name].append(importance)
                
                # Average importance across estimators
                avg_importance = {k: np.mean(v) for k, v in importance_dict.items()}
                return dict(sorted(avg_importance.items(), key=lambda x: x[1], reverse=True))
            
            elif hasattr(model, 'feature_importances_'):
                # Single tree-based model
                importance_dict = dict(zip(feature_names, model.feature_importances_))
                return dict(sorted(importance_dict.items(), key=lambda x: x[1], reverse=True))
            
            else:
                return {}
                
        except Exception as e:
            logger.warning(f"Error extracting feature importance: {e}")
            return {}
    
    def get_model_performance_summary(self) -> Dict:
        """Get summary of all trained models' performance."""
        summary = {
            'trained_models': list(self.models.keys()),
            'total_models': len(self.models),
            'feature_importance': self.feature_importance
        }
        
        return summary
