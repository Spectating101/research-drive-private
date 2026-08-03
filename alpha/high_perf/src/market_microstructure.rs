use ndarray::{Array1, Array2, ArrayView1, s};
use std::collections::HashMap;
use crate::error::{SharpeError, SharpeResult};

fn mean_view(data: ArrayView1<f64>) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    data.iter().sum::<f64>() / data.len() as f64
}

fn mean_array(data: &Array1<f64>) -> f64 {
    mean_view(data.view())
}

fn std_array(data: &Array1<f64>) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    let mean = mean_array(data);
    let var = data.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / data.len() as f64;
    var.sqrt()
}

#[derive(Debug, Clone)]
pub struct MarketImpact {
    pub temporary_impact: f64,
    pub permanent_impact: f64,
    pub total_impact: f64,
    pub optimal_trade_size: f64,
}

pub fn calculate_all_liquidity_metrics(
    prices: &Array2<f64>,
    volumes: &Array1<f64>,
) -> SharpeResult<HashMap<String, f64>> {
    let mut metrics = HashMap::new();
    
    // Extract OHLC data
    let _opens = prices.column(0);
    let highs = prices.column(1);
    let lows = prices.column(2);
    let closes = prices.column(3);
    let volumes = volumes.view();
    
    // Calculate basic liquidity measures
    metrics.insert("avg_volume".to_string(), mean_view(volumes));
    metrics.insert("volume_volatility".to_string(), calculate_volume_volatility(&volumes));
    metrics.insert("turnover_ratio".to_string(), calculate_turnover_ratio(&closes, &volumes)?);
    
    // Calculate Amihud illiquidity
    metrics.insert("amihud_illiquidity".to_string(), calculate_amihud_illiquidity(&closes, &volumes)?);
    
    // Calculate Roll's implicit spread
    metrics.insert("roll_spread".to_string(), calculate_roll_spread(&closes)?);
    
    // Calculate Kyle's lambda
    metrics.insert("kyle_lambda".to_string(), calculate_kyle_lambda(&closes, &volumes)?);
    
    // Calculate bid-ask spread proxy
    metrics.insert("spread_proxy".to_string(), calculate_spread_proxy(&highs, &lows, &closes)?);
    
    // Calculate liquidity ratio
    metrics.insert("liquidity_ratio".to_string(), calculate_liquidity_ratio(&closes, &volumes)?);
    
    // Calculate market depth proxy
    metrics.insert("market_depth".to_string(), calculate_market_depth(&volumes, &metrics["spread_proxy"])?);
    
    // Calculate liquidity persistence
    metrics.insert("liquidity_persistence".to_string(), calculate_liquidity_persistence(&volumes)?);
    
    // Calculate Indonesian market specific liquidity score
    metrics.insert("idx_liquidity_score".to_string(), calculate_idx_liquidity_score(&metrics));
    
    Ok(metrics)
}

pub fn calculate_market_impact(
    prices: &Array2<f64>,
    volumes: &Array1<f64>,
    trade_sizes: &Array1<f64>,
) -> SharpeResult<MarketImpact> {
    let closes = prices.column(3);
    
    // Calculate daily volume and price volatility
    let daily_volume = mean_view(volumes.view());
    let price_volatility = calculate_price_volatility(&closes)?;
    
    // Almgren-Chriss model parameters
    let alpha = 0.5; // Temporary impact parameter
    let beta = 0.3;  // Permanent impact parameter
    
    // Calculate impacts
    let mut temporary_impact = 0.0;
    let mut permanent_impact = 0.0;
    let mut total_impact = 0.0;
    for &trade_size in trade_sizes.iter() {
        let temp_impact = alpha * (trade_size / daily_volume) * price_volatility;
        let perm_impact = beta * (trade_size / daily_volume).sqrt() * price_volatility;
        let total = temp_impact + perm_impact;
        
        temporary_impact += temp_impact;
        permanent_impact += perm_impact;
        total_impact += total;
    }
    
    // Average impacts
    let n_trades = trade_sizes.len() as f64;
    temporary_impact /= n_trades;
    permanent_impact /= n_trades;
    total_impact /= n_trades;
    
    // Calculate optimal trade size
    let optimal_trade_size = daily_volume * 0.01 * (1.0 - total_impact).max(0.1);
    
    Ok(MarketImpact {
        temporary_impact,
        permanent_impact,
        total_impact,
        optimal_trade_size,
    })
}

pub fn calculate_price_discovery_metrics(
    prices: &Array2<f64>,
) -> SharpeResult<HashMap<String, f64>> {
    let mut metrics = HashMap::new();
    let closes = prices.column(3);
    
    // Calculate returns
    let returns = calculate_returns(&closes)?;
    
    // Variance ratio test
    metrics.insert("variance_ratio".to_string(), calculate_variance_ratio(&returns)?);
    
    // Hurst exponent
    metrics.insert("hurst_exponent".to_string(), calculate_hurst_exponent(&returns)?);
    
    // Price efficiency
    metrics.insert("price_efficiency".to_string(), calculate_price_efficiency(&returns)?);
    
    // Information share
    metrics.insert("information_share".to_string(), calculate_information_share(prices)?);
    
    // Price discovery speed
    metrics.insert("discovery_speed".to_string(), calculate_discovery_speed(&returns)?);
    
    Ok(metrics)
}

// Helper functions
fn calculate_volume_volatility(volumes: &ArrayView1<f64>) -> f64 {
    let mean = mean_view(*volumes);
    if mean > 0.0 {
        // population stddev
        let var = volumes.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / volumes.len() as f64;
        var.sqrt() / mean
    } else {
        0.0
    }
}

fn calculate_turnover_ratio(
    prices: &ArrayView1<f64>,
    volumes: &ArrayView1<f64>,
) -> SharpeResult<f64> {
    let volume_sum = volumes.sum();
    let price_volume_sum = prices.iter().zip(volumes.iter()).map(|(&p, &v)| p * v).sum::<f64>();
    
    if price_volume_sum > 0.0 {
        Ok(volume_sum / price_volume_sum)
    } else {
        Ok(0.0)
    }
}

fn calculate_amihud_illiquidity(
    prices: &ArrayView1<f64>,
    volumes: &ArrayView1<f64>,
) -> SharpeResult<f64> {
    let mut illiquidity_sum = 0.0;
    let mut count = 0;
    
    for i in 1..prices.len() {
        let return_abs = ((prices[i] / prices[i - 1]) - 1.0).abs();
        let volume_millions = volumes[i] / 1_000_000.0;
        
        if volume_millions > 0.0 {
            illiquidity_sum += return_abs / volume_millions;
            count += 1;
        }
    }
    
    if count > 0 {
        Ok(illiquidity_sum / count as f64)
    } else {
        Ok(0.0)
    }
}

fn calculate_roll_spread(prices: &ArrayView1<f64>) -> SharpeResult<f64> {
    if prices.len() < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut price_changes = Vec::new();
    for i in 1..prices.len() {
        price_changes.push(prices[i] - prices[i - 1]);
    }
    
    if price_changes.len() < 2 {
        return Ok(0.0);
    }
    
    // Calculate covariance between consecutive price changes
    let mean_change = price_changes.iter().sum::<f64>() / price_changes.len() as f64;
    let mut covariance = 0.0;
    
    for i in 1..price_changes.len() {
        covariance += (price_changes[i] - mean_change) * (price_changes[i - 1] - mean_change);
    }
    covariance /= (price_changes.len() - 1) as f64;
    
    // Roll's spread estimator
    let spread = if covariance < 0.0 {
        2.0 * (-covariance).sqrt()
    } else {
        0.0
    };
    
    Ok(spread)
}

fn calculate_kyle_lambda(
    prices: &ArrayView1<f64>,
    volumes: &ArrayView1<f64>,
) -> SharpeResult<f64> {
    if prices.len() < 2 || volumes.len() < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let returns = calculate_returns(prices)?;
    let volume_changes = calculate_volume_changes(volumes)?;
    
    // Calculate correlation between returns and volume changes
    let return_mean = mean_array(&returns);
    let volume_change_mean = mean_array(&volume_changes);
    
    let mut numerator = 0.0;
    let mut return_var = 0.0;
    let mut volume_var = 0.0;
    
    for i in 0..returns.len() {
        let return_diff = returns[i] - return_mean;
        let volume_diff = volume_changes[i] - volume_change_mean;
        
        numerator += return_diff * volume_diff;
        return_var += return_diff * return_diff;
        volume_var += volume_diff * volume_diff;
    }
    
    let correlation = if return_var > 0.0 && volume_var > 0.0 {
        numerator / (return_var.sqrt() * volume_var.sqrt())
    } else {
        0.0
    };
    
    let return_std = std_array(&returns);
    let volume_std = std_array(&volume_changes);
    
    let lambda = if volume_std > 0.0 {
        correlation * return_std / volume_std
    } else {
        0.0
    };
    
    Ok(lambda)
}

fn calculate_spread_proxy(
    highs: &ArrayView1<f64>,
    lows: &ArrayView1<f64>,
    closes: &ArrayView1<f64>,
) -> SharpeResult<f64> {
    let mut spread_sum = 0.0;
    let mut count = 0;
    
    for i in 0..closes.len() {
        let range = highs[i] - lows[i];
        if closes[i] > 0.0 {
            spread_sum += range / closes[i];
            count += 1;
        }
    }
    
    if count > 0 {
        Ok(spread_sum / count as f64)
    } else {
        Ok(0.0)
    }
}

fn calculate_liquidity_ratio(
    prices: &ArrayView1<f64>,
    volumes: &ArrayView1<f64>,
) -> SharpeResult<f64> {
    let window = 10.min(prices.len() - 1);
    
    let mut liquidity_sum = 0.0;
    let mut count = 0;
    
    for i in window..prices.len() {
        let price_slice = prices.slice(s![i - window..=i]);
        let volume_slice = volumes.slice(s![i - window..=i]);
        
        let price_sum = price_slice.iter().zip(volume_slice.iter()).map(|(&p, &v)| p * v).sum::<f64>();
        let return_sum = price_slice
            .windows(2)
            .into_iter()
            .map(|w| (w[1] / w[0] - 1.0).abs())
            .sum::<f64>();
        
        if return_sum > 0.0 {
            liquidity_sum += price_sum / return_sum;
            count += 1;
        }
    }
    
    if count > 0 {
        Ok(liquidity_sum / count as f64)
    } else {
        Ok(0.0)
    }
}

fn calculate_market_depth(
    volumes: &ArrayView1<f64>,
    spread_proxy: &f64,
) -> SharpeResult<f64> {
    let avg_volume = mean_view(*volumes);
    
    if *spread_proxy > 0.0 {
        Ok(avg_volume / spread_proxy)
    } else {
        Ok(0.0)
    }
}

fn calculate_liquidity_persistence(volumes: &ArrayView1<f64>) -> SharpeResult<f64> {
    if volumes.len() < 2 {
        return Ok(0.0);
    }
    
    let mean = mean_view(*volumes);
    let mut numerator = 0.0;
    let mut denominator = 0.0;
    
    for i in 1..volumes.len() {
        let diff1 = volumes[i] - mean;
        let diff2 = volumes[i - 1] - mean;
        
        numerator += diff1 * diff2;
        denominator += diff1 * diff1;
    }
    
    if denominator > 0.0 {
        Ok(numerator / denominator)
    } else {
        Ok(0.0)
    }
}

fn calculate_idx_liquidity_score(metrics: &HashMap<String, f64>) -> f64 {
    let weights = [
        ("amihud_illiquidity", -0.3),
        ("spread_proxy", -0.2),
        ("market_depth", 0.2),
        ("liquidity_persistence", 0.15),
        ("turnover_ratio", 0.15),
    ];
    
    let mut score = 0.0;
    for (metric, weight) in weights.iter() {
        if let Some(&value) = metrics.get(*metric) {
            let normalized_value = value.max(0.0).min(1.0);
            score += weight * normalized_value;
        }
    }
    
    score.max(0.0).min(1.0)
}

fn calculate_price_volatility(prices: &ArrayView1<f64>) -> SharpeResult<f64> {
    if prices.len() < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let returns = calculate_returns(prices)?;
    Ok(std_array(&returns))
}

fn calculate_returns(prices: &ArrayView1<f64>) -> SharpeResult<Array1<f64>> {
    if prices.len() < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut returns = Array1::zeros(prices.len() - 1);
    
    for i in 1..prices.len() {
        if prices[i - 1] > 0.0 {
            returns[i - 1] = (prices[i] / prices[i - 1] - 1.0).ln();
        }
    }
    
    Ok(returns)
}

fn calculate_volume_changes(volumes: &ArrayView1<f64>) -> SharpeResult<Array1<f64>> {
    if volumes.len() < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut changes = Array1::zeros(volumes.len() - 1);
    
    for i in 1..volumes.len() {
        if volumes[i - 1] > 0.0 {
            changes[i - 1] = (volumes[i] / volumes[i - 1] - 1.0).ln();
        }
    }
    
    Ok(changes)
}

fn calculate_variance_ratio(returns: &Array1<f64>) -> SharpeResult<f64> {
    if returns.len() < 20 {
        return Ok(1.0);
    }
    
    let lags = [2, 4, 8];
    let mut vr_values = Vec::new();
    
    for &lag in lags.iter() {
        if returns.len() >= lag * 2 {
            let k_returns: Vec<f64> = returns
                .windows(lag)
                .into_iter()
                .map(|w| w.sum())
                .collect();
            let var_k = calculate_variance(&k_returns);
            let var_1 = calculate_variance(returns.as_slice().unwrap());
            
            if var_1 > 0.0 {
                let vr = var_k / (lag as f64 * var_1);
                vr_values.push(vr);
            }
        }
    }
    
    if vr_values.is_empty() {
        Ok(1.0)
    } else {
        Ok(vr_values.iter().sum::<f64>() / vr_values.len() as f64)
    }
}

fn calculate_hurst_exponent(returns: &Array1<f64>) -> SharpeResult<f64> {
    if returns.len() < 50 {
        return Ok(0.5);
    }
    
    let lags: Vec<usize> = (10..=50.min(returns.len() / 2)).collect();
    let mut rs_values = Vec::new();
    
    for &lag in lags.iter() {
        let chunks: Vec<&[f64]> = returns.as_slice().unwrap().chunks(lag).collect();
        
        for chunk in chunks {
            if chunk.len() == lag {
                let rs = calculate_rs_statistic(chunk);
                rs_values.push(rs);
            }
        }
    }
    
    if rs_values.len() < 2 {
        return Ok(0.5);
    }
    
    // Calculate Hurst exponent using log-log regression
    let log_rs: Vec<f64> = rs_values.iter().map(|&x| x.ln()).collect();
    let log_lags: Vec<f64> = lags[..rs_values.len()].iter().map(|&x| x as f64).map(|x| x.ln()).collect();
    
    let hurst = calculate_linear_regression_slope(&log_lags, &log_rs);
    Ok(hurst)
}

fn calculate_price_efficiency(returns: &Array1<f64>) -> SharpeResult<f64> {
    if returns.len() < 2 {
        return Ok(0.5);
    }
    
    let autocorr = calculate_autocorrelation(returns, 1)?;
    let efficiency = 1.0 - autocorr.abs();
    
    Ok(efficiency.max(0.0).min(1.0))
}

fn calculate_information_share(prices: &Array2<f64>) -> SharpeResult<f64> {
    let highs = prices.column(1);
    let lows = prices.column(2);
    let closes = prices.column(3);
    
    let mut spreads = Vec::new();
    
    for i in 0..closes.len() {
        let range = highs[i] - lows[i];
        if closes[i] > 0.0 {
            spreads.push(range / closes[i]);
        }
    }
    
    if spreads.is_empty() {
        return Ok(0.5);
    }
    
    let avg_spread = spreads.iter().sum::<f64>() / spreads.len() as f64;
    let info_share = 1.0 / (1.0 + avg_spread);
    
    Ok(info_share.max(0.0).min(1.0))
}

fn calculate_discovery_speed(returns: &Array1<f64>) -> SharpeResult<f64> {
    if returns.len() < 10 {
        return Ok(0.5);
    }
    
    let max_lag = 10.min(returns.len() / 2);
    let mut autocorrs = Vec::new();
    
    for lag in 1..=max_lag {
        if let Ok(autocorr) = calculate_autocorrelation(returns, lag) {
            autocorrs.push(autocorr.abs());
        }
    }
    
    if autocorrs.is_empty() {
        return Ok(0.5);
    }
    
    let avg_autocorr = autocorrs.iter().sum::<f64>() / autocorrs.len() as f64;
    let speed = 1.0 - avg_autocorr;
    
    Ok(speed.max(0.0).min(1.0))
}

// Additional helper functions
fn calculate_variance(data: &[f64]) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    
    let mean = data.iter().sum::<f64>() / data.len() as f64;
    let variance = data.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / data.len() as f64;
    variance
}

fn calculate_rs_statistic(data: &[f64]) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    
    let mean = data.iter().sum::<f64>() / data.len() as f64;
    let deviations: Vec<f64> = data.iter().map(|&x| x - mean).collect();
    
    let cumsum: Vec<f64> = deviations.iter().scan(0.0, |acc, &x| {
        *acc += x;
        Some(*acc)
    }).collect();
    
    let max = cumsum
        .iter()
        .copied()
        .fold(f64::NEG_INFINITY, f64::max);
    let min = cumsum
        .iter()
        .copied()
        .fold(f64::INFINITY, f64::min);
    let r = max - min;
    let s = deviations.iter().map(|&x| x.powi(2)).sum::<f64>().sqrt();
    
    if s > 0.0 {
        r / s
    } else {
        0.0
    }
}

fn calculate_linear_regression_slope(x: &[f64], y: &[f64]) -> f64 {
    if x.len() != y.len() || x.is_empty() {
        return 0.5;
    }
    
    let n = x.len() as f64;
    let sum_x: f64 = x.iter().sum();
    let sum_y: f64 = y.iter().sum();
    let sum_xy: f64 = x.iter().zip(y.iter()).map(|(&x, &y)| x * y).sum();
    let sum_x2: f64 = x.iter().map(|&x| x * x).sum();
    
    let slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x2 - sum_x * sum_x);
    slope
}

fn calculate_autocorrelation(data: &Array1<f64>, lag: usize) -> SharpeResult<f64> {
    if data.len() <= lag {
        return Err(SharpeError::InsufficientData);
    }
    
    let mean = mean_array(data);
    let mut numerator = 0.0;
    let mut denominator = 0.0;
    
    for i in lag..data.len() {
        let diff1 = data[i] - mean;
        let diff2 = data[i - lag] - mean;
        
        numerator += diff1 * diff2;
        denominator += diff1 * diff1;
    }
    
    if denominator > 0.0 {
        Ok(numerator / denominator)
    } else {
        Ok(0.0)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;
    
    #[test]
    fn test_amihud_illiquidity() {
        let prices = array![100.0, 101.0, 99.0, 102.0];
        let volumes = array![1000000.0, 2000000.0, 1500000.0, 1800000.0];
        
        let illiquidity = calculate_amihud_illiquidity(&prices.view(), &volumes.view()).unwrap();
        assert!(illiquidity >= 0.0);
    }
    
    #[test]
    fn test_roll_spread() {
        let prices = array![100.0, 101.0, 99.0, 102.0, 100.5];
        let spread = calculate_roll_spread(&prices.view()).unwrap();
        assert!(spread >= 0.0);
    }
    
    #[test]
    fn test_variance_ratio() {
        let returns = array![0.01, 0.02, -0.01, 0.03, 0.01, -0.02, 0.01, 0.02];
        let vr = calculate_variance_ratio(&returns).unwrap();
        assert!(vr > 0.0);
    }
}
