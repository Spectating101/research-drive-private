use ndarray::{Array1, Array2, ArrayView1, s};
use rayon::prelude::*;
use std::collections::HashMap;
use crate::error::SharpeError;

#[derive(Debug, Clone)]
pub struct MacdResult {
    pub macd: Array1<f64>,
    pub signal: Array1<f64>,
    pub histogram: Array1<f64>,
}

#[derive(Debug, Clone)]
pub struct BollingerBandsResult {
    pub upper: Array1<f64>,
    pub middle: Array1<f64>,
    pub lower: Array1<f64>,
}

pub fn calculate_all_indicators_parallel(
    prices: &Array2<f64>,
    volumes: &Array1<f64>,
) -> Result<HashMap<String, Array1<f64>>, SharpeError> {
    let mut indicators = HashMap::new();
    
    // Extract OHLC data
    let _opens = prices.column(0);
    let highs = prices.column(1);
    let lows = prices.column(2);
    let closes = prices.column(3);
    let volumes = volumes.view();
    
    // Calculate indicators in parallel
    let results: Vec<_> = vec![
        ("ema_5", calculate_ema(closes, 5)),
        ("ema_10", calculate_ema(closes, 10)),
        ("ema_20", calculate_ema(closes, 20)),
        ("ema_50", calculate_ema(closes, 50)),
        ("rsi_14", calculate_rsi(closes, 14)),
        ("rsi_21", calculate_rsi(closes, 21)),
        ("sma_20", calculate_sma(closes, 20)),
        ("sma_50", calculate_sma(closes, 50)),
        ("atr_14", calculate_atr(highs, lows, closes, 14)),
        ("volume_sma", calculate_sma(volumes, 20)),
    ].into_par_iter().collect();
    
    for (name, result) in results {
        indicators.insert(name.to_string(), result?);
    }
    
    // Calculate MACD
    let macd_result = calculate_macd(closes, 12, 26, 9)?;
    indicators.insert("macd".to_string(), macd_result.macd);
    indicators.insert("macd_signal".to_string(), macd_result.signal);
    indicators.insert("macd_histogram".to_string(), macd_result.histogram);
    
    // Calculate Bollinger Bands
    let bb_result = calculate_bollinger_bands(closes, 20, 2.0)?;
    indicators.insert("bb_upper".to_string(), bb_result.upper);
    indicators.insert("bb_middle".to_string(), bb_result.middle);
    indicators.insert("bb_lower".to_string(), bb_result.lower);
    
    // Calculate additional features
    indicators.insert("price_position".to_string(), calculate_price_position(highs, lows, closes)?);
    indicators.insert("volume_ratio".to_string(), calculate_volume_ratio(volumes, 20)?);
    indicators.insert("volatility_20".to_string(), calculate_volatility(closes, 20)?);
    
    Ok(indicators)
}

pub fn calculate_ema(prices: ArrayView1<f64>, period: usize) -> Result<Array1<f64>, SharpeError> {
    if prices.len() < period {
        return Err(SharpeError::InsufficientData);
    }
    
    let alpha = 2.0 / (period as f64 + 1.0);
    let mut ema = Array1::zeros(prices.len());
    
    // Initialize with SMA
    let initial_sma = prices.slice(s![..period]).sum() / period as f64;
    ema[0] = initial_sma;
    
    // Calculate EMA
    for i in 1..prices.len() {
        ema[i] = alpha * prices[i] + (1.0 - alpha) * ema[i - 1];
    }
    
    Ok(ema)
}

pub fn calculate_sma(prices: ArrayView1<f64>, period: usize) -> Result<Array1<f64>, SharpeError> {
    if prices.len() < period {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut sma = Array1::zeros(prices.len());
    
    // Calculate rolling SMA
    for i in period - 1..prices.len() {
        let sum: f64 = prices.slice(s![i - period + 1..=i]).sum();
        sma[i] = sum / period as f64;
    }
    
    Ok(sma)
}

pub fn calculate_rsi(prices: ArrayView1<f64>, period: usize) -> Result<Array1<f64>, SharpeError> {
    if prices.len() < period + 1 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut rsi = Array1::zeros(prices.len());
    let mut gains = Array1::zeros(prices.len());
    let mut losses = Array1::zeros(prices.len());
    
    // Calculate price changes
    for i in 1..prices.len() {
        let change = prices[i] - prices[i - 1];
        if change > 0.0 {
            gains[i] = change;
        } else {
            losses[i] = -change;
        }
    }
    
    // Calculate initial averages
    let initial_gain = gains.slice(s![1..=period]).sum() / period as f64;
    let initial_loss = losses.slice(s![1..=period]).sum() / period as f64;
    
    let mut avg_gain = initial_gain;
    let mut avg_loss = initial_loss;
    
    // Calculate RSI
    for i in period..prices.len() {
        if avg_loss != 0.0 {
            rsi[i] = 100.0 - (100.0 / (1.0 + avg_gain / avg_loss));
        } else {
            rsi[i] = 100.0;
        }
        
        // Update averages
        avg_gain = (avg_gain * (period as f64 - 1.0) + gains[i]) / period as f64;
        avg_loss = (avg_loss * (period as f64 - 1.0) + losses[i]) / period as f64;
    }
    
    Ok(rsi)
}

pub fn calculate_macd(
    prices: ArrayView1<f64>,
    fast_period: usize,
    slow_period: usize,
    signal_period: usize,
) -> Result<MacdResult, SharpeError> {
    let ema_fast = calculate_ema(prices, fast_period)?;
    let ema_slow = calculate_ema(prices, slow_period)?;
    
    let macd_line = &ema_fast - &ema_slow;
    let signal_line = calculate_ema(macd_line.view(), signal_period)?;
    let histogram = &macd_line - &signal_line;
    
    Ok(MacdResult {
        macd: macd_line,
        signal: signal_line,
        histogram,
    })
}

pub fn calculate_bollinger_bands(
    prices: ArrayView1<f64>,
    period: usize,
    std_dev: f64,
) -> Result<BollingerBandsResult, SharpeError> {
    let sma = calculate_sma(prices, period)?;
    let mut upper = Array1::zeros(prices.len());
    let mut lower = Array1::zeros(prices.len());
    
    // Calculate standard deviation
    for i in period - 1..prices.len() {
        let slice = prices.slice(s![i - period + 1..=i]);
        let mean = sma[i];
        let variance: f64 = slice.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / period as f64;
        let std = variance.sqrt();
        
        upper[i] = mean + std_dev * std;
        lower[i] = mean - std_dev * std;
    }
    
    Ok(BollingerBandsResult {
        upper,
        middle: sma,
        lower,
    })
}

pub fn calculate_atr(
    highs: ArrayView1<f64>,
    lows: ArrayView1<f64>,
    closes: ArrayView1<f64>,
    period: usize,
) -> Result<Array1<f64>, SharpeError> {
    if highs.len() < period + 1 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut tr = Array1::zeros(highs.len());
    let mut atr = Array1::zeros(highs.len());
    
    // Calculate True Range
    for i in 1..highs.len() {
        let hl = highs[i] - lows[i];
        let hc = (highs[i] - closes[i - 1]).abs();
        let lc = (lows[i] - closes[i - 1]).abs();
        tr[i] = hl.max(hc).max(lc);
    }
    
    // Calculate ATR
    let initial_atr = tr.slice(s![1..=period]).sum() / period as f64;
    atr[period] = initial_atr;
    
    for i in period + 1..highs.len() {
        atr[i] = (atr[i - 1] * (period as f64 - 1.0) + tr[i]) / period as f64;
    }
    
    Ok(atr)
}

pub fn calculate_price_position(
    highs: ArrayView1<f64>,
    lows: ArrayView1<f64>,
    closes: ArrayView1<f64>,
) -> Result<Array1<f64>, SharpeError> {
    let mut position = Array1::zeros(closes.len());
    
    for i in 0..closes.len() {
        let range = highs[i] - lows[i];
        if range > 0.0 {
            position[i] = (closes[i] - lows[i]) / range;
        }
    }
    
    Ok(position)
}

pub fn calculate_volume_ratio(
    volumes: ArrayView1<f64>,
    period: usize,
) -> Result<Array1<f64>, SharpeError> {
    let volume_sma = calculate_sma(volumes, period)?;
    let mut ratio = Array1::zeros(volumes.len());
    
    for i in 0..volumes.len() {
        if volume_sma[i] > 0.0 {
            ratio[i] = volumes[i] / volume_sma[i];
        }
    }
    
    Ok(ratio)
}

pub fn calculate_volatility(
    prices: ArrayView1<f64>,
    period: usize,
) -> Result<Array1<f64>, SharpeError> {
    if prices.len() < period + 1 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut volatility = Array1::zeros(prices.len());
    
    for i in period..prices.len() {
        let slice = prices.slice(s![i - period + 1..=i]);
        let returns: Vec<f64> = slice
            .windows(2)
            .into_iter()
            .map(|w| (w[1] / w[0] - 1.0).ln())
            .collect();
        
        let mean = returns.iter().sum::<f64>() / returns.len() as f64;
        let variance: f64 = returns.iter()
            .map(|&x| (x - mean).powi(2))
            .sum::<f64>() / returns.len() as f64;
        
        volatility[i] = variance.sqrt() * (252.0_f64).sqrt(); // Annualized
    }
    
    Ok(volatility)
}

// Parallel processing functions
pub fn calculate_ema_parallel(prices: &Array1<f64>, periods: &[usize]) -> HashMap<usize, Array1<f64>> {
    periods.par_iter()
        .map(|&period| (period, calculate_ema(prices.view(), period).unwrap_or_default()))
        .collect()
}

pub fn calculate_rsi_parallel(prices: &Array1<f64>, periods: &[usize]) -> HashMap<usize, Array1<f64>> {
    periods.par_iter()
        .map(|&period| (period, calculate_rsi(prices.view(), period).unwrap_or_default()))
        .collect()
}

pub fn calculate_volatility_parallel(
    prices: &Array1<f64>,
    periods: &[usize],
) -> HashMap<usize, Array1<f64>> {
    periods.par_iter()
        .map(|&period| (period, calculate_volatility(prices.view(), period).unwrap_or_default()))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;
    
    #[test]
    fn test_ema_calculation() {
        let prices = array![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let ema = calculate_ema(prices.view(), 3).unwrap();
        
        assert_eq!(ema.len(), prices.len());
        assert!(ema[0] > 0.0);
    }
    
    #[test]
    fn test_rsi_calculation() {
        let prices = array![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let rsi = calculate_rsi(prices.view(), 3).unwrap();
        
        assert_eq!(rsi.len(), prices.len());
        assert!(rsi[9] > 0.0); // RSI should be positive for upward trend
    }
    
    #[test]
    fn test_macd_calculation() {
        let prices = array![1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0];
        let macd = calculate_macd(prices.view(), 3, 5, 2).unwrap();
        
        assert_eq!(macd.macd.len(), prices.len());
        assert_eq!(macd.signal.len(), prices.len());
        assert_eq!(macd.histogram.len(), prices.len());
    }
}
