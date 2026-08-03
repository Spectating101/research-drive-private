#!/usr/bin/env python3
"""
Indicator Calculations Module

Provides functions to compute advanced indicator metrics using either TA-Lib
(if available) or fallback implementations. Optionally, performance-critical
calculations can be offloaded to a Rust module (via PyO3) if available.
"""

import pandas as pd
import numpy as np
import logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

try:
    import talib
    TALIB_AVAILABLE = True
except ImportError:
    TALIB_AVAILABLE = False

try:
    from rust import fast_indicators  # Assume a Rust module for fast computations exists
    RUST_AVAILABLE = True
except ImportError:
    RUST_AVAILABLE = False

def calculate_vwap(trades, window):
    df = pd.DataFrame([trade.split(",") for trade in trades],
                      columns=['timestamp', 'price', 'volume', 'direction'])
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    df['price'] = df['price'].astype(float)
    df['volume'] = df['volume'].astype(float)
    vwap = (df['price'] * df['volume']).rolling(window=f'{window}s').sum() / \
           df['volume'].rolling(window=f'{window}s').sum()
    logger.info("VWAP calculated: %s", vwap.iloc[-1])
    return vwap.iloc[-1]

def calculate_whale_ratio(trades, window):
    df = pd.DataFrame([trade.split(",") for trade in trades],
                      columns=['timestamp', 'price', 'volume', 'direction'])
    df['price'] = df['price'].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    ohlc = df['price'].resample(f'{window}s').ohlc()
    ohlc['gain'] = ohlc['close'] > ohlc['open']
    ohlc['whale_ratio'] = np.where(ohlc['gain'],
                                   (ohlc['high'] / ohlc['close']) / (ohlc['open'] / ohlc['low']),
                                   (ohlc['high'] / ohlc['close']) / (ohlc['close'] / ohlc['low']))
    logger.info("Whale ratio calculated: %s", ohlc['whale_ratio'].iloc[-1])
    return ohlc['whale_ratio'].iloc[-1]

def calculate_volume_momentum(trades, window):
    df = pd.DataFrame([trade.split(",") for trade in trades],
                      columns=['timestamp', 'price', 'volume', 'direction'])
    df['price'] = df['price'].astype(float)
    df['volume'] = df['volume'].astype(float)
    if TALIB_AVAILABLE:
        obv = talib.OBV(df['price'].values, df['volume'].values)
    else:
        obv = np.cumsum(df['volume'].values)
    if len(obv) > window:
        momentum = obv[-1] - obv[-window]
    else:
        momentum = 0
    logger.info("Volume momentum calculated: %s", momentum)
    return momentum

def calculate_orderbook_imbalance(orderbook):
    if not orderbook:
        return None
    bids = orderbook.get('bids', '').split("\n")
    asks = orderbook.get('asks', '').split("\n")
    total_bid = np.sum([float(b.split(",")[1]) for b in bids if b])
    total_ask = np.sum([float(a.split(",")[1]) for a in asks if a])
    imbalance = (total_bid - total_ask) / (total_bid + total_ask)
    logger.info("Orderbook imbalance calculated: %s", imbalance)
    return imbalance

def calculate_whale_index(trades, window, top_n=10):
    df = pd.DataFrame([trade.split(",") for trade in trades],
                      columns=['timestamp', 'price', 'volume', 'direction'])
    df['volume'] = df['volume'].astype(float)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df.set_index('timestamp', inplace=True)
    vol_sum = df['volume'].resample(f'{window}s').sum()
    top_volume = vol_sum.nlargest(top_n).sum()
    total_volume = vol_sum.sum()
    index_val = top_volume / total_volume
    logger.info("Whale index calculated: %s", index_val)
    return index_val

def calculate_buy_signal_score(volume_momentum, orderbook_imbalance, whale_index, whale_ratio, vwap):
    norm_vm = (volume_momentum + 1) / 2
    norm_ob = (orderbook_imbalance + 1) / 2 if orderbook_imbalance is not None else 0
    norm_wi = whale_index if whale_index is not None else 0
    norm_wr = (whale_ratio + 1) / 2 if whale_ratio is not None else 0
    norm_vwap = (vwap + 1) / 2 if vwap is not None else 0
    weights = [0.2, 0.2 if orderbook_imbalance is not None else 0, 0.2 if whale_index is not None else 0, 0.2, 0.2]
    total_weight = sum(weights)
    weights = [w / total_weight for w in weights]
    score = weights[0]*norm_vm + weights[1]*norm_ob + weights[2]*norm_wi + weights[3]*norm_wr + weights[4]*norm_vwap
    logger.info("Buy signal score calculated: %s", score)
    return score
