from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

import pandas as pd

from trading.data.providers.base import BarsProvider, BarsRequest


@dataclass(frozen=True)
class RefinitivOfflineProvider(BarsProvider):
    """
    Offline provider reading a tidy Refinitiv-converted panel:
      Instrument, Date, Price_Close, Volume
    """

    panel_csv: Path
    name: str = "refinitiv_offline"

    def fetch_bars(self, req: BarsRequest) -> pd.DataFrame:
        if not self.panel_csv.exists():
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

        df = pd.read_csv(self.panel_csv, parse_dates=["Date"])
        need = {"Instrument", "Date", "Price_Close"}
        if not need.issubset(df.columns):
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

        df = df[df["Instrument"].isin(req.symbols)].copy()
        if req.start is not None:
            df = df[df["Date"] >= pd.Timestamp(req.start)]
        if req.end is not None:
            df = df[df["Date"] <= pd.Timestamp(req.end)]

        df["close"] = pd.to_numeric(df["Price_Close"], errors="coerce")
        df["volume"] = pd.to_numeric(df["Volume"], errors="coerce") if "Volume" in df.columns else pd.NA
        df = df.dropna(subset=["close", "Date"])

        # Refinitiv panel is daily; we approximate OHLC with close when needed.
        out = pd.DataFrame(
            {
                "symbol": df["Instrument"].astype(str),
                "timestamp": pd.to_datetime(df["Date"], errors="coerce"),
                "open": df["close"],
                "high": df["close"],
                "low": df["close"],
                "close": df["close"],
                "volume": df["volume"],
            }
        ).dropna(subset=["timestamp", "close"])
        out = out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return out

