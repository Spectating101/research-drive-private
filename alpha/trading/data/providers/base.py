from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Protocol

import pandas as pd


@dataclass(frozen=True)
class BarsRequest:
    symbols: list[str]
    start: datetime | None = None
    end: datetime | None = None
    interval: str = "1d"  # e.g. 1d, 1h, 5m


class BarsProvider(Protocol):
    name: str

    def fetch_bars(self, req: BarsRequest) -> pd.DataFrame:
        """
        Return a tidy OHLCV dataframe:
          symbol, timestamp, open, high, low, close, volume
        """
        ...

