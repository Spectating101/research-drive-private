#!/usr/bin/env python3
"""
Reverse Engineering Winners System
Identify actual winners from historical data and build statistical detectors
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import json
from typing import List, Dict, Optional, Tuple
import warnings
from scipy import stats
from sklearn.cluster import KMeans
from sklearn.preprocessing import StandardScaler
import matplotlib.pyplot as plt
import seaborn as sns
warnings.filterwarnings('ignore')

class WinnerReverseEngineer:
    """Reverse engineer trading patterns from actual winners"""
    
    def __init__(self):
        """Initialize reverse engineering system"""
        self.winner_patterns = {}
        self.statistical_insights = {}
        self.pattern_detectors = {}
        self.validation_results = {}
        
    def analyze_historical_winners(self, symbols: List[str], 
                                 start_date: str = '2020-01-01',
                                 end_date: str = '2024-12-31',
                                 min_gain_threshold: float = 0.05) -> Dict:
        """Analyze historical winners to identify patterns"""
        
        print(f"🔍 REVERSE ENGINEERING HISTORICAL WINNERS")
        print(f"Date Range: {start_date} to {end_date}")
        print(f"Symbols: {len(symbols)}")
        print(f"Minimum Gain Threshold: {min_gain_threshold:.1%}")
        print("=" * 80)
        
        all_winners = []
        all_losers = []
        pattern_analysis = {}
        
        for i, symbol in enumerate(symbols):
            print(f"📊 Analyzing {symbol} ({i+1}/{len(symbols)})")
            
            try:
                # Get historical data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date, interval='1d')
                
                if hist.empty or len(hist) < 100:
                    continue
                
                # Calculate daily returns
                hist['Returns'] = hist['Close'].pct_change()
                hist['Volume_Ratio'] = hist['Volume'] / hist['Volume'].rolling(20).mean()
                
                # Identify winners and losers
                winners = hist[hist['Returns'] > min_gain_threshold].copy()
                losers = hist[hist['Returns'] < -min_gain_threshold].copy()
                
                if len(winners) > 0:
                    # Analyze winner patterns
                    winner_patterns = self._analyze_winner_patterns(symbol, winners, hist)
                    all_winners.extend(winner_patterns)
                
                if len(losers) > 0:
                    # Analyze loser patterns for comparison
                    loser_patterns = self._analyze_loser_patterns(symbol, losers, hist)
                    all_losers.extend(loser_patterns)
                
            except Exception as e:
                print(f"  ❌ Error analyzing {symbol}: {str(e)}")
                continue
        
        # Statistical analysis of patterns
        if all_winners:
            pattern_analysis = self._statistical_pattern_analysis(all_winners, all_losers)
        
        # Build pattern detectors
        if pattern_analysis:
            detectors = self._build_pattern_detectors(pattern_analysis)
        
        # Validate detectors
        if detectors:
            validation = self._validate_detectors(detectors, symbols, start_date, end_date)
        
        return {
            'winner_patterns': all_winners,
            'loser_patterns': all_losers,
            'pattern_analysis': pattern_analysis,
            'detectors': detectors if 'detectors' in locals() else {},
            'validation': validation if 'validation' in locals() else {}
        }
    
    def _analyze_winner_patterns(self, symbol: str, winners: pd.DataFrame, 
                               full_data: pd.DataFrame) -> List[Dict]:
        """Analyze patterns before winning days"""
        
        patterns = []
        
        for idx, winner in winners.iterrows():
            try:
                # Get data before the winning day
                winner_date = idx
                pre_winner_data = full_data.loc[:winner_date].tail(30)  # 30 days before
                
                if len(pre_winner_data) < 20:
                    continue
                
                # Calculate technical indicators
                pattern = {
                    'symbol': symbol,
                    'date': winner_date.strftime('%Y-%m-%d'),
                    'gain': winner['Returns'],
                    'volume_ratio': winner['Volume_Ratio'],
                    
                    # Price momentum indicators
                    'price_5d_momentum': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].iloc[-6] - 1),
                    'price_10d_momentum': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].iloc[-11] - 1),
                    'price_20d_momentum': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].iloc[-21] - 1),
                    
                    # Volume indicators
                    'volume_5d_avg': pre_winner_data['Volume'].tail(5).mean(),
                    'volume_10d_avg': pre_winner_data['Volume'].tail(10).mean(),
                    'volume_20d_avg': pre_winner_data['Volume'].tail(20).mean(),
                    'volume_trend': pre_winner_data['Volume'].tail(5).mean() / pre_winner_data['Volume'].tail(20).mean(),
                    
                    # Volatility indicators
                    'volatility_5d': pre_winner_data['Returns'].tail(5).std(),
                    'volatility_10d': pre_winner_data['Returns'].tail(10).std(),
                    'volatility_20d': pre_winner_data['Returns'].tail(20).std(),
                    
                    # RSI
                    'rsi_14': self._calculate_rsi(pre_winner_data['Close'].tail(15)),
                    
                    # Moving averages
                    'sma_5': pre_winner_data['Close'].tail(5).mean(),
                    'sma_10': pre_winner_data['Close'].tail(10).mean(),
                    'sma_20': pre_winner_data['Close'].tail(20).mean(),
                    'price_vs_sma5': pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].tail(5).mean() - 1,
                    'price_vs_sma10': pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].tail(10).mean() - 1,
                    'price_vs_sma20': pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].tail(20).mean() - 1,
                    
                    # Gap analysis
                    'gap_up': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['Close'].iloc[-2] - 1) if len(pre_winner_data) > 1 else 0,
                    
                    # Support/Resistance
                    'near_52w_high': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['High'].max() - 1),
                    'near_52w_low': (pre_winner_data['Close'].iloc[-1] / pre_winner_data['Low'].min() - 1),
                    
                    # Market context
                    'days_since_high': len(pre_winner_data) - pre_winner_data['High'].idxmax().day if hasattr(pre_winner_data['High'].idxmax(), 'day') else 0,
                    'days_since_low': len(pre_winner_data) - pre_winner_data['Low'].idxmin().day if hasattr(pre_winner_data['Low'].idxmin(), 'day') else 0,
                }
                
                patterns.append(pattern)
                
            except Exception as e:
                continue
        
        return patterns
    
    def _analyze_loser_patterns(self, symbol: str, losers: pd.DataFrame, 
                              full_data: pd.DataFrame) -> List[Dict]:
        """Analyze patterns before losing days (for comparison)"""
        
        patterns = []
        
        for idx, loser in losers.iterrows():
            try:
                # Get data before the losing day
                loser_date = idx
                pre_loser_data = full_data.loc[:loser_date].tail(30)  # 30 days before
                
                if len(pre_loser_data) < 20:
                    continue
                
                # Calculate same indicators as winners
                pattern = {
                    'symbol': symbol,
                    'date': loser_date.strftime('%Y-%m-%d'),
                    'loss': loser['Returns'],
                    'volume_ratio': loser['Volume_Ratio'],
                    
                    # Price momentum indicators
                    'price_5d_momentum': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].iloc[-6] - 1),
                    'price_10d_momentum': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].iloc[-11] - 1),
                    'price_20d_momentum': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].iloc[-21] - 1),
                    
                    # Volume indicators
                    'volume_5d_avg': pre_loser_data['Volume'].tail(5).mean(),
                    'volume_10d_avg': pre_loser_data['Volume'].tail(10).mean(),
                    'volume_20d_avg': pre_loser_data['Volume'].tail(20).mean(),
                    'volume_trend': pre_loser_data['Volume'].tail(5).mean() / pre_loser_data['Volume'].tail(20).mean(),
                    
                    # Volatility indicators
                    'volatility_5d': pre_loser_data['Returns'].tail(5).std(),
                    'volatility_10d': pre_loser_data['Returns'].tail(10).std(),
                    'volatility_20d': pre_loser_data['Returns'].tail(20).std(),
                    
                    # RSI
                    'rsi_14': self._calculate_rsi(pre_loser_data['Close'].tail(15)),
                    
                    # Moving averages
                    'sma_5': pre_loser_data['Close'].tail(5).mean(),
                    'sma_10': pre_loser_data['Close'].tail(10).mean(),
                    'sma_20': pre_loser_data['Close'].tail(20).mean(),
                    'price_vs_sma5': pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].tail(5).mean() - 1,
                    'price_vs_sma10': pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].tail(10).mean() - 1,
                    'price_vs_sma20': pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].tail(20).mean() - 1,
                    
                    # Gap analysis
                    'gap_up': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['Close'].iloc[-2] - 1) if len(pre_loser_data) > 1 else 0,
                    
                    # Support/Resistance
                    'near_52w_high': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['High'].max() - 1),
                    'near_52w_low': (pre_loser_data['Close'].iloc[-1] / pre_loser_data['Low'].min() - 1),
                    
                    # Market context
                    'days_since_high': len(pre_loser_data) - pre_loser_data['High'].idxmax().day if hasattr(pre_loser_data['High'].idxmax(), 'day') else 0,
                    'days_since_low': len(pre_loser_data) - pre_loser_data['Low'].idxmin().day if hasattr(pre_loser_data['Low'].idxmin(), 'day') else 0,
                }
                
                patterns.append(pattern)
                
            except Exception as e:
                continue
        
        return patterns
    
    def _statistical_pattern_analysis(self, winners: List[Dict], losers: List[Dict]) -> Dict:
        """Perform statistical analysis of patterns"""
        
        print(f"\n📊 STATISTICAL PATTERN ANALYSIS")
        print(f"Winners: {len(winners)}")
        print(f"Losers: {len(losers)}")
        
        if len(winners) == 0:
            return {}
        
        # Convert to DataFrames
        winners_df = pd.DataFrame(winners)
        losers_df = pd.DataFrame(losers) if losers else pd.DataFrame()
        
        # Key indicators to analyze
        indicators = [
            'price_5d_momentum', 'price_10d_momentum', 'price_20d_momentum',
            'volume_trend', 'volatility_5d', 'volatility_10d', 'volatility_20d',
            'rsi_14', 'price_vs_sma5', 'price_vs_sma10', 'price_vs_sma20',
            'gap_up', 'near_52w_high', 'near_52w_low'
        ]
        
        analysis = {}
        
        for indicator in indicators:
            if indicator in winners_df.columns:
                winner_values = winners_df[indicator].dropna()
                
                if len(winner_values) > 0:
                    # Basic statistics
                    mean_val = winner_values.mean()
                    median_val = winner_values.median()
                    std_val = winner_values.std()
                    
                    # Percentile analysis
                    p25 = winner_values.quantile(0.25)
                    p75 = winner_values.quantile(0.75)
                    
                    # Compare with losers if available
                    comparison = {}
                    if not losers_df.empty and indicator in losers_df.columns:
                        loser_values = losers_df[indicator].dropna()
                        if len(loser_values) > 0:
                            # T-test for difference
                            t_stat, p_value = stats.ttest_ind(winner_values, loser_values)
                            comparison = {
                                't_statistic': t_stat,
                                'p_value': p_value,
                                'significant': p_value < 0.05,
                                'loser_mean': loser_values.mean(),
                                'difference': mean_val - loser_values.mean()
                            }
                    
                    analysis[indicator] = {
                        'mean': mean_val,
                        'median': median_val,
                        'std': std_val,
                        'p25': p25,
                        'p75': p75,
                        'range': p75 - p25,
                        'comparison': comparison
                    }
        
        # Identify most significant patterns
        significant_patterns = {}
        for indicator, stat_data in analysis.items():
            if 'comparison' in stat_data and stat_data['comparison'].get('significant', False):
                significant_patterns[indicator] = stat_data
        
        print(f"\n🎯 SIGNIFICANT PATTERNS (p < 0.05):")
        for indicator, stat_data in significant_patterns.items():
            comp = stat_data['comparison']
            print(f"• {indicator}:")
            print(f"  Winners: {stat_data['mean']:.4f} vs Losers: {comp['loser_mean']:.4f}")
            print(f"  Difference: {comp['difference']:.4f} (p={comp['p_value']:.4f})")
        
        return {
            'all_indicators': analysis,
            'significant_patterns': significant_patterns,
            'winner_summary': {
                'total_winners': len(winners),
                'avg_gain': winners_df['gain'].mean() if 'gain' in winners_df.columns else 0,
                'max_gain': winners_df['gain'].max() if 'gain' in winners_df.columns else 0,
                'min_gain': winners_df['gain'].min() if 'gain' in winners_df.columns else 0
            }
        }
    
    def _build_pattern_detectors(self, pattern_analysis: Dict) -> Dict:
        """Build practical pattern detectors based on statistical analysis"""
        
        print(f"\n🔧 BUILDING PATTERN DETECTORS")
        
        detectors = {}
        significant_patterns = pattern_analysis.get('significant_patterns', {})
        
        for indicator, stat_data in significant_patterns.items():
            comp = stat_data['comparison']
            winner_mean = stat_data['mean']
            loser_mean = comp['loser_mean']
            
            # Determine direction (higher or lower is better for winners)
            if comp['difference'] > 0:
                # Higher values are better for winners
                threshold = winner_mean - stat_data['std']  # One std below winner mean
                direction = 'above'
            else:
                # Lower values are better for winners
                threshold = winner_mean + stat_data['std']  # One std above winner mean
                direction = 'below'
            
            detectors[indicator] = {
                'threshold': threshold,
                'direction': direction,
                'confidence': 1 - comp['p_value'],
                'effect_size': abs(comp['difference']) / stat_data['std'],
                'description': f"{indicator} {direction} {threshold:.4f}"
            }
        
        # Create composite detector
        if detectors:
            composite_detector = self._create_composite_detector(detectors)
            detectors['composite'] = composite_detector
        
        print(f"✅ Built {len(detectors)} pattern detectors")
        
        return detectors
    
    def _create_composite_detector(self, individual_detectors: Dict) -> Dict:
        """Create a composite detector that combines multiple patterns"""
        
        # Weight detectors by their confidence and effect size
        weighted_detectors = []
        
        for indicator, detector in individual_detectors.items():
            if indicator != 'composite':
                weight = detector['confidence'] * detector['effect_size']
                weighted_detectors.append({
                    'indicator': indicator,
                    'weight': weight,
                    'detector': detector
                })
        
        # Sort by weight
        weighted_detectors.sort(key=lambda x: x['weight'], reverse=True)
        
        # Take top 5 most significant patterns
        top_detectors = weighted_detectors[:5]
        
        composite = {
            'type': 'composite',
            'components': top_detectors,
            'total_weight': sum(d['weight'] for d in top_detectors),
            'description': f"Combines {len(top_detectors)} most significant patterns"
        }
        
        return composite
    
    def _validate_detectors(self, detectors: Dict, symbols: List[str], 
                          start_date: str, end_date: str) -> Dict:
        """Validate pattern detectors on out-of-sample data"""
        
        print(f"\n🧪 VALIDATING DETECTORS")
        
        validation_results = {}
        
        for detector_name, detector in detectors.items():
            if detector_name == 'composite':
                continue
            
            print(f"Testing {detector_name}...")
            
            # Test detector on sample of symbols
            test_symbols = symbols[:20]  # Test on first 20 symbols
            results = self._test_detector(detector, test_symbols, start_date, end_date)
            
            validation_results[detector_name] = results
        
        # Test composite detector
        if 'composite' in detectors:
            print(f"Testing composite detector...")
            composite_results = self._test_composite_detector(
                detectors['composite'], symbols[:20], start_date, end_date
            )
            validation_results['composite'] = composite_results
        
        return validation_results
    
    def _test_detector(self, detector: Dict, symbols: List[str], 
                      start_date: str, end_date: str) -> Dict:
        """Test individual detector"""
        
        signals = []
        correct_predictions = 0
        total_predictions = 0
        
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date, interval='1d')
                
                if hist.empty or len(hist) < 30:
                    continue
                
                # Calculate indicator for each day
                for i in range(30, len(hist)):
                    current_date = hist.index[i]
                    pre_data = hist.iloc[:i+1].tail(30)
                    
                    # Calculate the indicator
                    indicator_value = self._calculate_indicator(detector, pre_data)
                    
                    # Check if signal is triggered
                    threshold = detector['threshold']
                    direction = detector['direction']
                    
                    signal_triggered = False
                    if direction == 'above' and indicator_value > threshold:
                        signal_triggered = True
                    elif direction == 'below' and indicator_value < threshold:
                        signal_triggered = True
                    
                    if signal_triggered:
                        # Check if next day was a winner (gain > 2%)
                        if i + 1 < len(hist):
                            next_day_return = (hist.iloc[i+1]['Close'] / hist.iloc[i]['Close']) - 1
                            
                            signals.append({
                                'symbol': symbol,
                                'date': current_date.strftime('%Y-%m-%d'),
                                'indicator_value': indicator_value,
                                'threshold': threshold,
                                'next_day_return': next_day_return,
                                'correct': next_day_return > 0.02
                            })
                            
                            total_predictions += 1
                            if next_day_return > 0.02:
                                correct_predictions += 1
                
            except Exception as e:
                continue
        
        # Calculate accuracy
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
        
        return {
            'total_signals': len(signals),
            'correct_predictions': correct_predictions,
            'accuracy': accuracy,
            'avg_next_day_return': np.mean([s['next_day_return'] for s in signals]) if signals else 0,
            'sample_signals': signals[:10]  # First 10 signals
        }
    
    def _test_composite_detector(self, composite: Dict, symbols: List[str], 
                               start_date: str, end_date: str) -> Dict:
        """Test composite detector"""
        
        signals = []
        correct_predictions = 0
        total_predictions = 0
        
        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(start=start_date, end=end_date, interval='1d')
                
                if hist.empty or len(hist) < 30:
                    continue
                
                # Calculate composite score for each day
                for i in range(30, len(hist)):
                    current_date = hist.index[i]
                    pre_data = hist.iloc[:i+1].tail(30)
                    
                    # Calculate composite score
                    composite_score = 0
                    total_weight = 0
                    
                    for component in composite['components']:
                        indicator_name = component['indicator']
                        weight = component['weight']
                        detector = component['detector']
                        
                        indicator_value = self._calculate_indicator(detector, pre_data)
                        threshold = detector['threshold']
                        direction = detector['direction']
                        
                        # Check if this component is triggered
                        component_triggered = False
                        if direction == 'above' and indicator_value > threshold:
                            component_triggered = True
                        elif direction == 'below' and indicator_value < threshold:
                            component_triggered = True
                        
                        if component_triggered:
                            composite_score += weight
                        
                        total_weight += weight
                    
                    # Normalize score
                    if total_weight > 0:
                        composite_score = composite_score / total_weight
                    
                    # Signal threshold (trigger if 60% of components agree)
                    if composite_score > 0.6:
                        if i + 1 < len(hist):
                            next_day_return = (hist.iloc[i+1]['Close'] / hist.iloc[i]['Close']) - 1
                            
                            signals.append({
                                'symbol': symbol,
                                'date': current_date.strftime('%Y-%m-%d'),
                                'composite_score': composite_score,
                                'next_day_return': next_day_return,
                                'correct': next_day_return > 0.02
                            })
                            
                            total_predictions += 1
                            if next_day_return > 0.02:
                                correct_predictions += 1
                
            except Exception as e:
                continue
        
        accuracy = correct_predictions / total_predictions if total_predictions > 0 else 0
        
        return {
            'total_signals': len(signals),
            'correct_predictions': correct_predictions,
            'accuracy': accuracy,
            'avg_next_day_return': np.mean([s['next_day_return'] for s in signals]) if signals else 0,
            'sample_signals': signals[:10]
        }
    
    def _calculate_indicator(self, detector: Dict, data: pd.DataFrame) -> float:
        """Calculate indicator value based on detector"""
        
        indicator_name = detector.get('description', '').split()[0]
        
        if 'price_5d_momentum' in indicator_name:
            return (data['Close'].iloc[-1] / data['Close'].iloc[-6] - 1) if len(data) >= 6 else 0
        elif 'price_10d_momentum' in indicator_name:
            return (data['Close'].iloc[-1] / data['Close'].iloc[-11] - 1) if len(data) >= 11 else 0
        elif 'price_20d_momentum' in indicator_name:
            return (data['Close'].iloc[-1] / data['Close'].iloc[-21] - 1) if len(data) >= 21 else 0
        elif 'volume_trend' in indicator_name:
            return data['Volume'].tail(5).mean() / data['Volume'].tail(20).mean() if len(data) >= 20 else 1
        elif 'volatility_5d' in indicator_name:
            return data['Returns'].tail(5).std() if len(data) >= 5 else 0
        elif 'volatility_10d' in indicator_name:
            return data['Returns'].tail(10).std() if len(data) >= 10 else 0
        elif 'volatility_20d' in indicator_name:
            return data['Returns'].tail(20).std() if len(data) >= 20 else 0
        elif 'rsi_14' in indicator_name:
            return self._calculate_rsi(data['Close'].tail(15))
        elif 'price_vs_sma5' in indicator_name:
            return data['Close'].iloc[-1] / data['Close'].tail(5).mean() - 1 if len(data) >= 5 else 0
        elif 'price_vs_sma10' in indicator_name:
            return data['Close'].iloc[-1] / data['Close'].tail(10).mean() - 1 if len(data) >= 10 else 0
        elif 'price_vs_sma20' in indicator_name:
            return data['Close'].iloc[-1] / data['Close'].tail(20).mean() - 1 if len(data) >= 20 else 0
        elif 'gap_up' in indicator_name:
            return (data['Close'].iloc[-1] / data['Close'].iloc[-2] - 1) if len(data) >= 2 else 0
        elif 'near_52w_high' in indicator_name:
            return (data['Close'].iloc[-1] / data['High'].max() - 1)
        elif 'near_52w_low' in indicator_name:
            return (data['Close'].iloc[-1] / data['Low'].min() - 1)
        else:
            return 0
    
    def _calculate_rsi(self, prices):
        """Calculate RSI"""
        if len(prices) < 2:
            return 50.0
        
        gains = []
        losses = []
        
        for i in range(1, len(prices)):
            change = prices.iloc[i] - prices.iloc[i-1]
            if change > 0:
                gains.append(change)
                losses.append(0.0)
            else:
                gains.append(0.0)
                losses.append(-change)
        
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        
        if avg_loss == 0:
            return 100.0
        
        rs = avg_gain / avg_loss
        rsi = 100.0 - (100.0 / (1.0 + rs))
        return rsi
    
    def generate_trading_signals(self, symbols: List[str], 
                               detectors: Dict) -> List[Dict]:
        """Generate trading signals using validated detectors"""
        
        print(f"\n🚀 GENERATING TRADING SIGNALS")
        
        signals = []
        
        for symbol in symbols:
            try:
                # Get recent data
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='60d', interval='1d')
                
                if hist.empty or len(hist) < 30:
                    continue
                
                # Calculate composite score
                composite_score = 0
                total_weight = 0
                triggered_components = []
                
                if 'composite' in detectors:
                    composite = detectors['composite']
                    
                    for component in composite['components']:
                        indicator_name = component['indicator']
                        weight = component['weight']
                        detector = component['detector']
                        
                        indicator_value = self._calculate_indicator(detector, hist)
                        threshold = detector['threshold']
                        direction = detector['direction']
                        
                        # Check if this component is triggered
                        component_triggered = False
                        if direction == 'above' and indicator_value > threshold:
                            component_triggered = True
                        elif direction == 'below' and indicator_value < threshold:
                            component_triggered = True
                        
                        if component_triggered:
                            composite_score += weight
                            triggered_components.append(indicator_name)
                        
                        total_weight += weight
                    
                    # Normalize score
                    if total_weight > 0:
                        composite_score = composite_score / total_weight
                    
                    # Generate signal if score is high enough
                    if composite_score > 0.6:
                        current_price = hist['Close'].iloc[-1]
                        
                        signal = {
                            'symbol': symbol,
                            'action': 'BUY',
                            'current_price': current_price,
                            'composite_score': composite_score,
                            'triggered_components': triggered_components,
                            'confidence': composite_score,
                            'date': datetime.now().strftime('%Y-%m-%d'),
                            'reason': f"Composite score {composite_score:.2f} based on {len(triggered_components)} patterns"
                        }
                        
                        signals.append(signal)
                
            except Exception as e:
                continue
        
        # Sort by composite score
        signals.sort(key=lambda x: x['composite_score'], reverse=True)
        
        print(f"✅ Generated {len(signals)} trading signals")
        
        return signals

def main():
    """Run reverse engineering analysis"""
    print("🔍 REVERSE ENGINEERING WINNERS SYSTEM")
    print("=" * 80)
    
    # Load symbols
    try:
        with open('data/processed_tickers.txt', 'r') as f:
            symbols = [line.strip() for line in f.readlines() if line.strip()]
        symbols = symbols[:50]  # Start with 50 symbols
    except (OSError, ValueError):
        symbols = ['BBCA.JK', 'TLKM.JK', 'ASII.JK', 'BMRI.JK', 'BBRI.JK', 'UNTR.JK', 'PGAS.JK', 'KLBF.JK']
    
    # Initialize system
    reverse_engineer = WinnerReverseEngineer()
    
    # Analyze historical winners
    results = reverse_engineer.analyze_historical_winners(
        symbols=symbols,
        start_date='2020-01-01',
        end_date='2024-12-31',
        min_gain_threshold=0.05  # 5% gain threshold
    )
    
    # Generate trading signals
    if 'detectors' in results and results['detectors']:
        signals = reverse_engineer.generate_trading_signals(symbols, results['detectors'])
        
        print(f"\n📊 TOP TRADING SIGNALS:")
        for i, signal in enumerate(signals[:10]):
            print(f"{i+1}. {signal['symbol']}: {signal['action']} @ {signal['current_price']:,.0f}")
            print(f"   Score: {signal['composite_score']:.2f}, Confidence: {signal['confidence']:.2f}")
            print(f"   Patterns: {', '.join(signal['triggered_components'][:3])}")
            print()
    
    # Save results
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    filename = f'reverse_engineering_results_{timestamp}.json'
    
    with open(filename, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    
    print(f"✅ Results saved to {filename}")

if __name__ == "__main__":
    main()
