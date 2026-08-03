"""Freeze and later evaluate investment decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import numpy as np
import pandas as pd

from src.research.investment_cockpit import load_weights
from src.research.stock_investment_data import price_panel_wide


DECISION_COLUMNS = [
    "decision_id",
    "strategy",
    "as_of",
    "horizon_days",
    "signal_path",
    "weights_path",
    "thesis_id",
    "benchmark",
    "status_at_decision",
    "evaluation_due",
    "evaluated_at",
    "forward_return",
    "benchmark_return",
    "active_return",
    "max_drawdown",
    "thesis_invalidated",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_decision_log(path: Path, *, overwrite: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    pd.DataFrame(columns=DECISION_COLUMNS).to_csv(path, index=False)
    return path


def load_decision_log(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        init_decision_log(path)
    return pd.read_csv(path, dtype=str).fillna("")


def freeze_decision(
    path: Path,
    *,
    decision_id: str,
    strategy: str,
    as_of: str,
    horizon_days: int,
    weights_path: str,
    signal_path: str = "",
    thesis_id: str = "",
    benchmark: str = "SPY",
    status_at_decision: str = "paper_candidate",
) -> Path:
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    due = (pd.Timestamp(as_of) + pd.Timedelta(days=horizon_days)).date().isoformat()
    row = {
        "decision_id": decision_id,
        "strategy": strategy,
        "as_of": as_of,
        "horizon_days": str(int(horizon_days)),
        "signal_path": signal_path,
        "weights_path": weights_path,
        "thesis_id": thesis_id,
        "benchmark": benchmark,
        "status_at_decision": status_at_decision,
        "evaluation_due": due,
        "evaluated_at": "",
        "forward_return": "",
        "benchmark_return": "",
        "active_return": "",
        "max_drawdown": "",
        "thesis_invalidated": "",
    }
    df = load_decision_log(path)
    df = df[df["decision_id"].astype(str) != decision_id]
    df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    df = df[DECISION_COLUMNS].sort_values(["as_of", "decision_id"])
    df.to_csv(path, index=False)
    return Path(path)


def freeze_from_candidate_registry(
    path: Path,
    *,
    registry_csv: Path,
    horizon_days: int = 21,
    include_statuses: set[str] | None = None,
) -> Path:
    """Freeze decisions for candidate manifests that have signal/weights artifacts."""
    statuses = include_statuses or {"paper_candidate", "deployable_sleeve"}
    if not Path(registry_csv).exists():
        init_decision_log(path)
        return Path(path)
    registry = pd.read_csv(registry_csv)
    for _, row in registry.iterrows():
        status = str(row.get("status", ""))
        if status not in statuses:
            continue
        manifest_path = Path(str(row.get("manifest_path", "")))
        if not manifest_path.exists():
            continue
        try:
            manifest = json.loads(manifest_path.read_text())
        except Exception:
            continue
        artifacts = manifest.get("artifacts", {}) if isinstance(manifest, dict) else {}
        signal_ref = artifacts.get("signal") or artifacts.get("target_signal") or {}
        weights_ref = artifacts.get("weights") or artifacts.get("target_weights") or signal_ref
        weights_path = str(weights_ref.get("path", "")) if isinstance(weights_ref, dict) else ""
        signal_path = str(signal_ref.get("path", "")) if isinstance(signal_ref, dict) else ""
        if not weights_path or not Path(weights_path).exists():
            continue
        signal = {}
        if signal_path and Path(signal_path).exists():
            try:
                signal = json.loads(Path(signal_path).read_text())
            except Exception:
                signal = {}
        as_of = signal.get("as_of_month") or signal.get("as_of") or str(manifest.get("created_at", ""))[:10]
        if not as_of:
            continue
        params = manifest.get("params", {}) if isinstance(manifest, dict) else {}
        decision_id = f"{manifest.get('run_id', row.get('run_id'))}-h{horizon_days}"
        freeze_decision(
            path,
            decision_id=decision_id,
            strategy=str(manifest.get("strategy", row.get("strategy", ""))),
            as_of=str(as_of),
            horizon_days=horizon_days,
            weights_path=weights_path,
            signal_path=signal_path,
            thesis_id=str(params.get("thesis_id", "")),
            benchmark=str(params.get("benchmark_id", "SPY") or "SPY"),
            status_at_decision=status,
        )
    return Path(path)


def _portfolio_path_return(wide: pd.DataFrame, weights: Mapping[str, float], start: pd.Timestamp, end: pd.Timestamp) -> tuple[float, float]:
    idx = wide.index
    start_idx = idx[idx <= start]
    end_idx = idx[idx <= end]
    if len(start_idx) == 0 or len(end_idx) == 0:
        raise ValueError("no panel prices for decision window")
    s = start_idx[-1]
    e = end_idx[-1]
    window = wide.loc[(wide.index >= s) & (wide.index <= e)]
    if len(window) < 2:
        raise ValueError("not enough prices in decision window")
    rets = window.pct_change(fill_method=None).fillna(0.0)
    held = {k: float(v) for k, v in weights.items() if k in rets.columns and np.isfinite(float(v))}
    if not held:
        raise ValueError("no decision weights overlap panel")
    w = pd.Series(held, dtype=float)
    gross = float(w.abs().sum())
    if gross > 0:
        w = w / gross
    daily = rets[list(w.index)].mul(w, axis=1).sum(axis=1)
    equity = (1.0 + daily).cumprod()
    total = float(equity.iloc[-1] - 1.0)
    max_dd = float((equity / equity.cummax() - 1.0).min())
    return total, max_dd


def evaluate_decisions(path: Path, *, panel_csv: Path, as_of: str | None = None) -> Path:
    df = load_decision_log(path).astype(object)
    if df.empty:
        return Path(path)
    wide = price_panel_wide(panel_csv)
    eval_as_of = pd.Timestamp(as_of) if as_of else pd.Timestamp(wide.index.max())
    for idx, row in df.iterrows():
        if str(row.get("evaluated_at", "")).strip():
            continue
        due = pd.Timestamp(row["evaluation_due"])
        if eval_as_of < due:
            continue
        weights_path = Path(str(row["weights_path"]))
        weights = load_weights(weights_path)
        start = pd.Timestamp(row["as_of"])
        horizon_days = int(row["horizon_days"])
        end = start + pd.Timedelta(days=horizon_days)
        fwd, mdd = _portfolio_path_return(wide, weights, start, end)
        bench = str(row.get("benchmark", "SPY") or "SPY")
        bench_ret = 0.0
        if bench in wide.columns:
            bret, _ = _portfolio_path_return(wide, {bench: 1.0}, start, end)
            bench_ret = bret
        df.loc[idx, "evaluated_at"] = _utc_now()
        df.loc[idx, "forward_return"] = fwd
        df.loc[idx, "benchmark_return"] = bench_ret
        df.loc[idx, "active_return"] = fwd - bench_ret
        df.loc[idx, "max_drawdown"] = mdd
        df.loc[idx, "thesis_invalidated"] = str(row.get("thesis_invalidated", ""))
    df.to_csv(path, index=False)
    return Path(path)


def decision_report(path: Path) -> dict[str, Any]:
    df = load_decision_log(path)
    evaluated = df[df["evaluated_at"].astype(str).str.strip() != ""] if not df.empty else df
    pending = int(len(df) - len(evaluated))
    active = pd.to_numeric(evaluated.get("active_return", pd.Series(dtype=float)), errors="coerce").dropna()
    return {
        "path": str(path),
        "n_decisions": int(len(df)),
        "n_evaluated": int(len(evaluated)),
        "n_pending": pending,
        "mean_active_return": float(active.mean()) if len(active) else None,
        "positive_active_rate": float((active > 0).mean()) if len(active) else None,
    }
