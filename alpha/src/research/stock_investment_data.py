"""Stock-investment data facade and universe helpers.

This is the first thin layer that prevents new investment modules from reading
random files ad hoc. It keeps schemas, freshness, and universe hashes in one
place while still using the repo's existing CSV/JSON artifacts.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd


PRICE_PANEL_COLUMNS = ("Instrument", "Date", "Price_Close")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _find_col(df: pd.DataFrame, candidates: Sequence[str], *, required: bool = True) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for cand in candidates:
        if cand in df.columns:
            return cand
        if cand.lower() in lower:
            return lower[cand.lower()]
    if required:
        raise ValueError(f"missing required column; tried {list(candidates)}")
    return None


def canonicalize_price_panel(df: pd.DataFrame) -> pd.DataFrame:
    """Return a tidy price panel with Instrument, Date, Price_Close columns."""
    inst = _find_col(df, ["Instrument", "instrument", "ticker", "symbol"])
    date = _find_col(df, ["Date", "date"])
    price = _find_col(df, ["Price_Close", "price_close", "close", "Close", "adj_close", "Adj Close"])
    out = df[[inst, date, price]].copy()
    out.columns = list(PRICE_PANEL_COLUMNS)
    out["Instrument"] = out["Instrument"].astype(str)
    out["Date"] = pd.to_datetime(out["Date"], errors="coerce")
    out["Price_Close"] = pd.to_numeric(out["Price_Close"], errors="coerce")
    out = out.dropna(subset=["Instrument", "Date", "Price_Close"])
    out = out.sort_values(["Instrument", "Date"]).drop_duplicates(["Instrument", "Date"], keep="last")
    return out


def load_price_panel(path: Path) -> pd.DataFrame:
    return canonicalize_price_panel(pd.read_csv(path))


def price_panel_wide(path: Path) -> pd.DataFrame:
    panel = load_price_panel(path)
    wide = panel.pivot_table(index="Date", columns="Instrument", values="Price_Close", aggfunc="last")
    return wide.sort_index().ffill()


@dataclass(frozen=True)
class PanelFreshness:
    path: str
    exists: bool
    latest_date: str | None
    n_instruments: int
    n_rows: int
    max_staleness_days: int | None
    stale: bool | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "latest_date": self.latest_date,
            "n_instruments": self.n_instruments,
            "n_rows": self.n_rows,
            "max_staleness_days": self.max_staleness_days,
            "stale": self.stale,
        }


def panel_freshness(path: Path, *, as_of: str | None = None, max_staleness_days: int | None = 5) -> PanelFreshness:
    path = Path(path)
    if not path.exists():
        return PanelFreshness(str(path), False, None, 0, 0, max_staleness_days, None)
    panel = load_price_panel(path)
    latest = panel["Date"].max()
    latest_str = latest.date().isoformat() if pd.notna(latest) else None
    stale = None
    if latest_str and max_staleness_days is not None:
        ref = pd.Timestamp(as_of) if as_of else pd.Timestamp.utcnow().tz_localize(None)
        stale = bool((ref.normalize() - pd.Timestamp(latest).normalize()).days > max_staleness_days)
    return PanelFreshness(
        path=str(path),
        exists=True,
        latest_date=latest_str,
        n_instruments=int(panel["Instrument"].nunique()),
        n_rows=int(len(panel)),
        max_staleness_days=max_staleness_days,
        stale=stale,
    )


def universe_from_panel(path: Path, *, as_of: str | None = None) -> list[str]:
    panel = load_price_panel(path)
    if as_of:
        panel = panel[panel["Date"] <= pd.Timestamp(as_of)]
    if panel.empty:
        return []
    latest_by_inst = panel.groupby("Instrument")["Date"].max()
    latest_global = latest_by_inst.max()
    active = latest_by_inst[latest_by_inst == latest_global].index
    return sorted(str(x) for x in active)


def universe_hash(tickers: Sequence[str]) -> str:
    payload = "\n".join(sorted(str(t).strip().upper() for t in tickers if str(t).strip()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def make_universe_record(
    *,
    universe_id: str,
    tickers: Sequence[str],
    source: str,
    as_of: str | None = None,
    notes: str = "",
) -> dict[str, Any]:
    clean = sorted(str(t).strip().upper() for t in tickers if str(t).strip())
    return {
        "universe_id": universe_id,
        "as_of": as_of or _utc_now()[:10],
        "source": source,
        "n_tickers": len(clean),
        "universe_hash": universe_hash(clean),
        "tickers": clean,
        "notes": notes,
        "updated_at": _utc_now(),
    }


def upsert_universe_registry(path: Path, record: Mapping[str, Any]) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]]
    if path.exists():
        data = json.loads(path.read_text())
        rows = data if isinstance(data, list) else data.get("universes", [])
    else:
        rows = []
    rows = [
        r for r in rows
        if not (
            str(r.get("universe_id")) == str(record.get("universe_id"))
            and str(r.get("as_of")) == str(record.get("as_of"))
        )
    ]
    rows.append(dict(record))
    rows.sort(key=lambda r: (str(r.get("universe_id")), str(r.get("as_of"))))
    path.write_text(json.dumps({"universes": rows}, indent=2, sort_keys=True) + "\n")
    return path


def load_candidate_registry(path: Path) -> pd.DataFrame:
    return pd.read_csv(path) if Path(path).exists() else pd.DataFrame()


def load_thesis_register(path: Path) -> pd.DataFrame:
    return pd.read_csv(path, dtype=str).fillna("") if Path(path).exists() else pd.DataFrame()


def load_json_artifact(path: Path) -> dict[str, Any]:
    if not Path(path).exists():
        return {}
    obj = json.loads(Path(path).read_text())
    return obj if isinstance(obj, dict) else {}


def data_surface_snapshot(repo: Path) -> dict[str, Any]:
    """Compact status payload for operator reports and agents."""
    repo = Path(repo)
    panel = repo / "data_lake" / "daily_alpha_panel.csv"
    return {
        "generated_at": _utc_now(),
        "price_panel": panel_freshness(panel).as_dict(),
        "candidate_registry": {
            "path": "backtests/outputs/investment_cockpit/candidates/registry.csv",
            "exists": (repo / "backtests/outputs/investment_cockpit/candidates/registry.csv").exists(),
        },
        "thesis_register": {
            "path": "config/thesis_register.csv",
            "exists": (repo / "config/thesis_register.csv").exists(),
        },
        "capability_audit": {
            "path": "reports/investment_capabilities/latest.json",
            "exists": (repo / "reports/investment_capabilities/latest.json").exists(),
        },
    }
