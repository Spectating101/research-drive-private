#!/usr/bin/env python3
"""
Multi-Market Historical Data Updater

This script updates stock data for multiple markets (e.g., Indonesia and Taiwan)
by fetching data from Yahoo Finance and storing it in a SQLite database.
It supports command-line options for market selection and statistics reporting.
"""

import argparse
import sqlite3
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta
import time
import random
import logging
from tqdm import tqdm
import os

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


class MultiMarketUpdater:
    def __init__(self, db_path='db/historical_data.db'):
        self.db_path = db_path
        self.end_date = datetime.now()
        # Define market configurations
        self.markets = {
            "indo": {
                "name": "Indonesia",
                "suffix": ".JK",
                "country_code": "indonesia"
            },
            "taiwan": {
                "name": "Taiwan",
                "suffix": ".TW",
                "country_code": "taiwan"
            }
        }
        # Ensure the database and table exist
        self.ensure_database()

    def ensure_database(self):
        """Ensure the SQLite database and the historical_data_daily table exist."""
        if not os.path.exists(os.path.dirname(self.db_path)):
            os.makedirs(os.path.dirname(self.db_path))
        conn = sqlite3.connect(self.db_path)
        try:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS historical_data_daily (
                    symbol TEXT,
                    timestamp TEXT,
                    open REAL,
                    high REAL,
                    low REAL,
                    close REAL,
                    volume REAL,
                    PRIMARY KEY (symbol, timestamp)
                )
            ''')
            conn.commit()
            logger.info("Database and table initialized at %s", self.db_path)
        except Exception as e:
            logger.error("Error initializing database: %s", e)
        finally:
            conn.close()

    def update_markets(self, market_codes=None):
        """Update specified markets; if none specified, update all."""
        if not market_codes:
            market_codes = list(self.markets.keys())

        total_results = {"updated": 0, "added": 0, "no_changes": 0, "failed": 0}

        for market_code in market_codes:
            if market_code not in self.markets:
                logger.warning("Unknown market code: %s", market_code)
                continue

            market_config = self.markets[market_code]
            market_name = market_config["name"]
            logger.info("Starting update for %s market", market_name)

            results = self.update_market(market_code, market_config)

            for key in total_results:
                total_results[key] += results.get(key, 0)

            # Pause briefly between markets to avoid rate limiting
            time.sleep(2)

        if len(market_codes) > 1:
            print("\nOverall Update Summary:")
            print(f"  Updated: {total_results['updated']} symbols")
            print(f"  Added new: {total_results['added']} symbols")
            print(f"  No changes needed: {total_results['no_changes']} symbols")
            print(f"  Failed: {total_results['failed']} symbols")

        return total_results

    def update_market(self, market_code, market_config):
        """Update all symbols for a specific market configuration."""
        market_name = market_config["name"]
        suffix = market_config["suffix"]
        logger.info("Processing %s Market (%s)", market_name, suffix)

        db_symbols = self.get_symbols_from_db(suffix)
        logger.info("Found %d existing symbols in database for %s", len(db_symbols), market_name)

        market_symbols = self.get_symbols_from_investpy(market_config["country_code"], suffix)
        logger.info("Found %d symbols from market source for %s", len(market_symbols), market_name)

        all_symbols = list(set(db_symbols + market_symbols))
        logger.info("Total unique symbols to process for %s: %d", market_name, len(all_symbols))

        results = {"updated": 0, "added": 0, "no_changes": 0, "failed": 0}

        for symbol in tqdm(all_symbols, desc=f"Processing {market_name} symbols"):
            is_new = symbol not in db_symbols
            if is_new:
                if self.add_new_symbol(symbol):
                    results["added"] += 1
                else:
                    results["failed"] += 1
            else:
                result = self.update_symbol(symbol)
                if result == "updated":
                    results["updated"] += 1
                elif result == "no_changes":
                    results["no_changes"] += 1
                else:
                    results["failed"] += 1
            time.sleep(random.uniform(0.5, 2.0))

        print(f"\n{market_name} Market Update Summary:")
        print(f"  Updated: {results['updated']} symbols")
        print(f"  Added new: {results['added']} symbols")
        print(f"  No changes needed: {results['no_changes']} symbols")
        print(f"  Failed: {results['failed']} symbols")
        return results

    def add_new_symbol(self, symbol):
        """Add a completely new symbol to the database using 5 years of history."""
        try:
            start_date = self.end_date - timedelta(days=365 * 5)
            logger.info("Adding new symbol: %s (5-year history)", symbol)
            ticker = yf.Ticker(symbol)
            data = ticker.history(start=start_date.strftime('%Y-%m-%d'), end=self.end_date.strftime('%Y-%m-%d'))
            if data.empty:
                logger.warning("No data available for new symbol: %s", symbol)
                return False
            rows_added = self.store_data(symbol, data)
            logger.info("Added new symbol %s with %d rows", symbol, rows_added)
            return rows_added > 0
        except Exception as e:
            logger.error("Error adding new symbol %s: %s", symbol, e)
            return False

    def update_symbol(self, symbol):
        """Update an existing symbol with new data from the day after its latest record."""
        max_retries = 3
        for attempt in range(max_retries):
            try:
                latest_date = self.get_latest_date(symbol)
                if not latest_date:
                    logger.warning("Symbol %s exists in DB but has no data; attempting to add new data.", symbol)
                    return "updated" if self.add_new_symbol(symbol) else "failed"

                start_date = latest_date + timedelta(days=1)
                if start_date >= self.end_date:
                    logger.info("Symbol %s already up to date (latest: %s)", symbol, latest_date.strftime('%Y-%m-%d'))
                    return "no_changes"

                logger.info("Updating %s from %s to %s", symbol, start_date.strftime('%Y-%m-%d'), self.end_date.strftime('%Y-%m-%d'))
                ticker = yf.Ticker(symbol)
                data = ticker.history(start=start_date.strftime('%Y-%m-%d'), end=self.end_date.strftime('%Y-%m-%d'))
                if data.empty:
                    logger.info("No new data for %s", symbol)
                    return "no_changes"

                rows_added = self.store_data(symbol, data)
                if rows_added > 0:
                    logger.info("Updated %s with %d new rows", symbol, rows_added)
                    return "updated"
                else:
                    logger.info("No new rows added for %s", symbol)
                    return "no_changes"
            except Exception as e:
                error_str = str(e).lower()
                if "404" in error_str or "not found" in error_str:
                    logger.warning("Symbol %s appears to be delisted or invalid: %s", symbol, e)
                    return "failed"
                else:
                    logger.error("Error updating %s (attempt %d/%d): %s", symbol, attempt+1, max_retries, e)
                    if attempt < max_retries - 1:
                        delay = 2 ** attempt
                        logger.info("Retrying in %d seconds...", delay)
                        time.sleep(delay)
        return "failed"

    def get_symbols_from_db(self, suffix):
        """Retrieve a list of symbols from the database that match a given suffix."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT DISTINCT symbol FROM historical_data_daily WHERE symbol LIKE ?", (f"%{suffix}",))
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logger.error("Error getting symbols from database: %s", e)
            return []

    def get_symbols_from_investpy(self, country_code, suffix):
        """Retrieve a list of symbols from Investpy for a given country."""
        try:
            import investpy
            stocks = investpy.stocks.get_stocks(country=country_code)
            symbols = []
            for sym in stocks['symbol'].tolist():
                clean_sym = sym.replace(suffix, '')
                symbols.append(f"{clean_sym}{suffix}")
            return symbols
        except Exception as e:
            logger.error("Error getting symbols from Investpy for %s: %s", country_code, e)
            return []

    def get_latest_date(self, symbol):
        """Return the latest date available in the database for a given symbol."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(timestamp) FROM historical_data_daily WHERE symbol = ?", (symbol,))
                latest_date_str = cursor.fetchone()[0]
                if latest_date_str:
                    return datetime.strptime(latest_date_str, '%Y-%m-%d')
                return None
        except Exception as e:
            logger.error("Error getting latest date for %s: %s", symbol, e)
            return None

    def store_data(self, symbol, data):
        """Insert historical data for a symbol into the database."""
        rows_added = 0
        if data.empty:
            return 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                data = data.reset_index()
                for _, row in data.iterrows():
                    try:
                        timestamp = row['Date'].strftime('%Y-%m-%d')
                        cursor.execute("""
                            INSERT OR REPLACE INTO historical_data_daily 
                            (symbol, timestamp, open, high, low, close, volume)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            symbol,
                            timestamp,
                            float(row['Open']),
                            float(row['High']),
                            float(row['Low']),
                            float(row['Close']),
                            float(row['Volume'])
                        ))
                        rows_added += 1
                    except Exception as inner_e:
                        logger.error("Error inserting row for %s: %s", symbol, inner_e)
                conn.commit()
            return rows_added
        except Exception as e:
            logger.error("Error storing data for %s: %s", symbol, e)
            return 0

    def print_market_stats(self, market_code=None):
        """Print overall database statistics and optionally market-specific stats."""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT COUNT(DISTINCT symbol) FROM historical_data_daily")
                total_symbols = cursor.fetchone()[0]
                cursor.execute("SELECT MIN(timestamp), MAX(timestamp) FROM historical_data_daily")
                min_date, max_date = cursor.fetchone()
                cursor.execute("SELECT COUNT(*) FROM historical_data_daily")
                total_rows = cursor.fetchone()[0]
                yesterday = (datetime.now() - timedelta(days=1)).strftime('%Y-%m-%d')
                cursor.execute(f"SELECT COUNT(DISTINCT symbol) FROM historical_data_daily WHERE timestamp >= '{yesterday}'")
                recent_symbols = cursor.fetchone()[0]
                print("\nOverall Database Statistics:")
                print(f"  Total symbols: {total_symbols}")
                print(f"  Date range: {min_date} to {max_date}")
                print(f"  Total rows: {total_rows}")
                print(f"  Symbols with yesterday's data: {recent_symbols}")
                if market_code:
                    if market_code not in self.markets:
                        print(f"Unknown market code: {market_code}")
                        return
                    market_configs = {market_code: self.markets[market_code]}
                else:
                    market_configs = self.markets
                for code, config in market_configs.items():
                    market_name = config["name"]
                    suffix = config["suffix"]
                    cursor.execute("SELECT COUNT(DISTINCT symbol) FROM historical_data_daily WHERE symbol LIKE ?", (f"%{suffix}",))
                    market_symbols = cursor.fetchone()[0]
                    cursor.execute(f"SELECT COUNT(DISTINCT symbol) FROM historical_data_daily WHERE symbol LIKE ? AND timestamp >= '{yesterday}'", (f"%{suffix}",))
                    market_recent = cursor.fetchone()[0]
                    print(f"\n{market_name} Market Statistics:")
                    print(f"  Total symbols: {market_symbols}")
                    print(f"  Symbols with yesterday's data: {market_recent}")
                    if market_symbols > 0:
                        cursor.execute("SELECT symbol FROM historical_data_daily WHERE symbol LIKE ? GROUP BY symbol LIMIT 5", (f"%{suffix}",))
                        sample_symbols = [row[0] for row in cursor.fetchall()]
                        print(f"  Sample symbols: {', '.join(sample_symbols)}")
        except Exception as e:
            logger.error("Error getting database stats: %s", e)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Update historical stock data")
    parser.add_argument("--market", choices=["indo", "taiwan", "all"], default="all", help="Select market to update (default: all)")
    parser.add_argument("--stats", action="store_true", help="Only show database statistics, do not update")
    parser.add_argument("--db", default="db/historical_data.db", help="Database file path (default: db/historical_data.db)")
    return parser.parse_args()

def main():
    args = parse_arguments()
    updater = MultiMarketUpdater(db_path=args.db)
    print("\nCurrent database status:")
    updater.print_market_stats()
    if args.stats:
        return
    if args.market == "all":
        markets_to_update = list(updater.markets.keys())
    else:
        markets_to_update = [args.market]
    print(f"\nStarting update for: {', '.join(markets_to_update)}")
    updater.update_markets(markets_to_update)
    print("\nUpdated database status:")
    updater.print_market_stats()

if __name__ == "__main__":
    main()