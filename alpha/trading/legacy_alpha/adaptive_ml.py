#!/usr/bin/env python3
"""
Adaptive ML Trading System
Sophisticated machine learning system that dynamically adapts to market conditions
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from typing import List, Dict, Tuple
import warnings
warnings.filterwarnings('ignore')

from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import classification_report, accuracy_score
from sklearn.cluster import KMeans
import joblib

class AdaptiveMLTradingSystem:
    """Sophisticated adaptive ML trading system"""
    
    def __init__(self):
        self.models = {}
        self.scalers = {}
        self.market_regime = 'UNKNOWN'
        self.regime_models = {}
        self.feature_importance = {}
        
        # Dynamic thresholds based on market conditions
        self.adaptive_thresholds = {
            'bull': {'confidence': 0.6, 'position_size': 0.08, 'stop_loss': 0.05},
            'bear': {'confidence': 0.8, 'position_size': 0.03, 'stop_loss': 0.02},
            'neutral': {'confidence': 0.7, 'position_size': 0.05, 'stop_loss': 0.03},
            'volatile': {'confidence': 0.85, 'position_size': 0.02, 'stop_loss': 0.015}
        }
        
    def detect_market_regime_ml(self, symbols: List[str]) -> str:
        """Advanced market regime detection using ML clustering"""
        
        print("🧠 DETECTING MARKET REGIME WITH ML...")
        
        # Collect market features
        market_features = []
        sample_size = min(100, len(symbols))
        
        for symbol in symbols[:sample_size]:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='30d', interval='1d')
                
                if not hist.empty and len(hist) >= 20:
                    returns = hist['Close'].pct_change().dropna()
                    
                    if len(returns) >= 15:
                        features = [
                            returns.mean(),  # Average return
                            returns.std(),   # Volatility
                            (returns > 0).mean(),  # Positive day ratio
                            returns.skew(),  # Skewness
                            returns.kurtosis(),  # Kurtosis
                            (returns > returns.std()).mean(),  # Large moves ratio
                            hist['Volume'].pct_change().mean(),  # Volume trend
                            hist['High'].max() / hist['Low'].min() - 1  # Price range
                        ]
                        market_features.append(features)
                        
            except Exception:
                continue
        
        if len(market_features) < 10:
            return 'UNKNOWN'
        
        # Convert to DataFrame
        feature_df = pd.DataFrame(market_features, columns=[
            'avg_return', 'volatility', 'positive_ratio', 'skewness', 
            'kurtosis', 'large_moves', 'volume_trend', 'price_range'
        ])
        
        # Clean data - remove infinite and NaN values
        feature_df = feature_df.replace([np.inf, -np.inf], np.nan)
        feature_df = feature_df.dropna()
        
        if len(feature_df) < 10:
            return 'UNKNOWN'
        
        # Normalize features
        scaler = StandardScaler()
        scaled_features = scaler.fit_transform(feature_df)
        
        # Cluster market conditions
        kmeans = KMeans(n_clusters=4, random_state=42)
        clusters = kmeans.fit_predict(scaled_features)
        
        # Analyze cluster characteristics
        cluster_centers = scaler.inverse_transform(kmeans.cluster_centers_)
        
        # Determine regime based on cluster characteristics
        regime_scores = []
        for center in cluster_centers:
            avg_return, volatility, positive_ratio = center[0], center[1], center[2]
            
            # Score each cluster
            if avg_return > 0.001 and positive_ratio > 0.55 and volatility < 0.03:
                score = 'BULL'
            elif avg_return < -0.001 and positive_ratio < 0.45:
                score = 'BEAR'
            elif volatility > 0.04:
                score = 'VOLATILE'
            else:
                score = 'NEUTRAL'
            
            regime_scores.append(score)
        
        # Get most common cluster
        cluster_counts = pd.Series(clusters).value_counts()
        dominant_cluster = cluster_counts.index[0]
        regime = regime_scores[dominant_cluster]
        
        print(f"📊 ML Market Analysis:")
        print(f"• Clusters found: {len(cluster_counts)}")
        print(f"• Dominant cluster: {dominant_cluster} ({cluster_counts[dominant_cluster]} stocks)")
        print(f"• Detected regime: {regime}")
        print(f"• Avg return: {cluster_centers[dominant_cluster][0]:.3%}")
        print(f"• Volatility: {cluster_centers[dominant_cluster][1]:.3%}")
        print(f"• Positive ratio: {cluster_centers[dominant_cluster][2]:.1%}")
        
        self.market_regime = regime
        return regime
    
    def extract_advanced_features(self, hist: pd.DataFrame) -> Dict:
        """Extract sophisticated features for ML models"""
        
        if hist.empty or len(hist) < 30:
            return {}
        
        # Price features
        returns = hist['Close'].pct_change().dropna()
        log_returns = np.log(hist['Close'] / hist['Close'].shift(1)).dropna()
        
        # Technical indicators
        sma_5 = hist['Close'].rolling(5).mean()
        sma_20 = hist['Close'].rolling(20).mean()
        ema_12 = hist['Close'].ewm(span=12).mean()
        ema_26 = hist['Close'].ewm(span=26).mean()
        
        # RSI
        delta = hist['Close'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        # MACD
        macd = ema_12 - ema_26
        macd_signal = macd.ewm(span=9).mean()
        macd_histogram = macd - macd_signal
        
        # Bollinger Bands
        bb_middle = hist['Close'].rolling(20).mean()
        bb_std = hist['Close'].rolling(20).std()
        bb_upper = bb_middle + (bb_std * 2)
        bb_lower = bb_middle - (bb_std * 2)
        bb_position = (hist['Close'] - bb_lower) / (bb_upper - bb_lower)
        
        # Volume features
        volume_sma = hist['Volume'].rolling(20).mean()
        volume_ratio = hist['Volume'] / volume_sma
        
        # Volatility features
        volatility_5 = returns.rolling(5).std()
        volatility_20 = returns.rolling(20).std()
        
        # Momentum features
        momentum_5 = hist['Close'] / hist['Close'].shift(5) - 1
        momentum_10 = hist['Close'] / hist['Close'].shift(10) - 1
        momentum_20 = hist['Close'] / hist['Close'].shift(20) - 1
        
        # Statistical features
        skewness = returns.rolling(20).skew()
        kurtosis = returns.rolling(20).kurt()
        
        # Market microstructure
        high_low_ratio = hist['High'] / hist['Low']
        close_open_ratio = hist['Close'] / hist['Open']
        
        # Create feature dictionary
        features = {
            'price_sma5_ratio': hist['Close'].iloc[-1] / sma_5.iloc[-1] - 1,
            'price_sma20_ratio': hist['Close'].iloc[-1] / sma_20.iloc[-1] - 1,
            'ema_cross': (ema_12.iloc[-1] - ema_26.iloc[-1]) / ema_26.iloc[-1],
            'rsi': rsi.iloc[-1],
            'macd': macd.iloc[-1],
            'macd_signal': macd_signal.iloc[-1],
            'macd_histogram': macd_histogram.iloc[-1],
            'bb_position': bb_position.iloc[-1],
            'volume_ratio': volume_ratio.iloc[-1],
            'volatility_5': volatility_5.iloc[-1],
            'volatility_20': volatility_20.iloc[-1],
            'momentum_5': momentum_5.iloc[-1],
            'momentum_10': momentum_10.iloc[-1],
            'momentum_20': momentum_20.iloc[-1],
            'skewness': skewness.iloc[-1],
            'kurtosis': kurtosis.iloc[-1],
            'high_low_ratio': high_low_ratio.iloc[-1],
            'close_open_ratio': close_open_ratio.iloc[-1],
            'avg_return_5': returns.tail(5).mean(),
            'avg_return_20': returns.tail(20).mean(),
            'positive_days_5': (returns.tail(5) > 0).mean(),
            'positive_days_20': (returns.tail(20) > 0).mean(),
            'max_gain_5': returns.tail(5).max(),
            'max_loss_5': returns.tail(5).min(),
            'price_range_20': (hist['High'].tail(20).max() / hist['Low'].tail(20).min()) - 1
        }
        
        return features
    
    def create_training_data(self, symbols: List[str], lookback_days: int = 60) -> Tuple[pd.DataFrame, pd.Series]:
        """Create training data for ML models"""
        
        print("📊 Creating ML training data...")
        
        training_data = []
        sample_size = min(200, len(symbols))
        
        for symbol in symbols[:sample_size]:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period=f'{lookback_days + 10}d', interval='1d')
                
                if hist.empty or len(hist) < lookback_days:
                    continue
                
                # Extract features
                features = self.extract_advanced_features(hist)
                
                if not features:
                    continue
                
                # Calculate future returns (target)
                future_returns = []
                for i in range(5, 16, 5):  # 5, 10, 15 days ahead
                    if len(hist) > i:
                        future_return = (hist['Close'].iloc[-i] / hist['Close'].iloc[-1]) - 1
                        future_returns.append(future_return)
                    else:
                        future_returns.append(0)
                
                # Create multiple training samples
                for i, future_return in enumerate(future_returns):
                    sample = features.copy()
                    sample['symbol'] = symbol
                    sample['future_return'] = future_return
                    sample['holding_period'] = (i + 1) * 5
                    training_data.append(sample)
                    
            except Exception as e:
                continue
        
        if not training_data:
            return pd.DataFrame(), pd.Series()
        
        # Convert to DataFrame
        df = pd.DataFrame(training_data)
        
        # Create target variable (1 for positive return, 0 for negative)
        df['target'] = (df['future_return'] > 0).astype(int)
        
        # Remove infinite and NaN values
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna()
        
        if df.empty:
            return pd.DataFrame(), pd.Series()
        
        print(f"✅ Created {len(df)} training samples")
        return df
    
    def train_ml_models(self, symbols: List[str]):
        """Train sophisticated ML models"""
        
        print("🤖 TRAINING ML MODELS...")
        
        # Create training data
        df = self.create_training_data(symbols)
        
        if df.empty:
            print("❌ No training data available")
            return
        
        # Feature columns (exclude target and metadata)
        feature_cols = [col for col in df.columns if col not in ['symbol', 'future_return', 'holding_period', 'target']]
        
        # Split data
        X = df[feature_cols]
        y = df['target']
        
        X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
        
        # Scale features
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)
        
        # Train multiple models
        models = {
            'random_forest': RandomForestClassifier(n_estimators=100, random_state=42, max_depth=10),
            'gradient_boosting': GradientBoostingClassifier(n_estimators=100, random_state=42, max_depth=6),
            'logistic_regression': LogisticRegression(random_state=42, max_iter=1000)
        }
        
        print("📈 Training models...")
        
        for name, model in models.items():
            print(f"  Training {name}...")
            model.fit(X_train_scaled, y_train)
            
            # Evaluate
            y_pred = model.predict(X_test_scaled)
            accuracy = accuracy_score(y_test, y_pred)
            
            print(f"    {name} accuracy: {accuracy:.3f}")
            
            # Store model and scaler
            self.models[name] = model
            self.scalers[name] = scaler
            
            # Feature importance
            if hasattr(model, 'feature_importances_'):
                self.feature_importance[name] = dict(zip(feature_cols, model.feature_importances_))
        
        print("✅ ML models trained successfully")
    
    def predict_signal_strength(self, hist: pd.DataFrame) -> Dict:
        """Predict signal strength using trained ML models"""
        
        # Extract features
        features = self.extract_advanced_features(hist)
        
        if not features:
            return {'confidence': 0, 'prediction': 0, 'model_agreement': 0}
        
        # Prepare feature vector
        feature_cols = list(features.keys())
        feature_vector = np.array([features[col] for col in feature_cols]).reshape(1, -1)
        
        predictions = []
        confidences = []
        
        # Get predictions from all models
        for name, model in self.models.items():
            scaler = self.scalers[name]
            
            # Scale features
            scaled_features = scaler.transform(feature_vector)
            
            # Get prediction and probability
            prediction = model.predict(scaled_features)[0]
            confidence = model.predict_proba(scaled_features)[0].max()
            
            predictions.append(prediction)
            confidences.append(confidence)
        
        # Ensemble prediction
        avg_confidence = np.mean(confidences)
        model_agreement = np.mean(predictions)  # How many models agree on positive signal
        
        # Adjust confidence based on market regime
        regime_threshold = self.adaptive_thresholds.get(self.market_regime, self.adaptive_thresholds['neutral'])
        
        return {
            'confidence': avg_confidence,
            'prediction': model_agreement,
            'model_agreement': model_agreement,
            'regime_threshold': regime_threshold['confidence']
        }
    
    def generate_adaptive_signals(self, max_signals: int = 10) -> List[Dict]:
        """Generate adaptive ML signals"""
        
        print(f"🚀 ADAPTIVE ML TRADING SYSTEM")
        print(f"Sophisticated machine learning with dynamic adaptation")
        print("=" * 80)
        
        # Load symbols
        try:
            with open('data/processed_tickers.txt', 'r') as f:
                symbols = [line.strip() for line in f.readlines() if line.strip()]
            print(f"📊 Loaded {len(symbols)} symbols")
        except FileNotFoundError:
            print("❌ processed_tickers.txt not found")
            return []
        
        # Detect market regime
        regime = self.detect_market_regime_ml(symbols)
        
        # Train ML models if not already trained
        if not self.models:
            self.train_ml_models(symbols)
        
        # Filter active symbols
        active_symbols = []
        for symbol in symbols[:300]:  # Sample for speed
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='60d', interval='1d')
                
                if not hist.empty and len(hist) >= 30:
                    recent_volume = hist['Volume'].tail(5).mean()
                    if recent_volume > 50000:  # Volume filter
                        active_symbols.append(symbol)
                        
            except Exception:
                continue
        
        print(f"✅ Found {len(active_symbols)} active symbols")
        
        # Generate signals
        signals = []
        analyzed = 0
        
        for symbol in active_symbols:
            try:
                # Get data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='60d', interval='1d')
                
                if hist.empty or len(hist) < 30:
                    continue
                
                # Get ML prediction
                prediction = self.predict_signal_strength(hist)
                
                # Apply regime-specific thresholds
                regime_config = self.adaptive_thresholds.get(regime, self.adaptive_thresholds['neutral'])
                
                if (prediction['confidence'] >= regime_config['confidence'] and 
                    prediction['model_agreement'] >= 0.5):
                    
                    # Dynamic position sizing
                    position_size = regime_config['position_size'] * prediction['confidence']
                    current_price = hist['Close'].iloc[-1]
                    
                    signals.append({
                        'symbol': symbol,
                        'confidence': prediction['confidence'],
                        'model_agreement': prediction['model_agreement'],
                        'position_size': position_size,
                        'current_price': current_price,
                        'action': 'BUY' if prediction['confidence'] >= 0.8 else 'WEAK_BUY',
                        'regime': regime,
                        'stop_loss': regime_config['stop_loss'],
                        'volume': hist['Volume'].iloc[-1],
                        'volatility': hist['Close'].pct_change().tail(20).std()
                    })
                
                analyzed += 1
                
                if analyzed % 50 == 0:
                    print(f"  Analyzed {analyzed}/{len(active_symbols)} symbols, found {len(signals)} signals")
                
                if len(signals) >= max_signals:
                    break
                    
            except Exception as e:
                continue
        
        # Sort by confidence
        signals.sort(key=lambda x: x['confidence'], reverse=True)
        
        print(f"\n📊 ADAPTIVE ML ANALYSIS COMPLETE:")
        print(f"• Market Regime: {regime}")
        print(f"• Symbols analyzed: {analyzed}")
        print(f"• Signals generated: {len(signals)}")
        print(f"• Success rate: {(len(signals)/analyzed*100):.1f}%" if analyzed > 0 else "N/A")
        
        return signals

def test_adaptive_ml_system():
    """Test the adaptive ML trading system"""
    
    print("🧪 TESTING ADAPTIVE ML TRADING SYSTEM")
    print("=" * 80)
    
    # Initialize system
    system = AdaptiveMLTradingSystem()
    
    # Generate signals
    signals = system.generate_adaptive_signals(max_signals=8)
    
    # Print results
    print(f"\n📊 ADAPTIVE ML SIGNALS:")
    for i, signal in enumerate(signals):
        print(f"{i+1}. {signal['symbol']}: {signal['action']}")
        print(f"   Confidence: {signal['confidence']:.3f}")
        print(f"   Model Agreement: {signal['model_agreement']:.3f}")
        print(f"   Position Size: {signal['position_size']:.1%}")
        print(f"   Current Price: {signal['current_price']:,.0f} IDR")
        print(f"   Stop Loss: {signal['stop_loss']:.1%}")
        print(f"   Regime: {signal['regime']}")
        print()
    
    print(f"📈 SUMMARY:")
    print(f"• Total Signals: {len(signals)}")
    print(f"• Buy Signals: {len([s for s in signals if s['action'] == 'BUY'])}")
    print(f"• Weak Buy Signals: {len([s for s in signals if s['action'] == 'WEAK_BUY'])}")
    
    if signals:
        avg_confidence = np.mean([s['confidence'] for s in signals])
        avg_agreement = np.mean([s['model_agreement'] for s in signals])
        print(f"• Average Confidence: {avg_confidence:.3f}")
        print(f"• Average Model Agreement: {avg_agreement:.3f}")
        print(f"✅ ADAPTIVE ML SYSTEM IS READY!")
        
        # Save results
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f'adaptive_ml_signals_{timestamp}.json'
        
        with open(filename, 'w') as f:
            json.dump(signals, f, indent=2, default=str)
        
        print(f"✅ Results saved to {filename}")
    else:
        print(f"⚠️  No signals generated - system may be too conservative")

def main():
    """Main function"""
    test_adaptive_ml_system()

if __name__ == "__main__":
    main()
