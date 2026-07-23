from __future__ import annotations

"""
Vendor adapter stubs (Bloomberg / Refinitiv / WRDS).

This file exists to turn Upwork "terminal data" jobs into a clean engineering surface:
- one interface per vendor
- consistent outputs (TidyPanel + optional events tables)

These are intentionally stubs: in this workspace we don't assume credentials.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

import os
import pandas as pd

from src.data_sources.tidy_panel import TidyPanel


@dataclass(frozen=True)
class VendorConfig:
    name: str
    env_prefix: str

    def keys_present(self) -> bool:
        # Minimal heuristic: any env var with prefix exists.
        pref = self.env_prefix.upper()
        return any(k.startswith(pref) and os.getenv(k) for k in os.environ.keys())


class BloombergAdapter:
    """
    Placeholder for Bloomberg API integration (blpapi / bql / terminal exports).
    Expected deliverable: implement `fetch_tidy_panel()` for a list of tickers.
    """

    config = VendorConfig(name="bloomberg", env_prefix="BLOOMBERG_")

    def fetch_tidy_panel(self, tickers: List[str], *, start: str, end: str) -> TidyPanel:
        raise NotImplementedError(
            "Bloomberg adapter not configured in this repo snapshot. "
            "Implement using blpapi or by ingesting terminal-exported CSVs into the tidy contract."
        )


class RefinitivAdapter:
    """
    Placeholder for Refinitiv (RDP / Eikon) integration.
    If you have local Refinitiv patches already in `From-refinitiv/`, you can also map those into the tidy contract.
    """

    config = VendorConfig(name="refinitiv", env_prefix="REFINITIV_")

    def fetch_tidy_panel(self, tickers: List[str], *, start: str, end: str) -> TidyPanel:
        raise NotImplementedError(
            "Refinitiv adapter not configured in this repo snapshot. "
            "Implement using RDP/Eikon SDK or map local patch data into the tidy contract."
        )


class WrdsAdapter:
    """
    Placeholder for WRDS (typically via PostgreSQL + python client).
    Often used for CRSP/Compustat/event-study datasets.
    """

    config = VendorConfig(name="wrds", env_prefix="WRDS_")

    def fetch_events_table(self, *, query: str) -> pd.DataFrame:
        raise NotImplementedError(
            "WRDS adapter not configured in this repo snapshot. "
            "Implement by connecting to WRDS and returning a normalized events table."
        )


__all__ = ["BloombergAdapter", "RefinitivAdapter", "WrdsAdapter", "VendorConfig"]

