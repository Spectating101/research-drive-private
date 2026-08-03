import pandas as pd
import numpy as np
import os
import logging
from typing import Dict, Optional, Union
import sys

# Add root to path to find config
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))
try:
    from config.settings import settings
    DATA_DIR = str(settings.DATA_LAKE_DIR)
except ImportError:
    DATA_DIR = "data_lake" # Fallback

logger = logging.getLogger(__name__)

class DataLoader:
    """
    Unified Data Loader for Sharpe-Renaissance.
    Bridges the gap between Raw Data (API/Parquet) and the Trading Engine.
    """
    
    def __init__(self, data_dir: str = DATA_DIR):
        self.data_dir = data_dir
        logger.info(f"DataLoader initialized on: {self.data_dir}")
        
    def load_market_data(self, ticker: str, source: str = "refinitiv") -> Optional[pd.DataFrame]:
        """
        Loads OHLCV data for a ticker from the data lake.
        Supports: parquet, csv
        """
        # Try Parquet first (Fastest)
        parquet_path = os.path.join(self.data_dir, "market_data", f"{ticker}.parquet")
        csv_path = os.path.join(self.data_dir, "market_data", f"{ticker}.csv")
        
        df = None
        if os.path.exists(parquet_path):
            df = pd.read_parquet(parquet_path)
        elif os.path.exists(csv_path):
            df = pd.read_csv(csv_path)
            
        if df is None:
            logger.warning(f"No market data found for {ticker} in {self.data_dir}")
            return None
            
        return self._normalize_market_columns(df)

    def load_fundamentals(self, ticker: str) -> Optional[pd.DataFrame]:
        """
        Loads Fundamental data (Balance Sheet, Income Statement).
        """
        path = os.path.join(self.data_dir, "fundamentals", f"{ticker}.parquet")
        if os.path.exists(path):
            return pd.read_parquet(path)
        
        logger.warning(f"No fundamental data found for {ticker}")
        return None

    def _normalize_market_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardizes column names to: timestamp, open, high, low, close, volume
        """
        df.columns = df.columns.str.lower().str.strip()
        
        # Mapping common variations
        mappings = {
            'date': 'timestamp',
            'time': 'timestamp',
            'price': 'close',
            'last': 'close',
            'vol': 'volume',
            'turnover': 'volume'
        }
        
        df.rename(columns=mappings, inplace=True)
        
        # Ensure timestamp index
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df.set_index('timestamp', inplace=True)
            
        # Ensure required columns exist
        required = ['open', 'high', 'low', 'close', 'volume']
        missing = [c for c in required if c not in df.columns]
        
        if missing:
            # If missing Open/High/Low, derive from Close if possible (Approximation)
            if 'close' in df.columns:
                if 'open' in missing: df['open'] = df['close']
                if 'high' in missing: df['high'] = df['close']
                if 'low' in missing: df['low'] = df['close']
            else:
                logger.error(f"Critical columns missing: {missing}")
                return df
                
        return df[required] # Return cleaned frame

    def save_market_data(self, df: pd.DataFrame, ticker: str):
        """Saves processed data back to the lake."""
        out_dir = os.path.join(self.data_dir, "market_data")
        os.makedirs(out_dir, exist_ok=True)
        df.to_parquet(os.path.join(out_dir, f"{ticker}.parquet"))
        logger.info(f"Saved {ticker} to {out_dir}")