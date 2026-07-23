#!/usr/bin/env python3
"""
Comprehensive Helper Functions Module

This module provides a collection of utility functions and context managers
designed to reduce code duplication and improve maintainability across the
trading system project.

Features include:
  • Database connection management with automatic retries.
  • Query execution with standardized logging and error handling.
  • Decorators for timing and logging function execution.
  • Data conversion utilities (safe_float, safe_int, safe_str).
  • Date formatting and parsing helpers.
  • File input/output helpers for JSON and CSV.
  • Retry mechanisms with exponential backoff.
  • Dictionary merging and other common utility functions.

This module is intended to encapsulate all the repetitive and verbose code
that may have been repeated in your large files, so that your main modules
can call these helpers and remain concise and maintainable.
"""

import sqlite3
import logging
import time
import json
import csv
import os
from contextlib import contextmanager
from datetime import datetime
import pandas as pd

# Setup logger for this module
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)  # Set to DEBUG for detailed output
handler = logging.StreamHandler()
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)


# --- Database Connection Management ---

@contextmanager
def get_db_connection(db_path, timeout=5, retries=3):
    """
    Context manager for establishing a SQLite database connection.
    Automatically retries connection attempts on failure.

    Parameters:
        db_path (str): Path to the SQLite database file.
        timeout (int): Time in seconds to wait before retrying.
        retries (int): Number of retry attempts.

    Yields:
        sqlite3.Connection: The database connection object.
    """
    attempt = 0
    conn = None
    while attempt < retries:
        try:
            conn = sqlite3.connect(db_path)
            logger.debug("Connected to database: %s", db_path)
            yield conn
            return
        except Exception as e:
            attempt += 1
            logger.error("Connection attempt %d failed for %s: %s", attempt, db_path, e)
            time.sleep(timeout * attempt)
        finally:
            if conn:
                try:
                    conn.close()
                    logger.debug("Closed database connection: %s", db_path)
                except Exception as close_err:
                    logger.error("Error closing connection: %s", close_err)
    raise Exception(f"Failed to connect to database {db_path} after {retries} attempts.")


def execute_query(db_path, query, params=(), commit=False):
    """
    Execute a SQL query using a managed database connection.

    Parameters:
        db_path (str): Path to the SQLite database.
        query (str): SQL query to execute.
        params (tuple): Parameters to pass into the query.
        commit (bool): Whether to commit the transaction.

    Returns:
        list: The fetched results from the query.
    """
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        try:
            logger.debug("Executing query: %s | Params: %s", query, params)
            cursor.execute(query, params)
            results = cursor.fetchall()
            if commit:
                conn.commit()
                logger.debug("Transaction committed.")
            logger.debug("Query result: %s", results)
            return results
        except Exception as e:
            logger.error("Query execution failed: %s", e, exc_info=True)
            raise


# --- Function Timing and Logging Decorator ---

def log_elapsed_time(func):
    """
    Decorator that logs the elapsed time for a function's execution.

    Usage:
        @log_elapsed_time
        def my_function(...):
            ...

    Returns:
        The result of the function call.
    """
    def wrapper(*args, **kwargs):
        start = time.time()
        result = func(*args, **kwargs)
        elapsed = time.time() - start
        logger.info("Function '%s' executed in %.3f seconds", func.__name__, elapsed)
        return result
    return wrapper


# --- Retry Mechanism with Exponential Backoff ---

def retry_operation(operation, max_retries=5, initial_delay=1):
    """
    Retry a callable operation with exponential backoff if it fails.

    Parameters:
        operation (callable): The function to execute.
        max_retries (int): Maximum number of retries.
        initial_delay (int): Initial delay in seconds before retrying.

    Returns:
        The result of the operation if successful.

    Raises:
        Exception: If all retry attempts fail.
    """
    delay = initial_delay
    for attempt in range(1, max_retries + 1):
        try:
            result = operation()
            logger.debug("Operation succeeded on attempt %d", attempt)
            return result
        except Exception as e:
            logger.error("Attempt %d failed: %s", attempt, e, exc_info=True)
            if attempt < max_retries:
                time.sleep(delay)
                delay *= 2
            else:
                raise Exception("Operation failed after maximum retries.")
    return None


# --- Data Conversion Utilities ---

def safe_float(value, default=0.0):
    """
    Safely convert a value to a float, returning a default if conversion fails.

    Parameters:
        value: The value to convert.
        default (float): The default value to return if conversion fails.

    Returns:
        float: The converted float value or default.
    """
    try:
        return float(value)
    except Exception as e:
        logger.warning("safe_float conversion failed for '%s': %s", value, e)
        return default

def safe_int(value, default=0):
    """
    Safely convert a value to an integer, returning a default if conversion fails.

    Parameters:
        value: The value to convert.
        default (int): The default value to return if conversion fails.

    Returns:
        int: The converted integer value or default.
    """
    try:
        return int(value)
    except Exception as e:
        logger.warning("safe_int conversion failed for '%s': %s", value, e)
        return default

def safe_str(value, default=""):
    """
    Safely convert a value to a string.

    Parameters:
        value: The value to convert.
        default (str): The default value to return if conversion fails.

    Returns:
        str: The converted string value or default.
    """
    try:
        return str(value)
    except Exception as e:
        logger.warning("safe_str conversion failed for '%s': %s", value, e)
        return default


# --- Date Formatting and Parsing Helpers ---

def format_date(dt, fmt='%Y-%m-%d'):
    """
    Format a datetime object into a string using the given format.

    Parameters:
        dt (datetime): The datetime object.
        fmt (str): The format string.

    Returns:
        str: The formatted date string.
    """
    try:
        return dt.strftime(fmt)
    except Exception as e:
        logger.error("Error formatting date: %s", e)
        return ""

def parse_date(date_str, fmt='%Y-%m-%d'):
    """
    Parse a date string into a datetime object.

    Parameters:
        date_str (str): The date string.
        fmt (str): The format string.

    Returns:
        datetime: The parsed datetime object, or None on failure.
    """
    try:
        return datetime.strptime(date_str, fmt)
    except Exception as e:
        logger.error("Error parsing date string '%s': %s", date_str, e)
        return None


# --- File Input/Output Helpers ---

def read_json(file_path):
    """
    Read and parse JSON data from a file.

    Parameters:
        file_path (str): Path to the JSON file.

    Returns:
        dict: Parsed JSON data, or an empty dict if an error occurs.
    """
    try:
        with open(file_path, 'r') as f:
            data = json.load(f)
            logger.info("Successfully read JSON from %s", file_path)
            return data
    except Exception as e:
        logger.error("Error reading JSON file %s: %s", file_path, e)
        return {}

def write_json(file_path, data, indent=2):
    """
    Write data to a JSON file.

    Parameters:
        file_path (str): Path to the output JSON file.
        data (dict): Data to write.
        indent (int): Indentation level.

    Returns:
        bool: True if writing was successful, False otherwise.
    """
    try:
        with open(file_path, 'w') as f:
            json.dump(data, f, indent=indent)
        logger.info("Successfully wrote JSON to %s", file_path)
        return True
    except Exception as e:
        logger.error("Error writing JSON to %s: %s", file_path, e)
        return False

def read_csv(file_path):
    """
    Read a CSV file into a Pandas DataFrame.

    Parameters:
        file_path (str): Path to the CSV file.

    Returns:
        DataFrame: The loaded DataFrame, or None if an error occurs.
    """
    try:
        df = pd.read_csv(file_path)
        logger.info("Successfully read CSV from %s", file_path)
        return df
    except Exception as e:
        logger.error("Error reading CSV file %s: %s", file_path, e)
        return None

def write_csv(file_path, df):
    """
    Write a Pandas DataFrame to a CSV file.

    Parameters:
        file_path (str): Path to the CSV file.
        df (DataFrame): DataFrame to write.

    Returns:
        bool: True if writing was successful, False otherwise.
    """
    try:
        df.to_csv(file_path, index=False)
        logger.info("Successfully wrote DataFrame to CSV %s", file_path)
        return True
    except Exception as e:
        logger.error("Error writing DataFrame to CSV %s: %s", file_path, e)
        return False


# --- Dictionary and Miscellaneous Helpers ---

def merge_dicts(*dicts):
    """
    Merge multiple dictionaries into one.

    Parameters:
        *dicts: Variable number of dictionary arguments.

    Returns:
        dict: A merged dictionary.
    """
    result = {}
    for d in dicts:
        result.update(d)
    logger.debug("Dictionaries merged into: %s", result)
    return result

def print_debug_info(label, data):
    """
    Print debug information with a label.
    
    Parameters:
        label (str): Description of the data.
        data: The data to print.
    """
    logger.debug("%s: %s", label, data)


# --- Additional Helper Functions ---

def calculate_percentage_change(old, new):
    """
    Calculate the percentage change from old to new value.

    Parameters:
        old (float): The original value.
        new (float): The new value.

    Returns:
        float: Percentage change.
    """
    try:
        if old == 0:
            return 0.0
        return ((new - old) / old) * 100.0
    except Exception as e:
        logger.error("Error calculating percentage change: %s", e)
        return 0.0


# --- End of Helpers Module ---

if __name__ == "__main__":
    # Quick tests for helper functions
    test_db = "test.db"
    try:
        with get_db_connection(test_db) as conn:
            logger.info("Test DB connection successful.")
    except Exception as e:
        logger.error("Test DB connection failed: %s", e)

    # Test date formatting
    now = datetime.now()
    formatted = format_date(now)
    logger.info("Formatted current date: %s", formatted)

    # Test JSON read/write
    sample_data = {"key": "value", "number": 123}
    if write_json("sample.json", sample_data):
        read_data = read_json("sample.json")
        logger.info("Read JSON data: %s", read_data)

    # Test CSV read/write with a simple DataFrame
    df_test = pd.DataFrame({"A": [1, 2, 3], "B": [4, 5, 6]})
    if write_csv("sample.csv", df_test):
        df_loaded = read_csv("sample.csv")
        logger.info("Loaded CSV DataFrame:\n%s", df_loaded)

    # Test merge_dicts
    d1 = {"a": 1, "b": 2}
    d2 = {"b": 3, "c": 4}
    merged = merge_dicts(d1, d2)
    logger.info("Merged dictionary: %s", merged)

    logger.info("Helper functions module test complete.")
