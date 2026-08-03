"""Stock investment cockpit primitives.

This module is deliberately small and file-oriented. It turns the useful lessons
from Qlib/RD-Agent/Lean/OpenBB-style projects into reusable repo components:

- candidate run manifests and a registry
- factor tear sheets for stock rankings
- a thesis register CSV
- constrained portfolio construction from scores
- a simulated paper order/fill/position ledger

The functions here do not place orders and do not depend on a broker API.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

import numpy as np
import pandas as pd


STATUS_VALUES = {"research_only", "radar", "paper_candidate", "deployable_sleeve", "blocked"}

THESIS_COLUMNS = [
    "thesis_id",
    "ticker",
    "entity",
    "as_of",
    "status",
    "horizon",
    "thesis",
    "evidence_refs",
    "contradiction_checks",
    "invalidation_trigger",
    "risk_notes",
    "owner",
    "updated_at",
]


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _slug(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9._-]+", "-", value)
    return value.strip("-") or "run"


def _json_default(obj: Any) -> Any:
    if isinstance(obj, (pd.Timestamp, datetime)):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        value = float(obj)
        return None if math.isnan(value) or math.isinf(value) else value
    if isinstance(obj, (np.ndarray,)):
        return obj.tolist()
    return str(obj)


def _find_col(df: pd.DataFrame, candidates: Sequence[str], *, required: bool = True) -> str | None:
    lower = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c in df.columns:
            return c
        if c.lower() in lower:
            return lower[c.lower()]
    if required:
        raise ValueError(f"missing required column; tried {list(candidates)}")
    return None


def _read_json(path: Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text())
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj


def _sha256(path: Path) -> str | None:
    path = Path(path)
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def artifact_ref(path: str | Path | None) -> dict[str, Any]:
    if path is None:
        return {"path": None, "exists": False, "sha256": None, "bytes": None}
    p = Path(path)
    return {
        "path": str(p),
        "exists": bool(p.exists()),
        "sha256": _sha256(p),
        "bytes": int(p.stat().st_size) if p.exists() and p.is_file() else None,
    }


def _flatten_metrics(obj: Mapping[str, Any], prefix: str = "") -> dict[str, float]:
    interesting = {
        "cagr",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "max_dd",
        "mdd",
        "latest_equity",
        "daily_return",
        "total_return",
        "test_sharpe",
        "test_cagr",
        "test_max_dd",
        "val_sharpe",
        "val_cagr",
        "val_max_dd",
        "pbo",
        "dsr",
        "alpha_tstat_hac",
        "turnover",
        "avg_turnover",
    }
    out: dict[str, float] = {}
    for key, value in obj.items():
        name = f"{prefix}.{key}" if prefix else str(key)
        key_l = str(key).lower()
        if isinstance(value, Mapping):
            out.update(_flatten_metrics(value, name))
            continue
        if key_l in interesting:
            try:
                f = float(value)
            except (TypeError, ValueError):
                continue
            if np.isfinite(f):
                out[name] = f
    return out


def build_candidate_manifest(
    *,
    strategy: str,
    status: str = "research_only",
    run_id: str | None = None,
    run_dir: str | Path | None = None,
    artifacts: Mapping[str, str | Path | None] | None = None,
    params: Mapping[str, Any] | None = None,
    notes: str = "",
    created_at: str | None = None,
) -> dict[str, Any]:
    """Build a JSON-serializable manifest for one strategy/config/run."""
    if status not in STATUS_VALUES:
        raise ValueError(f"status must be one of {sorted(STATUS_VALUES)}")
    stamp = created_at or _utc_now()
    rid = run_id or f"{_slug(strategy)}-{stamp.replace(':', '').replace('+', 'z')}"
    artifact_map = {k: artifact_ref(v) for k, v in (artifacts or {}).items()}

    metrics: dict[str, float] = {}
    for name, ref in artifact_map.items():
        path = ref.get("path")
        if not path or not ref.get("exists") or not str(path).endswith(".json"):
            continue
        try:
            metrics.update({f"{name}.{k}": v for k, v in _flatten_metrics(_read_json(Path(path))).items()})
        except (OSError, json.JSONDecodeError, ValueError):
            continue

    return {
        "manifest_version": 1,
        "run_id": rid,
        "strategy": strategy,
        "status": status,
        "created_at": stamp,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "params": dict(params or {}),
        "artifacts": artifact_map,
        "metrics": metrics,
        "notes": notes,
    }


def write_candidate_manifest(manifest: Mapping[str, Any], out_dir: Path) -> Path:
    """Write a manifest and upsert a compact row into registry.csv."""
    out_dir = Path(out_dir)
    run_id = str(manifest["run_id"])
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = run_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True, default=_json_default) + "\n")

    registry = out_dir / "registry.csv"
    row = {
        "run_id": run_id,
        "strategy": manifest.get("strategy", ""),
        "status": manifest.get("status", ""),
        "created_at": manifest.get("created_at", ""),
        "manifest_path": str(manifest_path),
        "run_dir": manifest.get("run_dir") or "",
        "notes": manifest.get("notes") or "",
    }
    metric_items = manifest.get("metrics") or {}
    for key in sorted(metric_items)[:24]:
        row[f"metric.{key}"] = metric_items[key]

    if registry.exists():
        df = pd.read_csv(registry)
        df = df[df["run_id"].astype(str) != run_id] if "run_id" in df.columns else df
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df = df.sort_values(["strategy", "created_at", "run_id"], na_position="last")
    df.to_csv(registry, index=False)
    return manifest_path


def register_candidate_run(
    *,
    strategy: str,
    out_dir: Path,
    status: str = "research_only",
    run_id: str | None = None,
    run_dir: str | Path | None = None,
    artifacts: Mapping[str, str | Path | None] | None = None,
    params: Mapping[str, Any] | None = None,
    notes: str = "",
) -> Path:
    manifest = build_candidate_manifest(
        strategy=strategy,
        status=status,
        run_id=run_id,
        run_dir=run_dir,
        artifacts=artifacts,
        params=params,
        notes=notes,
    )
    return write_candidate_manifest(manifest, out_dir)


@dataclass
class FactorTearsheet:
    observations: pd.DataFrame
    ic_by_date: pd.DataFrame
    ic_summary: dict[str, Any]
    bucket_returns: pd.DataFrame
    turnover: pd.DataFrame
    top_exposures: pd.DataFrame

    def to_summary(self) -> dict[str, Any]:
        return {
            "n_observations": int(len(self.observations)),
            "n_periods": int(self.observations["_entry_date"].nunique()) if not self.observations.empty else 0,
            "ic_summary": self.ic_summary,
            "avg_one_way_turnover": (
                float(self.turnover["one_way_turnover"].mean())
                if not self.turnover.empty and "one_way_turnover" in self.turnover
                else None
            ),
        }

    def write(self, out_dir: Path) -> dict[str, str]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        paths = {
            "observations": out_dir / "observations.csv",
            "ic_by_date": out_dir / "ic_by_date.csv",
            "bucket_returns": out_dir / "bucket_returns.csv",
            "turnover": out_dir / "turnover.csv",
            "top_exposures": out_dir / "top_exposures.csv",
            "summary": out_dir / "summary.json",
        }
        self.observations.to_csv(paths["observations"], index=False)
        self.ic_by_date.to_csv(paths["ic_by_date"], index=False)
        self.bucket_returns.to_csv(paths["bucket_returns"], index=False)
        self.turnover.to_csv(paths["turnover"], index=False)
        self.top_exposures.to_csv(paths["top_exposures"], index=False)
        paths["summary"].write_text(json.dumps(self.to_summary(), indent=2, sort_keys=True, default=_json_default) + "\n")
        return {k: str(v) for k, v in paths.items()}


def _load_prices(panel_csv: Path) -> pd.DataFrame:
    df = pd.read_csv(panel_csv)
    inst = _find_col(df, ["Instrument", "instrument", "ticker", "symbol"])
    date = _find_col(df, ["Date", "date"])
    price = _find_col(df, ["Price_Close", "price_close", "close", "Close", "adj_close", "Adj Close"])
    df[date] = pd.to_datetime(df[date], errors="coerce")
    df[price] = pd.to_numeric(df[price], errors="coerce")
    df = df.dropna(subset=[date, inst, price])
    wide = df.pivot_table(index=date, columns=inst, values=price, aggfunc="last").sort_index().ffill()
    wide.columns = wide.columns.astype(str)
    return wide


def _align_to_price_dates(dates: pd.Series, price_index: pd.DatetimeIndex) -> pd.Series:
    idx = price_index.get_indexer(pd.to_datetime(dates, errors="coerce"), method="pad")
    aligned = [price_index[i] if i >= 0 else pd.NaT for i in idx]
    return pd.Series(aligned, index=dates.index)


def compute_factor_tearsheet(
    rankings: pd.DataFrame,
    panel_csv: Path,
    *,
    date_col: str | None = None,
    instrument_col: str | None = None,
    score_col: str = "score",
    horizon_days: int = 21,
    quantiles: int = 5,
    top_n: int = 10,
    exposure_cols: Sequence[str] = ("sector", "country"),
) -> FactorTearsheet:
    """Compute stock-ranking IC, bucket returns, turnover, and top-name exposures."""
    if horizon_days <= 0:
        raise ValueError("horizon_days must be positive")
    if quantiles < 2:
        raise ValueError("quantiles must be at least 2")
    if top_n <= 0:
        raise ValueError("top_n must be positive")

    rank = rankings.copy()
    date_col = date_col or _find_col(rank, ["date", "Date", "as_of", "as_of_month"])
    instrument_col = instrument_col or _find_col(rank, ["Instrument", "instrument", "ticker", "symbol"])
    if score_col not in rank.columns:
        score_col = _find_col(rank, [score_col, "score", "rank_score", "composite", "signal"])
    rank[date_col] = pd.to_datetime(rank[date_col], errors="coerce")
    rank[score_col] = pd.to_numeric(rank[score_col], errors="coerce")
    rank[instrument_col] = rank[instrument_col].astype(str)
    rank = rank.dropna(subset=[date_col, instrument_col, score_col])

    prices = _load_prices(panel_csv)
    fwd = prices.shift(-horizon_days) / prices - 1.0
    rank["_entry_date"] = _align_to_price_dates(rank[date_col], prices.index)
    rank = rank.dropna(subset=["_entry_date"])

    def lookup(row: pd.Series) -> float:
        ticker = str(row[instrument_col])
        dt = row["_entry_date"]
        if ticker not in fwd.columns or pd.isna(dt):
            return float("nan")
        try:
            return float(fwd.at[dt, ticker])
        except KeyError:
            return float("nan")

    rank["forward_return"] = rank.apply(lookup, axis=1)
    obs = rank.dropna(subset=["forward_return"]).copy()
    obs = obs.rename(columns={date_col: "as_of", instrument_col: "instrument", score_col: "score"})
    obs["_entry_date"] = pd.to_datetime(obs["_entry_date"])
    obs = obs.sort_values(["_entry_date", "score"], ascending=[True, False])

    ic_rows = []
    for dt, grp in obs.groupby("_entry_date"):
        if len(grp) < 3 or grp["score"].nunique() < 2 or grp["forward_return"].nunique() < 2:
            ic = float("nan")
        else:
            ic = float(grp["score"].corr(grp["forward_return"], method="spearman"))
        ic_rows.append({"date": pd.Timestamp(dt).date().isoformat(), "rank_ic": ic, "n": int(len(grp))})
    ic_by_date = pd.DataFrame(ic_rows)
    valid_ic = ic_by_date["rank_ic"].dropna() if not ic_by_date.empty else pd.Series(dtype=float)
    ic_std = float(valid_ic.std(ddof=1)) if len(valid_ic) > 1 else float("nan")
    ic_summary = {
        "mean_rank_ic": float(valid_ic.mean()) if len(valid_ic) else None,
        "median_rank_ic": float(valid_ic.median()) if len(valid_ic) else None,
        "std_rank_ic": ic_std if np.isfinite(ic_std) else None,
        "t_stat": (
            float(valid_ic.mean() / (ic_std / math.sqrt(len(valid_ic))))
            if len(valid_ic) > 1 and np.isfinite(ic_std) and ic_std > 0
            else None
        ),
        "positive_ic_rate": float((valid_ic > 0).mean()) if len(valid_ic) else None,
        "n_periods": int(len(valid_ic)),
    }

    bucket_rows = []
    for dt, grp in obs.groupby("_entry_date"):
        if len(grp) < 2:
            continue
        q = min(quantiles, int(grp["score"].nunique()), len(grp))
        if q < 2:
            continue
        bucketed = grp.copy()
        ranks = bucketed["score"].rank(method="first")
        bucketed["bucket"] = pd.qcut(ranks, q=q, labels=range(1, q + 1), duplicates="drop").astype(int)
        for bucket, bgrp in bucketed.groupby("bucket"):
            bucket_rows.append(
                {
                    "date": pd.Timestamp(dt).date().isoformat(),
                    "bucket": int(bucket),
                    "mean_forward_return": float(bgrp["forward_return"].mean()),
                    "median_forward_return": float(bgrp["forward_return"].median()),
                    "n": int(len(bgrp)),
                }
            )
    bucket_returns = pd.DataFrame(bucket_rows)

    top_sets: list[tuple[pd.Timestamp, set[str]]] = []
    exposure_rows: list[dict[str, Any]] = []
    present_exposure_cols = [c for c in exposure_cols if c in obs.columns]
    for dt, grp in obs.groupby("_entry_date"):
        top = grp.sort_values("score", ascending=False).head(top_n)
        names = set(top["instrument"].astype(str))
        top_sets.append((pd.Timestamp(dt), names))
        for col in present_exposure_cols:
            counts = top[col].fillna("UNKNOWN").astype(str).value_counts(normalize=True)
            for value, share in counts.items():
                exposure_rows.append(
                    {
                        "date": pd.Timestamp(dt).date().isoformat(),
                        "field": col,
                        "value": value,
                        "top_n_share": float(share),
                    }
                )

    turnover_rows = []
    for (prev_dt, prev), (dt, curr) in zip(top_sets, top_sets[1:]):
        denom = max(len(prev), len(curr), 1)
        turnover_rows.append(
            {
                "date": dt.date().isoformat(),
                "previous_date": prev_dt.date().isoformat(),
                "one_way_turnover": float(1.0 - len(prev & curr) / denom),
                "n_current": int(len(curr)),
                "n_previous": int(len(prev)),
            }
        )

    return FactorTearsheet(
        observations=obs,
        ic_by_date=ic_by_date,
        ic_summary=ic_summary,
        bucket_returns=bucket_returns,
        turnover=pd.DataFrame(turnover_rows),
        top_exposures=pd.DataFrame(exposure_rows),
    )


def init_thesis_register(path: Path, *, overwrite: bool = False) -> Path:
    """Create an empty thesis register CSV with the standard schema."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    pd.DataFrame(columns=THESIS_COLUMNS).to_csv(path, index=False)
    return path


def upsert_thesis(path: Path, row: Mapping[str, Any]) -> Path:
    """Insert or update a thesis row keyed by thesis_id."""
    path = Path(path)
    if not path.exists():
        init_thesis_register(path)
    if "thesis_id" not in row or not str(row["thesis_id"]).strip():
        raise ValueError("thesis_id is required")
    df = pd.read_csv(path, dtype=str).fillna("")
    out = {col: str(row.get(col, "")) for col in THESIS_COLUMNS}
    out["updated_at"] = out["updated_at"] or _utc_now()
    if "as_of" not in row or not str(row.get("as_of", "")).strip():
        out["as_of"] = out["as_of"] or out["updated_at"][:10]
    if "thesis_id" in df.columns:
        df = df[df["thesis_id"].astype(str) != out["thesis_id"]]
    df = pd.concat([df, pd.DataFrame([out])], ignore_index=True)
    df = df[THESIS_COLUMNS].sort_values(["ticker", "as_of", "thesis_id"], na_position="last")
    df.to_csv(path, index=False)
    return path


@dataclass
class PortfolioConstructionResult:
    weights: pd.DataFrame
    summary: dict[str, Any]

    def to_weight_dict(self) -> dict[str, float]:
        return {str(r.instrument): float(r.weight) for r in self.weights.itertuples(index=False)}

    def write(self, out_dir: Path, *, strategy: str = "constructed_portfolio", as_of: str | None = None) -> dict[str, str]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        weights_csv = out_dir / "target_weights.csv"
        signal_json = out_dir / "target_signal.json"
        summary_json = out_dir / "portfolio_summary.json"
        self.weights.to_csv(weights_csv, index=False)
        signal = {
            "strategy": strategy,
            "as_of": as_of,
            "weights": self.to_weight_dict(),
            "summary": self.summary,
        }
        signal_json.write_text(json.dumps(signal, indent=2, sort_keys=True, default=_json_default) + "\n")
        summary_json.write_text(json.dumps(self.summary, indent=2, sort_keys=True, default=_json_default) + "\n")
        return {"weights_csv": str(weights_csv), "signal_json": str(signal_json), "summary_json": str(summary_json)}


def _cap_single_names(weights: pd.Series, max_weight: float) -> pd.Series:
    if max_weight <= 0:
        raise ValueError("max_weight must be positive")
    w = weights.clip(lower=0).astype(float).copy()
    total = float(w.sum())
    if total <= 0:
        return w
    for _ in range(100):
        over = w > max_weight + 1e-12
        if not over.any():
            break
        excess = float((w[over] - max_weight).sum())
        w[over] = max_weight
        under = ~over
        capacity = (max_weight - w[under]).clip(lower=0)
        cap_sum = float(capacity.sum())
        if excess <= 1e-12 or cap_sum <= 1e-12:
            break
        w.loc[capacity.index] += excess * capacity / cap_sum
    if float(w.sum()) > total:
        w *= total / float(w.sum())
    return w


def _cap_by_asset_limits(weights: pd.Series, caps: pd.Series) -> pd.Series:
    w = weights.clip(lower=0).astype(float).copy()
    caps = caps.reindex(w.index).fillna(0.0).clip(lower=0).astype(float)
    total = float(w.sum())
    if total <= 0:
        return w
    feasible_total = float(caps.sum())
    if feasible_total <= 0:
        return pd.Series(0.0, index=w.index)
    target_total = min(total, feasible_total)
    for _ in range(100):
        over = w > caps + 1e-12
        if not over.any():
            break
        excess = float((w[over] - caps[over]).sum())
        w[over] = caps[over]
        under = ~over
        capacity = (caps[under] - w[under]).clip(lower=0)
        cap_sum = float(capacity.sum())
        if excess <= 1e-12 or cap_sum <= 1e-12:
            break
        w.loc[capacity.index] += excess * capacity / cap_sum
    if float(w.sum()) > target_total and float(w.sum()) > 0:
        w *= target_total / float(w.sum())
    return w


def construct_portfolio_from_scores(
    scores: pd.DataFrame,
    *,
    instrument_col: str | None = None,
    score_col: str = "score",
    date_col: str | None = None,
    as_of: str | None = None,
    top_n: int = 10,
    max_weight: float = 0.15,
    gross_target: float = 1.0,
    min_score: float | None = None,
    group_caps: Mapping[str, float] | None = None,
    benchmark_weights: Mapping[str, float] | None = None,
    max_active_weight: float | None = None,
    cash_ticker: str | None = "CASH",
) -> PortfolioConstructionResult:
    """Convert a stock ranking table into constrained long-only target weights."""
    if top_n <= 0:
        raise ValueError("top_n must be positive")
    if not (0 < max_weight <= 1):
        raise ValueError("max_weight must be in (0, 1]")
    if not (0 <= gross_target <= 1):
        raise ValueError("gross_target must be in [0, 1]")

    df = scores.copy()
    instrument_col = instrument_col or _find_col(df, ["Instrument", "instrument", "ticker", "symbol"])
    if score_col not in df.columns:
        score_col = _find_col(df, [score_col, "score", "rank_score", "composite", "signal"])
    date_col = date_col or _find_col(df, ["date", "Date", "as_of", "as_of_month"], required=False)

    if date_col:
        df[date_col] = pd.to_datetime(df[date_col], errors="coerce")
        if as_of:
            cutoff = pd.Timestamp(as_of)
            df = df[df[date_col] <= cutoff]
        latest = df[date_col].max()
        df = df[df[date_col] == latest]
        as_of_value = latest.date().isoformat() if pd.notna(latest) else as_of
    else:
        as_of_value = as_of

    df[score_col] = pd.to_numeric(df[score_col], errors="coerce")
    df[instrument_col] = df[instrument_col].astype(str)
    df = df.dropna(subset=[instrument_col, score_col])
    if "veto" in df.columns:
        df = df[~df["veto"].astype(str).str.lower().isin({"1", "true", "yes", "y"})]
    if min_score is not None:
        df = df[df[score_col] >= min_score]
    df = df.sort_values(score_col, ascending=False).head(top_n).copy()

    if df.empty or gross_target == 0:
        weights = pd.DataFrame(columns=["instrument", "weight", "score"])
        if cash_ticker:
            weights = pd.DataFrame([{"instrument": cash_ticker, "weight": 1.0, "score": np.nan}])
        return PortfolioConstructionResult(
            weights=weights,
            summary={"as_of": as_of_value, "n_selected": 0, "cash_weight": 1.0 if cash_ticker else 0.0},
        )

    raw = df[score_col].clip(lower=0)
    if float(raw.sum()) <= 0:
        raw = pd.Series(1.0, index=df.index)
    w = raw / float(raw.sum()) * gross_target
    w = _cap_single_names(w, max_weight=max_weight)

    if benchmark_weights is not None and max_active_weight is not None:
        if max_active_weight < 0:
            raise ValueError("max_active_weight cannot be negative")
        bench = {str(k): float(v) for k, v in benchmark_weights.items()}
        caps = pd.Series(
            {
                idx: min(max_weight, max(0.0, bench.get(str(df.loc[idx, instrument_col]), 0.0) + max_active_weight))
                for idx in df.index
            },
            dtype=float,
        )
        w = _cap_by_asset_limits(w, caps)

    group_caps = dict(group_caps or {})
    for col, cap in group_caps.items():
        if col not in df.columns:
            continue
        if not (0 < cap <= 1):
            raise ValueError(f"group cap for {col} must be in (0, 1]")
        groups = df[col].fillna("UNKNOWN").astype(str)
        for _, idx in groups.groupby(groups).groups.items():
            group_weight = float(w.loc[list(idx)].sum())
            if group_weight > cap and group_weight > 0:
                w.loc[list(idx)] *= cap / group_weight
        w = _cap_single_names(w, max_weight=max_weight)

    out = df.copy()
    out["weight"] = w
    out = out[out["weight"] > 1e-12]
    out = out.rename(columns={instrument_col: "instrument", score_col: "score"})
    keep = ["instrument", "weight", "score"]
    for col in group_caps:
        if col in out.columns and col not in keep:
            keep.append(col)
    for col in ("sector", "country"):
        if col in out.columns and col not in keep:
            keep.append(col)
    out = out[keep].sort_values("weight", ascending=False).reset_index(drop=True)

    invested = float(out["weight"].sum()) if not out.empty else 0.0
    cash_weight = max(0.0, 1.0 - invested)
    if cash_ticker and cash_weight > 1e-10:
        out = pd.concat(
            [out, pd.DataFrame([{"instrument": cash_ticker, "weight": cash_weight, "score": np.nan}])],
            ignore_index=True,
        )

    summary = {
        "as_of": as_of_value,
        "n_selected": int((out["instrument"] != cash_ticker).sum()) if cash_ticker else int(len(out)),
        "gross_target": float(gross_target),
        "invested_weight": invested,
        "cash_weight": cash_weight if cash_ticker else 0.0,
        "max_name_weight": float(out.loc[out["instrument"] != cash_ticker, "weight"].max())
        if cash_ticker and (out["instrument"] != cash_ticker).any()
        else float(out["weight"].max()) if not out.empty else 0.0,
        "group_caps": group_caps,
        "benchmark_aware": benchmark_weights is not None,
        "max_active_weight": max_active_weight,
    }
    return PortfolioConstructionResult(weights=out, summary=summary)


@dataclass
class PaperRebalanceResult:
    orders: pd.DataFrame
    positions: pd.DataFrame
    ledger_row: dict[str, Any]

    def write(self, out_dir: Path) -> dict[str, str]:
        out_dir = Path(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)
        orders_path = out_dir / "orders.csv"
        fills_path = out_dir / "fills.csv"
        positions_path = out_dir / "positions_latest.csv"
        ledger_path = out_dir / "equity_ledger.csv"

        def append(path: Path, df: pd.DataFrame) -> None:
            if path.exists():
                prior = pd.read_csv(path)
                df = pd.concat([prior, df], ignore_index=True)
            df.to_csv(path, index=False)

        append(orders_path, self.orders)
        append(fills_path, self.orders.assign(fill_status="filled"))
        self.positions.to_csv(positions_path, index=False)
        append(ledger_path, pd.DataFrame([self.ledger_row]))
        return {
            "orders": str(orders_path),
            "fills": str(fills_path),
            "positions": str(positions_path),
            "equity_ledger": str(ledger_path),
        }


def latest_prices_from_panel(panel_csv: Path, *, as_of: str | None = None) -> tuple[str, dict[str, float]]:
    prices = _load_prices(panel_csv)
    if prices.empty:
        raise ValueError("price panel is empty")
    if as_of:
        idx = prices.index[prices.index <= pd.Timestamp(as_of)]
        if len(idx) == 0:
            raise ValueError(f"no prices on or before {as_of}")
        dt = pd.Timestamp(idx[-1])
    else:
        dt = pd.Timestamp(prices.index.max())
    row = prices.loc[dt].dropna()
    return dt.date().isoformat(), {str(k): float(v) for k, v in row.items()}


def simulate_paper_rebalance(
    *,
    target_weights: Mapping[str, float],
    prices: Mapping[str, float],
    positions: Mapping[str, float] | None = None,
    cash: float = 10_000.0,
    as_of: str | None = None,
    fee_bps: float = 0.0,
    min_trade_value: float = 0.0,
    cash_ticker: str = "CASH",
) -> PaperRebalanceResult:
    """Simulate close-price rebalance from current shares/cash to target weights."""
    if fee_bps < 0:
        raise ValueError("fee_bps cannot be negative")
    pos = {str(k): float(v) for k, v in (positions or {}).items() if str(k) != cash_ticker}
    px = {str(k): float(v) for k, v in prices.items() if np.isfinite(float(v)) and float(v) > 0}
    weights = {str(k): float(v) for k, v in target_weights.items() if str(k) != cash_ticker}
    if not weights:
        raise ValueError("target_weights has no investable tickers")

    missing = [t for t in weights if t not in px]
    if missing:
        raise ValueError(f"missing prices for target tickers: {missing}")

    equity_before = float(cash + sum(pos.get(t, 0.0) * px.get(t, 0.0) for t in pos))
    if equity_before <= 0:
        raise ValueError("portfolio equity must be positive")

    gross = sum(max(0.0, w) for w in weights.values())
    if gross > 1.0 + 1e-9:
        weights = {k: v / gross for k, v in weights.items()}

    order_rows: list[dict[str, Any]] = []
    new_pos = dict(pos)
    cash_after = float(cash)
    total_fees = 0.0
    turnover = 0.0
    date_value = as_of or _utc_now()[:10]

    for ticker in sorted(weights):
        target_value = float(weights[ticker]) * equity_before
        current_shares = float(new_pos.get(ticker, 0.0))
        current_value = current_shares * px[ticker]
        trade_value = target_value - current_value
        if abs(trade_value) < min_trade_value:
            continue
        quantity = trade_value / px[ticker]
        fee = abs(trade_value) * fee_bps / 10_000.0
        side = "BUY" if quantity > 0 else "SELL"
        new_pos[ticker] = current_shares + quantity
        cash_after -= trade_value + fee
        total_fees += fee
        turnover += abs(trade_value)
        order_rows.append(
            {
                "date": date_value,
                "instrument": ticker,
                "side": side,
                "quantity": float(quantity),
                "price": float(px[ticker]),
                "trade_value": float(trade_value),
                "fee": float(fee),
                "target_weight": float(weights[ticker]),
                "current_weight": float(current_value / equity_before),
            }
        )

    for ticker in list(new_pos):
        if abs(new_pos[ticker]) < 1e-12:
            new_pos.pop(ticker)

    position_rows = []
    for ticker in sorted(new_pos):
        price = px.get(ticker)
        if price is None:
            continue
        market_value = float(new_pos[ticker] * price)
        position_rows.append(
            {
                "date": date_value,
                "instrument": ticker,
                "shares": float(new_pos[ticker]),
                "price": float(price),
                "market_value": market_value,
            }
        )
    positions_df = pd.DataFrame(position_rows)
    equity_after = float(cash_after + (positions_df["market_value"].sum() if not positions_df.empty else 0.0))
    if not positions_df.empty:
        positions_df["weight"] = positions_df["market_value"] / equity_after if equity_after > 0 else 0.0

    ledger_row = {
        "date": date_value,
        "equity_before": equity_before,
        "equity_after": equity_after,
        "cash_after": cash_after,
        "fees": total_fees,
        "turnover_dollars": turnover,
        "turnover_pct": turnover / equity_before,
        "n_orders": int(len(order_rows)),
        "gross_exposure": float(positions_df["market_value"].abs().sum() / equity_after)
        if equity_after > 0 and not positions_df.empty
        else 0.0,
    }
    return PaperRebalanceResult(
        orders=pd.DataFrame(order_rows),
        positions=positions_df,
        ledger_row=ledger_row,
    )


def load_weights(path: Path) -> dict[str, float]:
    path = Path(path)
    if path.suffix.lower() == ".json":
        data = _read_json(path)
        weights = data.get("weights", data)
        if not isinstance(weights, Mapping):
            raise ValueError(f"cannot find weights mapping in {path}")
        return {str(k): float(v) for k, v in weights.items()}
    df = pd.read_csv(path)
    inst = _find_col(df, ["instrument", "Instrument", "ticker", "symbol"])
    weight = _find_col(df, ["weight", "target_weight"])
    return {str(r[inst]): float(r[weight]) for _, r in df.iterrows()}


def load_positions(path: Path | None) -> tuple[dict[str, float], float | None]:
    if path is None or not Path(path).exists():
        return {}, None
    df = pd.read_csv(path)
    inst = _find_col(df, ["instrument", "Instrument", "ticker", "symbol"])
    shares = _find_col(df, ["shares", "quantity", "qty"])
    cash_col = _find_col(df, ["cash", "cash_after"], required=False)
    cash = None
    if cash_col and not df[cash_col].dropna().empty:
        cash = float(pd.to_numeric(df[cash_col], errors="coerce").dropna().iloc[-1])
    return {str(r[inst]): float(r[shares]) for _, r in df.iterrows()}, cash
