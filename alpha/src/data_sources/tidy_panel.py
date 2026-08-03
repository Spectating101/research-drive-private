from __future__ import annotations

"""
Tidy panel utilities and a simple contract used across scripts and data sources.

Contract (tidy):
  Instrument, Date, Price_Close, Volume(optional)
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd


@dataclass(frozen=True)
class TidyPanel:
    prices: pd.DataFrame  # Date index, Instrument columns
    volumes: Optional[pd.DataFrame]  # Date index, Instrument columns (may be None)


def load_tidy_panel_csv(panel_csv: Path) -> TidyPanel:
    df = pd.read_csv(panel_csv)
    if not {"Instrument", "Date", "Price_Close"}.issubset(df.columns):
        raise ValueError("Panel must have columns: Instrument, Date, Price_Close, Volume(optional)")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["Date", "Instrument", "Price_Close"]).copy()
    df["Price_Close"] = pd.to_numeric(df["Price_Close"], errors="coerce")
    df = df.dropna(subset=["Price_Close"])
    if "Volume" in df.columns:
        df["Volume"] = pd.to_numeric(df["Volume"], errors="coerce")

    prices = df.pivot(index="Date", columns="Instrument", values="Price_Close").sort_index()
    prices = prices.ffill()
    volumes = None
    if "Volume" in df.columns:
        volumes = df.pivot(index="Date", columns="Instrument", values="Volume").sort_index()
    return TidyPanel(prices=prices, volumes=volumes)


__all__ = ["TidyPanel", "load_tidy_panel_csv"]

