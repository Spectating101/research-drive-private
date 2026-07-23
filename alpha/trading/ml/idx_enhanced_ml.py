#!/usr/bin/env python3
"""
Enhanced IDX Machine Learning System

This module implements ML techniques specifically designed to exploit
Indonesian market inefficiencies and characteristics.
"""

import pandas as pd
import numpy as np
import sqlite3
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import logging
from scipy import stats
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier, VotingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler, RobustScaler
from sklearn.model_selection import TimeSeriesSplit, cross_val_score
from sklearn.metrics import classification_report, confusion_matrix
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)

class IDXEnhancedML:
    """
    Enhanced ML system specifically designed for IDX market inefficiencies.
    
    Key ML Strategies for IDX:
    1. Ensemble Learning → Captures multiple inefficiency types
    2. Feature Engineering → Extracts hidden market microstructure
    3. Regime-Dependent Models → Adapts to changing market conditions
    4. Cross-Sectional Learning → Sector rotation opportunities
    5. Sentiment Integration → Retail-driven market patterns
    """
    
    def __init__(self, db_path: str = 'db/historical_data.db'):
        self.db_path = db_path
        
        # IDX-specific ML parameters
        self.ml_params = {
            'ensemble_size': 5,           # Multiple models for robustness
            'feature_window': 60,         # 60-day feature window
            'prediction_horizon': 5,      # 5-day prediction horizon
            'regime_threshold': 0.7,      # Regime switching threshold
            'sentiment_weight': 0.3,      # Sentiment feature weight
            'liquidity_weight': 0.2,      # Liquidity feature weight
            'momentum_weight': 0.5        # Momentum feature weight
        }
        
        # Model storage
        self.models = {}
        self.scalers = {}
        self.feature_importance = {}
        self.regime_models = {}
        
        logger.info("IDX Enhanced ML System initialized")
    
    def engineer_idx_features(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """
        Engineer features specifically for IDX market inefficiencies.
        
        Args:
            df: OHLCV DataFrame
            symbol: Stock symbol
            
        Returns:
            DataFrame with engineered features
        """
        if df.empty or len(df) < 100:
            return pd.DataFrame()
        
        features = df.copy()
        
        # 1. IDX-Specific Technical Features
        features = self._add_idx_technical_features(features)
        
        # 2. Volatility Features (IDX is more volatile)
        features = self._add_volatility_features(features)
        
        # 3. Liquidity Features (IDX liquidity constraints)
        features = self._add_liquidity_features(features)
        
        # 4. Sentiment Features (Retail-driven market)
        features = self._add_sentiment_features(features)
        
        # 5. Momentum Features (IDX momentum persistence)
        features = self._add_momentum_features(features)
        
        # 6. Cross-Sectional Features (Sector rotation)
        features = self._add_cross_sectional_features(features, symbol)
        
        # 7. Market Microstructure Features
        features = self._add_microstructure_features(features)
        
        return features
    
    def _add_idx_technical_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add IDX-specific technical features."""
        # Price-based features
        df['price_position'] = (df['close'] - df['low']) / (df['high'] - df['low'])
        df['price_range'] = (df['high'] - df['low']) / df['close']
        
        # Volume-based features
        df['volume_price_trend'] = df['volume'] * df['close'].pct_change()
        df['volume_ma_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
        
        # IDX-specific patterns
        df['gap_up'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        df['gap_down'] = (df['close'].shift(1) - df['open']) / df['close'].shift(1)
        
        # Intraday patterns
        df['intraday_volatility'] = (df['high'] - df['low']) / df['open']
        df['close_position'] = (df['close'] - df['low']) / (df['high'] - df['low'])
        
        return df
    
    def _add_volatility_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add volatility features (IDX is more volatile)."""
        returns = df['close'].pct_change().dropna()
        
        # Rolling volatility measures
        for window in [5, 10, 20, 50]:
            df[f'volatility_{window}'] = returns.rolling(window).std()
            df[f'volatility_ratio_{window}'] = df[f'volatility_{window}'] / df[f'volatility_{window}'].rolling(50).mean()
        
        # Volatility clustering
        df['volatility_clustering'] = returns.rolling(20).apply(
            lambda x: abs(x.autocorr()) if len(x) > 1 else 0
        )
        
        # Extreme volatility events
        df['extreme_volatility'] = (df['volatility_20'] > df['volatility_20'].rolling(100).quantile(0.9)).astype(int)
        
        return df
    
    def _add_liquidity_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add liquidity features (IDX liquidity constraints)."""
        # Amihud illiquidity measure
        returns = df['close'].pct_change().abs()
        df['amihud_illiquidity'] = returns / df['volume']
        
        # Volume-based liquidity measures
        df['volume_liquidity'] = df['volume'] / df['volume'].rolling(20).mean()
        df['price_impact'] = returns / df['volume']
        
        # Liquidity regime
        df['liquidity_regime'] = (df['amihud_illiquidity'] > df['amihud_illiquidity'].rolling(50).quantile(0.8)).astype(int)
        
        # Volume drying up
        df['volume_drying'] = (df['volume'] < df['volume'].rolling(20).mean() * 0.5).astype(int)
        
        return df
    
    def _add_sentiment_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add sentiment features (Retail-driven market)."""
        # Price range sentiment
        df['sentiment_range'] = (df['high'] - df['low']) / df['close']
        df['sentiment_extreme'] = (df['sentiment_range'] > df['sentiment_range'].rolling(20).quantile(0.9)).astype(int)
        
        # Gap sentiment
        df['gap_sentiment'] = (df['open'] - df['close'].shift(1)) / df['close'].shift(1)
        df['gap_extreme'] = (abs(df['gap_sentiment']) > abs(df['gap_sentiment']).rolling(20).quantile(0.9)).astype(int)
        
        # Volume sentiment
        df['volume_sentiment'] = df['volume'] * np.sign(df['close'].pct_change())
        df['volume_sentiment_ma'] = df['volume_sentiment'].rolling(10).mean()
        
        # Price momentum sentiment
        df['momentum_sentiment'] = df['close'].pct_change(5).rolling(10).mean()
        
        return df
    
    def _add_momentum_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add momentum features (IDX momentum persistence)."""
        returns = df['close'].pct_change().dropna()
        
        # Multi-timeframe momentum
        for window in [5, 10, 20, 50]:
            df[f'momentum_{window}'] = returns.rolling(window).mean()
            df[f'momentum_acceleration_{window}'] = df[f'momentum_{window}'].diff()
        
        # Momentum alignment
        df['momentum_alignment'] = (
            (df['momentum_5'] > 0).astype(int) + 
            (df['momentum_10'] > 0).astype(int) + 
            (df['momentum_20'] > 0).astype(int)
        ) / 3
        
        # Momentum strength
        df['momentum_strength'] = df['momentum_20'].abs() / df['volatility_20']
        
        # Momentum reversal
        df['momentum_reversal'] = (
            (df['momentum_5'] > 0) & (df['momentum_20'] < 0)
        ).astype(int) - (
            (df['momentum_5'] < 0) & (df['momentum_20'] > 0)
        ).astype(int)
        
        return df
    
    def _add_cross_sectional_features(self, df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Add cross-sectional features (Sector rotation)."""
        # This would require sector data
        # For now, add relative strength features
        
        # Relative strength vs market (simplified)
        df['relative_strength'] = df['close'].pct_change(20) - df['close'].pct_change(20).rolling(50).mean()
        
        # Sector rotation proxy
        df['sector_momentum'] = df['momentum_20'].rolling(10).mean()
        
        # Cross-sectional volatility
        df['cross_volatility'] = df['volatility_20'] / df['volatility_20'].rolling(50).mean()
        
        return df
    
    def _add_microstructure_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add market microstructure features."""
        # Bid-ask spread proxy
        df['spread_proxy'] = (df['high'] - df['low']) / df['close']
        
        # Price efficiency
        returns = df['close'].pct_change().dropna()
        df['price_efficiency'] = returns.rolling(20).apply(
            lambda x: abs(x.autocorr()) if len(x) > 1 else 0
        )
        
        # Order flow imbalance (simplified)
        df['flow_imbalance'] = df['volume'] * np.sign(df['close'].pct_change())
        df['flow_imbalance_ma'] = df['flow_imbalance'].rolling(10).mean()
        
        return df
    
    def create_target_variable(self, df: pd.DataFrame, horizon: int = 5) -> pd.Series:
        """
        Create target variable for IDX-specific prediction.
        
        Args:
            df: Feature DataFrame
            horizon: Prediction horizon in days
            
        Returns:
            Target series (1 for positive return, 0 for negative)
        """
        # Calculate future returns
        future_returns = df['close'].pct_change(horizon).shift(-horizon)
        
        # IDX-specific target: 1 if return > 2% (IDX threshold), 0 otherwise
        target = (future_returns > 0.02).astype(int)
        
        # Remove any NaN values
        target = target.dropna()
        
        return target
    
    def build_idx_ensemble_model(self) -> VotingClassifier:
        """
        Build ensemble model specifically for IDX market inefficiencies.
        
        Returns:
            Ensemble classifier
        """
        # Base models
        rf = RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=20,
            min_samples_leaf=10,
            random_state=42
        )
        
        gb = GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.1,
            max_depth=6,
            random_state=42
        )
        
        lr = LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=42
        )
        
        # Ensemble with voting
        ensemble = VotingClassifier(
            estimators=[
                ('rf', rf),
                ('gb', gb),
                ('lr', lr)
            ],
            voting='soft'
        )
        
        return ensemble
    
    def train_regime_dependent_models(self, symbol: str) -> Dict:
        """
        Train regime-dependent models for IDX market.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with training results
        """
        # Get data
        df = self._get_symbol_data(symbol)
        if df.empty:
            return {'error': f'No data available for {symbol}'}
        
        # Engineer features
        features = self.engineer_idx_features(df, symbol)
        if features.empty:
            return {'error': f'Feature engineering failed for {symbol}'}
        
        # Create target
        target = self.create_target_variable(features)
        
        # Align features and target
        aligned_data = pd.concat([features, target], axis=1).dropna()
        # Select only numeric features
        feature_cols = [col for col in aligned_data.columns 
                       if col != target.name and 
                       col not in ['symbol', 'timestamp'] and
                       aligned_data[col].dtype in ['float64', 'int64']]
        
        X = aligned_data[feature_cols]
        y = aligned_data[target.name]
        
        # Ensure we have binary classification
        if len(y.unique()) < 2:
            logger.warning(f"Insufficient target classes for {symbol}")
            return {'error': 'Insufficient target classes'}
        
        # Identify market regimes
        regimes = self._identify_market_regimes(X)
        
        results = {}
        
        # Train regime-specific models
        for regime in regimes.unique():
            if regime == -1:  # Unknown regime
                continue
                
            regime_mask = regimes == regime
            X_regime = X[regime_mask]
            y_regime = y[regime_mask]
            
            if len(X_regime) < 50:  # Need sufficient data
                continue
            
            # Train model for this regime
            model = self.build_idx_ensemble_model()
            scaler = RobustScaler()
            
            X_scaled = scaler.fit_transform(X_regime)
            model.fit(X_scaled, y_regime)
            
            # Store model and scaler
            self.regime_models[f'{symbol}_{regime}'] = {
                'model': model,
                'scaler': scaler,
                'regime': regime,
                'sample_size': len(X_regime)
            }
            
            results[f'regime_{regime}'] = {
                'sample_size': len(X_regime),
                'positive_ratio': y_regime.mean(),
                'model_trained': True
            }
        
        return results
    
    def _identify_market_regimes(self, X: pd.DataFrame) -> pd.Series:
        """
        Identify market regimes based on volatility and momentum.
        
        Args:
            X: Feature DataFrame
            
        Returns:
            Regime series
        """
        # Use volatility and momentum to identify regimes
        if 'volatility_20' in X.columns and 'momentum_20' in X.columns:
            vol = X['volatility_20']
            mom = X['momentum_20']
            
            # High volatility regime
            high_vol = vol > vol.rolling(100).quantile(0.8)
            
            # Strong momentum regime
            strong_mom = mom.abs() > mom.abs().rolling(100).quantile(0.8)
            
            # Regime classification
            regimes = pd.Series(index=X.index, data=-1)  # -1 for unknown
            
            # Regime 0: Low volatility, low momentum
            regimes[~high_vol & ~strong_mom] = 0
            
            # Regime 1: High volatility, low momentum
            regimes[high_vol & ~strong_mom] = 1
            
            # Regime 2: Low volatility, high momentum
            regimes[~high_vol & strong_mom] = 2
            
            # Regime 3: High volatility, high momentum
            regimes[high_vol & strong_mom] = 3
            
            return regimes
        else:
            # Fallback: use simple volatility regime
            if 'volatility_20' in X.columns:
                vol = X['volatility_20']
                high_vol = vol > vol.rolling(100).quantile(0.8)
                return high_vol.astype(int)
            else:
                return pd.Series(index=X.index, data=0)
    
    def predict_with_regime_models(self, symbol: str) -> Dict:
        """
        Make predictions using regime-dependent models.
        
        Args:
            symbol: Stock symbol
            
        Returns:
            Dictionary with predictions and confidence
        """
        # Get latest data
        df = self._get_symbol_data(symbol)
        if df.empty:
            return {'error': f'No data available for {symbol}'}
        
        # Engineer features
        features = self.engineer_idx_features(df, symbol)
        if features.empty:
            return {'error': f'Feature engineering failed for {symbol}'}
        
        # Get latest features
        latest_features = features.iloc[-1:]
        # Select only numeric features
        feature_cols = [col for col in latest_features.columns 
                       if col not in ['symbol', 'timestamp', 'open', 'high', 'low', 'close', 'volume'] and
                       latest_features[col].dtype in ['float64', 'int64']]
        
        X_latest = latest_features[feature_cols]
        
        # Identify current regime
        regimes = self._identify_market_regimes(features[feature_cols])
        current_regime = regimes.iloc[-1]
        
        predictions = {}
        
        # Make prediction with regime-specific model
        regime_key = f'{symbol}_{current_regime}'
        if regime_key in self.regime_models:
            model_data = self.regime_models[regime_key]
            model = model_data['model']
            scaler = model_data['scaler']
            
            # Scale features
            X_scaled = scaler.transform(X_latest)
            
            # Make prediction
            prob = model.predict_proba(X_scaled)[0]
            prediction = model.predict(X_scaled)[0]
            
            predictions['regime_prediction'] = {
                'regime': current_regime,
                'prediction': prediction,
                'probability': prob[1] if len(prob) > 1 else prob[0],
                'confidence': max(prob)
            }
        else:
            predictions['regime_prediction'] = {
                'regime': current_regime,
                'prediction': -1,
                'probability': 0.5,
                'confidence': 0.0,
                'note': 'No model trained for this regime'
            }
        
        # Add market context
        predictions['market_context'] = {
            'current_volatility': features['volatility_20'].iloc[-1] if 'volatility_20' in features.columns else None,
            'current_momentum': features['momentum_20'].iloc[-1] if 'momentum_20' in features.columns else None,
            'liquidity_condition': features['amihud_illiquidity'].iloc[-1] if 'amihud_illiquidity' in features.columns else None
        }
        
        return predictions
    
    def _get_symbol_data(self, symbol: str) -> pd.DataFrame:
        """Get symbol data from database."""
        try:
            conn = sqlite3.connect(self.db_path)
            query = f"""
            SELECT * FROM historical_data_daily 
            WHERE symbol = '{symbol}' 
            ORDER BY timestamp
            """
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return pd.DataFrame()

if __name__ == "__main__":
    # Test the enhanced ML system
    ml_system = IDXEnhancedML()
    
    # Train regime-dependent models
    training_results = ml_system.train_regime_dependent_models('BBCA.JK')
    print("Training Results:")
    print(training_results)
    
    # Make prediction
    prediction = ml_system.predict_with_regime_models('BBCA.JK')
    print("\nPrediction Results:")
    print(prediction)
