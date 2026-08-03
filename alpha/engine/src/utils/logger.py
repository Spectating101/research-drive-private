import logging
import sys
from datetime import datetime
from typing import Optional
from pathlib import Path

class ColorFormatter(logging.Formatter):
    """Custom formatter with colors"""
    
    COLORS = {
        'DEBUG': '\033[36m',    # Cyan
        'INFO': '\033[32m',     # Green
        'WARNING': '\033[33m',  # Yellow
        'ERROR': '\033[31m',    # Red
        'CRITICAL': '\033[41m', # Red background
        'RESET': '\033[0m'      # Reset
    }

    def format(self, record):
        # Save original levelname
        orig_levelname = record.levelname
        # Add color to levelname
        record.levelname = f"{self.COLORS.get(record.levelname, '')}{record.levelname}{self.COLORS['RESET']}"
        # Format with color
        result = super().format(record)
        # Restore original levelname
        record.levelname = orig_levelname
        return result

def setup_logging(log_file: Optional[Path] = None):
    """Setup logging configuration"""
    logger = logging.getLogger('nocturnal_archive')
    logger.setLevel(logging.DEBUG)

    # Console handler with colors
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_format = ColorFormatter(
        '%(asctime)s [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_format)
    logger.addHandler(console_handler)

    # File handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(message)s (%(filename)s:%(lineno)d)',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        logger.addHandler(file_handler)

    return logger

# Create the main logger
logger = setup_logging()

def log_operation(operation_name: str):
    """Decorator to log function calls with timing"""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            start_time = datetime.now()
            logger.info(f"Starting {operation_name}...")
            try:
                result = await func(*args, **kwargs)
                duration = datetime.now() - start_time
                logger.info(f"Completed {operation_name} in {duration.total_seconds():.2f}s")
                return result
            except Exception as e:
                logger.error(f"Error in {operation_name}: {str(e)}")
                raise
        return wrapper
    return decorator