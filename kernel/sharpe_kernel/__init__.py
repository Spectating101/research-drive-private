"""Shared contract between Research Drive (procurement) and Alpha engine."""

from sharpe_kernel.paths import alpha_root, data_lake_root, drive_root, registry_path, repo_root
from sharpe_kernel.platform_bridge import (
    FUSED_DATASET_ID,
    STRESS_COLS,
    global_news_risk_overlay,
    load_integration_config,
    load_registry,
    market_relevance_overlay,
    resolve_dataset_parquet,
)

__all__ = [
    "FUSED_DATASET_ID",
    "STRESS_COLS",
    "alpha_root",
    "data_lake_root",
    "drive_root",
    "global_news_risk_overlay",
    "load_integration_config",
    "load_registry",
    "market_relevance_overlay",
    "registry_path",
    "repo_root",
    "resolve_dataset_parquet",
]
