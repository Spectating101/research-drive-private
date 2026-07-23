#!/usr/bin/env python3
"""
Database Setup and Maintenance Module

This module provides functions for initializing and maintaining our SQLite databases,
including a function to recalculate benchmark results using only rows with ranking_cat='top10'
from the benchmark_test_results table.
"""

import sqlite3
import numpy as np
import logging
import sys

# Configure logging to output to stdout
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)


def overwrite_result_with_top10_only(db_file='benchmark_result_final.db'):
    """
    Recomputes benchmark_results.result using ONLY rows with ranking_cat='top10'
    from the benchmark_test_results table and updates the benchmark_results table accordingly.

    Parameters:
        db_file (str): Path to the benchmark results SQLite database.
    """
    conn = None
    try:
        logger.info("Connecting to database: %s", db_file)
        conn = sqlite3.connect(db_file)
        c = conn.cursor()

        # Fetch all indicator combinations from benchmark_results
        logger.info("Fetching indicator combinations from benchmark_results table")
        combos = c.execute("SELECT id, combination FROM benchmark_results").fetchall()

        if not combos:
            logger.warning("No combinations found in benchmark_results table.")
            return

        for combo_id, combo_str in combos:
            logger.info("Processing combination id %s: %s", combo_id, combo_str)
            # Retrieve synergy values where ranking_cat is 'top10'
            rows = c.execute("""
                SELECT synergy
                  FROM benchmark_test_results
                 WHERE indicators = ?
                   AND ranking_cat = 'top10'
            """, (combo_str,)).fetchall()

            # Filter out None values and compute the average if available
            synergy_vals = [r[0] for r in rows if r[0] is not None]
            if synergy_vals:
                avg_synergy = float(np.mean(synergy_vals))
                logger.info("Calculated average synergy for combination '%s': %f", combo_str, avg_synergy)
            else:
                avg_synergy = None
                logger.warning("No valid synergy values for combination '%s'", combo_str)

            c.execute("""
                UPDATE benchmark_results
                   SET result = ?
                 WHERE id = ?
            """, (avg_synergy, combo_id))
            logger.info("Updated combination id %s with new result.", combo_id)

        conn.commit()
        logger.info("Database commit complete. Benchmark results updated.")
    except Exception as e:
        logger.error("Error during database update: %s", e, exc_info=True)
    finally:
        if conn:
            try:
                conn.close()
                logger.info("Database connection closed.")
            except Exception as close_error:
                logger.error("Error closing database connection: %s", close_error)


if __name__ == "__main__":
    overwrite_result_with_top10_only()
    print("Recalculated benchmark_results.result using ONLY top10 synergy rows.")
