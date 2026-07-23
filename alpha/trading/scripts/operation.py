#!/usr/bin/env python3
"""
Comprehensive Daily Operation Script for Trading System

This script performs the following:
  • Asynchronously updates historical data for a list of symbols.
  • Detects the current market regime.
  • Generates trading picks and optimizes portfolio allocation.
  • Runs strategy analysis/backtesting.
  • Optionally publishes results to Discord.
  • Can run once or in a scheduled loop.
"""

import sys
import os
import asyncio
import logging
import time
import random
import argparse
import json
from datetime import datetime, timedelta
import sqlite3
import yfinance as yf

# Configuration
DB_PATH = 'db/historical_data.db'
OP_DB_PATH = 'db/operation.db'
STRATEGY_CSV = 'config/Caveman - Sheet11.csv'
SCHEDULE_TIME = "16:00"  # 24-hr format (e.g., 16:00)
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")
DISCORD_CHANNEL_ID = os.getenv("DISCORD_CHANNEL_ID")  # Must be set in environment

# Setup logging
logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    handlers=[logging.StreamHandler()])
logger = logging.getLogger(__name__)

# Ensure src directory is in sys.path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from src.data.historical_updater import HistoricalDataUpdater
from src.ml.regime_detector import RegimeDetector
from src.core.portfolio_optimizer import PortfolioOptimizer
from src.core.strategy_analyzer import StrategyAnalyzer

# Optional: Discord integration
try:
    import discord
    from discord.ext import commands
    DISCORD_AVAILABLE = True
except ImportError:
    DISCORD_AVAILABLE = False

async def publish_to_discord(message):
    if not DISCORD_AVAILABLE or not DISCORD_TOKEN or not DISCORD_CHANNEL_ID:
        logger.warning("Discord not configured properly. Skipping Discord publishing.")
        return
    client = discord.Client(intents=discord.Intents.default())
    @client.event
    async def on_ready():
        try:
            channel = client.get_channel(int(DISCORD_CHANNEL_ID))
            if channel:
                await channel.send(message)
                logger.info("Published message to Discord.")
            else:
                logger.error("Discord channel not found.")
        except Exception as e:
            logger.error("Error publishing to Discord: %s", e)
        finally:
            await client.close()
    try:
        await client.start(DISCORD_TOKEN)
    except Exception as e:
        logger.error("Error starting Discord client: %s", e)

async def async_update_data(symbols):
    updater = HistoricalDataUpdater(db_path=DB_PATH)
    try:
        await updater.update_all(symbols)
    except Exception as e:
        logger.error("Error in asynchronous data update: %s", e)

def run_historical_update():
    symbols = ["BBCA", "TLKM", "ASII"]
    try:
        asyncio.run(async_update_data(symbols))
    except Exception as e:
        logger.error("Historical update failed: %s", e)

def detect_market_regime():
    rd = RegimeDetector(db_path=DB_PATH)
    regime = rd.get_regime(market_code='indo', lookback=90)
    logger.info("Market regime detected: %s", regime)
    return regime

def generate_trading_picks():
    # Replace with your actual signal generation logic; this is a placeholder.
    picks = {
        "win_rate": {
            "symbol": "BBCA.JK",
            "current_close": 9000,
            "avg_gain": 5.0,
            "avg_loss": -3.0
        },
        "reward/risk": {
            "symbol": "TLKM.JK",
            "current_close": 4000,
            "avg_gain": 7.0,
            "avg_loss": -4.0
        }
    }
    logger.info("Generated dummy trading picks.")
    return picks

def optimize_portfolio(picks, regime):
    optimizer = PortfolioOptimizer(db_path=DB_PATH, lookback_days=90)
    optimized = optimizer.optimize_allocation(picks, regime)
    logger.info("Portfolio optimization completed.")
    return optimized

def analyze_strategies():
    analyzer = StrategyAnalyzer(hist_db=DB_PATH, strategy_csv=STRATEGY_CSV)
    performance = analyzer.analyze_strategy("ema,rsi,vwap", num_samples=10)
    logger.info("Strategy analysis metrics: %s", json.dumps(performance['metrics']))
    return performance

def build_discord_message(regime, picks, performance):
    msg = f"Daily Operation Completed on {datetime.now().strftime('%Y-%m-%d')}\n"
    msg += f"Market Regime: {regime}\n"
    msg += "Optimized Picks:\n"
    for cat, pick in picks.items():
        msg += f"  {cat}: {pick['symbol']} | Current: {pick['current_close']} | Allocation: {pick.get('allocation_pct', 0):.2f}%\n"
    msg += "Strategy Performance Metrics:\n"
    for k, v in performance['metrics'].items():
        msg += f"  {k}: {v}\n"
    return msg

def run_daily_operation():
    logger.info("=== Daily Operation Start ===")
    run_historical_update()
    regime = detect_market_regime()
    picks = generate_trading_picks()
    picks = optimize_portfolio(picks, regime)
    performance = analyze_strategies()
    msg = build_discord_message(regime, picks, performance)
    logger.info("Daily Operation Summary:\n%s", msg)
    print(msg)
    if DISCORD_AVAILABLE and DISCORD_TOKEN and DISCORD_CHANNEL_ID:
        try:
            asyncio.run(publish_to_discord(msg))
        except Exception as e:
            logger.error("Discord publishing failed: %s", e)
    logger.info("=== Daily Operation Complete ===")

def schedule_loop():
    logger.info("Entering scheduled operation loop.")
    while True:
        now = datetime.now()
        if now.strftime("%H:%M") == SCHEDULE_TIME:
            logger.info("Scheduled time reached (%s). Running operation.", SCHEDULE_TIME)
            run_daily_operation()
            time.sleep(61)  # Avoid duplicate runs in the same minute
        else:
            time.sleep(30)

def parse_arguments():
    parser = argparse.ArgumentParser(description="Trading System Daily Operation")
    parser.add_argument("--schedule", action="store_true", help="Run in scheduled mode (loop until termination)")
    parser.add_argument("--once", action="store_true", help="Run the daily operation once and exit")
    return parser.parse_args()

def main():
    args = parse_arguments()
    if args.schedule:
        schedule_loop()
    else:
        run_daily_operation()

if __name__ == "__main__":
    main()
