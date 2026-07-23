#!/usr/bin/env python3
"""Fast offline refresh of IDN weekly sheet using local panels only."""
from __future__ import annotations
import json
from datetime import UTC, datetime
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
PANEL = REPO / "data_lake/markets/yfinance_asia/idn_liquid_daily_panel.parquet"
IHSG = REPO / "data_lake/markets/yfinance_asia/ihsg_regime_daily.parquet"
GROUPS = REPO / "config/markets/indonesia_stock_groups.json"
PROOF = REPO / "backtests/outputs/idn_alpha_proof/latest.json"
OUT = REPO / "backtests/outputs/idn_weekly_position_sheet"
CORE = ["BBCA.JK", "BBRI.JK", "BMRI.JK"]

def load_close() -> pd.DataFrame:
    df = pd.read_parquet(PANEL)
    return df["close"].unstack("symbol").sort_index()

def regime_from_ihsg() -> dict[str, Any]:
    s = pd.read_parquet(IHSG)["close"]
    s.index = pd.to_datetime(s.index)
    last = float(s.iloc[-1])
    dd = last / float(s.iloc[-63:].max()) - 1.0
    bounce = last / float(s.iloc[-20:].min()) - 1.0
    ret5 = last / float(s.iloc[-6]) - 1.0
    if dd <= -0.10 and bounce < 0.08:
        label, core, action = "washout", 0.55, "add_core_beta"
    elif dd <= -0.10 and bounce >= 0.08:
        label, core, action = "recovery", 0.45, "hold_core_dont_chase"
    elif bounce >= 0.12 and ret5 >= 0.05:
        label, core, action = "extended", 0.25, "trim_raise_cash"
    else:
        label, core, action = "neutral", 0.40, "standard"
    return {"label": label, "core_sleeve_pct": core, "action": action,
            "dd_63": round(dd * 100, 2), "bounce_20": round(bounce * 100, 2),
            "ret_5d": round(ret5 * 100, 2), "as_of": str(s.index[-1].date())}

def group_sync(close: pd.DataFrame, lookback: int = 5) -> list[dict]:
    groups = json.loads(GROUPS.read_text(encoding="utf-8"))
    gmap = groups.get("groups") or groups
    rets = close.pct_change()
    dates = close.index[-lookback:]
    hits = []
    for gname, g in gmap.items():
        if not isinstance(g, dict):
            continue
        tickers = [t for t in g.get("tickers", []) if t in close.columns]
        for dt in dates:
            up = []
            for t in tickers:
                r = float(rets.loc[dt, t]) if dt in rets.index else np.nan
                if pd.notna(r) and r >= 0.08:
                    up.append((t, r))
            if len(up) >= 2:
                up = sorted(up, key=lambda x: -x[1])
                hits.append({"date": str(pd.Timestamp(dt).date()), "group": gname,
                             "symbol": up[0][0], "return_pct": round(up[0][1] * 100, 1),
                             "n_peers": len(up)})
    return sorted(hits, key=lambda x: (x["date"], x["return_pct"]), reverse=True)

def proof_boost() -> bool:
    if not PROOF.exists():
        return False
    d = json.loads(PROOF.read_text(encoding="utf-8"))
    return d.get("verdict") == "candidate_alpha" and d.get("best_strategy") == "group_sync_2plus"

def build_fresh(regime, hits):
    w, why = {}, {}
    label = regime["label"]
    core_pct = float(regime["core_sleeve_pct"])
    boost = proof_boost()
    tact_pct = (0.15 if boost else 0.10) if hits and label != "extended" else 0.0
    cash = max(0.15, 1.0 - core_pct - tact_pct)
    for b in CORE:
        w[b] = core_pct / len(CORE)
        why[b] = f"core_beta:{label}"
    names = []
    for h in hits:
        if h["symbol"] not in names:
            names.append(h["symbol"])
        if len(names) >= (3 if boost else 2):
            break
    if names and tact_pct > 0:
        tag = "tactical_group_sync (oos_candidate_alpha)" if boost else "tactical_group_sync (paper)"
        for s in names:
            w[s] = w.get(s, 0.0) + tact_pct / len(names)
            why[s] = tag
    w["CASH"] = cash
    why["CASH"] = regime["action"]
    return w, why, f"offline_regime_{label}" + ("_group_sync" if tact_pct else "")

def merge_retail_prior(prior, hits, regime):
    mode = str(prior.get("weight_mode") or "")
    if not mode.startswith("retail"):
        return None
    w = {k: float(v) for k, v in (prior.get("weights") or {}).items()}
    why = dict(prior.get("rationale") or {})
    if not w:
        return None
    boost = proof_boost()
    if boost and hits:
        cash = float(w.get("CASH", 0.0))
        sleeve = min(0.15 if cash >= 0.20 else 0.05, cash)
        names = []
        for h in hits:
            if h["symbol"] not in names:
                names.append(h["symbol"])
            if len(names) >= 2:
                break
        if names and sleeve > 0:
            w["CASH"] = cash - sleeve
            for s in names:
                w[s] = w.get(s, 0.0) + sleeve / len(names)
                why[s] = (why.get(s, "") + " + " if s in why else "") + "tactical_group_sync (oos_candidate_alpha)"
            mode = mode + "+group_sync"
    return w, why, mode

def main() -> int:
    close = load_close()
    regime = regime_from_ihsg()
    hits = group_sync(close)
    prior_path = OUT / "latest_portfolio.json"
    prior = json.loads(prior_path.read_text(encoding="utf-8")) if prior_path.exists() else {}
    merged = merge_retail_prior(prior, hits, regime)
    if merged:
        weights, rationale, mode = merged
        note = "merged_retail_prior+offline_group_sync"
    else:
        weights, rationale, mode = build_fresh(regime, hits)
        note = "offline_fresh"
    tot = sum(weights.values())
    if tot > 0:
        weights = {k: v / tot for k, v in weights.items()}
    as_of = str(close.index[-1].date())
    report = {
        "strategy": "idn_weekly_position_sheet",
        "as_of_week": as_of, "as_of": as_of, "weight_mode": mode,
        "regime": regime, "weights": weights, "rationale": rationale,
        "group_sync_hits": hits[:12], "proof_boost": proof_boost(),
        "refresh": note, "offline": True,
        "generated_at_utc": datetime.now(UTC).isoformat(),
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest_portfolio.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Indonesia weekly position sheet (offline refresh)", "",
             f"**As of:** {as_of}  |  **Mode:** `{mode}`  |  **Regime:** {regime['label']}",
             f"- proof_boost={proof_boost()} · refresh={note}",
             f"- IHSG dd63={regime['dd_63']}% bounce20={regime['bounce_20']}%", "",
             "| Ticker | Weight | Why |", "|--------|-------:|-----|"]
    for k, v in sorted(weights.items(), key=lambda x: -x[1]):
        lines.append(f"| {k} | {v:.1%} | {rationale.get(k, '')} |")
    lines += ["", "## Recent group_sync", ""]
    if hits:
        for h in hits[:8]:
            lines.append(f"- {h['date']} `{h['symbol']}` {h['group']} +{h['return_pct']}% ({h['n_peers']} peers)")
    else:
        lines.append("- none in lookback")
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
