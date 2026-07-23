#!/usr/bin/env python3
"""IDX-only single-factor screen — ticker + category, no ML.

Tests each news/entity factor alone on Indonesian tickers:
  1) Weekly cross-section rank IC (all IDX vs liquid core)
  2) Sector-group equal-weight signal (banks, coal, nickel, Barito complex)
  3) Per-ticker time-series (liquid names) → PICK / AVOID / NEUTRAL

Outputs:
  backtests/outputs/platform/idn_factor_screen/latest.json
  backtests/outputs/platform/idn_factor_screen/latest.md
"""

from __future__ import annotations

import json
import math
import sys
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))
OUT = REPO / "backtests/outputs/platform/idn_factor_screen"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
GROUPS_CFG = REPO / "config/markets/indonesia_stock_groups.json"
UNIVERSE_CFG = REPO / "config/markets/asia_yfinance_universes.json"

from idn_eval_splits import ERA_OOS, build_eras, time_cutoff  # noqa: E402
TARGETS = ("fwd_return_1w", "fwd_return_4w", "fwd_vol_4w")
ENTITY_FACTORS = (
    "entity_mention_rows",
    "unique_entities",
    "entity_news_days",
    "mean_market_relevance_score",
    "mean_tone_avg",
    "financial_stress_per_1k_entity_rows",
    "political_instability_per_1k_entity_rows",
    "macro_policy_per_1k_entity_rows",
    "geopolitical_security_per_1k_entity_rows",
    "governance_corruption_per_1k_entity_rows",
    "trade_supply_chain_per_1k_entity_rows",
    "health_per_1k_entity_rows",
    "natural_environment_per_1k_entity_rows",
)
BROADCAST_SHOCKS = (
    "financial_stress_per_1k_rows",
    "political_instability_per_1k_rows",
    "macro_policy_per_1k_rows",
    "geopolitical_security_per_1k_rows",
    "mean_market_relevance_score_weighted",
    "news_rows",
)


def load_liquid() -> list[str]:
    cfg = json.loads(UNIVERSE_CFG.read_text(encoding="utf-8"))
    for u in cfg.get("universes", []):
        if u.get("id") == "indonesia_liquid_core":
            return list(u["tickers"])
    return []


def load_groups() -> dict[str, list[str]]:
    cfg = json.loads(GROUPS_CFG.read_text(encoding="utf-8"))
    return {k: list(v["tickers"]) for k, v in cfg.get("groups", {}).items()}


def era_slice(df: pd.DataFrame, start: str | None, end: str | None) -> pd.DataFrame:
    out = df
    if start:
        out = out[out["week_end"] >= pd.Timestamp(start)]
    if end:
        out = out[out["week_end"] < pd.Timestamp(end)]
    return out


def weekly_rank_ic(df: pd.DataFrame, x: str, y: str, *, min_names: int = 8) -> tuple[float, float, int]:
    sub = df[["week_end", x, y]].dropna()
    if len(sub) < 80:
        return np.nan, np.nan, 0
    sub = sub.copy()
    sub["rx"] = sub.groupby("week_end", sort=False)[x].rank()
    sub["ry"] = sub.groupby("week_end", sort=False)[y].rank()
    ics = sub.groupby("week_end", sort=False).apply(
        lambda g: float(g["rx"].corr(g["ry"])) if len(g) >= min_names and g["rx"].std() > 0 else np.nan,
        include_groups=False,
    ).dropna()
    if len(ics) < 10:
        return np.nan, np.nan, int(len(ics))
    a = ics.to_numpy(dtype=float)
    mu = float(a.mean())
    sd = float(a.std(ddof=1))
    return mu, mu / (sd / math.sqrt(len(a)) + 1e-12), int(len(a))


def spearman_ts(df: pd.DataFrame, x: str, y: str) -> tuple[float, float, int]:
    sub = df[[x, y]].dropna()
    if len(sub) < 30:
        return np.nan, np.nan, int(len(sub))
    r = float(sub[x].corr(sub[y], method="spearman"))
    return r, r * math.sqrt(len(sub)), int(len(sub))


def factor_family(name: str) -> str:
    if name in {"entity_mention_rows", "unique_entities", "entity_news_days"}:
        return "firm_attention"
    if "relevance" in name or "tone" in name:
        return "relevance_tone"
    if "per_1k" in name:
        return "entity_taxonomy"
    if name in {"news_rows", "entity_count"}:
        return "country_broadcast"
    return "other"


def screen_xs(df: pd.DataFrame, universe: str, factors: list[str]) -> list[dict]:
    rows = []
    for era, start, end in build_eras(df):
        sub = era_slice(df, start, end)
        for fac in factors:
            if fac not in sub.columns:
                continue
            for tgt in TARGETS:
                if tgt not in sub.columns:
                    continue
                mu, t, w = weekly_rank_ic(sub, fac, tgt)
                rows.append(
                    {
                        "test": "ticker_xs_rank_ic",
                        "universe": universe,
                        "factor": fac,
                        "family": factor_family(fac),
                        "era": era,
                        "target": tgt,
                        "mean_ic": mu,
                        "tstat": t,
                        "weeks": w,
                    }
                )
    return rows


def screen_groups(df: pd.DataFrame, groups: dict[str, list[str]], factor: str) -> list[dict]:
    rows = []
    for gname, tickers in groups.items():
        gdf = df[df["yahoo_symbol"].isin(tickers)].copy()
        if gdf.empty or factor not in gdf.columns:
            continue
        wk = (
            gdf.groupby("week_end", as_index=False)
            .agg(
                signal=(factor, "mean"),
                ret_1w=("fwd_return_1w", "mean"),
                ret_4w=("fwd_return_4w", "mean"),
                vol_4w=("fwd_vol_4w", "mean"),
                n=("yahoo_symbol", "nunique"),
            )
            .query("n >= 2")
        )
        for era, start, end in build_eras(wk):
            sub = era_slice(wk, start, end)
            for tgt, col in [("fwd_return_1w", "ret_1w"), ("fwd_return_4w", "ret_4w"), ("fwd_vol_4w", "vol_4w")]:
                ic, t, n = spearman_ts(sub, "signal", col)
                rows.append(
                    {
                        "test": "sector_group_ts",
                        "group": gname,
                        "factor": factor,
                        "family": factor_family(factor),
                        "era": era,
                        "target": tgt,
                        "spearman": ic,
                        "tstat": t,
                        "weeks": n,
                    }
                )
    return rows


def screen_tickers(df: pd.DataFrame, symbols: list[str], factor: str, *, min_weeks: int = 60) -> list[dict]:
    rows = []
    for sym in symbols:
        tdf = df[df["yahoo_symbol"] == sym].sort_values("week_end").copy()
        if len(tdf) < min_weeks or factor not in tdf.columns:
            continue
        # z-score within ticker history (attention spike vs own baseline)
        mu = tdf[factor].expanding(min_periods=20).mean()
        sd = tdf[factor].expanding(min_periods=20).std(ddof=0)
        tdf["z"] = (tdf[factor] - mu) / sd.replace(0, np.nan)
        for era, start, end in build_eras(tdf):
            sub = era_slice(tdf, start, end)
            for tgt in ("fwd_return_1w", "fwd_return_4w"):
                if tgt not in sub.columns:
                    continue
                ic, t, n = spearman_ts(sub, "z", tgt)
                rows.append(
                    {
                        "test": "ticker_own_history_ts",
                        "ticker": sym,
                        "factor": factor,
                        "era": era,
                        "target": tgt,
                        "spearman": ic,
                        "tstat": t,
                        "weeks": n,
                    }
                )
    return rows


def classify_ticker(tdf: pd.DataFrame, factor: str = "entity_mention_rows", *, min_oos: int = 12) -> dict:
    sym = str(tdf["yahoo_symbol"].iloc[0])
    oos_cut = time_cutoff(tdf["week_end"])
    oos = tdf[tdf["week_end"] >= oos_cut].copy()
    use = oos if len(oos) >= min_oos else tdf.copy()
    era = ERA_OOS if len(oos) >= min_oos else "full_fallback"
    if len(use) < 30:
        return {"ticker": sym, "verdict": "insufficient_data", "oos_t": None, "era": era}
    mu = use[factor].expanding(min_periods=10).mean()
    sd = use[factor].expanding(min_periods=10).std(ddof=0)
    use["z"] = (use[factor] - mu) / sd.replace(0, np.nan)
    ic, t, n = spearman_ts(use, "z", "fwd_return_1w")
    if not np.isfinite(t):
        verdict = "neutral"
    elif t >= 2.0:
        verdict = "pick_attention_long"
    elif t <= -2.0:
        verdict = "avoid_attention_long"
    else:
        verdict = "neutral"
    return {"ticker": sym, "verdict": verdict, "oos_t": t, "oos_ic": ic, "weeks": n, "era": era}


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    liquid = load_liquid()
    groups = load_groups()

    ent = pd.read_parquet(ENTITY)
    ent["week_end"] = pd.to_datetime(ent["week_end"])
    idn = ent[ent["country_iso3"] == "IDN"].copy()
    idn_liq = idn[idn["yahoo_symbol"].isin(liquid)].copy()

    factors = [f for f in ENTITY_FACTORS if f in idn.columns]

    rows: list[dict] = []
    rows.extend(screen_xs(idn, "idx_all", factors))
    rows.extend(screen_xs(idn_liq, "liquid_core", factors))

    # Broadcast shocks on liquid tickers (country news mapped to each ticker)
    if BROADCAST.exists():
        b = pd.read_parquet(BROADCAST)
        b["week_end"] = pd.to_datetime(b["week_end"])
        bl = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))].copy()
        bfac = [c for c in BROADCAST_SHOCKS if c in bl.columns]
        rows.extend(screen_xs(bl, "liquid_broadcast", bfac))

    group_rows: list[dict] = []
    for fac in factors:
        group_rows.extend(screen_groups(idn, groups, fac))

    ticker_rows: list[dict] = []
    mom_picks: list[dict] = []
    mom_avoids: list[dict] = []
    ticker_rows.extend(screen_tickers(idn_liq, liquid, "entity_mention_rows"))
    ticker_rows.extend(screen_tickers(idn_liq, liquid, "mean_market_relevance_score"))
    if BROADCAST.exists():
        b = pd.read_parquet(BROADCAST)
        b["week_end"] = pd.to_datetime(b["week_end"])
        bl = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))].sort_values(["yahoo_symbol", "week_end"])
        bl["mom_4w"] = (
            bl.groupby("yahoo_symbol")["return_1w"]
            .rolling(4, min_periods=2)
            .sum()
            .reset_index(level=0, drop=True)
            .shift(1)
        )
        bl["rev_1w"] = bl.groupby("yahoo_symbol")["return_1w"].shift(1)
        for fac in ("mom_4w", "rev_1w"):
            ticker_rows.extend(screen_tickers(bl, liquid, fac))
        for sym in liquid:
            tdf = bl[bl["yahoo_symbol"] == sym].dropna(subset=["mom_4w", "fwd_return_1w"])
            if len(tdf) < 80:
                continue
            ic, t, n = spearman_ts(tdf, "mom_4w", "fwd_return_1w")
            row = {"ticker": sym, "oos_t": t, "weeks": n, "signal": "mom_4w"}
            if np.isfinite(t) and t >= 2.0:
                mom_picks.append(row)
            elif np.isfinite(t) and t <= -2.0:
                mom_avoids.append(row)

    # Summarize factors
    df = pd.DataFrame(rows)
    summ = []
    for fac in sorted(set(df.factor)):
        f = df[(df.factor == fac) & (df.universe == "liquid_core")]
        ret_oos = f[(f.target == "fwd_return_1w") & (f.era == ERA_OOS)]
        vol_oos = f[(f.target == "fwd_vol_4w") & (f.era == ERA_OOS)]
        ret_full = f[(f.target == "fwd_return_1w") & (f.era == "full")]
        vol_full = f[(f.target == "fwd_vol_4w") & (f.era == "full")]

        def _t(frame: pd.DataFrame) -> float | None:
            if frame.empty or not np.isfinite(frame.iloc[0]["tstat"]):
                return None
            return float(frame.iloc[0]["tstat"])

        summ.append(
            {
                "factor": fac,
                "family": factor_family(fac),
                "ret_1w_full_t": _t(ret_full),
                "ret_1w_oos_t": _t(ret_oos),
                "vol_4w_full_t": _t(vol_full),
                "vol_4w_oos_t": _t(vol_oos),
            }
        )
    summ_df = pd.DataFrame(summ).sort_values("ret_1w_oos_t", key=lambda s: s.abs(), ascending=False)

    # Group best factors
    gdf = pd.DataFrame(group_rows)
    group_best = []
    for gname in groups:
        g = gdf[(gdf.group == gname) & (gdf.target == "fwd_return_1w") & (gdf.era == ERA_OOS)]
        if g.empty:
            continue
        top = g.assign(abs_t=g.tstat.abs()).sort_values("abs_t", ascending=False).iloc[0]
        group_best.append(
            {
                "group": gname,
                "best_factor": top["factor"],
                "oos_t": float(top["tstat"]),
                "direction": "long_attention" if top["tstat"] > 0 else "fade_attention",
            }
        )

    # Ticker pick/avoid on entity mentions
    tdf = pd.DataFrame(ticker_rows)
    mentions_oos = tdf[(tdf.factor == "entity_mention_rows") & (tdf.target == "fwd_return_1w") & (tdf.era == ERA_OOS)]
    ticker_verdicts = []
    for sym in liquid:
        sub = idn_liq[idn_liq["yahoo_symbol"] == sym]
        if sub.empty:
            continue
        ticker_verdicts.append(classify_ticker(sub, "entity_mention_rows"))
    tv = pd.DataFrame(ticker_verdicts)

    picks = tv[tv.verdict == "pick_attention_long"].sort_values("oos_t", ascending=False)
    avoids = tv[tv.verdict == "avoid_attention_long"].sort_values("oos_t")

    # Factor recommendations
    def factor_verdict(row: pd.Series) -> str:
        t = row.get("ret_1w_oos_t")
        if t is None or not np.isfinite(t):
            return "skip"
        if abs(t) < 1.5:
            return "skip"
        return "use_long_attention" if t > 0 else "use_fade_attention"

    summ_df["verdict"] = summ_df.apply(factor_verdict, axis=1)

    manifest = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "method": "single_factor_idx_no_ml",
        "entity_panel": str(ENTITY),
        "span": [str(idn["week_end"].min().date()), str(idn["week_end"].max().date())],
        "idx_tickers": int(idn["yahoo_symbol"].nunique()),
        "liquid_tickers": len(liquid),
        "factor_summary_liquid": summ_df.to_dict(orient="records"),
        "sector_group_signals_oos": group_best,
        "ticker_picks_oos": picks.to_dict(orient="records"),
        "ticker_avoids_oos": avoids.to_dict(orient="records"),
        "ticker_mom_picks": sorted(mom_picks, key=lambda x: x["oos_t"], reverse=True),
        "ticker_mom_avoids": sorted(mom_avoids, key=lambda x: x["oos_t"]),
        "ticker_neutral_count": int((tv.verdict == "neutral").sum()),
        "recommendation": {
            "factors_to_use": summ_df[summ_df.verdict.str.startswith("use")][["factor", "verdict", "ret_1w_oos_t"]].to_dict(orient="records"),
            "factors_to_skip": summ_df[summ_df.verdict == "skip"]["factor"].tolist(),
            "best_sector_plays": group_best,
        },
    }

    latest = OUT / "latest.json"
    latest.write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    lines = [
        "# IDX single-factor screen",
        f"- span: {manifest['span']} | liquid: {len(liquid)} names | IDX: {manifest['idx_tickers']}",
        "",
        "## Factors — use or skip (liquid core, OOS holdout)",
    ]
    for r in summ_df.itertuples():
        lines.append(f"- **{r.factor}** [{r.family}]: ret_1w t={r.ret_1w_oos_t} → **{r.verdict}**")

    lines += ["", "## Sector groups (equal-weight group signal → group return, OOS holdout)"]
    for g in group_best:
        lines.append(f"- **{g['group']}**: {g['best_factor']} t={g['oos_t']:.2f} → {g['direction']}")

    lines += ["", "## Tickers — momentum works (4w mom → next week, full sample)"]
    for r in sorted(mom_picks, key=lambda x: x["oos_t"], reverse=True)[:12]:
        lines.append(f"- **{r['ticker']}** t={r['oos_t']:.2f}")

    lines += ["", "## Tickers — momentum fails / reversal"]
    for r in sorted(mom_avoids, key=lambda x: x["oos_t"])[:12]:
        lines.append(f"- **{r['ticker']}** t={r['oos_t']:.2f}")

    lines += ["", "## Tickers — PICK when firm attention spikes"]
    for r in picks.head(15).itertuples():
        lines.append(f"- **{r.ticker}** t={r.oos_t:.2f}")

    lines += ["", "## Tickers — AVOID / fade attention (OOS holdout)"]
    for r in avoids.head(15).itertuples():
        lines.append(f"- **{r.ticker}** t={r.oos_t:.2f}")

    (OUT / "latest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps(manifest["recommendation"], indent=2, default=str))
    print(f"wrote {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
