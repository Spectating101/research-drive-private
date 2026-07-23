use pyo3::prelude::*;
use pyo3::wrap_pyfunction;
use pyo3::types::PyDict;
use numpy::{IntoPyArray, PyArray1, PyArray2};
use ndarray::{Array1, Array2, ArrayView1, ArrayView2, s};
use rayon::prelude::*;

pub mod error;
pub mod market_microstructure;
pub mod portfolio_optimization;
pub mod parallel_processing;
pub mod technical_indicators;

use market_microstructure::{calculate_all_liquidity_metrics, calculate_price_discovery_metrics};

fn mean_view_1d(data: ArrayView1<f64>) -> f64 {
    if data.is_empty() {
        return 0.0;
    }
    data.iter().sum::<f64>() / data.len() as f64
}

/// A Python module implemented in Rust.
#[pymodule]
fn sharpe_rust(_py: Python, m: &PyModule) -> PyResult<()> {
    // Technical indicators
    m.add_function(wrap_pyfunction!(calculate_ema_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_rsi_parallel, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_sma_parallel, m)?)?;
    
    // Parallel processing
    m.add_function(wrap_pyfunction!(parallel_correlation_matrix, m)?)?;
    m.add_function(wrap_pyfunction!(parallel_returns_calculation, m)?)?;

    // Market Microstructure (NEW)
    m.add_function(wrap_pyfunction!(calculate_microstructure_metrics, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_discovery_metrics, m)?)?;
    
    Ok(())
}

#[pyfunction]
fn calculate_microstructure_metrics(
    py: Python,
    prices: &PyArray2<f64>,
    volumes: &PyArray1<f64>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array().to_owned() };
    let volumes_array = unsafe { volumes.as_array().to_owned() };

    let result = py
        .allow_threads(|| calculate_all_liquidity_metrics(&prices_array, &volumes_array))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;
        
    let result_dict = PyDict::new(py);
    for (key, value) in result {
        result_dict.set_item(key, value)?;
    }
    
    Ok(result_dict.into())
}

#[pyfunction]
fn calculate_discovery_metrics(
    py: Python,
    prices: &PyArray2<f64>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array().to_owned() };

    let result = py
        .allow_threads(|| calculate_price_discovery_metrics(&prices_array))
        .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(format!("{}", e)))?;
        
    let result_dict = PyDict::new(py);
    for (key, value) in result {
        result_dict.set_item(key, value)?;
    }
    
    Ok(result_dict.into())
}

#[pyfunction]
fn calculate_ema_parallel(
    py: Python,
    prices: &PyArray1<f64>,
    periods: Vec<usize>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array() };
    
    let result = py.allow_threads(|| {
        periods.par_iter().map(|&period| {
            let ema = calculate_ema(&prices_array, period);
            (period, ema)
        }).collect::<Vec<_>>()
    });
    
    let result_dict = PyDict::new(py);
    
    for (period, values) in result {
        let py_array = values.into_pyarray(py);
        result_dict.set_item(format!("ema_{}", period), py_array)?;
    }
    
    Ok(result_dict.into())
}

#[pyfunction]
fn calculate_rsi_parallel(
    py: Python,
    prices: &PyArray1<f64>,
    periods: Vec<usize>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array() };
    
    let result = py.allow_threads(|| {
        periods.par_iter().map(|&period| {
            let rsi = calculate_rsi(&prices_array, period);
            (period, rsi)
        }).collect::<Vec<_>>()
    });
    
    let result_dict = PyDict::new(py);
    
    for (period, values) in result {
        let py_array = values.into_pyarray(py);
        result_dict.set_item(format!("rsi_{}", period), py_array)?;
    }
    
    Ok(result_dict.into())
}

#[pyfunction]
fn calculate_sma_parallel(
    py: Python,
    prices: &PyArray1<f64>,
    periods: Vec<usize>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array() };
    
    let result = py.allow_threads(|| {
        periods.par_iter().map(|&period| {
            let sma = calculate_sma(&prices_array, period);
            (period, sma)
        }).collect::<Vec<_>>()
    });
    
    let result_dict = PyDict::new(py);
    
    for (period, values) in result {
        let py_array = values.into_pyarray(py);
        result_dict.set_item(format!("sma_{}", period), py_array)?;
    }
    
    Ok(result_dict.into())
}

#[pyfunction]
fn parallel_correlation_matrix(
    py: Python,
    returns: &PyArray2<f64>,
) -> PyResult<PyObject> {
    let returns_array = unsafe { returns.as_array() };
    
    let result = py.allow_threads(|| {
        calculate_correlation_matrix(&returns_array)
    });
    
    Ok(result.into_pyarray(py).into())
}

#[pyfunction]
fn parallel_returns_calculation(
    py: Python,
    prices: &PyArray2<f64>,
) -> PyResult<PyObject> {
    let prices_array = unsafe { prices.as_array() };
    
    let result = py.allow_threads(|| {
        calculate_returns(&prices_array)
    });
    
    Ok(result.into_pyarray(py).into())
}

// Helper functions (Kept local for now, could be moved to modules)
fn calculate_ema(prices: &ArrayView1<f64>, period: usize) -> Array1<f64> {
    if prices.len() < period {
        return Array1::zeros(prices.len());
    }
    
    let mut ema = Array1::zeros(prices.len());
    let alpha = 2.0 / (period as f64 + 1.0);
    
    // Initialize with SMA
    let initial_sma = prices.slice(s![..period]).sum() / period as f64;
    ema[period - 1] = initial_sma;
    
    // Calculate EMA
    for i in period..prices.len() {
        ema[i] = alpha * prices[i] + (1.0 - alpha) * ema[i - 1];
    }
    
    ema
}

fn calculate_rsi(prices: &ArrayView1<f64>, period: usize) -> Array1<f64> {
    if prices.len() < period + 1 {
        return Array1::zeros(prices.len());
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
    let avg_gain = gains.slice(s![1..=period]).sum() / period as f64;
    let avg_loss = losses.slice(s![1..=period]).sum() / period as f64;
    
    if avg_loss == 0.0 {
        rsi[period] = 100.0;
    } else {
        let rs = avg_gain / avg_loss;
        rsi[period] = 100.0 - (100.0 / (1.0 + rs));
    }
    
    // Calculate RSI for remaining periods
    for i in period + 1..prices.len() {
        let gain = gains[i];
        let loss = losses[i];
        
        let avg_gain = (avg_gain * (period as f64 - 1.0) + gain) / period as f64;
        let avg_loss = (avg_loss * (period as f64 - 1.0) + loss) / period as f64;
        
        if avg_loss == 0.0 {
            rsi[i] = 100.0;
        } else {
            let rs = avg_gain / avg_loss;
            rsi[i] = 100.0 - (100.0 / (1.0 + rs));
        }
    }
    
    rsi
}

fn calculate_sma(prices: &ArrayView1<f64>, period: usize) -> Array1<f64> {
    if prices.len() < period {
        return Array1::zeros(prices.len());
    }
    
    let mut sma = Array1::zeros(prices.len());
    
    // Calculate initial SMA
    let initial_sma = prices.slice(s![..period]).sum() / period as f64;
    sma[period - 1] = initial_sma;
    
    // Calculate SMA for remaining periods
    for i in period..prices.len() {
        let sum: f64 = prices.slice(s![i - period + 1..=i]).sum();
        sma[i] = sum / period as f64;
    }
    
    sma
}

fn calculate_correlation_matrix(returns: &ArrayView2<f64>) -> Array2<f64> {
    let (n_rows, n_cols) = returns.dim();
    let mut corr_matrix = Array2::zeros((n_cols, n_cols));
    
    for i in 0..n_cols {
        for j in 0..n_cols {
            if i == j {
                corr_matrix[[i, j]] = 1.0;
            } else {
                let col_i = returns.column(i);
                let col_j = returns.column(j);
                
                let mean_i = mean_view_1d(col_i);
                let mean_j = mean_view_1d(col_j);
                
                let mut numerator = 0.0;
                let mut var_i: f64 = 0.0;
                let mut var_j: f64 = 0.0;
                
                for k in 0..n_rows {
                    let diff_i = col_i[k] - mean_i;
                    let diff_j = col_j[k] - mean_j;
                    
                    numerator += diff_i * diff_j;
                    var_i += diff_i * diff_i;
                    var_j += diff_j * diff_j;
                }
                
                if var_i > 0.0 && var_j > 0.0 {
                    corr_matrix[[i, j]] = numerator / (var_i.sqrt() * var_j.sqrt());
                }
            }
        }
    }
    
    corr_matrix
}

fn calculate_returns(prices: &ArrayView2<f64>) -> Array2<f64> {
    let (n_rows, n_cols) = prices.dim();
    let mut returns = Array2::zeros((n_rows - 1, n_cols));
    
    for i in 1..n_rows {
        for j in 0..n_cols {
            if prices[[i - 1, j]] > 0.0 {
                returns[[i - 1, j]] = (prices[[i, j]] / prices[[i - 1, j]] - 1.0).ln();
            }
        }
    }
    
    returns
}
