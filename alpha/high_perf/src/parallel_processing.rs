use ndarray::{Array1, Array2, ArrayView2, Axis, s};
use rayon::prelude::*;
use std::collections::HashMap;
use crate::error::{SharpeError, SharpeResult};

pub fn calculate_correlation_matrix_parallel(
    returns: &ArrayView2<f64>,
) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut corr_matrix = Array2::zeros((n_assets, n_assets));
    
    // Calculate means in parallel
    let means: Vec<f64> = returns
        .axis_iter(Axis(0))
        .par_bridge()
        .map(|row| row.sum() / n_obs as f64)
        .collect();
    
    // Calculate correlation matrix in parallel
    let correlation_pairs: Vec<_> = (0..n_assets)
        .flat_map(|i| (i..n_assets).map(move |j| (i, j)))
        .collect();
    
    let correlations: Vec<_> = correlation_pairs
        .par_iter()
        .map(|&(i, j)| {
            let row_i = returns.row(i);
            let row_j = returns.row(j);
            
            let mean_i = means[i];
            let mean_j = means[j];
            
            let mut numerator = 0.0;
            let mut var_i = 0.0;
            let mut var_j = 0.0;
            
            for k in 0..n_obs {
                let diff_i = row_i[k] - mean_i;
                let diff_j = row_j[k] - mean_j;
                
                numerator += diff_i * diff_j;
                var_i += diff_i * diff_i;
                var_j += diff_j * diff_j;
            }
            
            let correlation = if var_i > 0.0 && var_j > 0.0 {
                numerator / (var_i.sqrt() * var_j.sqrt())
            } else {
                0.0
            };
            
            ((i, j), correlation)
        })
        .collect();
    
    // Fill the correlation matrix
    for ((i, j), corr) in correlations {
        corr_matrix[[i, j]] = corr;
        if i != j {
            corr_matrix[[j, i]] = corr;
        }
    }
    
    // Set diagonal to 1.0
    for i in 0..n_assets {
        corr_matrix[[i, i]] = 1.0;
    }
    
    Ok(corr_matrix)
}

pub fn calculate_returns_parallel(prices: &ArrayView2<f64>) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = prices.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut returns = Array2::zeros((n_assets, n_obs - 1));
    
    returns
        .axis_iter_mut(Axis(0))
        .zip(prices.axis_iter(Axis(0)))
        .par_bridge()
        .for_each(|(mut return_row, price_row)| {
            for i in 1..n_obs {
                let prev_price = price_row[i - 1];
                let curr_price = price_row[i];
                
                if prev_price > 0.0 {
                    return_row[i - 1] = (curr_price / prev_price - 1.0).ln();
                }
            }
        });
    
    Ok(returns)
}

pub fn calculate_volatility_parallel(
    returns: &ArrayView2<f64>,
    windows: &[usize],
) -> SharpeResult<HashMap<usize, Array1<f64>>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let max_window = *windows.iter().max().unwrap_or(&20);
    
    if n_obs < max_window {
        return Err(SharpeError::InsufficientData);
    }
    
    let volatilities: HashMap<usize, Array1<f64>> = windows
        .par_iter()
        .map(|&window| {
            let mut vol_array = Array1::zeros(n_assets);
            
            vol_array
                .iter_mut()
                .zip(returns.axis_iter(Axis(0)))
                .for_each(|(vol, return_row)| {
                    let mut sum_sq = 0.0;
                    let mut count = 0;
                    
                    for i in window..n_obs {
                        let slice = return_row.slice(s![i - window..i]);
                        let mean = slice.sum() / window as f64;
                        let variance: f64 = slice.iter()
                            .map(|&x| (x - mean).powi(2))
                            .sum::<f64>() / window as f64;
                        
                        sum_sq += variance;
                        count += 1;
                    }
                    
                    if count > 0 {
                        *vol = (sum_sq / count as f64).sqrt() * (252.0_f64).sqrt();
                    }
                });
            
            (window, vol_array)
        })
        .collect();
    
    Ok(volatilities)
}

pub fn calculate_covariance_matrix_parallel(
    returns: &ArrayView2<f64>,
) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut cov_matrix = Array2::zeros((n_assets, n_assets));
    
    // Calculate means in parallel
    let means: Vec<f64> = returns
        .axis_iter(Axis(0))
        .par_bridge()
        .map(|row| row.sum() / n_obs as f64)
        .collect();
    
    // Calculate covariance matrix in parallel
    let covariance_pairs: Vec<_> = (0..n_assets)
        .flat_map(|i| (i..n_assets).map(move |j| (i, j)))
        .collect();
    
    let covariances: Vec<_> = covariance_pairs
        .par_iter()
        .map(|&(i, j)| {
            let row_i = returns.row(i);
            let row_j = returns.row(j);
            
            let mean_i = means[i];
            let mean_j = means[j];
            
            let mut covariance = 0.0;
            
            for k in 0..n_obs {
                covariance += (row_i[k] - mean_i) * (row_j[k] - mean_j);
            }
            
            covariance /= (n_obs - 1) as f64;
            ((i, j), covariance)
        })
        .collect();
    
    // Fill the covariance matrix
    for ((i, j), cov) in covariances {
        cov_matrix[[i, j]] = cov;
        if i != j {
            cov_matrix[[j, i]] = cov;
        }
    }
    
    Ok(cov_matrix)
}

pub fn calculate_rolling_statistics_parallel(
    data: &ArrayView2<f64>,
    window: usize,
) -> SharpeResult<(Array2<f64>, Array2<f64>)> {
    let (n_assets, n_obs) = data.dim();
    
    if n_obs < window {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut means = Array2::zeros((n_assets, n_obs - window + 1));
    let mut stds = Array2::zeros((n_assets, n_obs - window + 1));
    
    means
        .axis_iter_mut(Axis(0))
        .zip(stds.axis_iter_mut(Axis(0)))
        .zip(data.axis_iter(Axis(0)))
        .par_bridge()
        .for_each(|((mut mean_row, mut std_row), data_row)| {
            for i in 0..=n_obs - window {
                let slice = data_row.slice(s![i..i + window]);
                let mean = slice.sum() / window as f64;
                let variance: f64 = slice.iter()
                    .map(|&x| (x - mean).powi(2))
                    .sum::<f64>() / window as f64;
                
                mean_row[i] = mean;
                std_row[i] = variance.sqrt();
            }
        });
    
    Ok((means, stds))
}

pub fn calculate_percentile_parallel(
    data: &ArrayView2<f64>,
    percentile: f64,
) -> SharpeResult<Array1<f64>> {
    let (_n_assets, n_obs) = data.dim();
    
    if n_obs == 0 {
        return Err(SharpeError::InsufficientData);
    }
    
    let percentiles: Vec<f64> = data
        .axis_iter(Axis(0))
        .par_bridge()
        .map(|row| {
            let mut sorted: Vec<f64> = row.to_vec();
            sorted.sort_by(|a, b| a.partial_cmp(b).unwrap());
            
            let index = (percentile / 100.0 * (n_obs - 1) as f64).round() as usize;
            sorted[index.min(n_obs - 1)]
        })
        .collect();
    
    Ok(Array1::from(percentiles))
}

pub fn calculate_rank_correlation_parallel(
    data1: &ArrayView2<f64>,
    data2: &ArrayView2<f64>,
) -> SharpeResult<Array2<f64>> {
    let (n_assets1, n_obs1) = data1.dim();
    let (n_assets2, n_obs2) = data2.dim();
    
    if n_obs1 != n_obs2 || n_obs1 < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut rank_corr = Array2::zeros((n_assets1, n_assets2));
    
    rank_corr
        .axis_iter_mut(Axis(0))
        .enumerate()
        .par_bridge()
        .for_each(|(i, mut row)| {
            let data1_row = data1.row(i);
            
            for j in 0..n_assets2 {
                let data2_row = data2.row(j);
                
                // Calculate rank correlation (Spearman's rho)
                let mut rank1: Vec<usize> = (0..n_obs1).collect();
                let mut rank2: Vec<usize> = (0..n_obs1).collect();
                
                rank1.sort_by(|&a, &b| data1_row[a].partial_cmp(&data1_row[b]).unwrap());
                rank2.sort_by(|&a, &b| data2_row[a].partial_cmp(&data2_row[b]).unwrap());
                
                let mut d_squared_sum = 0.0;
                for k in 0..n_obs1 {
                    let d = rank1[k] as f64 - rank2[k] as f64;
                    d_squared_sum += d * d;
                }
                
                let n = n_obs1 as f64;
                let rho = 1.0 - (6.0 * d_squared_sum) / (n * (n * n - 1.0));
                
                row[j] = rho;
            }
        });
    
    Ok(rank_corr)
}

pub fn calculate_moving_average_parallel(
    data: &ArrayView2<f64>,
    window: usize,
) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = data.dim();
    
    if n_obs < window {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut ma = Array2::zeros((n_assets, n_obs - window + 1));
    
    ma.axis_iter_mut(Axis(0))
        .zip(data.axis_iter(Axis(0)))
        .par_bridge()
        .for_each(|(mut ma_row, data_row)| {
            for i in 0..=n_obs - window {
                let slice = data_row.slice(s![i..i + window]);
                ma_row[i] = slice.sum() / window as f64;
            }
        });
    
    Ok(ma)
}

pub fn calculate_exponential_moving_average_parallel(
    data: &ArrayView2<f64>,
    alpha: f64,
) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = data.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut ema = Array2::zeros((n_assets, n_obs));
    
    ema.axis_iter_mut(Axis(0))
        .zip(data.axis_iter(Axis(0)))
        .par_bridge()
        .for_each(|(mut ema_row, data_row)| {
            // Initialize with first value
            ema_row[0] = data_row[0];
            
            // Calculate EMA
            for i in 1..n_obs {
                ema_row[i] = alpha * data_row[i] + (1.0 - alpha) * ema_row[i - 1];
            }
        });
    
    Ok(ema)
}

pub fn calculate_momentum_parallel(
    data: &ArrayView2<f64>,
    periods: &[usize],
) -> SharpeResult<HashMap<usize, Array2<f64>>> {
    let (n_assets, n_obs) = data.dim();
    
    let max_period = *periods.iter().max().unwrap_or(&20);
    
    if n_obs < max_period {
        return Err(SharpeError::InsufficientData);
    }
    
    let momentum: HashMap<usize, Array2<f64>> = periods
        .par_iter()
        .map(|&period| {
            let mut momentum_array = Array2::zeros((n_assets, n_obs - period));
            
            momentum_array
                .axis_iter_mut(Axis(0))
                .zip(data.axis_iter(Axis(0)))
                .for_each(|(mut momentum_row, data_row)| {
                    for i in period..n_obs {
                        momentum_row[i - period] = data_row[i] / data_row[i - period] - 1.0;
                    }
                });
            
            (period, momentum_array)
        })
        .collect();
    
    Ok(momentum)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;
    
    #[test]
    fn test_correlation_matrix_parallel() {
        let returns = array![
            [0.01, 0.02, -0.01, 0.03],
            [0.02, 0.01, 0.02, -0.01],
            [-0.01, 0.03, 0.01, 0.02]
        ];
        
        let corr_matrix = calculate_correlation_matrix_parallel(&returns.view()).unwrap();
        
        assert_eq!(corr_matrix.dim(), (3, 3));
        assert!((corr_matrix[[0, 0]] - 1.0).abs() < 1e-10);
    }
    
    #[test]
    fn test_returns_calculation_parallel() {
        let prices = array![
            [100.0, 101.0, 99.0, 102.0],
            [50.0, 51.0, 50.5, 49.0]
        ];
        
        let returns = calculate_returns_parallel(&prices.view()).unwrap();
        
        assert_eq!(returns.dim(), (2, 3));
    }
    
    #[test]
    fn test_volatility_calculation_parallel() {
        let returns = array![
            [0.01, 0.02, -0.01, 0.03, 0.01, -0.02],
            [0.02, 0.01, 0.02, -0.01, 0.03, 0.01]
        ];
        
        let windows = vec![3, 5];
        let volatilities = calculate_volatility_parallel(&returns.view(), &windows).unwrap();
        
        assert!(volatilities.contains_key(&3));
        assert!(volatilities.contains_key(&5));
    }
}
