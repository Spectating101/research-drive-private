"""IHSG regime labeling + long-history cache helpers (1990+).

Mechanical rules match ``run_idn_weekly_position_sheet.regime_state``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
IHSG_CACHE = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
BANKS_CACHE = REPO / "data_lake/markets/yfinance_asia/idn_core_banks_daily.parquet"

INDEX_PROXY = "^JKSE"
CORE_BANKS = ["BBCA.JK", "BBRI.JK", "BMRI.JK"]
IHSG_START = "1990-01-01"
BANKS_START = "2003-01-01"

CORE_SLEEVE_PCT = {
    "washout": 0.55,
    "recovery": 0.45,
    "extended": 0.25,
    "neutral": 0.40,
    "unknown": 0.40,
}

FORWARD_HORIZONS_DAYS = (5, 20)  # ~1w and ~1mo — primary horizons
LONG_HORIZONS_DAYS = (126,)  # optional context only; not operational default
HIT_THRESHOLDS_PCT = (5.0, 10.0, 25.0)


def summarize_returns_pct(vals: list[float] | np.ndarray) -> dict[str, Any]:
    """Distribution summary for forward returns already in percent."""
    if len(vals) == 0:
        return {"n": 0}
    arr = np.asarray(vals, dtype=float)
    out: dict[str, Any] = {
        "n": int(len(arr)),
        "mean_pct": round(float(arr.mean()), 2),
        "median_pct": round(float(np.median(arr)), 2),
        "std_pct": round(float(arr.std(ddof=1)), 2) if len(arr) > 1 else 0.0,
        "p10_pct": round(float(np.percentile(arr, 10)), 2),
        "p25_pct": round(float(np.percentile(arr, 25)), 2),
        "p75_pct": round(float(np.percentile(arr, 75)), 2),
        "p90_pct": round(float(np.percentile(arr, 90)), 2),
        "min_pct": round(float(arr.min()), 2),
        "max_pct": round(float(arr.max()), 2),
        "hit_positive_pct": round(float((arr > 0).mean() * 100), 1),
    }
    for thr in HIT_THRESHOLDS_PCT:
        out[f"hit_gt_{int(thr)}pct"] = round(float((arr > thr).mean() * 100), 1)
    return out


def _aligned_series(banks: pd.DataFrame, symbol: str) -> pd.Series:
    if symbol not in banks.columns:
        return pd.Series(dtype=float)
    return pd.to_numeric(banks[symbol], errors="coerce").dropna().sort_index()


def bank_equal_weight_series(banks: pd.DataFrame) -> pd.Series:
    cols = [_aligned_series(banks, c) for c in CORE_BANKS if c in banks.columns]
    if not cols:
        return pd.Series(dtype=float)
    panel = pd.concat(cols, axis=1).mean(axis=1)
    return panel.dropna().sort_index()


def _hold_return(close: pd.Series, start: pd.Timestamp, end: pd.Timestamp) -> float | None:
    close = close.dropna().sort_index()
    if start not in close.index or end not in close.index:
        return None
    a = float(close.loc[start])
    b = float(close.loc[end])
    if a <= 0:
        return None
    return b / a - 1.0


def _washout_start_before_recovery(labels: pd.Series, recovery_dt: pd.Timestamp) -> pd.Timestamp | None:
    walk = labels.loc[:recovery_dt]
    start: pd.Timestamp | None = None
    for dt in reversed(walk.index):
        if walk.loc[dt] == "washout":
            start = dt
        elif start is not None:
            break
    return start


def washout_to_recovery_holds(tape: pd.DataFrame, banks: pd.DataFrame) -> dict[str, Any]:
    """Return from washout episode start through first recovery flip."""
    labels = tape["label"]
    bank_ew = bank_equal_weight_series(banks)
    ihsg = tape["close"].dropna()
    rows: list[dict[str, Any]] = []
    prev: str | None = None
    for dt, lab in labels.items():
        if prev == "washout" and lab == "recovery":
            start = _washout_start_before_recovery(labels, dt)
            if start is None:
                prev = lab
                continue
            hold_days = int((dt - start).days)
            row: dict[str, Any] = {
                "washout_start": str(start.date()),
                "recovery_date": str(dt.date()),
                "calendar_days": hold_days,
                "dd_at_start_pct": float(tape.loc[start, "dd_from_63d_high_pct"]),
            }
            for name, series in (
                ("ihsg", ihsg),
                ("banks_ew", bank_ew),
                ("bbca", _aligned_series(banks, "BBCA.JK")),
                ("bbri", _aligned_series(banks, "BBRI.JK")),
                ("bmri", _aligned_series(banks, "BMRI.JK")),
            ):
                r = _hold_return(series, start, dt)
                row[f"{name}_hold_pct"] = round(r * 100, 2) if r is not None else None
            core = float(tape.loc[start, "core_sleeve_pct"])
            bk = row.get("banks_ew_hold_pct")
            if bk is not None:
                row["sleeve_hold_pct"] = round(core * bk, 2)
            rows.append(row)
        prev = str(lab)

    summary: dict[str, Any] = {"cycles": len(rows), "holds": rows}
    for key in ("ihsg", "banks_ew", "bbca", "sleeve"):
        col = f"{key}_hold_pct"
        summary[key] = summarize_returns_pct([r[col] for r in rows if r.get(col) is not None])
    return summary


def random_entry_baseline(series: pd.Series, horizons: tuple[int, ...] = FORWARD_HORIZONS_DAYS) -> dict[str, Any]:
    """Any-day forward returns (percent) for comparison vs timed entries."""
    s = series.dropna().sort_index()
    rets = s.pct_change().dropna()
    out: dict[str, Any] = {"symbol": getattr(series, "name", "series")}
    for h in horizons:
        vals: list[float] = []
        for i in range(len(rets) - h):
            r = float((1 + rets.iloc[i + 1 : i + 1 + h]).prod() - 1)
            vals.append(r * 100)
        out[f"fwd_{h}d"] = summarize_returns_pct(vals)
    return out


def deepest_washout_entries(tape: pd.DataFrame, banks: pd.DataFrame) -> dict[str, Any]:
    """Enter at deepest index close inside each washout episode (often better timing)."""
    labels = tape["label"]
    ihsg = tape["close"]
    rows: list[dict[str, Any]] = []
    for ep in episode_runs(labels):
        if ep["label"] != "washout":
            continue
        sub = ihsg.loc[ep["start"] : ep["end"]]
        if sub.empty:
            continue
        trough_dt = sub.idxmin()
        row: dict[str, Any] = {
            "trough_date": str(trough_dt.date()),
            "episode_start": str(ep["start"].date()),
            "episode_end": str(ep["end"].date()),
            "dd_at_trough_pct": float(tape.loc[trough_dt, "dd_from_63d_high_pct"]),
        }
        for h in FORWARD_HORIZONS_DAYS:
            ih = _fwd_return(ihsg, trough_dt, h)
            bk = bank_equal_weight_return(banks, trough_dt, h)
            bb = _fwd_return(_aligned_series(banks, "BBCA.JK"), trough_dt, h)
            row[f"ihsg_fwd_{h}d_pct"] = round(ih * 100, 2) if ih is not None else None
            row[f"banks_fwd_{h}d_pct"] = round(bk * 100, 2) if bk is not None else None
            row[f"bbca_fwd_{h}d_pct"] = round(bb * 100, 2) if bb is not None else None
        rows.append(row)

    out: dict[str, Any] = {"episodes": len(rows), "entries": rows}
    for lane, prefix in (("ihsg", "ihsg"), ("banks_ew", "banks"), ("bbca", "bbca")):
        for h in FORWARD_HORIZONS_DAYS:
            col = f"{prefix}_fwd_{h}d_pct"
            out[f"{lane}_fwd_{h}d"] = summarize_returns_pct([r[col] for r in rows if r.get(col) is not None])
    return out


def current_episode_live(tape: pd.DataFrame, banks: pd.DataFrame) -> dict[str, Any]:
    """Live P&L for the active or most recent washout/recovery episode."""
    labels = tape["label"]
    eps = episode_runs(labels)
    if not eps:
        return {}
    last = eps[-1]
    as_of = tape.index.max()
    row: dict[str, Any] = {
        "label": last["label"],
        "start": str(last["start"].date()),
        "end": str(last["end"].date()),
        "n_days": last["n_days"],
        "as_of": str(as_of.date()),
    }
    if last["label"] in ("washout", "recovery"):
        start = last["start"]
        for name, series in (
            ("ihsg", tape["close"]),
            ("banks_ew", bank_equal_weight_series(banks)),
            ("bbca", _aligned_series(banks, "BBCA.JK")),
        ):
            r = _hold_return(series, start, as_of)
            row[f"{name}_since_start_pct"] = round(r * 100, 2) if r is not None else None
    return row


def lane_playbook_summary(
    washout_start: dict[str, Any],
    washout_trough: dict[str, Any],
    washout_hold: dict[str, Any],
    random_banks: dict[str, Any],
) -> dict[str, str]:
    """Plain-language ops hints derived from the stats."""
    b20 = washout_start.get("lanes", {}).get("banks_ew", {}).get("fwd_20d", {})
    b63 = washout_start.get("lanes", {}).get("banks_ew", {}).get("fwd_63d", {})
    hold = washout_hold.get("banks_ew", {})
    rnd = random_banks.get("fwd_20d", {})
    lines = {
        "what_regime_is": (
            "Regime lane = monthly/weekly beta filter on IHSG drawdown/bounce. "
            "Not year-hold, not ARA chase."
        ),
        "horizon": (
            "Operate on ~4w (20d) decisions. Run run_idn_monthly_horse_race.py for winners."
        ),
        "vs_random": (
            f"20d banks at washout start mean {b20.get('mean_pct', 0):+.1f}% "
            f"vs random any-day {rnd.get('mean_pct', 0):+.1f}%."
        ),
        "recovery_monthly": (
            "IHSG recovery label → best 4w index forward (~+3% full-sample). "
            "Washout IHSG 4w is negative on average — use banks in washout, not index."
        ),
        "when_to_use": (
            "Weekly/monthly rebalance: retail TA when rules fire; "
            "regime picks which beta sleeve for the next 4w."
        ),
    }
    if b20.get("hit_gt_10pct", 0):
        lines["banks_tail"] = (
            f"20d banks at washout: p90 {b20.get('p90_pct', 0):+.1f}%, "
            f"max {b20.get('max_pct', 0):+.1f}% — tail exists at monthly horizon."
        )
    return lines


def regime_from_levels(
    last: float,
    high_63: float,
    low_20: float,
    ret_5d: float,
    *,
    min_history: bool = True,
) -> dict[str, Any]:
    """Point-in-time regime label from trailing index levels."""
    if high_63 <= 0 or low_20 <= 0:
        return _regime_payload("unknown", last, 0.0, 0.0, ret_5d, 0.0)

    dd_63 = last / high_63 - 1.0
    bounce_20 = last / low_20 - 1.0

    if dd_63 <= -0.10 and bounce_20 < 0.08:
        label = "washout"
    elif dd_63 <= -0.10 and bounce_20 >= 0.08:
        label = "recovery"
    elif bounce_20 >= 0.12 and ret_5d >= 0.05:
        label = "extended"
    else:
        label = "neutral"

    return _regime_payload(label, last, dd_63, bounce_20, ret_5d, 0.0)


def _regime_payload(
    label: str,
    last: float,
    dd_63: float,
    bounce_20: float,
    ret_5d: float,
    ret_20d: float,
) -> dict[str, Any]:
    return {
        "label": label,
        "core_sleeve_pct": CORE_SLEEVE_PCT.get(label, 0.40),
        "ihsg_last": round(last, 4),
        "dd_from_63d_high_pct": round(dd_63 * 100, 2),
        "bounce_from_20d_low_pct": round(bounce_20 * 100, 2),
        "ret_5d_pct": round(ret_5d * 100, 2),
        "ret_20d_pct": round(ret_20d * 100, 2),
    }


def label_ihsg_close(close: pd.Series) -> pd.DataFrame:
    """Label every day with point-in-time regime metrics."""
    idx = pd.to_numeric(close, errors="coerce").dropna().sort_index()
    rows: list[dict[str, Any]] = []
    for i in range(len(idx)):
        if i < 21:
            continue
        sub = idx.iloc[: i + 1]
        last = float(sub.iloc[-1])
        high_63 = float(sub.iloc[-63:].max()) if len(sub) >= 63 else float(sub.max())
        low_20 = float(sub.iloc[-20:].min())
        ret_5d = float(sub.iloc[-1] / sub.iloc[-6] - 1.0) if len(sub) >= 6 else 0.0
        ret_20d = float(sub.iloc[-1] / sub.iloc[-21] - 1.0) if len(sub) >= 21 else 0.0
        payload = regime_from_levels(last, high_63, low_20, ret_5d)
        payload["ret_20d_pct"] = round(ret_20d * 100, 2)
        rows.append({"date": sub.index[-1], "close": last, **payload})
    return pd.DataFrame(rows).set_index("date").sort_index()


def episode_runs(labels: pd.Series) -> list[dict[str, Any]]:
    """Contiguous label episodes (excludes unknown)."""
    s = labels.dropna().astype(str)
    if s.empty:
        return []
    episodes: list[dict[str, Any]] = []
    start = s.index[0]
    prev = s.iloc[0]
    for dt, lab in s.iloc[1:].items():
        if lab != prev:
            episodes.append({"label": prev, "start": start, "end": s.index[s.index.get_loc(dt) - 1]})
            start = dt
            prev = lab
    episodes.append({"label": prev, "start": start, "end": s.index[-1]})
    for ep in episodes:
        ep["n_days"] = int((ep["end"] - ep["start"]).days) + 1
    return episodes


def transition_events(labels: pd.Series) -> list[dict[str, Any]]:
    """Day-level regime transitions."""
    s = labels.dropna().astype(str)
    out: list[dict[str, Any]] = []
    prev = None
    for dt, lab in s.items():
        if prev is not None and lab != prev:
            out.append({"date": dt, "from": prev, "to": lab})
        prev = lab
    return out


def _fwd_return(close: pd.Series, start: pd.Timestamp, horizon_days: int) -> float | None:
    if start not in close.index:
        return None
    pos = close.index.get_loc(start)
    end_pos = pos + horizon_days
    if end_pos >= len(close):
        return None
    a = float(close.iloc[pos])
    b = float(close.iloc[end_pos])
    if a <= 0:
        return None
    return b / a - 1.0


def bank_equal_weight_return(banks: pd.DataFrame, start: pd.Timestamp, horizon_days: int) -> float | None:
    cols = [c for c in CORE_BANKS if c in banks.columns]
    if not cols:
        return None
    rets = []
    for c in cols:
        r = _fwd_return(banks[c].dropna(), start, horizon_days)
        if r is not None:
            rets.append(r)
    if not rets:
        return None
    return float(np.mean(rets))


def sleeve_return(
    ihsg_ret: float | None,
    bank_ret: float | None,
    core_pct: float,
) -> float | None:
    if bank_ret is None:
        return None
    cash_ret = 0.0
    return core_pct * bank_ret + (1.0 - core_pct) * cash_ret


def episode_entry_forward_stats(
    tape: pd.DataFrame,
    banks: pd.DataFrame,
    entry_label: str,
) -> dict[str, Any]:
    """Forward returns from first day of each entry_label episode."""
    labels = tape["label"]
    episodes = [e for e in episode_runs(labels) if e["label"] == entry_label]
    rows: list[dict[str, Any]] = []
    for ep in episodes:
        dt = ep["start"]
        if dt not in tape.index:
            continue
        core = float(tape.loc[dt, "core_sleeve_pct"])
        row: dict[str, Any] = {
            "start": str(dt.date()),
            "end": str(ep["end"].date()),
            "n_days": ep["n_days"],
            "dd_from_63d_high_pct": float(tape.loc[dt, "dd_from_63d_high_pct"]),
            "bounce_from_20d_low_pct": float(tape.loc[dt, "bounce_from_20d_low_pct"]),
        }
        for h in FORWARD_HORIZONS_DAYS:
            ih = _fwd_return(tape["close"], dt, h)
            bk = bank_equal_weight_return(banks, dt, h)
            bb = _fwd_return(_aligned_series(banks, "BBCA.JK"), dt, h)
            sl = sleeve_return(ih, bk, core)
            row[f"ihsg_fwd_{h}d_pct"] = round(ih * 100, 2) if ih is not None else None
            row[f"banks_fwd_{h}d_pct"] = round(bk * 100, 2) if bk is not None else None
            row[f"bbca_fwd_{h}d_pct"] = round(bb * 100, 2) if bb is not None else None
            row[f"sleeve_fwd_{h}d_pct"] = round(sl * 100, 2) if sl is not None else None
        rows.append(row)

    lanes = ("ihsg", "banks_ew", "bbca", "sleeve")
    prefix_map = {"ihsg": "ihsg", "banks_ew": "banks", "bbca": "bbca", "sleeve": "sleeve"}
    lane_stats: dict[str, Any] = {}
    for lane in lanes:
        prefix = prefix_map[lane]
        lane_stats[lane] = {}
        for h in FORWARD_HORIZONS_DAYS:
            col = f"{prefix}_fwd_{h}d_pct"
            lane_stats[lane][f"fwd_{h}d"] = summarize_returns_pct(
                [r[col] for r in rows if r.get(col) is not None]
            )

    return {
        "episodes": len(rows),
        "entries": rows,
        "lanes": lane_stats,
        # legacy keys for older consumers
        **{
            f"{pfx}_fwd_{h}d": lane_stats[lane][f"fwd_{h}d"]
            for lane, pfx in (
                ("ihsg", "ihsg"),
                ("banks_ew", "banks"),
                ("bbca", "bbca"),
                ("sleeve", "sleeve"),
            )
            for h in FORWARD_HORIZONS_DAYS
        },
    }


def fetch_and_cache(
    *,
    refresh: bool = False,
    end: str | None = None,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    from idn_spike_explainer import fetch_history

    end_s = end or (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    IHSG_CACHE.parent.mkdir(parents=True, exist_ok=True)

    if IHSG_CACHE.exists() and not refresh:
        tape = pd.read_parquet(IHSG_CACHE)
        if not tape.empty and "close" in tape.columns:
            tape.index = pd.to_datetime(tape.index)
    else:
        close, _ = fetch_history([INDEX_PROXY], IHSG_START, end_s)
        if close.empty or INDEX_PROXY not in close.columns:
            raise RuntimeError("Failed to fetch ^JKSE")
        tape = label_ihsg_close(close[INDEX_PROXY])
        tape.to_parquet(IHSG_CACHE)

    if BANKS_CACHE.exists() and not refresh:
        banks = pd.read_parquet(BANKS_CACHE)
        banks.index = pd.to_datetime(banks.index)
    else:
        close_b, _ = fetch_history(CORE_BANKS, BANKS_START, end_s)
        if close_b.empty:
            raise RuntimeError("Failed to fetch core bank prices")
        banks = close_b.sort_index()
        banks.to_parquet(BANKS_CACHE)

    # Incremental append if cache is stale vs end
    last_ix = tape.index.max()
    end_ts = pd.Timestamp(end_s) - pd.Timedelta(days=1)
    if last_ix.date() < end_ts.date() and not refresh:
        close, _ = fetch_history([INDEX_PROXY], str((last_ix - pd.Timedelta(days=90)).date()), end_s)
        if not close.empty and INDEX_PROXY in close.columns:
            merged_close = close[INDEX_PROXY].sort_index()
            full = merged_close.combine_first(tape["close"])
            tape = label_ihsg_close(full)
            tape.to_parquet(IHSG_CACHE)
        close_b, _ = fetch_history(CORE_BANKS, str((banks.index.max() - pd.Timedelta(days=90)).date()), end_s)
        if not close_b.empty:
            banks = banks.combine_first(close_b).sort_index()
            banks.to_parquet(BANKS_CACHE)

    return tape, banks


def label_distribution(tape: pd.DataFrame) -> dict[str, int]:
    return {str(k): int(v) for k, v in tape["label"].value_counts().items()}


def current_regime(tape: pd.DataFrame) -> dict[str, Any]:
    if tape.empty:
        return {"label": "unknown"}
    row = tape.iloc[-1]
    return {
        "as_of": str(tape.index[-1].date()),
        "label": str(row["label"]),
        "core_sleeve_pct": float(row["core_sleeve_pct"]),
        "dd_from_63d_high_pct": float(row["dd_from_63d_high_pct"]),
        "bounce_from_20d_low_pct": float(row["bounce_from_20d_low_pct"]),
        "ret_5d_pct": float(row["ret_5d_pct"]),
        "ret_20d_pct": float(row["ret_20d_pct"]),
        "ihsg_last": float(row["close"]),
    }
