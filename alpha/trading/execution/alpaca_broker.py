from __future__ import annotations

import os
from dataclasses import asdict
from typing import Any, Dict, List, Optional

import requests

from .broker_base import AccountSnapshot, Broker, OrderRequest, OrderResult, Position


class AlpacaBroker(Broker):
    """
    Minimal Alpaca REST broker adapter.

    Safety notes:
      - This module is intentionally small and strict.
      - You must still wrap it with preflight checks and idempotency.
    """

    name = "alpaca"

    def __init__(
        self,
        *,
        api_key_id: Optional[str] = None,
        api_secret_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_s: float = 10.0,
    ) -> None:
        self.base_url = (base_url or os.getenv("ALPACA_BASE_URL") or "https://paper-api.alpaca.markets").rstrip("/")
        self.api_key_id = api_key_id or os.getenv("ALPACA_API_KEY_ID") or ""
        self.api_secret_key = api_secret_key or os.getenv("ALPACA_SECRET_KEY") or ""
        self.timeout_s = float(timeout_s)

        if not self.api_key_id or not self.api_secret_key:
            raise RuntimeError("Missing Alpaca credentials (ALPACA_API_KEY_ID / ALPACA_SECRET_KEY).")

        self._sess = requests.Session()
        self._sess.headers.update(
            {
                "APCA-API-KEY-ID": self.api_key_id,
                "APCA-API-SECRET-KEY": self.api_secret_key,
                "Accept": "application/json",
                "Content-Type": "application/json",
            }
        )

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return f"{self.base_url}{path}"

    def _get(self, path: str) -> Any:
        resp = self._sess.get(self._url(path), timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, payload: Dict[str, Any]) -> Any:
        resp = self._sess.post(self._url(path), json=payload, timeout=self.timeout_s)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> Any:
        resp = self._sess.delete(self._url(path), timeout=self.timeout_s)
        resp.raise_for_status()
        if not resp.text:
            return None
        try:
            return resp.json()
        except Exception:
            return resp.text

    def get_account(self) -> AccountSnapshot:
        raw = self._get("/v2/account")
        return AccountSnapshot(
            equity=float(raw.get("equity", 0.0)),
            cash=float(raw.get("cash", 0.0)),
            buying_power=float(raw.get("buying_power", 0.0)) if raw.get("buying_power") is not None else None,
            currency="USD",
        )

    def list_positions(self) -> List[Position]:
        raw = self._get("/v2/positions")
        out: List[Position] = []
        for p in raw or []:
            out.append(
                Position(
                    symbol=str(p.get("symbol", "")),
                    qty=float(p.get("qty", 0.0)),
                    market_value=float(p.get("market_value", 0.0)),
                )
            )
        return out

    def submit_order(self, order: OrderRequest) -> OrderResult:
        if (order.qty is None) == (order.notional is None):
            raise ValueError("Order must set exactly one of qty or notional.")
        side = str(order.side).strip().lower()
        if side not in {"buy", "sell"}:
            raise ValueError("side must be BUY or SELL.")
        order_type = str(order.order_type).strip().lower()
        if order_type not in {"market", "limit"}:
            raise ValueError("order_type must be market or limit.")
        tif = str(order.time_in_force).strip().lower()
        payload: Dict[str, Any] = {
            "symbol": order.symbol,
            "side": side,
            "type": order_type,
            "time_in_force": tif,
        }
        if order.qty is not None:
            payload["qty"] = str(float(order.qty))
        if order.notional is not None:
            payload["notional"] = str(float(order.notional))
        if order_type == "limit":
            if order.limit_price is None:
                raise ValueError("limit_price required for limit orders.")
            payload["limit_price"] = str(float(order.limit_price))

        raw = self._post("/v2/orders", payload)
        return OrderResult(
            id=str(raw.get("id", "")),
            symbol=str(raw.get("symbol", order.symbol)),
            side=str(raw.get("side", side)).upper(),
            qty=float(raw["qty"]) if raw.get("qty") is not None else None,
            notional=float(raw["notional"]) if raw.get("notional") is not None else None,
            status=str(raw.get("status", "")),
            raw=dict(raw),
        )

    def cancel_all_orders(self) -> None:
        self._delete("/v2/orders")

    def get_last_price(self, symbol: str) -> Optional[float]:
        """
        Best-effort last price.
        Uses Alpaca data endpoint if ALPACA_DATA_BASE_URL is set; otherwise None.
        """
        data_base = (os.getenv("ALPACA_DATA_BASE_URL") or "").rstrip("/")
        if not data_base:
            return None
        # v2/stocks/{symbol}/trades/latest
        url = f"{data_base}/v2/stocks/{symbol}/trades/latest"
        resp = self._sess.get(url, timeout=self.timeout_s)
        if resp.status_code != 200:
            return None
        try:
            raw = resp.json()
        except Exception:
            return None
        trade = raw.get("trade") or {}
        price = trade.get("p") or trade.get("price")
        try:
            return float(price)
        except Exception:
            return None

