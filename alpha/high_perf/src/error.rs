use thiserror::Error;

#[derive(Error, Debug)]
pub enum SharpeError {
    #[error("Insufficient data for calculation")]
    InsufficientData,
    
    #[error("Invalid parameters: {message}")]
    InvalidParameters { message: String },
    
    #[error("Numerical computation error: {message}")]
    NumericalError { message: String },
    
    #[error("Matrix operation failed: {message}")]
    MatrixError { message: String },
    
    #[error("Optimization failed: {message}")]
    OptimizationError { message: String },
    
    #[error("Data processing error: {message}")]
    DataProcessingError { message: String },
    
    #[error("Memory allocation failed")]
    MemoryError,
    
    #[error("Thread pool error: {message}")]
    ThreadPoolError { message: String },
    
    #[error("Async operation failed: {message}")]
    AsyncError { message: String },
    
    #[error("Unknown error: {message}")]
    Unknown { message: String },
}

impl From<std::io::Error> for SharpeError {
    fn from(err: std::io::Error) -> Self {
        SharpeError::DataProcessingError {
            message: err.to_string(),
        }
    }
}

impl From<ndarray::ShapeError> for SharpeError {
    fn from(err: ndarray::ShapeError) -> Self {
        SharpeError::MatrixError {
            message: err.to_string(),
        }
    }
}

impl From<rayon::ThreadPoolBuildError> for SharpeError {
    fn from(err: rayon::ThreadPoolBuildError) -> Self {
        SharpeError::ThreadPoolError {
            message: err.to_string(),
        }
    }
}

impl From<serde_json::Error> for SharpeError {
    fn from(err: serde_json::Error) -> Self {
        SharpeError::DataProcessingError {
            message: err.to_string(),
        }
    }
}

impl From<std::num::ParseFloatError> for SharpeError {
    fn from(err: std::num::ParseFloatError) -> Self {
        SharpeError::NumericalError {
            message: err.to_string(),
        }
    }
}

impl From<std::num::ParseIntError> for SharpeError {
    fn from(err: std::num::ParseIntError) -> Self {
        SharpeError::NumericalError {
            message: err.to_string(),
        }
    }
}

impl From<Box<dyn std::error::Error + Send + Sync>> for SharpeError {
    fn from(err: Box<dyn std::error::Error + Send + Sync>) -> Self {
        SharpeError::Unknown {
            message: err.to_string(),
        }
    }
}

pub type SharpeResult<T> = Result<T, SharpeError>;
