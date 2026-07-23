#!/usr/bin/env python3
"""Weekly Indonesia position sheet — actionable weights.

Priority order (what actually works OOS):
  1. Retail TA — compounder support/RSI + blue-chip sleeves (replicated playbook)
  2. Regime — IHSG washout/recovery → banks
  3. OOS resource tilt (small)
  4. Tactical group_sync (tiny, paper)

Example:
  python scripts/run_idn_weekly_position_sheet.py
  python scripts/idn_paper_tracker.py --portfolio backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "alpha"))

from idn_research_evidence import LANES, gather_metrics  # noqa: E402
from idn_fry_actionable_lib import load_fry_watch_monitors  # noqa: E402
from idn_fry_ara_alert_lib import build_ara_alert_pack  # noqa: E402
from idn_fry_best_pick_lib import pick_best_fry_candidates  # noqa: E402
from idn_fry_outcome_certainty_lib import certainty_blurb_for_tier  # noqa: E402
from idn_retail_strategies import PLAYBOOK, build_all_signals  # noqa: E402
from idn_retail_gdelt_lib import (  # noqa: E402
    bandar_scores_for_symbols,
    cap_single_name_weights,
    entity_scores_for_symbols,
    filter_retail_symbols,
)
from idn_discovered_universe_lib import discover_position_sheet_inputs  # noqa: E402
from idn_spike_explainer import fetch_history, load_groups, load_universe, peer_moves  # noqa: E402

AUDIT_JSON = REPO / "backtests/outputs/idn_research_audit/latest.json"
REPLICATION_JSON = REPO / "backtests/outputs/idn_retail_replication/latest.json"

OUT = REPO / "backtests/outputs/idn_weekly_position_sheet"
PANEL_CACHE = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
WINNER_GLOB = REPO / "backtests/outputs/idn_invest/patterns/winner_patterns_*.json"

# Risk + GDELT conditioning defaults (overridable via CLI / platform_integration.json)
DEFAULT_MAX_SINGLE_NAME_WEIGHT = 0.25
DEFAULT_GDELT_RETAIL_FILTER = "prefer"  # off | prefer | require
DEFAULT_GDELT_LOOKBACK_DAYS = 5
DEFAULT_GDELT_MIN_MENTION_ROWS = 1
DEFAULT_BANDAR_CONFIRM = "prefer"  # off | prefer | require
DEFAULT_MAX_TILT_SYMBOLS = 12
DEFAULT_SIGNAL_UNIVERSE = "liquid"  # local liquid-50 panel; use tradable only when intended
DEFAULT_REFRESH_WINNER_PATTERNS_DAYS = 0.0  # 0 = never auto-refresh (live subprocess hung runs)
DEFAULT_TILT_SELECTION_MODE = "pattern_profile"  # pattern_profile | named_tickers
DEFAULT_MIN_PATTERN_OOS_LIFT = 1.15


def _liquid_core_from_panel(close: pd.DataFrame, vol: pd.DataFrame) -> list[str]:
    from idn_name_type_lib import ensure_full_universe_snapshot, liquid_core_from_snapshot

    core = liquid_core_from_snapshot(ensure_full_universe_snapshot())
    if core:
        return core
    from idn_name_type_lib import liquid_core_symbols

    return liquid_core_symbols(close.pct_change(), vol, close=close)


def _load_liquid_core_snapshot() -> list[str]:
    snap = REPO / "data_lake/research_panels/idn_name_types/latest.json"
    if snap.exists():
        data = json.loads(snap.read_text(encoding="utf-8"))
        core = data.get("liquid_core_symbols")
        if core:
            return list(core)
    return []
INDEX_PROXY = "^JKSE"
THEME_GROUPS = ("barito_prajogo", "coal_mining", "nickel_mining")

# Replicated retail rules — drive weights when active (symbol-agnostic; weight what fires)
RETAIL_PRIMARY = ("compounder_support_rsi",)
RETAIL_SECONDARY = ("bluechip_support", "banks_rsi_oversold", "drawdown_dip_volume", "ihsg_washout_banks")

OFF_STRATEGIES = [
    "news_ridge_top5_weekly",
    "spike_chase_10pct",
    "mom20_breakout",
    "broker_accdist_only",
    "quiet_volume_build",
    "ma20_golden_cross",
    "fib_618_pullback",
    "breakout_20d_high",
    "fry_trigger_hold_5d",  # empirics: pop is spike-day, not hold from trigger
]

FRY_WATCH_DOC = "data_lake/research_panels/idn_fry_episode/fry_actionable_pack.json"



def _attach_local_ihsg(close: pd.DataFrame, vol: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if INDEX_PROXY in close.columns:
        return close, vol
    ihsg = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
    if not ihsg.exists():
        return close, vol
    s = pd.read_parquet(ihsg)["close"]
    s.index = pd.to_datetime(s.index)
    s.name = INDEX_PROXY
    close = close.join(s, how="left")
    if INDEX_PROXY not in vol.columns:
        vol = vol.copy()
        vol[INDEX_PROXY] = 0.0
    return close, vol


def ensure_index(close: pd.DataFrame, vol: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    if INDEX_PROXY in close.columns:
        return close, vol
    # Prefer local IHSG artifacts (avoid hanging yfinance in offline research loops)
    local_candidates = [
        REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet",
        REPO / "data_lake/markets/yfinance_asia/ihsg_and_core_banks_20260718.csv",
    ]
    for path in local_candidates:
        if not path.exists():
            continue
        try:
            if path.suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_csv(path)
            cols = {str(c).lower(): c for c in df.columns}
            if isinstance(df.index, pd.DatetimeIndex) or "date" in str(df.index.name).lower():
                s = df
            else:
                date_c = cols.get("date")
                inst_c = cols.get("instrument") or cols.get("symbol") or cols.get("ticker")
                close_c = cols.get("close") or cols.get("price_close") or cols.get("adj close")
                if date_c and close_c and inst_c:
                    sub = df[df[inst_c].astype(str).str.contains("JKSE|IHSG", case=False, na=False)]
                    if sub.empty:
                        # single-series file
                        sub = df
                    s = sub.set_index(pd.to_datetime(sub[date_c]))[close_c]
                elif date_c and close_c:
                    s = df.set_index(pd.to_datetime(df[date_c]))[close_c]
                else:
                    continue
            if isinstance(s, pd.DataFrame):
                # take first numeric col or JKSE-like
                num = s.select_dtypes("number")
                s = num.iloc[:, 0] if num.shape[1] else None
            if s is None or s.dropna().empty:
                continue
            s = pd.to_numeric(s, errors="coerce").dropna()
            s.name = INDEX_PROXY
            c2 = s.to_frame()
            v2 = pd.DataFrame(index=c2.index, columns=[INDEX_PROXY], data=0.0)
            return close.join(c2, how="outer").sort_index(), vol.join(v2, how="outer").sort_index()
        except Exception:
            continue
    # Last resort: leave without index rather than hang on yfinance
    close, vol = _attach_local_ihsg(close, vol)
    return close, vol



def load_panel_offline(universe_mode: str = "liquid") -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Local liquid/all panels only — no yfinance.

    Important: research_universe mode "liquid" is only core banks (3).
    Offline sheet uses the full liquid parquet symbol set for signals/group_sync.
    """
    from idn_panel_lib import IDX_LIQUID_PANEL, IDX_ALL_PANEL, load_idx_close_volume

    if universe_mode in ("tradable", "merged") and IDX_ALL_PANEL.exists():
        df = pd.read_parquet(IDX_ALL_PANEL)
        if isinstance(df.index, pd.MultiIndex) and "symbol" in (df.index.names or []):
            syms = sorted(set(df.index.get_level_values("symbol").astype(str)))
        else:
            syms = sorted(set(df.reset_index()["symbol"].astype(str))) if "symbol" in df.reset_index().columns else []
    else:
        df = pd.read_parquet(IDX_LIQUID_PANEL)
        syms = sorted(set(df.index.get_level_values("symbol").astype(str)))
    close, vol = load_idx_close_volume(syms, min_date="2019-07-01")
    use = [s for s in syms if s in close.columns]
    if not use:
        raise SystemExit("offline panel empty — expected idn_liquid_daily_panel.parquet")
    close, vol = close[use].sort_index(), vol[use].sort_index()
    if INDEX_PROXY not in close.columns:
        ihsg = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
        if ihsg.exists():
            s = pd.read_parquet(ihsg)["close"]
            s.index = pd.to_datetime(s.index)
            s.name = INDEX_PROXY
            close = close.join(s, how="left")
            vol[INDEX_PROXY] = 0.0
    return close, vol, use


def load_panel(
    universe_mode: str = DEFAULT_SIGNAL_UNIVERSE,
    *,
    allow_live_fetch: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Load close/volume from local panels. Live yfinance only if allow_live_fetch=True."""
    from idn_panel_lib import load_idx_panel_for_universe

    groups = load_groups()
    extra = sorted({t for g in groups.values() for t in g.get("tickers", [])})
    close, vol, universe = load_idx_panel_for_universe(mode=universe_mode, min_date="2019-07-01")
    if close.empty:
        if not allow_live_fetch:
            raise SystemExit(
                "local IDX panel empty — run a research pull or pass --allow-live-fetch "
                "(live yfinance can hang)."
            )
        end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
        from idn_panel_lib import load_research_universe

        syms = sorted(set(load_research_universe(mode=universe_mode) + extra + [INDEX_PROXY]))
        close, vol = fetch_history(syms, "2019-07-01", end)
        universe = [s for s in syms if s in close.columns and s != INDEX_PROXY]
    else:
        missing = [s for s in extra if s not in close.columns]
        if missing and allow_live_fetch:
            end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
            c2, v2 = fetch_history(missing, str(close.index.min().date()), end)
            close = close.join(c2, how="outer").sort_index()
            vol = vol.join(v2, how="outer").sort_index()
        close, vol = _attach_local_ihsg(close, vol)
        if INDEX_PROXY not in close.columns and allow_live_fetch:
            c2, v2 = fetch_history([INDEX_PROXY], str(close.index.min().date()), str(close.index.max().date()))
            close = close.join(c2, how="outer").sort_index()
            vol = vol.join(v2, how="outer").sort_index()
        # Keep universe as panel symbols; extras only if present (no silent empty cols)
        universe = sorted({s for s in (set(universe) | set(extra)) if s in close.columns})
    return close, vol, universe


def theme_symbols() -> set[str]:
    groups = load_groups()
    out: set[str] = set()
    for g in THEME_GROUPS:
        out.update(groups.get(g, {}).get("tickers", []))
    return out


def regime_state(close: pd.DataFrame) -> dict[str, Any]:
    if INDEX_PROXY not in close.columns:
        return {"label": "unknown", "action": "neutral", "core_sleeve_pct": 0.4}
    idx = close[INDEX_PROXY].dropna()
    if len(idx) < 22:
        return {"label": "unknown", "action": "neutral", "core_sleeve_pct": 0.4}
    last = float(idx.iloc[-1])
    high_63 = float(idx.iloc[-63:].max()) if len(idx) >= 63 else float(idx.max())
    low_20 = float(idx.iloc[-20:].min())
    dd_63 = last / high_63 - 1.0
    bounce_20 = last / low_20 - 1.0 if low_20 > 0 else 0.0
    ret_5d = float(idx.iloc[-1] / idx.iloc[-6] - 1.0) if len(idx) >= 6 else 0.0
    ret_20d = float(idx.iloc[-1] / idx.iloc[-21] - 1.0) if len(idx) >= 21 else 0.0

    if dd_63 <= -0.10 and bounce_20 < 0.08:
        label, action, core_pct = "washout", "add_core_beta", 0.55
    elif dd_63 <= -0.10 and bounce_20 >= 0.08:
        label, action, core_pct = "recovery", "hold_core_dont_chase", 0.45
    elif bounce_20 >= 0.12 and ret_5d >= 0.05:
        label, action, core_pct = "extended", "trim_core_raise_cash", 0.25
    else:
        label, action, core_pct = "neutral", "standard", 0.40

    return {
        "label": label,
        "action": action,
        "core_sleeve_pct": core_pct,
        "ihsg_last": round(last, 2),
        "dd_from_63d_high_pct": round(dd_63 * 100, 1),
        "bounce_from_20d_low_pct": round(bounce_20 * 100, 1),
        "ret_5d_pct": round(ret_5d * 100, 1),
        "ret_20d_pct": round(ret_20d * 100, 1),
        "as_of": str(idx.index[-1].date()),
    }



def _group_sync_proof_boost() -> bool:
    """True when latest idn_alpha_proof names group_sync_2plus as candidate_alpha."""
    proof = REPO / "backtests/outputs/idn_alpha_proof/latest.json"
    if not proof.exists():
        return False
    try:
        data = json.loads(proof.read_text(encoding="utf-8"))
    except Exception:
        return False
    return (
        str(data.get("verdict") or "") == "candidate_alpha"
        and str(data.get("best_strategy") or "") == "group_sync_2plus"
    )


def tactical_group_sync(close: pd.DataFrame, lookback_days: int = 5) -> list[dict]:
    universe = load_universe()
    theme = theme_symbols()
    rets = close.pct_change()
    dates = close.index[-lookback_days:]
    hits: list[dict] = []
    for dt in dates:
        for sym in universe:
            if sym not in theme or sym not in close.columns or dt not in rets.index:
                continue
            r1 = float(rets.loc[dt, sym])
            if r1 * 100 < 10.0:
                continue
            peers = peer_moves(sym, dt, close, min_pct=0.08)
            n_peers = len(peers[0]["peers_up"]) if peers else 0
            if n_peers >= 2:
                hits.append(
                    {
                        "date": str(dt.date()),
                        "symbol": sym,
                        "return_pct": round(r1 * 100, 1),
                        "n_peers": n_peers,
                    }
                )
    return sorted(hits, key=lambda x: (x["date"], x["return_pct"]), reverse=True)


def _replication_verdicts() -> dict[str, str]:
    if not REPLICATION_JSON.exists():
        return {}
    data = json.loads(REPLICATION_JSON.read_text(encoding="utf-8"))
    verdicts = {s["id"]: s["verdict"] for s in data.get("strategies", [])}
    # Generalized from bbca_support_rsi replication until compounder rule is scored separately.
    if "compounder_support_rsi" not in verdicts and "bbca_support_rsi" in verdicts:
        verdicts["compounder_support_rsi"] = verdicts["bbca_support_rsi"]
    return verdicts


def _retail_firing_symbols(retail: dict[str, Any], strategy_ids: tuple[str, ...]) -> list[str]:
    syms: list[str] = []
    for bucket in ("signals_today", "signals_in_hold"):
        for sig in retail.get(bucket, []):
            if sig["strategy"] in strategy_ids:
                syms.extend(sig.get("symbols", []))
    return sorted(set(syms))


def _allocate_equal(w: dict[str, float], why: dict[str, str], symbols: list[str], budget: float, reason: str) -> None:
    if not symbols or budget <= 0:
        return
    per = budget / len(symbols)
    for sym in symbols:
        w[sym] = w.get(sym, 0.0) + per
        why[sym] = reason


def retail_ta_state(close: pd.DataFrame, vol: pd.DataFrame, universe: list[str]) -> dict[str, Any]:
    """Active retail signals: today + still inside hold window."""
    close, vol = ensure_index(close, vol)
    # ~90 sessions covers hold windows without scanning full multi-year history
    sigs = build_all_signals(close, vol, universe, lookback_days=90)
    verdicts = _replication_verdicts()
    strat_by_id = {s.id: s for s in PLAYBOOK}
    last_dt = close.index[-1]
    today: list[dict] = []
    active: list[dict] = []

    for strat in PLAYBOOK:
        v = verdicts.get(strat.id, "unknown")
        if v not in ("replicate", "conditional"):
            continue
        strat_sigs = sigs.get(strat.id, {})
        if last_dt in strat_sigs:
            today.append(
                {
                    "strategy": strat.id,
                    "jargon": strat.retail_jargon,
                    "symbols": strat_sigs[last_dt],
                    "verdict": v,
                    "description": strat.description,
                    "fired": str(last_dt.date()),
                    "status": "new_today",
                }
            )
        # still in hold window from prior session
        dates = sorted(strat_sigs.keys())
        for dt in reversed(dates):
            if dt > last_dt:
                continue
            days_ago = (last_dt - dt).days
            if days_ago == 0:
                break
            if 0 < days_ago < strat.hold_days:
                active.append(
                    {
                        "strategy": strat.id,
                        "jargon": strat.retail_jargon,
                        "symbols": strat_sigs[dt],
                        "verdict": v,
                        "description": strat.description,
                        "fired": str(dt.date()),
                        "days_ago": days_ago,
                        "hold_days": strat.hold_days,
                        "status": "in_hold",
                    }
                )
                break

    active_ids = {x["strategy"] for x in today} | {x["strategy"] for x in active}
    dip_syms: list[str] = []
    for bucket in (today, active):
        for x in bucket:
            if x["strategy"] == "drawdown_dip_volume":
                dip_syms.extend(x["symbols"])

    return {
        "as_of": str(last_dt.date()),
        "signals_today": today,
        "signals_in_hold": active,
        "active_strategy_ids": sorted(active_ids),
        "compounder_support_rsi": "compounder_support_rsi" in active_ids,
        "bluechip_support": "bluechip_support" in active_ids,
        "banks_rsi_oversold": "banks_rsi_oversold" in active_ids,
        "firing_symbols": _retail_firing_symbols(
            {"signals_today": today, "signals_in_hold": active},
            RETAIL_PRIMARY + RETAIL_SECONDARY,
        ),
        "drawdown_dip_symbols": sorted(set(dip_syms)),
        "primary_active": any(s in active_ids for s in RETAIL_PRIMARY),
    }


def _apply_retail_filters_to_symbols(
    symbols: list[str],
    as_of: str,
    *,
    lane: str,
    gdelt_mode: str,
    bandar_mode: str,
    lookback_days: int,
    min_mention_rows: int,
    bag: dict[str, Any],
) -> list[str]:
    if not symbols or (gdelt_mode == "off" and bandar_mode == "off"):
        return symbols
    scores = (
        entity_scores_for_symbols(symbols, as_of, lookback_days=lookback_days)
        if gdelt_mode != "off"
        else {s: {"available": False, "mention_rows_sum": 0, "active_days": 0, "score": 0.0} for s in symbols}
    )
    bandar_scores = bandar_scores_for_symbols(symbols, as_of) if bandar_mode != "off" else None
    filtered, report = filter_retail_symbols(
        symbols,
        scores,
        mode=gdelt_mode,
        min_mention_rows=min_mention_rows,
        bandar_scores=bandar_scores,
        bandar_mode=bandar_mode,
    )
    bag[lane] = report
    return filtered


def build_weights(
    regime: dict[str, Any],
    tilt_syms: list[str],
    avoid_syms: set[str],
    tactical: list[dict],
    retail: dict[str, Any],
    liquid_core: list[str],
    *,
    max_single_name_weight: float = DEFAULT_MAX_SINGLE_NAME_WEIGHT,
    gdelt_mode: str = DEFAULT_GDELT_RETAIL_FILTER,
    gdelt_lookback_days: int = DEFAULT_GDELT_LOOKBACK_DAYS,
    gdelt_min_mention_rows: int = DEFAULT_GDELT_MIN_MENTION_ROWS,
    bandar_mode: str = DEFAULT_BANDAR_CONFIRM,
    max_tilt_symbols: int = DEFAULT_MAX_TILT_SYMBOLS,
    tilt_pattern_rationales: dict[str, str] | None = None,
) -> tuple[dict[str, float], dict[str, str], str, dict[str, Any]]:
    """Retail TA first, then regime/tilt. Returns weights, rationale, mode, policy_meta."""
    w: dict[str, float] = {}
    why: dict[str, str] = {}
    mode = "standard"
    policy_meta: dict[str, Any] = {"retail_filter": {}, "weight_caps": {}}
    as_of = str(retail.get("as_of", ""))

    has_compounder = retail.get("compounder_support_rsi")
    has_bluechip = retail.get("bluechip_support")
    has_banks_rsi = retail.get("banks_rsi_oversold")
    primary = retail.get("primary_active", False)
    label = regime.get("label", "neutral")

    compounder_syms = _retail_firing_symbols(retail, ("compounder_support_rsi",))
    bluechip_syms = _retail_firing_symbols(retail, ("bluechip_support",))
    bank_rsi_syms = _retail_firing_symbols(retail, ("banks_rsi_oversold",))

    compounder_syms = _apply_retail_filters_to_symbols(
        compounder_syms,
        as_of,
        lane="compounder_support_rsi",
        gdelt_mode=gdelt_mode,
        bandar_mode=bandar_mode,
        lookback_days=gdelt_lookback_days,
        min_mention_rows=gdelt_min_mention_rows,
        bag=policy_meta["retail_filter"],
    )
    bluechip_syms = _apply_retail_filters_to_symbols(
        bluechip_syms,
        as_of,
        lane="bluechip_support",
        gdelt_mode=gdelt_mode,
        bandar_mode=bandar_mode,
        lookback_days=gdelt_lookback_days,
        min_mention_rows=gdelt_min_mention_rows,
        bag=policy_meta["retail_filter"],
    )
    bank_rsi_syms = _apply_retail_filters_to_symbols(
        bank_rsi_syms,
        as_of,
        lane="banks_rsi_oversold",
        gdelt_mode=gdelt_mode,
        bandar_mode=bandar_mode,
        lookback_days=gdelt_lookback_days,
        min_mention_rows=gdelt_min_mention_rows,
        bag=policy_meta["retail_filter"],
    )

    # --- Lane 1: Retail TA — weight symbols that actually fired ---
    if has_compounder and compounder_syms:
        mode = "retail_compounder_support_rsi"
        inv_budget = 0.68 if label != "extended" else 0.50
        _allocate_equal(w, why, compounder_syms, inv_budget, "retail: compounder support+RSI")
        # Bank beta sleeve when compounder signal is bank-heavy or regime supportive
        bank_companions = [s for s in liquid_core if s not in compounder_syms]
        if bank_companions and label in ("washout", "recovery", "neutral"):
            _allocate_equal(w, why, bank_companions[:2], 0.12, "retail: bank beta sleeve")
            tilt_budget = 0.12
            cash = max(0.0, 1.0 - inv_budget - 0.12 - tilt_budget)
        else:
            tilt_budget = 0.20
            cash = max(0.0, 1.0 - inv_budget - tilt_budget)
    elif has_bluechip and bluechip_syms:
        mode = "retail_bluechip_support"
        inv_budget = 0.55 if label != "extended" else 0.40
        _allocate_equal(w, why, bluechip_syms, inv_budget, "retail: blue-chip at 40d support")
        tilt_budget = 0.22
        cash = max(0.0, 1.0 - inv_budget - tilt_budget)
    elif has_banks_rsi and bank_rsi_syms:
        mode = "retail_banks_rsi"
        inv_budget = 0.62
        _allocate_equal(w, why, bank_rsi_syms, inv_budget, "retail: bank RSI oversold")
        tilt_budget = 0.25
        cash = 0.13
    else:
        # --- Lane 2–4: no retail signal — regime core + tilt ---
        tilt_budget = 0.35 if label in ("washout", "recovery", "neutral") else 0.20
        # group_sync_2plus cleared OOS alpha-proof (candidate_alpha) — size as research tilt, not toy.
        proof_boost = _group_sync_proof_boost()
        if tactical and label != "extended":
            tact_pct = 0.15 if proof_boost else 0.10
            tact_n = 3 if proof_boost else 2
        else:
            tact_pct = 0.0
            tact_n = 0
        core_pct = float(regime.get("core_sleeve_pct", 0.4))
        # Keep investable after larger tactical
        if core_pct + tilt_budget + tact_pct > 0.92:
            tilt_budget = max(0.15, 0.92 - core_pct - tact_pct)
        cash = max(0.0, 1.0 - core_pct - tilt_budget - tact_pct)
        per_bank = core_pct / max(len(liquid_core), 1)
        for b in liquid_core:
            w[b] = per_bank
            why[b] = f"core_beta:{label}"

        if tactical and tact_pct > 0:
            tact_names = []
            for h in tactical:
                if h["symbol"] not in tact_names:
                    tact_names.append(h["symbol"])
                if len(tact_names) >= tact_n:
                    break
            per_t = tact_pct / len(tact_names)
            tag = "tactical_group_sync (oos_candidate_alpha)" if proof_boost else "tactical_group_sync (paper)"
            for s in tact_names:
                w[s] = w.get(s, 0.0) + per_t
                why[s] = tag

        if cash > 0.01:
            w["CASH"] = cash
            why["CASH"] = regime.get("action", "standard")

    # Tilt sleeve (smaller when retail active)
    tilt_cap = max(1, int(max_tilt_symbols))
    if primary or mode.startswith("retail"):
        tilt_syms = [s for s in tilt_syms if s not in avoid_syms and s not in liquid_core][:tilt_cap]
    else:
        tilt_syms = [s for s in tilt_syms if s not in avoid_syms and s not in liquid_core][: max(tilt_cap, 6)]

    if tilt_syms and tilt_budget > 0:
        per = tilt_budget / len(tilt_syms)
        rationales = tilt_pattern_rationales or {}
        for s in tilt_syms:
            w[s] = w.get(s, 0.0) + per
            tag = rationales.get(s, "oos_resource_tilt")
            tilt_label = f"pattern_tilt:{tag}" if tag != "oos_resource_tilt" else "oos_resource_tilt"
            why[s] = why.get(s, "") + (" + " if s in why else "") + tilt_label

    # No universe-wide oversold/dip adds — retail sleeve is blue-chip playbook, not a 50-name screener.

    if "CASH" not in w and mode.startswith("retail"):
        w["CASH"] = cash
        why["CASH"] = "uninvested"

    # Micro group_sync under retail when OOS proof is candidate_alpha
    if tactical and (primary or mode.startswith("retail")) and _group_sync_proof_boost():
        micro = 0.05
        names = []
        for h in tactical:
            if h["symbol"] not in names and h["symbol"] not in w:
                names.append(h["symbol"])
            if len(names) >= 1:
                break
        if names:
            take = min(micro, float(w.get("CASH", 0.0)))
            if take > 0:
                w["CASH"] = float(w.get("CASH", 0.0)) - take
                w[names[0]] = w.get(names[0], 0.0) + take
                why[names[0]] = why.get(names[0], "") + (" + " if names[0] in why else "") + "tactical_group_sync_micro"


    # Normalize
    non_cash = sum(v for k, v in w.items() if k != "CASH")
    target_inv = 1.0 - w.get("CASH", 0.0)
    if non_cash > target_inv + 1e-9:
        scale = target_inv / non_cash
        for k in list(w):
            if k != "CASH":
                w[k] *= scale

    w, why, policy_meta["weight_caps"] = cap_single_name_weights(
        w,
        why,
        max_weight=max_single_name_weight,
    )

    return w, why, mode, policy_meta


def render_md(report: dict) -> str:
    mode = report.get("weight_mode", "standard")
    lines = [
        "# Indonesia weekly position sheet",
        "",
        f"**As of:** {report['as_of']}  |  **Mode:** `{mode}`  |  **Regime:** {report['regime']['label']}",
        "",
    ]
    if report.get("retail_ta", {}).get("primary_active"):
        lines.append("## PRIMARY: compounder / blue-chip retail sleeve")
        lines.append("")
        show_ids = set(RETAIL_PRIMARY) | set(RETAIL_SECONDARY)
        for sig in report["retail_ta"].get("signals_today", []) + report["retail_ta"].get("signals_in_hold", []):
            if sig["strategy"] in show_ids:
                lines.append(f"- **{sig['jargon']}** ({sig['status']}) — {sig.get('fired', '')} — {', '.join(sig['symbols'])}")
        lines.append("")

    retail_filter = report.get("retail_filter") or report.get("gdelt_filter") or {}
    if retail_filter:
        lines.append("## Retail filters (GDELT + bandar)")
        lines.append("")
        for lane, detail in retail_filter.items():
            bandar = detail.get("bandar_action") or detail.get("bandar_mode", "")
            suffix = f" [{bandar}]" if bandar else ""
            lines.append(
                f"- **{lane}**: {detail.get('action')}{suffix} → "
                f"{', '.join(detail.get('output_symbols', [])) or '—'}"
            )
        lines.append("")
    if report.get("weight_caps", {}).get("capped"):
        lines.append("## Single-name caps")
        lines.append("")
        for row in report["weight_caps"]["capped"]:
            lines.append(f"- {row['symbol']} capped at {row['to']:.0%}")
        lines.append("")

    lines.append("## What to do")
    lines.append("")
    for bullet in report["actions"]:
        lines.append(f"- {bullet}")
    lines.append("")
    lines.append("## Target weights")
    lines.append("")
    lines.append("| Ticker | Weight | Why |")
    lines.append("|--------|--------|-----|")
    for sym, wt in sorted(report["weights"].items(), key=lambda x: -x[1]):
        lines.append(f"| {sym} | {wt:.1%} | {report['rationale'].get(sym, '')} |")
    lines.append("")
    fry_w = report.get("fry_watch_only", [])
    if fry_w:
        lines.append("## Fry episode monitors (watch only — 0% weight)")
        lines.append("")
        lines.append("Pre-pop bandar state. **Do not buy the trigger** — wait for ARA spike day or skip.")
        lines.append("")
        lines.append("| Ticker | Tier | 5d ret | Vol× | Score | Note |")
        lines.append("|--------|------|--------|------|-------|------|")
        for m in fry_w:
            lines.append(
                f"| {m['yahoo_symbol']} | {m.get('tier', '')} | {m.get('return_5d_pct', '')}% "
                f"| {m.get('vol_ratio_20d', '')} | {m.get('action_score', '')} | monitor pop day |"
            )
        cert = report.get("fry_outcome_certainty")
        if cert:
            lines.append("")
            lines.append(f"**Outcome menu (T1 historical):** {cert}")
        ara = report.get("fry_ara_alerts", {}).get("alerts") or []
        if ara:
            lines.append("")
            lines.append("### ARA pop alerts (today)")
            lines.append("")
            lines.append("| Ticker | Move | Class | Recent trigger |")
            lines.append("|--------|------|-------|----------------|")
            for a in ara:
                lines.append(
                    f"| {a['yahoo_symbol']} | {a.get('return_1d_pct')}% | {a.get('ara_class')} "
                    f"| {a.get('recent_t1_trigger_date') or 'fresh'} |"
                )
        picks = report.get("fry_best_picks", {}).get("top_picks") or []
        if picks:
            lines.append("")
            lines.append("### Fry best picks (gated top checks)")
            lines.append("")
            lines.append("Selective shortlist after hard gates — still 0% weight.")
            lines.append("")
            lines.append("| Rank | Ticker | Score | 5d ret | Vol× | Gates | Failures |")
            lines.append("|------|--------|-------|--------|------|-------|----------|")
            for p in picks:
                fails = ", ".join(p.get("hard_failures") or []) or "—"
                lines.append(
                    f"| {p.get('pick_rank')} | {p['yahoo_symbol']} | {p.get('rank_score')} "
                    f"| {p.get('features', {}).get('return_5d_pct')}% "
                    f"| {p.get('features', {}).get('vol_ratio_20d')} "
                    f"| {p.get('gates_passed')}/{p.get('gates_total')} | {fails} |"
                )
        lines.append("")
    lines.append("## Do NOT auto-trade")
    lines.append("")
    for x in report["off_list"]:
        lines.append(f"- {x}")
    lines.append("")
    lines.append("*Paper-trade first. Retail replication: `docs/IDN_RETAIL_REPLICATION.md`*")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--max-single-name-weight", type=float, default=DEFAULT_MAX_SINGLE_NAME_WEIGHT)
    ap.add_argument(
        "--gdelt-retail-filter",
        choices=["off", "prefer", "require"],
        default=DEFAULT_GDELT_RETAIL_FILTER,
    )
    ap.add_argument("--gdelt-lookback-days", type=int, default=DEFAULT_GDELT_LOOKBACK_DAYS)
    ap.add_argument("--gdelt-min-mention-rows", type=int, default=DEFAULT_GDELT_MIN_MENTION_ROWS)
    ap.add_argument(
        "--bandar-confirm",
        choices=["off", "prefer", "require"],
        default=DEFAULT_BANDAR_CONFIRM,
        help="Bandar-lite / broker accumulation confirm for retail entries",
    )
    ap.add_argument("--max-tilt-symbols", type=int, default=DEFAULT_MAX_TILT_SYMBOLS)
    ap.add_argument(
        "--signal-universe",
        choices=["liquid", "tradable", "merged"],
        default=DEFAULT_SIGNAL_UNIVERSE,
        help="Panel-derived scan universe (default: tradable from idx_all history)",
    )
    ap.add_argument(
        "--refresh-winner-patterns-days",
        type=float,
        default=DEFAULT_REFRESH_WINNER_PATTERNS_DAYS,
        help="Re-run winner_patterns if artifact older than N days (0=never auto-refresh)",
    )
    ap.add_argument("--offline", action="store_true", help="Use local panels only; never call yfinance")
    ap.add_argument(
        "--skip-winner-refresh",
        action="store_true",
        help="Use latest winner_patterns on disk without auto-refresh",
    )
    ap.add_argument(
        "--tilt-selection-mode",
        choices=["pattern_profile", "named_tickers"],
        default=DEFAULT_TILT_SELECTION_MODE,
        help="Tilt sleeve: match winner patterns today vs fixed OOS winner tickers",
    )
    ap.add_argument(
        "--min-pattern-oos-lift",
        type=float,
        default=DEFAULT_MIN_PATTERN_OOS_LIFT,
        help="Minimum OOS lift for a pattern to count in profile scoring",
    )
    args = ap.parse_args(argv)


    if getattr(args, "offline", False):
        global fetch_history
        def fetch_history(*a, **k):  # type: ignore
            raise RuntimeError("offline mode: yfinance fetch_history blocked")

    if getattr(args, "offline", False):
        close, vol, universe = load_panel_offline(str(args.signal_universe))
        close_ix, vol_ix = ensure_index(close, vol)
    else:
        close, vol, universe = load_panel(
            str(args.signal_universe),
            allow_live_fetch=bool(getattr(args, "allow_live_fetch", False)),
        )
        close_ix, vol_ix = ensure_index(close, vol)
    regime = regime_state(close_ix)

    refresh_days = 0.0 if args.skip_winner_refresh else float(args.refresh_winner_patterns_days)
    as_of = str(close_ix.index[-1].date())
    discovered = discover_position_sheet_inputs(
        close_ix,
        vol_ix,
        as_of=as_of,
        symbols=universe,
        max_tilt_symbols=int(args.max_tilt_symbols),
        refresh_winner_patterns_days=refresh_days,
        universe_mode=str(args.signal_universe),
        tilt_selection_mode=str(args.tilt_selection_mode),
        min_pattern_oos_lift=float(args.min_pattern_oos_lift),
    )
    top = list(discovered["tilt_candidates"])
    avoid = set(discovered["avoid"])
    liquid_core = discovered["liquid_core"] or _liquid_core_from_panel(close_ix, vol_ix) or _load_liquid_core_snapshot()
    discovery_meta = discovered.get("discovery_meta", {})
    discovery_meta["refresh_winner_patterns"] = discovered.get("refresh_winner_patterns", {})
    discovery_meta["signal_universe_size"] = len(universe)
    discovery_meta["liquid_core"] = liquid_core

    retail = retail_ta_state(close_ix, vol_ix, universe)
    from idn_fry_pop_research_lib import CATALOG_JSON, load_fry_pop_catalog

    fry_catalog = load_fry_pop_catalog()
    try:
        fry_watch = load_fry_watch_monitors(
            min_tier="monitor",
            rebuild=bool(fry_catalog) and not getattr(args, "offline", False),
        )
        fry_best_picks = pick_best_fry_candidates(fry_watch, top_k=3, as_of=as_of)
        ara_pack = build_ara_alert_pack(watchlist=fry_watch, as_of=pd.Timestamp(as_of))
        fry_certainty_blurb = certainty_blurb_for_tier(t1=True)
    except Exception as exc:
        fry_watch, fry_best_picks, ara_pack = [], {}, {}
        fry_certainty_blurb = f"fry_skip: {exc}"
    # Always compute; build_weights sizes it. Keep tiny sleeve even under retail when proof boosts.
    tactical = tactical_group_sync(close_ix)
    if retail.get("primary_active") and not _group_sync_proof_boost():
        tactical = []
    elif retail.get("primary_active") and _group_sync_proof_boost():
        tactical = tactical[:1]  # one name max under retail


    weights, rationale, mode, policy_meta = build_weights(
        regime,
        top,
        avoid,
        tactical,
        retail,
        liquid_core,
        max_single_name_weight=float(args.max_single_name_weight),
        gdelt_mode=str(args.gdelt_retail_filter),
        gdelt_lookback_days=int(args.gdelt_lookback_days),
        gdelt_min_mention_rows=int(args.gdelt_min_mention_rows),
        bandar_mode=str(args.bandar_confirm),
        max_tilt_symbols=int(args.max_tilt_symbols),
        tilt_pattern_rationales=discovery_meta.get("pattern_rationales"),
    )

    # Fry monitors never receive weight — strip if any collision with tilt/tactical
    fry_syms = {m["yahoo_symbol"] for m in fry_watch}
    for sym in fry_syms:
        if sym in weights and weights[sym] > 0:
            freed = weights.pop(sym)
            rationale.pop(sym, None)
            weights["CASH"] = weights.get("CASH", 0.0) + freed
            rationale["CASH"] = rationale.get("CASH", "") + " (fry watch demoted to cash)"

    actions: list[str] = []
    firing = retail.get("firing_symbols", [])
    if retail.get("primary_active"):
        if retail.get("compounder_support_rsi"):
            actions.append(
                f"BUY / OVERWEIGHT compounders at support+RSI — {', '.join(firing) or 'see signals'}."
            )
        for sig in retail.get("signals_in_hold", []):
            if sig["strategy"] in RETAIL_PRIMARY:
                actions.append(f"Still in hold window: {sig['jargon']} fired {sig['fired']} ({sig['days_ago']}d ago).")
    elif retail.get("bluechip_support"):
        actions.append(f"OVERWEIGHT blue chips at support — {', '.join(firing) or 'see signals'}.")
    elif retail.get("banks_rsi_oversold"):
        actions.append(f"OVERWEIGHT liquid core — RSI oversold on {', '.join(firing) or ', '.join(liquid_core)}.")
    else:
        actions.append("No retail TA signal today — running regime + tilt sleeve.")
        if regime["label"] == "washout":
            actions.append("ADD banks — IHSG washout, bounce not extended.")
        elif regime["label"] == "recovery":
            actions.append("HOLD banks — recovery, don't chase spikes.")
        elif regime["label"] == "extended":
            actions.append("TRIM — extended bounce; raise cash.")

    if top and not retail.get("primary_active"):
        sel = discovery_meta.get("selection_mode", "named_tickers")
        if sel == "pattern_profile":
            actions.append(f"Pattern tilt ({sel}): {', '.join(top[: min(8, len(top))])}…")
        else:
            actions.append(f"Tilt (discovered OOS): {', '.join(top[: min(8, len(top))])}…")
    if avoid:
        actions.append(f"Avoid: {', '.join(sorted(avoid)[:5])}…")
    if tactical:
        actions.append(f"Small tactical sync: {', '.join(dict.fromkeys(h['symbol'] for h in tactical[:2]))}")
    elevated = [m for m in fry_watch if m.get("tier") in ("elevated", "high")]
    top_picks = fry_best_picks.get("top_picks") or []
    if top_picks:
        syms = ", ".join(f"{p['yahoo_symbol']} (score {p.get('rank_score')})" for p in top_picks)
        actions.append(f"FRY BEST PICKS (gated, 0%): {syms}")
    elif elevated:
        syms = ", ".join(f"{m['yahoo_symbol']} ({m.get('return_5d_pct')}% 5d)" for m in elevated)
        actions.append(f"FRY WATCH ONLY (0% weight): {syms} — monitor for ARA pop; do not hold from trigger.")
    elif fry_watch:
        actions.append(
            f"FRY WATCH ONLY: {', '.join(m['yahoo_symbol'] for m in fry_watch[:5])} — pre-pop monitor, no allocation."
        )
    actions.append("OFF: news ridge, spike chase, golden cross, fib, breakout, fry hold-from-trigger.")

    evidence_summary = []
    if AUDIT_JSON.exists():
        audit = json.loads(AUDIT_JSON.read_text(encoding="utf-8"))
        evidence_summary = [
            {"lane": r["lane"], "status": r["status"], "summary": r["summary"]}
            for r in audit.get("lane_verdicts", [])
        ]

    report: dict[str, Any] = {
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "as_of": as_of,
        "weight_mode": mode,
        "regime": regime,
        "actions": actions,
        "weights": {k: round(v, 4) for k, v in weights.items()},
        "rationale": rationale,
        "tilt_candidates": top,
        "avoid_list": sorted(avoid),
        "tactical_signals": tactical,
        "retail_ta": retail,
        "fry_watch_only": fry_watch,
        "fry_watch_source": FRY_WATCH_DOC,
        "fry_outcome_certainty": fry_certainty_blurb,
        "fry_ara_alerts": ara_pack,
        "fry_best_picks": fry_best_picks,
        "off_list": OFF_STRATEGIES,
        "evidence_summary": evidence_summary,
        "research_doc": "docs/IDN_RESEARCH.md",
        "retail_replication_doc": "docs/IDN_RETAIL_REPLICATION.md",
        "discovered_universe": discovery_meta,
        "fry_pop_catalog": str(CATALOG_JSON) if fry_catalog else None,
        "fry_pop_catalog_patterns": len(fry_catalog.get("scoring_patterns", [])) if fry_catalog else 0,
        "retail_filter": policy_meta.get("retail_filter", {}),
        "gdelt_filter": policy_meta.get("retail_filter", {}),
        "weight_caps": policy_meta.get("weight_caps", {}),
        "policy": {
            "max_single_name_weight": float(args.max_single_name_weight),
            "gdelt_retail_filter": str(args.gdelt_retail_filter),
            "gdelt_lookback_days": int(args.gdelt_lookback_days),
            "gdelt_min_mention_rows": int(args.gdelt_min_mention_rows),
            "bandar_confirm": str(args.bandar_confirm),
            "max_tilt_symbols": int(args.max_tilt_symbols),
            "signal_universe": str(args.signal_universe),
            "signal_universe_size": len(universe),
            "discover_from_data": True,
            "tilt_selection_mode": str(args.tilt_selection_mode),
            "min_pattern_oos_lift": float(args.min_pattern_oos_lift),
            "refresh_winner_patterns_days": float(args.refresh_winner_patterns_days),
        },
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    (OUT / "latest.md").write_text(render_md(report), encoding="utf-8")

    portfolio = {
        "strategy": "weekly_position_sheet",
        "as_of_week": as_of,
        "weights": report["weights"],
        "regime": regime["label"],
        "weight_mode": mode,
        "retail_active": retail.get("primary_active", False),
        "fry_watch_only": [m["yahoo_symbol"] for m in fry_watch],
        "retail_filter": policy_meta.get("retail_filter", {}),
        "gdelt_filter": policy_meta.get("retail_filter", {}),
        "weight_caps": policy_meta.get("weight_caps", {}),
        "max_single_name_weight": float(args.max_single_name_weight),
        "bandar_confirm": str(args.bandar_confirm),
        "max_tilt_symbols": int(args.max_tilt_symbols),
        "signal_universe": str(args.signal_universe),
        "signal_universe_size": len(universe),
        "discovered_universe": discovery_meta,
        "source": "run_idn_weekly_position_sheet.py",
    }
    (OUT / "latest_portfolio.json").write_text(json.dumps(portfolio, indent=2), encoding="utf-8")

    print(render_md(report))
    print(f"\nWrote {OUT / 'latest.md'}")
    print(f"Paper track: python scripts/idn_paper_tracker.py --portfolio {OUT / 'latest_portfolio.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
