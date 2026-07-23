from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd

from trading.data.providers.base import BarsProvider, BarsRequest


@dataclass(frozen=True)
class YFinanceProvider(BarsProvider):
    name: str = "yfinance"

    def fetch_bars(self, req: BarsRequest) -> pd.DataFrame:
        import yfinance as yf

        symbols = list(dict.fromkeys([s for s in req.symbols if s]))
        if not symbols:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

        start: Optional[str] = req.start.strftime("%Y-%m-%d") if req.start else None
        end: Optional[str] = req.end.strftime("%Y-%m-%d") if req.end else None

        df = yf.download(
            symbols,
            start=start,
            end=end,
            interval=req.interval,
            auto_adjust=False,
            group_by="ticker",
            threads=True,
            progress=False,
        )
        if df is None or df.empty:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])

        frames: list[pd.DataFrame] = []
        if isinstance(df.columns, pd.MultiIndex):
            # Depending on version: (Field, Ticker) or (Ticker, Field)
            lvl0 = [str(x) for x in df.columns.get_level_values(0)]
            ticker_first = any(t in set(lvl0) for t in symbols)
            for sym in symbols:
                try:
                    sub = df.xs(sym, axis=1, level=0 if ticker_first else 1, drop_level=True)
                except Exception:
                    continue
                if sub is None or sub.empty:
                    continue
                sub = sub.reset_index()
                ts_col = "Date" if "Date" in sub.columns else ("Datetime" if "Datetime" in sub.columns else None)
                if ts_col is None:
                    continue
                out = pd.DataFrame(
                    {
                        "symbol": sym,
                        "timestamp": pd.to_datetime(sub[ts_col], errors="coerce"),
                        "open": pd.to_numeric(sub.get("Open"), errors="coerce"),
                        "high": pd.to_numeric(sub.get("High"), errors="coerce"),
                        "low": pd.to_numeric(sub.get("Low"), errors="coerce"),
                        "close": pd.to_numeric(sub.get("Close"), errors="coerce"),
                        "volume": pd.to_numeric(sub.get("Volume"), errors="coerce") if "Volume" in sub.columns else pd.NA,
                    }
                ).dropna(subset=["timestamp", "close"])
                if not out.empty:
                    frames.append(out)
        else:
            if len(symbols) == 1:
                sub = df.reset_index()
                ts_col = "Date" if "Date" in sub.columns else ("Datetime" if "Datetime" in sub.columns else None)
                if ts_col is None:
                    return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
                out = pd.DataFrame(
                    {
                        "symbol": symbols[0],
                        "timestamp": pd.to_datetime(sub[ts_col], errors="coerce"),
                        "open": pd.to_numeric(sub.get("Open"), errors="coerce"),
                        "high": pd.to_numeric(sub.get("High"), errors="coerce"),
                        "low": pd.to_numeric(sub.get("Low"), errors="coerce"),
                        "close": pd.to_numeric(sub.get("Close"), errors="coerce"),
                        "volume": pd.to_numeric(sub.get("Volume"), errors="coerce") if "Volume" in sub.columns else pd.NA,
                    }
                ).dropna(subset=["timestamp", "close"])
                frames.append(out)

        if not frames:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        out = pd.concat(frames, ignore_index=True)
        out = out.sort_values(["symbol", "timestamp"]).reset_index(drop=True)
        return out

