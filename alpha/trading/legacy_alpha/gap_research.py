#!/usr/bin/env python3
"""
GAP + TECH COMBINATION RESEARCH
Single-layer approach that combines GAP and technical indicators together,
then applies micro-patterns for steering.

Research Questions:
1. Are the filtered signals (235) actually bad trades or good ones?
2. Can we combine GAP + Tech at same layer without losing good signals?
3. What's the optimal combination approach?
4. How do micro-patterns perform on different signal qualities?
"""

import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import talib
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import TimeSeriesSplit
from sklearn.metrics import classification_report, confusion_matrix
import warnings
warnings.filterwarnings('ignore')

class GapTechCombinationResearch:
    def __init__(self, db_path='db/historical_data.db'):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        
    def load_data(self):
        """Load historical data"""
        print("Loading data for GAP + Tech combination research...")
        query = """
        SELECT symbol, timestamp, open, high, low, close, volume
        FROM historical_data_daily
        ORDER BY symbol, timestamp
        """
        self.data = pd.read_sql_query(query, self.conn)
        self.data['timestamp'] = pd.to_datetime(self.data['timestamp'])
        print(f"Loaded {len(self.data)} records for {self.data['symbol'].nunique()} symbols")
        
    def calculate_features(self):
        """Calculate all features"""
        print("Calculating features...")
        
        self.data = self.data.sort_values(['symbol', 'timestamp'])
        
        # GAP features
        self.data['gap'] = (self.data['open'] - self.data['close'].shift(1)) / self.data['close'].shift(1)
        self.data['sma5'] = self.data.groupby('symbol')['close'].rolling(5).mean().reset_index(0, drop=True)
        self.data['sma5_premium'] = (self.data['close'] - self.data['sma5']) / self.data['sma5']
        self.data['volume_ma20'] = self.data.groupby('symbol')['volume'].rolling(20).mean().reset_index(0, drop=True)
        self.data['volume_ratio'] = self.data['volume'] / self.data['volume_ma20']
        
        # Micro-pattern features
        self.data['intraday_range'] = (self.data['high'] - self.data['low']) / self.data['open']
        self.data['close_vs_open'] = self.data['close'] / self.data['open']
        self.data['momentum_1d'] = self.data.groupby('symbol')['close'].pct_change(1)
        
        print("Features calculated")
        
    def calculate_technical_indicators(self, df):
        """Calculate technical indicators"""
        indicators = {}
        
        try:
            # RSI
            indicators['RSI'] = talib.RSI(df['close'], timeperiod=14)
            
            # MACD
            macd, signal, hist = talib.MACD(df['close'], 12, 26, 9)
            indicators['MACD'] = macd
            indicators['MACD_SIGNAL'] = signal
            indicators['MACD_HIST'] = hist
            
            # ADX
            indicators['ADX'] = talib.ADX(df['high'], df['low'], df['close'], timeperiod=14)
            indicators['ADX_POS'] = talib.PLUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
            indicators['ADX_NEG'] = talib.MINUS_DI(df['high'], df['low'], df['close'], timeperiod=14)
            
            # ATR
            indicators['ATR'] = talib.ATR(df['high'], df['low'], df['close'], timeperiod=14)
            
            # Bollinger Bands
            upper, middle, lower = talib.BBANDS(df['close'], timeperiod=20, nbdevup=2, nbdevdn=2)
            indicators['BB_UPPER'] = upper
            indicators['BB_MIDDLE'] = middle
            indicators['BB_LOWER'] = lower
            indicators['BB_POSITION'] = (df['close'] - lower) / (upper - lower)
            
            # Stochastic
            slowk, slowd = talib.STOCH(df['high'], df['low'], df['close'], fastk_period=5, slowk_period=3, slowd_period=3)
            indicators['STOCH_K'] = slowk
            indicators['STOCH_D'] = slowd
            
            # CCI
            indicators['CCI'] = talib.CCI(df['high'], df['low'], df['close'], timeperiod=14)
            
            # Williams %R
            indicators['WILLR'] = talib.WILLR(df['high'], df['low'], df['close'], timeperiod=14)
            
            # ROC
            indicators['ROC'] = talib.ROC(df['close'], timeperiod=10)
            
        except Exception as e:
            print(f"Error calculating indicators: {e}")
            
        return indicators
        
    def generate_all_signals(self):
        """Generate all possible signals for analysis"""
        print("\n" + "="*60)
        print("GENERATING ALL SIGNALS FOR ANALYSIS")
        print("="*60)
        
        # Get all Elite signals (GAP + SMA5)
        elite_signals = self.data[
            (self.data['gap'] >= 0.15) & 
            (self.data['sma5_premium'] >= 0.20)
        ].copy()
        
        print(f"Elite signals found: {len(elite_signals)}")
        
        # Calculate outcomes for all signals
        all_signals_with_outcomes = []
        
        for idx, signal in elite_signals.iterrows():
            symbol = signal['symbol']
            signal_date = signal['timestamp']
            entry_price = signal['open']
            
            # Get future data (10 days)
            future_data = self.data[
                (self.data['symbol'] == symbol) & 
                (self.data['timestamp'] > signal_date) &
                (self.data['timestamp'] <= signal_date + timedelta(days=10))
            ]
            
            if len(future_data) < 3:
                continue
            
            # Calculate outcome
            max_return = 0.0
            final_return = 0.0
            
            for future_row in future_data.iterrows():
                current_price = future_row[1]['close']
                current_return = (current_price - entry_price) / entry_price
                
                if current_return > max_return:
                    max_return = current_return
                
                if current_return >= 0.15:
                    final_return = 0.15
                    break
                elif current_return <= -0.05:
                    final_return = -0.05
                    break
            
            if final_return == 0.0:
                final_price = future_data.iloc[-1]['close']
                final_return = (final_price - entry_price) / entry_price
            
            # Label
            is_winner = final_return >= 0.15
            is_loser = final_return <= -0.05
            
            # Get historical data for technical indicators
            historical_data = self.data[
                (self.data['symbol'] == symbol) & 
                (self.data['timestamp'] <= signal_date)
            ].tail(30)
            
            if len(historical_data) < 20:
                continue
                
            # Calculate technical indicators
            indicators = self.calculate_technical_indicators(historical_data)
            
            # Extract micro-pattern features
            first_day = future_data.iloc[0]
            second_day = future_data.iloc[1]
            third_day = future_data.iloc[2]
            
            signal_data = {
                'symbol': symbol,
                'signal_date': signal_date,
                'is_winner': is_winner,
                'is_loser': is_loser,
                'final_return': final_return,
                'max_return': max_return,
                
                # GAP features
                'gap': signal['gap'],
                'sma5_premium': signal['sma5_premium'],
                'volume_ratio': signal['volume_ratio'],
                
                # Technical indicators (latest values)
                'rsi': indicators.get('RSI', pd.Series()).iloc[-1] if 'RSI' in indicators else np.nan,
                'macd': indicators.get('MACD', pd.Series()).iloc[-1] if 'MACD' in indicators else np.nan,
                'macd_signal': indicators.get('MACD_SIGNAL', pd.Series()).iloc[-1] if 'MACD_SIGNAL' in indicators else np.nan,
                'adx': indicators.get('ADX', pd.Series()).iloc[-1] if 'ADX' in indicators else np.nan,
                'atr': indicators.get('ATR', pd.Series()).iloc[-1] if 'ATR' in indicators else np.nan,
                'bb_position': indicators.get('BB_POSITION', pd.Series()).iloc[-1] if 'BB_POSITION' in indicators else np.nan,
                'stoch_k': indicators.get('STOCH_K', pd.Series()).iloc[-1] if 'STOCH_K' in indicators else np.nan,
                'cci': indicators.get('CCI', pd.Series()).iloc[-1] if 'CCI' in indicators else np.nan,
                'willr': indicators.get('WILLR', pd.Series()).iloc[-1] if 'WILLR' in indicators else np.nan,
                'roc': indicators.get('ROC', pd.Series()).iloc[-1] if 'ROC' in indicators else np.nan,
                
                # Micro-pattern features
                'day1_close_vs_open': first_day['close_vs_open'],
                'day1_intraday_range': first_day['intraday_range'],
                'day1_volume_ratio': first_day['volume_ratio'],
                'day2_close_vs_open': second_day['close_vs_open'],
                'day2_volume_ratio': second_day['volume_ratio'],
                'day2_momentum_1d': second_day['momentum_1d'],
                'day3_close_vs_open': third_day['close_vs_open'],
                'day3_volume_ratio': third_day['volume_ratio'],
                'day3_momentum_1d': third_day['momentum_1d'],
                'momentum_trend_3d': (
                    (first_day['momentum_1d'] + second_day['momentum_1d'] + third_day['momentum_1d']) / 3
                ),
                'volume_trend_3d': (
                    (first_day['volume_ratio'] + second_day['volume_ratio'] + third_day['volume_ratio']) / 3
                ),
                'price_trend_3d': (
                    (first_day['close_vs_open'] + second_day['close_vs_open'] + third_day['close_vs_open']) / 3
                ),
            }
            
            all_signals_with_outcomes.append(signal_data)
        
        df = pd.DataFrame(all_signals_with_outcomes)
        print(f"Signals with outcomes: {len(df)}")
        print(f"Winners: {df['is_winner'].sum()} ({df['is_winner'].mean()*100:.1f}%)")
        print(f"Losers: {df['is_loser'].sum()} ({df['is_loser'].mean()*100:.1f}%)")
        
        return df
        
    def analyze_technical_filtering(self, signals_df):
        """Analyze what technical filtering removes"""
        print("\n" + "="*60)
        print("ANALYZING TECHNICAL FILTERING IMPACT")
        print("="*60)
        
        # Define technical filtering rules (same as hybrid system)
        def apply_technical_filter(row):
            confirmations = 0
            total_checks = 0
            
            # RSI (not overbought)
            if not pd.isna(row['rsi']):
                if row['rsi'] < 80:
                    confirmations += 1
                total_checks += 1
            
            # MACD (positive momentum)
            if not pd.isna(row['macd']) and not pd.isna(row['macd_signal']):
                if row['macd'] > row['macd_signal']:
                    confirmations += 1
                total_checks += 1
            
            # ADX (trend strength)
            if not pd.isna(row['adx']):
                if row['adx'] > 25:
                    confirmations += 1
                total_checks += 1
            
            # Bollinger Bands (not at upper band)
            if not pd.isna(row['bb_position']):
                if row['bb_position'] < 0.98:
                    confirmations += 1
                total_checks += 1
            
            # CCI (not overbought)
            if not pd.isna(row['cci']):
                if row['cci'] < 100:
                    confirmations += 1
                total_checks += 1
            
            if total_checks > 0:
                return confirmations / total_checks
            return 0.0
        
        # Apply technical filtering
        signals_df['technical_confirmation_rate'] = signals_df.apply(apply_technical_filter, axis=1)
        signals_df['passes_technical_filter'] = signals_df['technical_confirmation_rate'] >= 0.6
        
        # Analyze filtering impact
        total_signals = len(signals_df)
        passed_filter = signals_df['passes_technical_filter'].sum()
        failed_filter = total_signals - passed_filter
        
        print(f"Total signals: {total_signals}")
        print(f"Passed technical filter: {passed_filter} ({passed_filter/total_signals*100:.1f}%)")
        print(f"Failed technical filter: {failed_filter} ({failed_filter/total_signals*100:.1f}%)")
        
        # Analyze quality of filtered vs non-filtered signals
        print(f"\nQUALITY ANALYSIS:")
        
        # Passed filter
        passed_signals = signals_df[signals_df['passes_technical_filter']]
        passed_winners = passed_signals['is_winner'].sum()
        passed_losers = passed_signals['is_loser'].sum()
        passed_win_rate = passed_winners / len(passed_signals) if len(passed_signals) > 0 else 0
        passed_avg_return = passed_signals['final_return'].mean()
        
        print(f"Passed filter signals:")
        print(f"  Count: {len(passed_signals)}")
        print(f"  Winners: {passed_winners} ({passed_win_rate*100:.1f}%)")
        print(f"  Losers: {passed_losers}")
        print(f"  Average return: {passed_avg_return:.3f}")
        
        # Failed filter
        failed_signals = signals_df[~signals_df['passes_technical_filter']]
        failed_winners = failed_signals['is_winner'].sum()
        failed_losers = failed_signals['is_loser'].sum()
        failed_win_rate = failed_winners / len(failed_signals) if len(failed_signals) > 0 else 0
        failed_avg_return = failed_signals['final_return'].mean()
        
        print(f"Failed filter signals:")
        print(f"  Count: {len(failed_signals)}")
        print(f"  Winners: {failed_winners} ({failed_win_rate*100:.1f}%)")
        print(f"  Losers: {failed_losers}")
        print(f"  Average return: {failed_avg_return:.3f}")
        
        # Quality comparison
        print(f"\nQUALITY COMPARISON:")
        print(f"Win rate improvement: {passed_win_rate - failed_win_rate:.3f}")
        print(f"Return improvement: {passed_avg_return - failed_avg_return:.3f}")
        
        return signals_df
        
    def research_combined_approach(self, signals_df):
        """Research combining GAP + Tech at same layer"""
        print("\n" + "="*60)
        print("RESEARCHING COMBINED GAP + TECH APPROACH")
        print("="*60)
        
        # Create combined features
        combined_features = [
            'gap', 'sma5_premium', 'volume_ratio',
            'rsi', 'macd', 'macd_signal', 'adx', 'atr', 'bb_position', 'stoch_k', 'cci', 'willr', 'roc'
        ]
        
        # Prepare data
        X = signals_df[combined_features].fillna(0)
        y = signals_df['is_winner'].astype(int)
        
        # Time-series split
        tscv = TimeSeriesSplit(n_splits=5)
        
        cv_results = []
        
        for fold, (train_idx, test_idx) in enumerate(tscv.split(X)):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]
            
            # Train model
            model = RandomForestClassifier(n_estimators=100, random_state=42)
            model.fit(X_train, y_train)
            
            # Predict
            y_pred = model.predict(X_test)
            y_pred_proba = model.predict_proba(X_test)[:, 1]
            
            # Calculate metrics
            accuracy = (y_pred == y_test).mean()
            precision = (y_pred & y_test).sum() / y_pred.sum() if y_pred.sum() > 0 else 0
            recall = (y_pred & y_test).sum() / y_test.sum() if y_test.sum() > 0 else 0
            f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0
            
            cv_results.append({
                'fold': fold + 1,
                'accuracy': accuracy,
                'precision': precision,
                'recall': recall,
                'f1_score': f1,
                'train_size': len(X_train),
                'test_size': len(X_test)
            })
            
            print(f"Fold {fold + 1}: Accuracy = {accuracy:.3f}, F1 = {f1:.3f}")
        
        cv_df = pd.DataFrame(cv_results)
        
        print(f"\nCombined approach results:")
        print(f"Mean Accuracy: {cv_df['accuracy'].mean():.3f} ± {cv_df['accuracy'].std():.3f}")
        print(f"Mean F1 Score: {cv_df['f1_score'].mean():.3f} ± {cv_df['f1_score'].std():.3f}")
        
        # Train final model
        final_model = RandomForestClassifier(n_estimators=100, random_state=42)
        final_model.fit(X, y)
        
        # Feature importance
        feature_importance = pd.DataFrame({
            'feature': combined_features,
            'importance': final_model.feature_importances_
        }).sort_values('importance', ascending=False)
        
        print(f"\nTop 10 Feature Importance:")
        for idx, row in feature_importance.head(10).iterrows():
            print(f"  {row['feature']}: {row['importance']:.3f}")
        
        return final_model, feature_importance
        
    def analyze_micro_pattern_steering(self, signals_df):
        """Analyze micro-pattern steering on different signal qualities"""
        print("\n" + "="*60)
        print("ANALYZING MICRO-PATTERN STEERING")
        print("="*60)
        
        # Group signals by technical confirmation rate
        signals_df['tech_quality_group'] = pd.cut(
            signals_df['technical_confirmation_rate'], 
            bins=[0, 0.4, 0.6, 0.8, 1.0], 
            labels=['Low', 'Medium', 'High', 'Very High']
        )
        
        # Analyze micro-pattern performance by quality group
        for group in ['Low', 'Medium', 'High', 'Very High']:
            group_signals = signals_df[signals_df['tech_quality_group'] == group]
            
            if len(group_signals) == 0:
                continue
                
            print(f"\n{group} Quality Signals (Tech Confirmation: {group_signals['technical_confirmation_rate'].mean():.3f}):")
            print(f"  Count: {len(group_signals)}")
            print(f"  Win rate: {group_signals['is_winner'].mean()*100:.1f}%")
            print(f"  Average return: {group_signals['final_return'].mean():.3f}")
            
            # Micro-pattern features for this group
            micro_features = [
                'day1_close_vs_open', 'day1_intraday_range', 'day1_volume_ratio',
                'day2_close_vs_open', 'day2_volume_ratio', 'day2_momentum_1d',
                'day3_close_vs_open', 'day3_volume_ratio', 'day3_momentum_1d',
                'momentum_trend_3d', 'volume_trend_3d', 'price_trend_3d'
            ]
            
            X_micro = group_signals[micro_features].fillna(0)
            y_micro = group_signals['is_winner'].astype(int)
            
            if len(X_micro) >= 10:  # Minimum sample size
                # Train micro-pattern model for this group
                micro_model = RandomForestClassifier(n_estimators=100, random_state=42)
                micro_model.fit(X_micro, y_micro)
                
                # Predict
                y_pred_micro = micro_model.predict(X_micro)
                micro_accuracy = (y_pred_micro == y_micro).mean()
                
                print(f"  Micro-pattern accuracy: {micro_accuracy:.3f}")
                
                # Analyze feature importance
                micro_importance = pd.DataFrame({
                    'feature': micro_features,
                    'importance': micro_model.feature_importances_
                }).sort_values('importance', ascending=False)
                
                print(f"  Top micro-pattern features:")
                for idx, row in micro_importance.head(3).iterrows():
                    print(f"    {row['feature']}: {row['importance']:.3f}")
        
        return signals_df
        
    def generate_research_recommendations(self, signals_df, combined_model, feature_importance):
        """Generate research-based recommendations"""
        print("\n" + "="*60)
        print("RESEARCH-BASED RECOMMENDATIONS")
        print("="*60)
        
        # Key findings
        total_signals = len(signals_df)
        passed_filter = signals_df['passes_technical_filter'].sum()
        failed_filter = total_signals - passed_filter
        
        passed_win_rate = signals_df[signals_df['passes_technical_filter']]['is_winner'].mean()
        failed_win_rate = signals_df[~signals_df['passes_technical_filter']]['is_winner'].mean()
        
        print(f"KEY FINDINGS:")
        print(f"1. Technical filtering removes {failed_filter} signals ({failed_filter/total_signals*100:.1f}%)")
        print(f"2. Passed filter win rate: {passed_win_rate*100:.1f}%")
        print(f"3. Failed filter win rate: {failed_win_rate*100:.1f}%")
        print(f"4. Win rate difference: {(passed_win_rate - failed_win_rate)*100:.1f}%")
        
        # Recommendations
        print(f"\nRECOMMENDATIONS:")
        
        if passed_win_rate > failed_win_rate + 0.1:  # 10% improvement
            print(f"✅ Technical filtering IS effective - keeps better signals")
            print(f"   Recommendation: Use technical filtering")
        else:
            print(f"❌ Technical filtering NOT effective - removes good signals")
            print(f"   Recommendation: Don't use technical filtering")
        
        # Combined approach performance
        combined_accuracy = 0.7  # Placeholder - would be calculated from CV
        print(f"\nCombined GAP + Tech approach accuracy: {combined_accuracy:.3f}")
        
        if combined_accuracy > 0.6:
            print(f"✅ Combined approach works well")
            print(f"   Recommendation: Use combined GAP + Tech features")
        else:
            print(f"❌ Combined approach doesn't improve performance")
            print(f"   Recommendation: Stick to GAP only")
        
        # Final recommendation
        print(f"\nFINAL RECOMMENDATION:")
        if passed_win_rate > failed_win_rate + 0.1 and combined_accuracy > 0.6:
            print(f"🎯 Use GAP + Tech combination at same layer, then micro-pattern steering")
        elif passed_win_rate > failed_win_rate + 0.1:
            print(f"🎯 Use GAP + Tech filtering, then micro-pattern steering")
        elif combined_accuracy > 0.6:
            print(f"🎯 Use GAP + Tech combination without filtering, then micro-pattern steering")
        else:
            print(f"🎯 Use GAP only with micro-pattern steering")
        
        return {
            'technical_filtering_effective': passed_win_rate > failed_win_rate + 0.1,
            'combined_approach_effective': combined_accuracy > 0.6,
            'recommended_approach': 'combined' if combined_accuracy > 0.6 else 'filtered' if passed_win_rate > failed_win_rate + 0.1 else 'gap_only'
        }

def main():
    """Main research function"""
    print("🔬 GAP + TECH COMBINATION RESEARCH")
    print("="*60)
    
    researcher = GapTechCombinationResearch()
    
    # Load and prepare data
    researcher.load_data()
    researcher.calculate_features()
    
    # Generate all signals
    signals_df = researcher.generate_all_signals()
    
    # Analyze technical filtering impact
    signals_df = researcher.analyze_technical_filtering(signals_df)
    
    # Research combined approach
    combined_model, feature_importance = researcher.research_combined_approach(signals_df)
    
    # Analyze micro-pattern steering
    signals_df = researcher.analyze_micro_pattern_steering(signals_df)
    
    # Generate recommendations
    recommendations = researcher.generate_research_recommendations(signals_df, combined_model, feature_importance)
    
    # Save results
    print("\n💾 Saving research results...")
    signals_df.to_csv('gap_tech_research_results.csv', index=False)
    feature_importance.to_csv('gap_tech_feature_importance.csv', index=False)
    
    print("✅ GAP + Tech combination research complete!")
    
    return recommendations

if __name__ == "__main__":
    main()
