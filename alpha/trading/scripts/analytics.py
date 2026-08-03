#!/usr/bin/env python3
"""
Consolidated Analytics Module

This module performs the following steps:
  1. Loads raw benchmark test data from the benchmark_test_results table.
  2. For each benchmark entry, calculates 10-day candlestick metrics based on historical_data.db.
  3. Computes price performance metrics (percentage changes, win/loss classification).
  4. Groups trades by indicator and analyzes performance bands.
  5. Computes overall summary statistics.
  6. Saves various CSV reports with the results.

Adjust sample sizes or thresholds as needed.
"""

import sqlite3
import pandas as pd
import numpy as np
import json
from tqdm import tqdm
from datetime import datetime

# --------------------------
# Utility Function: Candlestick Totals
# --------------------------
def get_candlestick_totals(symbol, start_timestamp, historical_conn):
    """
    Given a symbol and a start timestamp, fetch the next 10 days of data 
    from historical_data_daily and compute candlestick metrics.
    """
    # Format the symbol to include the .JK suffix
    adjusted_symbol = f"{symbol}.JK"
    historical_query = f"""
    SELECT timestamp, open, high, low, close
    FROM historical_data_daily
    WHERE symbol = '{adjusted_symbol}' AND timestamp > '{start_timestamp}'
    ORDER BY timestamp
    LIMIT 10
    """
    historical_data = pd.read_sql_query(historical_query, historical_conn)
    if historical_data.empty:
        return None
    return {
        'open': historical_data.iloc[0]['open'],
        'close': historical_data.iloc[-1]['close'],
        'high': historical_data['high'].max(),
        'low': historical_data['low'].min(),
        'avg_high': historical_data['high'].mean(),
        'avg_low': historical_data['low'].mean(),
        'avg_close': historical_data['close'].mean()
    }

# --------------------------
# Consolidated Analytics Class
# --------------------------
class StructuredAnalytics:
    def __init__(self, benchmark_db='benchmark_result_final.db', historical_db='historical_data.db'):
        self.benchmark_db = benchmark_db
        self.historical_db = historical_db

    def get_raw_benchmark_data(self):
        """Load raw benchmark test data from the benchmark_test_results table."""
        conn = sqlite3.connect(self.benchmark_db)
        query = """
        SELECT id, timestamp, symbol, indicators, synergy
        FROM benchmark_test_results
        """
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df

    def get_latest_available_before(self, conn, symbol, target_date):
        """
        Returns the latest available timestamp (as a string) in historical_data_daily 
        for a given symbol that is <= target_date.
        """
        cursor = conn.cursor()
        # First try the given symbol
        cursor.execute("""
            SELECT MIN(timestamp), MAX(timestamp)
            FROM historical_data_daily 
            WHERE symbol = ?
        """, (symbol,))
        date_range = cursor.fetchone()
        if date_range[0] is None:
            # Try without the .JK suffix
            symbol_alt = symbol.replace('.JK', '')
            cursor.execute("""
                SELECT MIN(timestamp), MAX(timestamp)
                FROM historical_data_daily 
                WHERE symbol = ?
            """, (symbol_alt,))
            date_range = cursor.fetchone()
            if date_range[0] is not None:
                symbol = symbol_alt
        if date_range[0] is None:
            return None
        cursor.execute("""
            SELECT timestamp 
            FROM historical_data_daily 
            WHERE symbol = ? AND timestamp <= ?
            ORDER BY timestamp DESC
            LIMIT 1
        """, (symbol, target_date))
        result = cursor.fetchone()
        return result[0] if result else None

    def get_price_performance(self, benchmark_data):
        """
        For each benchmark entry (top signal per date and indicator combination),
        compute performance metrics over the next 10 days.
        """
        results = []
        skipped = []
        conn = sqlite3.connect(self.historical_db)
        cursor = conn.cursor()
        
        # Build a lookup of available symbols and their date ranges
        cursor.execute("""
            SELECT symbol, MIN(timestamp) as min_date, MAX(timestamp) as max_date
            FROM historical_data_daily
            GROUP BY symbol
        """)
        symbol_data = cursor.fetchall()
        available_symbols = {}
        for symbol, min_date, max_date in symbol_data:
            available_symbols[symbol] = {'min': min_date, 'max': max_date}
            if symbol.endswith('.JK'):
                symbol_alt = symbol[:-3]
                available_symbols[symbol_alt] = {'min': min_date, 'max': max_date}
        
        print(f"\nFound {len(symbol_data)} unique symbols in historical data")
        print("Sample symbols:", list(available_symbols.keys())[:5])
        
        # Ensure index exists to speed up queries
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_symbol_timestamp ON historical_data_daily(symbol, timestamp)")
        conn.commit()
        
        # Group by timestamp and indicator combination; select top signal per group (using highest synergy)
        benchmark_df = pd.DataFrame(benchmark_data)
        grouped = benchmark_df.groupby(['timestamp', 'indicators'])
        top_signals = []
        for (date, indicator), group in grouped:
            top = group.nlargest(1, 'synergy')
            top_signals.extend(top.to_dict('records'))
        
        # Process each top signal
        for row in tqdm(top_signals, desc="Processing price data"):
            try:
                symbol_full = f"{row['symbol']}.JK"
                symbol_plain = row['symbol']
                original_date = row['timestamp']
                
                if symbol_full in available_symbols:
                    actual_symbol = symbol_full
                    date_range = available_symbols[symbol_full]
                elif symbol_plain in available_symbols:
                    actual_symbol = symbol_plain
                    date_range = available_symbols[symbol_plain]
                else:
                    skipped.append({'symbol': row['symbol'], 'timestamp': original_date, 'reason': 'Symbol not found'})
                    continue
                
                if original_date < date_range['min']:
                    skipped.append({'symbol': row['symbol'], 'timestamp': original_date, 'reason': 'Date before available data'})
                    continue

                historical_query = """
                WITH latest_date AS (
                    SELECT MAX(timestamp) as avail_date
                    FROM historical_data_daily
                    WHERE symbol = ? AND timestamp <= ?
                )
                SELECT h.timestamp, h.open, h.high, h.low, h.close
                FROM historical_data_daily h, latest_date l
                WHERE h.symbol = ? AND h.timestamp >= l.avail_date
                ORDER BY h.timestamp
                LIMIT 10
                """
                hist_data = pd.read_sql_query(historical_query, conn, params=(actual_symbol, original_date, actual_symbol))
                
                if len(hist_data) < 10:
                    skipped.append({'symbol': row['symbol'], 'timestamp': original_date, 'found_bars': len(hist_data),
                                     'reason': f'Insufficient bars (found {len(hist_data)})'})
                    continue
                
                for col in ["open", "high", "low", "close"]:
                    hist_data[col] = pd.to_numeric(hist_data[col], errors="coerce")
                hist_data.dropna(subset=["open", "high", "low", "close"], inplace=True)
                if hist_data.empty:
                    skipped.append({'symbol': row['symbol'], 'timestamp': original_date, 'reason': 'No valid price data'})
                    continue

                first_bar = hist_data.iloc[0]
                last_bar = hist_data.iloc[-1]
                metrics = {
                    "id": row["id"],
                    "symbol": row["symbol"],
                    "timestamp": first_bar["timestamp"],
                    "indicator": row["indicators"],
                    "ind_value": row["synergy"],
                    "open": first_bar["open"],
                    "close": last_bar["close"],
                    "high": hist_data["high"].max(),
                    "low": hist_data["low"].min(),
                    "avg_high": hist_data["high"].mean(),
                    "avg_low": hist_data["low"].mean(),
                    "avg_close": hist_data["close"].mean(),
                    "days_to_peak": hist_data["high"].idxmax() + 1,  # index position as proxy
                    "bars_found": len(hist_data)
                }
                results.append(metrics)
            except Exception as e:
                skipped.append({'symbol': row['symbol'], 'timestamp': original_date, 'reason': f'Error: {str(e)}'})
                continue
        
        conn.close()
        if skipped:
            skip_df = pd.DataFrame(skipped)
            skip_df.to_csv('skipped_records.csv', index=False)
            print(f"\nSkipped {len(skipped)} records. Details saved to 'skipped_records.csv'")
            print("\nSkip reasons summary:")
            print(skip_df['reason'].value_counts())
        return pd.DataFrame(results)
        
    def calculate_performance_metrics(self, price_data):
        """Calculate percentage changes and classify trades as Win or Loss."""
        if price_data.empty:
            return price_data
        
        metrics = price_data.copy()
        if "open" in metrics.columns and "close" in metrics.columns:
            metrics["change%"] = ((metrics["close"] - metrics["open"]) / metrics["open"] * 100)
            metrics["high%"] = ((metrics["high"] - metrics["open"]) / metrics["open"] * 100)
            metrics["low%"] = ((metrics["low"] - metrics["open"]) / metrics["open"] * 100)
            metrics["avg_high%"] = ((metrics["avg_high"] - metrics["open"]) / metrics["open"] * 100)
            metrics["avg_low%"] = ((metrics["avg_low"] - metrics["open"]) / metrics["open"] * 100)
            metrics["avg_close%"] = ((metrics["avg_close"] - metrics["open"]) / metrics["open"] * 100)
            metrics["result"] = metrics["change%"].apply(lambda x: "Win" if x > 0 else "Loss")
        else:
            for col in ["change%", "high%", "low%", "avg_high%", "avg_low%", "avg_close%", "result"]:
                metrics[col] = np.nan
        return metrics
        
    def group_trades(self, performance_data):
        """Group trades by indicator and summarize performance statistics."""
        if performance_data.empty or "indicator" not in performance_data.columns:
            return pd.DataFrame(), pd.DataFrame()
        
        winning = performance_data[performance_data["result"] == "Win"]
        losing = performance_data[performance_data["result"] == "Loss"]
        
        def process_group(data):
            rows = []
            for ind_val in data["indicator"].unique():
                sub = data[data["indicator"] == ind_val]
                rows.append({
                    "indicator": ind_val,
                    "ind_value": sub["ind_value"].mean(),
                    "change%": sub["change%"].mean(),
                    "high%": sub["high%"].mean(),
                    "low%": sub["low%"].mean(),
                    "days_to_peak": sub["days_to_peak"].mean(),
                    "count": len(sub),
                    "avg_bars": sub["bars_found"].mean()
                })
            return pd.DataFrame(rows)
        
        return process_group(winning), process_group(losing)
        
    def analyze_value_bands(self, performance_data):
        """Analyze performance in different synergy value bands using quantiles."""
        if performance_data.empty or "indicator" not in performance_data.columns:
            return pd.DataFrame()
        
        bands = []
        for ind_val in performance_data["indicator"].unique():
            sub = performance_data[performance_data["indicator"] == ind_val].copy()
            if len(sub) < 3:
                continue
            try:
                sub["ind_value_float"] = pd.to_numeric(sub["ind_value"], errors="coerce")
                sub = sub[sub["ind_value_float"].notna()]
                qcuts = pd.qcut(sub["ind_value_float"], 3)
                for rng in qcuts.unique():
                    rng_sub = sub[qcuts == rng]
                    if rng_sub.empty:
                        continue
                    wins = rng_sub["result"] == "Win"
                    win_rate = wins.sum() / len(rng_sub) if len(rng_sub) else 0
                    bands.append({
                        "indicator": ind_val,
                        "value_range": f"{rng.left:.2f}-{rng.right:.2f}",
                        "win_rate": win_rate * 100,
                        "avg_gain": rng_sub[wins]["change%"].mean(),
                        "avg_loss": rng_sub[~wins]["change%"].mean(),
                        "sample_size": len(rng_sub),
                        "avg_bars": rng_sub["bars_found"].mean(),
                        "characterization": self.get_characterization(win_rate)
                    })
            except Exception as e:
                print(f"Error processing {ind_val}: {e}")
                continue
        return pd.DataFrame(bands)
        
    def get_characterization(self, win_rate):
        """Return a qualitative description based on win rate."""
        if win_rate >= 0.7:
            return "Optimal Zone"
        elif win_rate >= 0.5:
            return "Neutral Zone"
        else:
            return "High Risk Zone"
            
    def calculate_summary_stats(self, performance_data):
        """Calculate overall summary statistics for each indicator."""
        if performance_data.empty or "indicator" not in performance_data.columns:
            return pd.DataFrame()
        
        summary = []
        for ind_val in performance_data["indicator"].unique():
            sub = performance_data[performance_data["indicator"] == ind_val]
            if sub.empty:
                continue
            wins = sub["result"] == "Win"
            total_trades = len(sub)
            if total_trades == 0:
                continue
            win_rate = wins.sum() / total_trades * 100
            avg_gain = sub[wins]["change%"].mean()
            avg_loss = sub[~wins]["change%"].mean()
            rr = abs(avg_gain / avg_loss) if avg_loss not in [None, 0] and not np.isnan(avg_loss) else 0
            exp = (win_rate/100.0 * avg_gain + (1 - win_rate/100.0) * avg_loss) if not np.isnan(win_rate) else 0
            summary.append({
                "indicator": ind_val,
                "total_trades": total_trades,
                "win_rate": win_rate,
                "avg_gain": avg_gain,
                "avg_loss": avg_loss,
                "reward_risk": rr,
                "exp_value": exp,
                "avg_bars": sub["bars_found"].mean()
            })
        return pd.DataFrame(summary)

    def run_analysis(self):
        """Run the complete analysis pipeline and save outputs to CSV."""
        # Step 1: Load raw benchmark data and save as CSV
        benchmark_data = self.get_raw_benchmark_data()
        benchmark_data.to_csv('table1_raw_benchmark.csv', index=False)
        
        # Step 2: Compute price performance metrics
        price_data = self.get_price_performance(benchmark_data)
        if price_data.empty:
            print("No valid price_data rows after processing. Exiting.")
            return
        price_data.to_csv('table2_price_performance.csv', index=False)
        
        # Step 3: Calculate performance percentage changes and classify trades
        performance_metrics = self.calculate_performance_metrics(price_data)
        if performance_metrics.empty:
            print("No performance metrics to analyze. Exiting.")
            return
        performance_metrics.to_csv('table3_performance_metrics.csv', index=False)
        
        # Step 4: Group trades by indicator (winning and losing)
        winning_analysis, losing_analysis = self.group_trades(performance_metrics)
        winning_analysis.to_csv('table4a_winning_trades.csv', index=False)
        losing_analysis.to_csv('table4b_losing_trades.csv', index=False)
        
        # Step 5: Analyze performance in different synergy value bands
        value_bands = self.analyze_value_bands(performance_metrics)
        value_bands.to_csv('table5_value_bands.csv', index=False)
        
        # Step 6: Calculate overall summary statistics
        summary_stats = self.calculate_summary_stats(performance_metrics)
        summary_stats.to_csv('table6_summary_stats.csv', index=False)
        
        return {
            'benchmark_data': benchmark_data,
            'price_data': price_data,
            'performance_metrics': performance_metrics,
            'winning_analysis': winning_analysis,
            'losing_analysis': losing_analysis,
            'value_bands': value_bands,
            'summary_stats': summary_stats
        }

def main():
    analyzer = StructuredAnalytics()
    results = analyzer.run_analysis()
    if results is None:
        print("Analysis failed - no valid data to process.")
    else:
        print("\nAnalysis complete. Files generated:")
        print("- table1_raw_benchmark.csv")
        print("- table2_price_performance.csv")
        print("- table3_performance_metrics.csv")
        print("- table4a_winning_trades.csv")
        print("- table4b_losing_trades.csv")
        print("- table5_value_bands.csv")
        print("- table6_summary_stats.csv")
        print("- skipped_records.csv (if any records were skipped)")

if __name__ == "__main__":
    main()
