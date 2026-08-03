#!/usr/bin/env python3
"""
Technical Indicator Calculations Module

This module calculates a variety of technical indicators for a given
DataFrame of stock data. It attempts to use TA-Lib for fast computations,
falling back to pandas_ta if TA-Lib is unavailable.

The calculated indicators include:
  - Moving Averages (SMA, EMA)
  - Momentum indicators (RSI, ROC, Williams %R)
  - MACD (and its signal and histogram)
  - Volatility (ATR)
  - Trend indicators (ADX with directional indicators)
  - Aroon Oscillator (Aroon Up and Down)
  - Chande Momentum Oscillator (CMO)
  - Money Flow Index (MFI)
  - On Balance Volume (OBV)
  - Volume Weighted Average Price (VWAP, manually computed)
  - Accumulation/Distribution Index (ADI)
  
Extensive logging is provided to trace computation time and any errors.
"""

import pandas as pd
import pandas_ta as ta
import numpy as np
import logging
import time

# Configure logging to output detailed information
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Attempt to import TA-Lib for accelerated indicator calculations.
try:
    import talib
    TALIB_AVAILABLE = True
    logger.info("TA-Lib available - using accelerated indicator calculations.")
except ImportError:
    TALIB_AVAILABLE = False
    logger.info("TA-Lib not available - using pandas_ta for calculations.")

def calculate_technical_indicators(df):
    """
    Calculate various technical indicators for a given DataFrame.

    Parameters:
        df (DataFrame): Must contain columns ['open', 'high', 'low', 'close', 'volume'].
    
    Returns:
        dict: A dictionary of calculated technical indicators, each as a Pandas Series.
    """
    start_time = time.time()
    import warnings
    warnings.filterwarnings('ignore')  # Suppress warnings from underlying libraries
    
    # Dictionary to store all indicator results
    indicators = {}

    # Ensure there is sufficient data to calculate indicators
    if df.shape[0] < 2:
        logger.warning("Not enough data to calculate indicators.")
        return indicators

    try:
        if TALIB_AVAILABLE:
            # Calculate Simple and Exponential Moving Averages
            indicators['sma'] = pd.Series(talib.SMA(df['close']), index=df.index)
            indicators['ema'] = pd.Series(talib.EMA(df['close']), index=df.index)
            logger.info("Calculated SMA and EMA using TA-Lib.")

            # Calculate RSI for momentum assessment
            indicators['rsi'] = pd.Series(talib.RSI(df['close']), index=df.index)
            logger.info("Calculated RSI using TA-Lib.")

            # Calculate MACD and its signal and histogram components
            macd, macd_signal, macd_hist = talib.MACD(df['close'])
            indicators['macd'] = pd.Series(macd, index=df.index)
            indicators['macd_signal'] = pd.Series(macd_signal, index=df.index)
            indicators['macd_hist'] = pd.Series(macd_hist, index=df.index)
            logger.info("Calculated MACD components using TA-Lib.")

            # Calculate ADX and directional indicators (PLUS_DI and MINUS_DI)
            indicators['adx'] = pd.Series(talib.ADX(df['high'], df['low'], df['close']), index=df.index)
            indicators['adx_pos'] = pd.Series(talib.PLUS_DI(df['high'], df['low'], df['close']), index=df.index)
            indicators['adx_neg'] = pd.Series(talib.MINUS_DI(df['high'], df['low'], df['close']), index=df.index)
            logger.info("Calculated ADX and directional indicators using TA-Lib.")

            # Calculate Commodity Channel Index (CCI)
            indicators['cci'] = pd.Series(talib.CCI(df['high'], df['low'], df['close']), index=df.index)
            logger.info("Calculated CCI using TA-Lib.")

            # Calculate Rate of Change (ROC)
            indicators['roc'] = pd.Series(talib.ROC(df['close']), index=df.index)
            logger.info("Calculated ROC using TA-Lib.")

            # Calculate Williams %R
            indicators['willr'] = pd.Series(talib.WILLR(df['high'], df['low'], df['close']), index=df.index)
            logger.info("Calculated Williams %R using TA-Lib.")

            # Calculate Average True Range (ATR) as a measure of volatility
            indicators['atr'] = pd.Series(talib.ATR(df['high'], df['low'], df['close']), index=df.index)
            logger.info("Calculated ATR using TA-Lib.")

            # Calculate Aroon Oscillator values: Up and Down
            aroon_down, aroon_up = talib.AROON(df['high'], df['low'])
            indicators['aroon_up'] = pd.Series(aroon_up, index=df.index)
            indicators['aroon_down'] = pd.Series(aroon_down, index=df.index)
            logger.info("Calculated Aroon indicators using TA-Lib.")

            # Calculate Chande Momentum Oscillator (CMO)
            indicators['cmo'] = pd.Series(talib.CMO(df['close']), index=df.index)
            logger.info("Calculated CMO using TA-Lib.")

            # Calculate Money Flow Index (MFI)
            indicators['mfi'] = pd.Series(talib.MFI(df['high'], df['low'], df['close'], df['volume']), index=df.index)
            logger.info("Calculated MFI using TA-Lib.")

            # Calculate On Balance Volume (OBV)
            indicators['obv'] = pd.Series(talib.OBV(df['close'], df['volume']), index=df.index)
            logger.info("Calculated OBV using TA-Lib.")

            # Manually compute VWAP (Volume Weighted Average Price)
            cum_vol = df['volume'].cumsum()
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            cum_vol_price = (df['volume'] * typical_price).cumsum()
            indicators['vwap'] = pd.Series(cum_vol_price / cum_vol, index=df.index)
            logger.info("Calculated VWAP manually.")

            # Calculate Accumulation/Distribution Index (ADI)
            ad = talib.AD(df['high'], df['low'], df['close'], df['volume'])
            indicators['adi'] = pd.Series(ad, index=df.index)
            logger.info("Calculated ADI using TA-Lib.")

            duration = time.time() - start_time
            logger.debug(f"TA-Lib based indicator calculations completed in {duration:.3f} seconds.")
        else:
            # Fallback using pandas_ta if TA-Lib is not available
            indicators['sma'] = ta.sma(df['close'])
            indicators['ema'] = ta.ema(df['close'])
            indicators['rsi'] = ta.rsi(df['close'])
            macd = ta.macd(df['close'])
            if macd is not None and isinstance(macd, pd.DataFrame):
                indicators['macd'] = macd.iloc[:, 0]
                indicators['macd_signal'] = macd.iloc[:, 1]
                indicators['macd_hist'] = macd.iloc[:, 2]
            adx = ta.adx(df['high'], df['low'], df['close'])
            if adx is not None and isinstance(adx, pd.DataFrame):
                indicators['adx'] = adx.iloc[:, 0]
                indicators['adx_pos'] = adx.iloc[:, 1]
                indicators['adx_neg'] = adx.iloc[:, 2]
            indicators['cci'] = ta.cci(df['high'], df['low'], df['close'])
            indicators['cmf'] = ta.cmf(df['high'], df['low'], df['close'], df['volume'])
            indicators['roc'] = ta.roc(df['close'])
            indicators['willr'] = ta.willr(df['high'], df['low'], df['close'])
            indicators['atr'] = ta.atr(df['high'], df['low'], df['close'])
            aroon = ta.aroon(df['high'], df['low'])
            if aroon is not None and isinstance(aroon, pd.DataFrame):
                indicators['aroon_up'] = aroon.iloc[:, 0]
                indicators['aroon_down'] = aroon.iloc[:, 1]
            indicators['cmo'] = ta.cmo(df['close'])
            indicators['mfi'] = ta.mfi(df['high'], df['low'], df['close'], df['volume'])
            indicators['adi'] = ta.ad(df['high'], df['low'], df['close'], df['volume'])
            indicators['vwap'] = ta.vwap(df['high'], df['low'], df['close'], df['volume'])
            duration = time.time() - start_time
            logger.debug(f"pandas_ta based indicator calculations completed in {duration:.3f} seconds.")
    except Exception as e:
        logger.error(f"Error calculating indicators: {e}")
    
    return indicators

def normalize_series(series):
    """
    Normalize a Pandas Series to the range [0, 1].
    
    Parameters:
        series (Series): The data series to normalize.
    
    Returns:
        Series: Normalized series.
    """
    min_val = series.min()
    max_val = series.max()
    if max_val == min_val:
        return series - min_val
    return (series - min_val) / (max_val - min_val)

def determine_signal(indicators, current_price, use_weights=True):
    """
    Determine a trading signal based on multiple technical indicators.

    Parameters:
        indicators (dict): Dictionary containing indicator series.
        current_price (float): The current asset price.
        use_weights (bool): Flag to use weighted combination of indicators.

    Returns:
        tuple: (signal, signal_strength) where signal is 'buy', 'sell', or 'hold'
               and signal_strength is a value between 0 and 1.
    """
    signals = {'buy': 0.0, 'sell': 0.0}
    
    # Default weights for each indicator
    weights = {
        'sma': 1.0, 'ema': 1.0, 'rsi': 1.0, 'macd': 1.0,
        'adx': 1.0, 'cci': 1.0, 'cmf': 1.0, 'roc': 1.0,
        'willr': 1.0, 'aroon': 1.0, 'cmo': 1.0, 'mfi': 1.0,
        'adi': 1.0, 'vwap': 1.0, 'atr': 1.0,
    }
    
    # Normalize series if applicable
    normalized_indicators = {}
    for key, val in indicators.items():
        if isinstance(val, pd.Series):
            normalized_indicators[key] = normalize_series(val)
        else:
            normalized_indicators[key] = val

    # Helper to rate an indicator
    def rate_indicator(indicator, condition, weight=1.0):
        if condition:
            return weight * normalized_indicators[indicator].iloc[-1]
        return 0

    # Evaluate each indicator condition
    if 'sma' in indicators:
        signals['buy'] += rate_indicator('sma', current_price > indicators['sma'].iloc[-1], weights['sma'])
        signals['sell'] += rate_indicator('sma', current_price <= indicators['sma'].iloc[-1], weights['sma'])
    
    if 'ema' in indicators:
        signals['buy'] += rate_indicator('ema', current_price > indicators['ema'].iloc[-1], weights['ema'])
        signals['sell'] += rate_indicator('ema', current_price <= indicators['ema'].iloc[-1], weights['ema'])
    
    if 'rsi' in indicators:
        signals['buy'] += rate_indicator('rsi', indicators['rsi'].iloc[-1] < 30, weights['rsi'])
        signals['sell'] += rate_indicator('rsi', indicators['rsi'].iloc[-1] > 70, weights['rsi'])
    
    if 'atr' in indicators:
        signals['buy'] += rate_indicator('atr', indicators['atr'].iloc[-1] < indicators['atr'].mean(), weights['atr'])
        signals['sell'] += rate_indicator('atr', indicators['atr'].iloc[-1] > indicators['atr'].mean(), weights['atr'])
    
    if all(k in indicators for k in ['macd', 'macd_signal']):
        signals['buy'] += rate_indicator('macd', indicators['macd'].iloc[-1] > indicators['macd_signal'].iloc[-1], weights['macd'])
        signals['sell'] += rate_indicator('macd', indicators['macd'].iloc[-1] <= indicators['macd_signal'].iloc[-1], weights['macd'])
    
    if all(k in indicators for k in ['adx', 'adx_pos', 'adx_neg']):
        signals['buy'] += rate_indicator('adx', 
                                         indicators['adx'].iloc[-1] > 25 and 
                                         indicators['adx_pos'].iloc[-1] > indicators['adx_neg'].iloc[-1], 
                                         weights['adx'])
        signals['sell'] += rate_indicator('adx', 
                                          indicators['adx'].iloc[-1] > 25 and 
                                          indicators['adx_pos'].iloc[-1] < indicators['adx_neg'].iloc[-1], 
                                          weights['adx'])
    
    if 'cci' in indicators:
        signals['buy'] += rate_indicator('cci', indicators['cci'].iloc[-1] < -100, weights['cci'])
        signals['sell'] += rate_indicator('cci', indicators['cci'].iloc[-1] > 100, weights['cci'])
    
    if 'cmf' in indicators:
        signals['buy'] += rate_indicator('cmf', indicators['cmf'].iloc[-1] > 0, weights['cmf'])
        signals['sell'] += rate_indicator('cmf', indicators['cmf'].iloc[-1] <= 0, weights['cmf'])
    
    if 'roc' in indicators:
        signals['buy'] += rate_indicator('roc', indicators['roc'].iloc[-1] > 0, weights['roc'])
        signals['sell'] += rate_indicator('roc', indicators['roc'].iloc[-1] <= 0, weights['roc'])
    
    if 'willr' in indicators:
        signals['buy'] += rate_indicator('willr', indicators['willr'].iloc[-1] < -80, weights['willr'])
        signals['sell'] += rate_indicator('willr', indicators['willr'].iloc[-1] > -20, weights['willr'])
    
    if all(k in indicators for k in ['aroon_up', 'aroon_down']):
        signals['buy'] += rate_indicator('aroon_up', indicators['aroon_up'].iloc[-1] > indicators['aroon_down'].iloc[-1], weights['aroon'])
        signals['sell'] += rate_indicator('aroon_down', indicators['aroon_up'].iloc[-1] <= indicators['aroon_down'].iloc[-1], weights['aroon'])
    
    if 'cmo' in indicators:
        signals['buy'] += rate_indicator('cmo', indicators['cmo'].iloc[-1] < -50, weights['cmo'])
        signals['sell'] += rate_indicator('cmo', indicators['cmo'].iloc[-1] > 50, weights['cmo'])
    
    if 'mfi' in indicators:
        signals['buy'] += rate_indicator('mfi', indicators['mfi'].iloc[-1] < 20, weights['mfi'])
        signals['sell'] += rate_indicator('mfi', indicators['mfi'].iloc[-1] > 80, weights['mfi'])
    
    if 'adi' in indicators:
        signals['buy'] += rate_indicator('adi', indicators['adi'].iloc[-1] > 0, weights['adi'])
        signals['sell'] += rate_indicator('adi', indicators['adi'].iloc[-1] <= 0, weights['adi'])
    
    if 'vwap' in indicators:
        signals['buy'] += rate_indicator('vwap', current_price > indicators['vwap'].iloc[-1], weights['vwap'])
        signals['sell'] += rate_indicator('vwap', current_price <= indicators['vwap'].iloc[-1], weights['vwap'])
    
    total = signals['buy'] + signals['sell']
    if total == 0:
        return 'hold', 0.0
    norm_buy = signals['buy'] / total
    norm_sell = signals['sell'] / total
    strength = max(norm_buy, norm_sell)
    
    if norm_buy > norm_sell:
        return 'buy', strength
    elif norm_sell > norm_buy:
        return 'sell', strength
    else:
        return 'hold', strength

if __name__ == "__main__":
    import yfinance as yf
    ticker = "BBCA.JK"
    print(f"Downloading data for {ticker}...")
    data = yf.download(ticker, start="2022-01-01", end="2023-01-01", interval="1d")
    print("Calculating indicators...")
    start_t = time.time()
    inds = calculate_technical_indicators(data)
    end_t = time.time()
    print(f"Indicator calculation took {end_t - start_t:.3f} seconds")
    print("Determining signal...")
    sig, strg = determine_signal(inds, data['Close'].iloc[-1])
    print(f"Signal for {ticker}: {sig} (strength: {strg:.2f})")
    print("\nKey indicator values:")
    for key in ['ema', 'rsi', 'macd', 'adx', 'cci', 'atr', 'vwap']:
        if key in inds:
            print(f"{key}: {inds[key].iloc[-1]:.2f}")