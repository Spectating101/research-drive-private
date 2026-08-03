from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from .broker_base import AccountSnapshot, Broker, OrderRequest, OrderResult, Position


@dataclass
class _FileState:
    cash: float
    positions: Dict[str, float]  # shares


class FileBroker(Broker):
    """
    Broker simulator backed by local state + a price panel.

    Intended for validating safety gates and order generation without real broker credentials.
    """

    name = "file"

    def __init__(
        self,
        *,
        state_json: Path,
        panel_csv: Path,
        cash_symbol: str = "BIL",
        allow_shorts: bool = False,
        margin_multiplier: float = 1.0,
    ) -> None:
        self.state_json = Path(state_json)
        self.panel_csv = Path(panel_csv)
        self.cash_symbol = str(cash_symbol)
        self.allow_shorts = bool(allow_shorts)
        self.margin_multiplier = float(margin_multiplier)
        self._px = self._load_prices(panel_csv)
        self._state = self._load_state()

    def _load_prices(self, panel_csv: Path) -> pd.DataFrame:
        df = pd.read_csv(panel_csv, parse_dates=["Date"])
        need = {"Instrument", "Date", "Price_Close"}
        if not need.issubset(df.columns):
            raise ValueError(f"Panel must have columns: {sorted(need)}")
        df = df.dropna(subset=["Instrument", "Date", "Price_Close"]).copy()
        df["Price_Close"] = pd.to_numeric(df["Price_Close"], errors="coerce")
        df = df.dropna(subset=["Price_Close"])
        px = df.pivot_table(index="Date", columns="Instrument", values="Price_Close", aggfunc="last").sort_index().ffill()
        return px

    def _load_state(self) -> _FileState:
        if not self.state_json.exists():
            return _FileState(cash=0.0, positions={})
        raw = json.loads(self.state_json.read_text())
        return _FileState(
            cash=float(raw.get("cash", 0.0)),
            positions={str(k): float(v) for k, v in (raw.get("positions", {}) or {}).items()},
        )

    def _save_state(self) -> None:
        self.state_json.parent.mkdir(parents=True, exist_ok=True)
        self.state_json.write_text(json.dumps({"cash": self._state.cash, "positions": self._state.positions}, indent=2) + "\n")

    def get_last_price(self, symbol: str) -> Optional[float]:
        if self._px.empty or symbol not in self._px.columns:
            return None
        v = float(self._px.iloc[-1][symbol])
        return v if v == v and v > 0 else None

    def get_account(self) -> AccountSnapshot:
        equity = float(self._state.cash)
        for sym, sh in self._state.positions.items():
            px = self.get_last_price(sym) or 0.0
            equity += float(sh) * float(px)
        buying_power = float(equity) * float(self.margin_multiplier)
        return AccountSnapshot(equity=float(equity), cash=float(self._state.cash), buying_power=float(buying_power), currency="USD")

    def list_positions(self) -> List[Position]:
        out: List[Position] = []
        for sym, sh in self._state.positions.items():
            px = self.get_last_price(sym) or 0.0
            out.append(Position(symbol=sym, qty=float(sh), market_value=float(sh) * float(px)))
        return out

    def submit_order(self, order: OrderRequest) -> OrderResult:
        # Very small simulation: fills at limit_price if present else last price.
        px = order.limit_price or self.get_last_price(order.symbol)
        if px is None or px <= 0:
            raise RuntimeError(f"No price for {order.symbol}")
        side = str(order.side).upper()
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY/SELL")

        qty: float
        notional: float
        if order.qty is not None:
            qty = float(order.qty)
            notional = qty * float(px)
        elif order.notional is not None:
            notional = float(order.notional)
            qty = notional / float(px)
        else:
            raise ValueError("qty or notional required")

        if side == "BUY":
            if notional > self._state.cash:
                raise RuntimeError("Insufficient cash in FileBroker")
            self._state.cash -= float(notional)
            self._state.positions[order.symbol] = float(self._state.positions.get(order.symbol, 0.0) + qty)
        else:
            cur = float(self._state.positions.get(order.symbol, 0.0))
            if not self.allow_shorts:
                sell_qty = min(cur, qty)
                self._state.positions[order.symbol] = float(cur - sell_qty)
                self._state.cash += float(sell_qty * float(px))
                if abs(self._state.positions[order.symbol]) < 1e-9:
                    self._state.positions.pop(order.symbol, None)
            else:
                sell_qty = float(qty)
                self._state.positions[order.symbol] = float(cur - sell_qty)
                self._state.cash += float(sell_qty * float(px))
                if abs(self._state.positions[order.symbol]) < 1e-9:
                    self._state.positions.pop(order.symbol, None)

        self._save_state()
        return OrderResult(
            id=f"file-{order.symbol}-{side}",
            symbol=order.symbol,
            side=side,
            qty=float(qty) if order.qty is not None else None,
            notional=float(notional) if order.notional is not None else None,
            status="filled",
            raw={"fill_price": float(px)},
        )

    def cancel_all_orders(self) -> None:
        return None
