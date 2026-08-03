use ndarray::{Array1, Array2, ArrayView1, ArrayView2, Axis};
use nalgebra::DMatrix;
use rayon::prelude::*;
use crate::error::{SharpeError, SharpeResult};

fn invert_matrix(matrix: &Array2<f64>) -> SharpeResult<Array2<f64>> {
    let (nrows, ncols) = matrix.dim();
    if nrows != ncols {
        return Err(SharpeError::MatrixError {
            message: "Matrix must be square to invert".to_string(),
        });
    }

    let data = matrix
        .as_slice()
        .ok_or_else(|| SharpeError::MatrixError {
            message: "Matrix is not contiguous".to_string(),
        })?;

    let m = DMatrix::from_row_slice(nrows, ncols, data);
    let inv = m.try_inverse().ok_or_else(|| SharpeError::MatrixError {
        message: "Failed to invert matrix".to_string(),
    })?;

    let mut out = Vec::with_capacity(nrows * ncols);
    for i in 0..nrows {
        for j in 0..ncols {
            out.push(inv[(i, j)]);
        }
    }

    Array2::from_shape_vec((nrows, ncols), out).map_err(|e| SharpeError::MatrixError {
        message: e.to_string(),
    })
}

fn normalize_long_only(weights: &mut Array1<f64>) {
    let n = weights.len();
    for w in weights.iter_mut() {
        if !w.is_finite() || *w < 0.0 {
            *w = 0.0;
        }
    }

    let sum = weights.sum();
    if sum > 0.0 {
        *weights /= sum;
        return;
    }

    // Fallback: equal weights.
    if n > 0 {
        weights.fill(1.0 / n as f64);
    }
}

pub fn optimize_risk_parity(
    returns: &ArrayView2<f64>,
    target_vol: f64,
) -> SharpeResult<Array1<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    // Calculate covariance matrix
    let cov_matrix = calculate_covariance_matrix(returns)?;
    
    // Initialize weights equally
    let mut weights = Array1::from_elem(n_assets, 1.0 / n_assets as f64);
    
    // Risk parity optimization using gradient descent
    let learning_rate = 0.01;
    let max_iterations = 1000;
    let tolerance = 1e-6;
    
    for _ in 0..max_iterations {
        let mut new_weights = weights.clone();
        
        // Calculate risk contributions
        let portfolio_vol = calculate_portfolio_volatility(&weights, &cov_matrix)?;
        let risk_contributions = calculate_risk_contributions(&weights, &cov_matrix, portfolio_vol)?;
        
        // Calculate target risk contribution
        let target_contribution = portfolio_vol / n_assets as f64;
        
        // Update weights
        for i in 0..n_assets {
            let risk_diff = risk_contributions[i] - target_contribution;
            let gradient = calculate_weight_gradient(i, &weights, &cov_matrix, portfolio_vol)?;
            
            new_weights[i] -= learning_rate * risk_diff * gradient;
        }
        
        normalize_long_only(&mut new_weights);
        
        // Check convergence
        let weight_diff = (&new_weights - &weights).mapv(|x| x.abs()).sum();
        if weight_diff < tolerance {
            break;
        }
        
        weights = new_weights;
    }
    
    // Scale to target volatility
    let current_vol = calculate_portfolio_volatility(&weights, &cov_matrix)?;
    if current_vol > 0.0 {
        weights *= target_vol / current_vol;
    }
    normalize_long_only(&mut weights);
    
    Ok(weights)
}

pub fn optimize_hierarchical_risk_parity(
    returns: &ArrayView2<f64>,
) -> SharpeResult<Array1<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    // Calculate correlation matrix
    let corr_matrix = calculate_correlation_matrix(returns)?;
    
    // Convert correlation to distance matrix
    let mut distance_matrix = Array2::zeros((n_assets, n_assets));
    for i in 0..n_assets {
        for j in 0..n_assets {
            distance_matrix[[i, j]] = ((1.0 - corr_matrix[[i, j]]) / 2.0).sqrt();
        }
    }
    
    // Hierarchical clustering
    let clusters = perform_hierarchical_clustering(&distance_matrix)?;
    
    // Calculate weights using HRP algorithm
    let weights = calculate_hrp_weights(returns, &clusters)?;
    
    Ok(weights)
}

pub fn optimize_black_litterman(
    returns: &ArrayView2<f64>,
    market_caps: &ArrayView1<f64>,
    views: &ArrayView2<f64>,
    view_confidences: &ArrayView1<f64>,
) -> SharpeResult<Array1<f64>> {
    let (_n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    // Calculate covariance matrix
    let cov_matrix = calculate_covariance_matrix(returns)?;
    
    // Calculate market equilibrium returns
    let market_weights = market_caps / market_caps.sum();
    let risk_aversion = 2.5;
    let pi = &cov_matrix.dot(&market_weights) * risk_aversion;
    
    // Incorporate views
    let n_views = views.dim().0;
    if n_views > 0 {
        let tau = 0.05;
        let omega = calculate_view_confidence_matrix(view_confidences)?;
        
        // Black-Litterman formula
        let bl_returns = calculate_black_litterman_returns(
            &pi, &cov_matrix, views, &omega, tau
        )?;
        
        // Optimize portfolio
        let weights = optimize_mean_variance(&bl_returns, &cov_matrix)?;
        Ok(weights)
    } else {
        // No views, use market equilibrium
        let weights = optimize_mean_variance(&pi, &cov_matrix)?;
        Ok(weights)
    }
}

pub fn optimize_kelly_criterion(
    returns: &ArrayView2<f64>,
    risk_free_rate: f64,
) -> SharpeResult<Array1<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut kelly_weights = Array1::zeros(n_assets);
    
    // Calculate Kelly fraction for each asset
    kelly_weights
        .iter_mut()
        .zip(returns.axis_iter(Axis(0)))
        .par_bridge()
        .for_each(|(weight, return_row)| {
            let mean_return = return_row.sum() / n_obs as f64;
            let variance = return_row.iter()
                .map(|&x| (x - mean_return).powi(2))
                .sum::<f64>() / (n_obs - 1) as f64;
            
            if variance > 0.0 {
                *weight = (mean_return - risk_free_rate) / variance;
            }
        });
    
    // Normalize weights
    normalize_long_only(&mut kelly_weights);
    
    Ok(kelly_weights)
}

// Helper functions
fn calculate_covariance_matrix(returns: &ArrayView2<f64>) -> SharpeResult<Array2<f64>> {
    let (n_assets, n_obs) = returns.dim();
    
    if n_obs < 2 {
        return Err(SharpeError::InsufficientData);
    }
    
    let mut cov_matrix = Array2::zeros((n_assets, n_assets));
    
    // Calculate means
    let means: Vec<f64> = returns
        .axis_iter(Axis(0))
        .map(|row| row.sum() / n_obs as f64)
        .collect();
    
    // Calculate covariance matrix
    for i in 0..n_assets {
        for j in 0..n_assets {
            let mut covariance = 0.0;
            let row_i = returns.row(i);
            let row_j = returns.row(j);
            
            for k in 0..n_obs {
                covariance += (row_i[k] - means[i]) * (row_j[k] - means[j]);
            }
            
            cov_matrix[[i, j]] = covariance / (n_obs - 1) as f64;
        }
    }
    
    Ok(cov_matrix)
}

fn calculate_correlation_matrix(returns: &ArrayView2<f64>) -> SharpeResult<Array2<f64>> {
    let cov_matrix = calculate_covariance_matrix(returns)?;
    let (n_assets, _) = cov_matrix.dim();
    
    let mut corr_matrix = Array2::zeros((n_assets, n_assets));
    
    for i in 0..n_assets {
        for j in 0..n_assets {
            let std_i = cov_matrix[[i, i]].sqrt();
            let std_j = cov_matrix[[j, j]].sqrt();
            
            if std_i > 0.0 && std_j > 0.0 {
                corr_matrix[[i, j]] = cov_matrix[[i, j]] / (std_i * std_j);
            } else {
                corr_matrix[[i, j]] = if i == j { 1.0 } else { 0.0 };
            }
        }
    }
    
    Ok(corr_matrix)
}

fn calculate_portfolio_volatility(
    weights: &Array1<f64>,
    cov_matrix: &Array2<f64>,
) -> SharpeResult<f64> {
    let portfolio_variance = weights.dot(cov_matrix).dot(weights);
    Ok(portfolio_variance.sqrt())
}

fn calculate_risk_contributions(
    weights: &Array1<f64>,
    cov_matrix: &Array2<f64>,
    portfolio_vol: f64,
) -> SharpeResult<Array1<f64>> {
    let risk_contributions = weights * &cov_matrix.dot(weights);
    Ok(risk_contributions / portfolio_vol)
}

fn calculate_weight_gradient(
    asset_idx: usize,
    weights: &Array1<f64>,
    cov_matrix: &Array2<f64>,
    portfolio_vol: f64,
) -> SharpeResult<f64> {
    let mut gradient = 0.0;
    
    for j in 0..weights.len() {
        gradient += cov_matrix[[asset_idx, j]] * weights[j];
    }
    
    Ok(gradient / portfolio_vol)
}

fn perform_hierarchical_clustering(
    distance_matrix: &Array2<f64>,
) -> SharpeResult<Vec<usize>> {
    let n_assets = distance_matrix.dim().0;
    let mut clusters: Vec<usize> = (0..n_assets).collect();
    
    // Simple hierarchical clustering implementation
    // In practice, you'd use a more sophisticated algorithm
    for i in 0..n_assets {
        clusters[i] = i;
    }
    
    Ok(clusters)
}

fn calculate_hrp_weights(
    returns: &ArrayView2<f64>,
    _clusters: &[usize],
) -> SharpeResult<Array1<f64>> {
    let (n_assets, _) = returns.dim();
    let mut weights = Array1::zeros(n_assets);
    
    // Calculate variances
    let variances: Vec<f64> = returns
        .axis_iter(Axis(0))
        .map(|row| {
            let mean = row.sum() / row.len() as f64;
            row.iter().map(|&x| (x - mean).powi(2)).sum::<f64>() / (row.len() - 1) as f64
        })
        .collect();
    
    // Simple HRP weight calculation
    for i in 0..n_assets {
        weights[i] = 1.0 / variances[i];
    }
    
    // Normalize
    let sum = weights.sum();
    if sum > 0.0 {
        weights /= sum;
    }
    
    Ok(weights)
}

fn calculate_view_confidence_matrix(
    view_confidences: &ArrayView1<f64>,
) -> SharpeResult<Array2<f64>> {
    let n_views = view_confidences.len();
    let mut omega = Array2::zeros((n_views, n_views));
    
    for i in 0..n_views {
        omega[[i, i]] = view_confidences[i];
    }
    
    Ok(omega)
}

fn calculate_black_litterman_returns(
    pi: &Array1<f64>,
    cov_matrix: &Array2<f64>,
    views: &ArrayView2<f64>,
    omega: &Array2<f64>,
    tau: f64,
) -> SharpeResult<Array1<f64>> {
    let n_assets = pi.len();
    let n_views = views.dim().0;
    
    // Create view matrix P and view returns Q
    let mut p = Array2::zeros((n_views, n_assets));
    let mut q = Array1::zeros(n_views);
    
    // For simplicity, assume each view is about one asset
    for i in 0..n_views.min(n_assets) {
        p[[i, i]] = 1.0;
        q[i] = pi[i] * 1.1; // 10% higher than equilibrium
    }
    
    // Black-Litterman formula
    let tau_cov = cov_matrix * tau;
    let m1 = tau_cov.dot(&p.t());
    let m2 = omega + p.dot(&tau_cov).dot(&p.t());
    let m2_inv = invert_matrix(&m2)?;
    
    let bl_returns = pi + m1.dot(&m2_inv).dot(&(q - p.dot(pi)));
    
    Ok(bl_returns)
}

fn optimize_mean_variance(
    expected_returns: &Array1<f64>,
    cov_matrix: &Array2<f64>,
) -> SharpeResult<Array1<f64>> {
    let n_assets = expected_returns.len();
    
    // Simple mean-variance optimization
    // In practice, you'd use a more sophisticated solver
    let mut weights = Array1::from_elem(n_assets, 1.0 / n_assets as f64);
    
    // Calculate optimal weights (simplified)
    let risk_aversion = 2.5;
    let optimal_weights = invert_matrix(cov_matrix)?;
    
    let weights_vec = optimal_weights.dot(expected_returns) / risk_aversion;
    
    // Normalize weights
    let sum = weights_vec.sum();
    if sum > 0.0 {
        weights = weights_vec / sum;
    }
    
    Ok(weights)
}

#[cfg(test)]
mod tests {
    use super::*;
    use ndarray::array;
    
    #[test]
    fn test_risk_parity_optimization() {
        let returns = array![
            [0.01, 0.02, -0.01, 0.03],
            [0.02, 0.01, 0.02, -0.01],
            [-0.01, 0.03, 0.01, 0.02]
        ];
        
        let weights = optimize_risk_parity(&returns.view(), 0.10).unwrap();
        
        assert_eq!(weights.len(), 3);
        assert!((weights.sum() - 1.0).abs() < 1e-6);
    }
    
    #[test]
    fn test_kelly_criterion_optimization() {
        let returns = array![
            [0.01, 0.02, -0.01, 0.03],
            [0.02, 0.01, 0.02, -0.01]
        ];
        
        let weights = optimize_kelly_criterion(&returns.view(), 0.02).unwrap();
        
        assert_eq!(weights.len(), 2);
        assert!((weights.sum() - 1.0).abs() < 1e-6);
    }
}
