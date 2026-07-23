"""Discover IDX universes from panel history + research artifacts (no static ticker lists)."""

from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

WINNER_GLOB = REPO / "backtests/outputs/idn_invest/patterns/winner_patterns_*.json"
BIG_WINNER_JSON = REPO / "backtests/outputs/idn_big_winner_reverse/latest.json"
WINNER_SCRIPT = REPO / "alpha/scripts/run_idn_winner_patterns.py"


def _file_age_days(path: Path) -> float:
    if not path.exists():
        return float("inf")
    return (time.time() - path.stat().st_mtime) / 86400.0


def latest_winner_patterns_path() -> Path | None:
    paths = sorted(WINNER_GLOB.parent.glob(WINNER_GLOB.name), reverse=True)
    return paths[0] if paths else None


def load_winner_patterns_report() -> dict[str, Any]:
    path = latest_winner_patterns_path()
    if not path:
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def load_big_winner_reverse_report() -> dict[str, Any]:
    if not BIG_WINNER_JSON.exists():
        return {}
    try:
        return json.loads(BIG_WINNER_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}


def discovered_oos_winners(*, max_n: int = 20) -> list[str]:
    """OOS mean weekly forward-return leaders from latest winner_patterns run."""
    wp = load_winner_patterns_report()
    wl = wp.get("winner_loser", wp)
    rows = wl.get("top20_tickers") or wl.get("top10_tickers") or []
    out: list[str] = []
    for row in rows:
        sym = row.get("yahoo_symbol")
        if sym and sym not in out:
            out.append(str(sym))
        if len(out) >= max_n:
            break
    return out


def discovered_oos_losers(*, max_n: int = 20) -> set[str]:
    wp = load_winner_patterns_report()
    wl = wp.get("winner_loser", wp)
    rows = wl.get("bottom20_tickers") or wl.get("bottom10_tickers") or []
    return {str(r["yahoo_symbol"]) for r in rows[:max_n] if r.get("yahoo_symbol")}


def discovered_big_winner_episode_symbols(*, max_n: int = 30) -> list[str]:
    """Symbols from largest realized 20d runs in winner-first reverse study."""
    bw = load_big_winner_reverse_report()
    out: list[str] = []
    for ep in bw.get("top_episodes", []):
        sym = ep.get("yahoo_symbol")
        if sym and sym not in out:
            out.append(str(sym))
        if len(out) >= max_n:
            break
    return out


def discovered_liquid_core(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    *,
    top_n: int = 15,
) -> list[str]:
    """Top compounders by ADV from price panel — not a config file."""
    from idn_name_type_lib import ensure_full_universe_snapshot, liquid_core_from_snapshot, liquid_core_symbols

    snap = ensure_full_universe_snapshot()
    core = liquid_core_from_snapshot(snap)
    if core:
        return list(core)[:top_n]
    rets = close.pct_change()
    return liquid_core_symbols(rets, vol, close=close, n=top_n)


def discovered_named_tilt_candidates(
    *,
    max_n: int = 12,
    include_big_winner_episodes: bool = True,
) -> tuple[list[str], set[str], dict[str, Any]]:
    """Legacy: tilt from OOS winner ticker rankings (not pattern profile)."""
    avoid = discovered_oos_losers(max_n=20)
    wp = load_winner_patterns_report()
    wp_path = latest_winner_patterns_path()

    ranked: list[str] = []
    for sym in discovered_oos_winners(max_n=max(20, max_n * 2)):
        if sym not in avoid:
            ranked.append(sym)

    episode_boost: list[str] = []
    if include_big_winner_episodes:
        for sym in discovered_big_winner_episode_symbols(max_n=30):
            if sym not in avoid and sym not in ranked:
                episode_boost.append(sym)
        ranked.extend(episode_boost)

    tilt = ranked[:max_n]
    meta: dict[str, Any] = {
        "source": "named_oos_winners",
        "selection_mode": "named_tickers",
        "winner_patterns_path": str(wp_path) if wp_path else None,
        "winner_patterns_age_days": round(_file_age_days(wp_path), 2) if wp_path else None,
        "winner_patterns_universe_mode": wp.get("universe_mode"),
        "winner_patterns_universe_size": wp.get("universe_size"),
        "big_winner_reverse_path": str(BIG_WINNER_JSON) if BIG_WINNER_JSON.exists() else None,
        "oos_winner_pool": discovered_oos_winners(max_n=20),
        "episode_boost": episode_boost[:10],
        "tilt_candidates": tilt,
        "avoid": sorted(avoid),
    }
    return tilt, avoid, meta


def discovered_pattern_tilt_candidates(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    as_of: pd.Timestamp | str,
    symbols: list[str],
    *,
    max_n: int = 12,
    min_oos_lift: float = 1.15,
    min_pattern_matches: int = 1,
) -> tuple[list[str], set[str], dict[str, Any]]:
    """Tilt from today's cross-section vs stable winner patterns (not fixed tickers)."""
    from idn_winner_pattern_lib import (
        anti_pattern_avoid_symbols,
        load_pattern_catalog,
        pattern_rationale,
        rank_symbols_by_winner_patterns,
    )

    as_of = pd.Timestamp(as_of)
    ranked = rank_symbols_by_winner_patterns(
        close,
        vol,
        as_of,
        symbols,
        max_n=max_n,
        min_oos_lift=min_oos_lift,
        min_pattern_matches=min_pattern_matches,
        sleeve="retail_tilt",
    )

    avoid = discovered_oos_losers(max_n=20)
    avoid |= anti_pattern_avoid_symbols(close, vol, as_of, symbols)

    tilt: list[str] = []
    pattern_matches: list[dict[str, Any]] = []
    pattern_rationales: dict[str, str] = {}
    for row in ranked:
        sym = row["yahoo_symbol"]
        if sym in avoid or sym in tilt:
            continue
        tilt.append(sym)
        pattern_matches.append(row)
        pattern_rationales[sym] = pattern_rationale(row.get("matched_patterns") or [])
        if len(tilt) >= max_n:
            break

    catalog = load_pattern_catalog(min_oos_lift=min_oos_lift, sleeve="retail_tilt")
    meta: dict[str, Any] = {
        "source": "discovered_from_data",
        "selection_mode": "pattern_profile",
        "as_of": str(as_of.date()),
        "big_winner_reverse_path": str(BIG_WINNER_JSON) if BIG_WINNER_JSON.exists() else None,
        "pattern_catalog_size": len(catalog),
        "pattern_catalog_sample": [r.pattern for r in catalog[:8]],
        "min_oos_lift": min_oos_lift,
        "min_pattern_matches": min_pattern_matches,
        "pattern_ranked_pool": ranked[: max_n * 2],
        "pattern_matches": pattern_matches,
        "pattern_rationales": pattern_rationales,
        "anti_pattern_avoid": sorted(anti_pattern_avoid_symbols(close, vol, as_of, symbols)),
        "oos_loser_avoid": sorted(discovered_oos_losers(max_n=20)),
        "tilt_candidates": tilt,
        "avoid": sorted(avoid),
    }
    return tilt, avoid, meta


def discovered_tilt_candidates(
    close: pd.DataFrame | None = None,
    vol: pd.DataFrame | None = None,
    as_of: pd.Timestamp | str | None = None,
    symbols: list[str] | None = None,
    *,
    max_n: int = 12,
    selection_mode: str = "pattern_profile",
    min_oos_lift: float = 1.15,
    include_big_winner_episodes: bool = True,
) -> tuple[list[str], set[str], dict[str, Any]]:
    """Tilt + avoid — pattern profile by default; named winners as fallback."""
    use_pattern = (
        selection_mode == "pattern_profile"
        and close is not None
        and vol is not None
        and as_of is not None
        and symbols
        and BIG_WINNER_JSON.exists()
    )
    if use_pattern:
        tilt, avoid, meta = discovered_pattern_tilt_candidates(
            close,
            vol,
            as_of,
            symbols,
            max_n=max_n,
            min_oos_lift=min_oos_lift,
        )
        if tilt:
            return tilt, avoid, meta

    return discovered_named_tilt_candidates(
        max_n=max_n,
        include_big_winner_episodes=include_big_winner_episodes,
    )


def ensure_winner_patterns_fresh(
    *,
    max_age_days: float = 7.0,
    universe_mode: str = "tradable",
    force: bool = False,
) -> dict[str, Any]:
    """Refresh winner_patterns from panel if missing or stale."""
    path = latest_winner_patterns_path()
    age = _file_age_days(path) if path else float("inf")
    # max_age_days <= 0 means never auto-refresh (use on-disk artifact only)
    if not force and max_age_days <= 0:
        return {
            "refreshed": False,
            "skipped": True,
            "reason": "max_age_days<=0",
            "path": str(path) if path else None,
            "age_days": round(age, 2) if path else None,
            "universe_mode": universe_mode,
        }
    if not force and path and age <= max_age_days:
        return {
            "refreshed": False,
            "path": str(path),
            "age_days": round(age, 2),
            "universe_mode": universe_mode,
        }

    script = WINNER_SCRIPT if WINNER_SCRIPT.exists() else REPO / "scripts/run_idn_winner_patterns.py"
    if not script.exists():
        return {"refreshed": False, "error": f"missing script: {script}"}

    try:
        proc = subprocess.run(
            [sys.executable, str(script), "--universe", universe_mode],
            cwd=str(REPO),
            capture_output=True,
            text=True,
            timeout=180,
            env={**dict(__import__("os").environ), "PYTHONPATH": f"{REPO / 'kernel'}:{REPO / 'alpha'}:{REPO / 'alpha' / 'scripts'}:{REPO}"},
        )
    except subprocess.TimeoutExpired:
        return {
            "refreshed": False,
            "error": "winner_patterns refresh timed out after 180s",
            "universe_mode": universe_mode,
            "path": str(path) if path else None,
        }
    path = latest_winner_patterns_path()
    return {
        "refreshed": proc.returncode == 0,
        "returncode": proc.returncode,
        "path": str(path) if path else None,
        "stderr_tail": (proc.stderr or "")[-800:] if proc.returncode != 0 else "",
        "universe_mode": universe_mode,
    }


def discover_position_sheet_inputs(
    close: pd.DataFrame,
    vol: pd.DataFrame,
    *,
    as_of: pd.Timestamp | str | None = None,
    symbols: list[str] | None = None,
    max_tilt_symbols: int = 12,
    refresh_winner_patterns_days: float = 7.0,
    universe_mode: str = "tradable",
    force_refresh_winners: bool = False,
    tilt_selection_mode: str = "pattern_profile",
    min_pattern_oos_lift: float = 1.15,
) -> dict[str, Any]:
    """Full discovery bundle for weekly position sheet."""
    refresh = ensure_winner_patterns_fresh(
        max_age_days=refresh_winner_patterns_days,
        universe_mode=universe_mode,
        force=force_refresh_winners,
    )
    as_of_ts = pd.Timestamp(as_of) if as_of is not None else close.index[-1]
    sym_list = symbols or [c for c in close.columns if str(c) != "CASH"]
    tilt, avoid, tilt_meta = discovered_tilt_candidates(
        close,
        vol,
        as_of_ts,
        sym_list,
        max_n=max_tilt_symbols,
        selection_mode=tilt_selection_mode,
        min_oos_lift=min_pattern_oos_lift,
    )
    liquid_core = discovered_liquid_core(close, vol)
    return {
        "refresh_winner_patterns": refresh,
        "tilt_candidates": tilt,
        "avoid": avoid,
        "liquid_core": liquid_core,
        "discovery_meta": tilt_meta,
    }
