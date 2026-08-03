from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass(frozen=True)
class Position:
    symbol: str
    qty: float
    market_value: float


@dataclass(frozen=True)
class AccountSnapshot:
    equity: float
    cash: float
    buying_power: Optional[float] = None
    currency: str = "USD"


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: str  # BUY/SELL
    qty: Optional[float] = None
    notional: Optional[float] = None
    order_type: str = "market"  # market/limit
    time_in_force: str = "day"
    limit_price: Optional[float] = None


@dataclass(frozen=True)
class OrderResult:
    id: str
    symbol: str
    side: str
    qty: Optional[float]
    notional: Optional[float]
    status: str
    raw: dict


class Broker:
    name: str

    def get_account(self) -> AccountSnapshot:
        raise NotImplementedError

    def list_positions(self) -> List[Position]:
        raise NotImplementedError

    def submit_order(self, order: OrderRequest) -> OrderResult:
        raise NotImplementedError

    def cancel_all_orders(self) -> None:
        raise NotImplementedError

    def get_last_price(self, symbol: str) -> Optional[float]:
        raise NotImplementedError

