#!/usr/bin/env python3
"""IDX operator brief — Telegram-speed radar + rules-based pick/avoid (no ML).

Answers: what moved, what's hot in news, what we buy/avoid this week, why.

Outputs:
  backtests/outputs/idn_operator/latest.json
  backtests/outputs/idn_operator/latest.md
  backtests/outputs/idn_operator/latest_portfolio.json  (--emit-portfolio)
"""

from __future__ import annotations

import argparse
import json
import math
import sys
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
sys.path.insert(0, str(REPO / "scripts"))

from run_idn_invest_trial import load_liquid_universe  # noqa: E402
from idn_eval_splits import time_cutoff  # noqa: E402
from idn_spike_explainer import fetch_history, load_groups  # noqa: E402
from idn_operator_llm import (  # noqa: E402
    build_evidence_pack,
    enrich_daily_crosscheck,
    portfolio_from_decision,
    synthesize_operator_decision,
)
from idn_analyst_agent import synthesize_analyst_agent  # noqa: E402

OUT = REPO / "backtests/outputs/idn_operator"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
ENTITY = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260611/ticker_week_entity_market_panel.parquet"
INDEX = "^JKSE"

# From single-factor screen — name-specific history (revisit after entity gather).
MOM_PICK_BIAS = {"BYAN.JK", "TKIM.JK", "INKP.JK", "TPIA.JK", "ASII.JK", "AALI.JK"}
MOM_AVOID_BIAS = {"CPIN.JK", "HRUM.JK", "GOTO.JK", "MDKA.JK", "INTP.JK", "MYOR.JK", "ESSA.JK"}
ATTENTION_PICK_BIAS = {"INTP.JK", "MAPA.JK"}
ATTENTION_AVOID_BIAS = {"INCO.JK", "MEDC.JK"}


def _z(s: pd.Series) -> pd.Series:
    s = pd.to_numeric(s, errors="coerce")
    mu, sd = s.mean(), s.std(ddof=0)
    if not np.isfinite(sd) or sd < 1e-12:
        return s * 0.0
    return (s - mu) / sd


def load_broadcast_liquid() -> pd.DataFrame:
    liquid = load_liquid_universe()
    b = pd.read_parquet(BROADCAST)
    b["week_end"] = pd.to_datetime(b["week_end"])
    bl = b[(b["country_iso3"] == "IDN") & (b["yahoo_symbol"].isin(liquid))].copy()
    bl = bl.sort_values(["yahoo_symbol", "week_end"])
    bl["mom_4w"] = (
        bl.groupby("yahoo_symbol")["return_1w"]
        .rolling(4, min_periods=2)
        .sum()
        .reset_index(level=0, drop=True)
        .shift(1)
    )
    return bl


def load_entity_latest() -> pd.DataFrame:
    if not ENTITY.exists():
        return pd.DataFrame()
    e = pd.read_parquet(ENTITY)
    e["week_end"] = pd.to_datetime(e["week_end"])
    e = e[e["country_iso3"] == "IDN"].copy()
    if e.empty:
        return e
    last_week = e["week_end"].max()
    return e[e["week_end"] == last_week]


def scan_daily_spikes(close: pd.DataFrame, *, min_pct: float = 8.0, days: int = 5) -> list[dict]:
    rets = close.pct_change()
    rows: list[dict] = []
    for sym in close.columns:
        if sym == INDEX:
            continue
        for dt in close.index[-days:]:
            if dt not in rets.index:
                continue
            r = float(rets.loc[dt, sym])
            if np.isfinite(r) and r * 100 >= min_pct:
                rows.append({"ticker": sym, "date": str(dt.date()), "return_pct": round(r * 100, 1)})
    return sorted(rows, key=lambda x: -x["return_pct"])[:15]


def build_brief(*, aggressive: bool = False, top_n: int = 6) -> dict[str, Any]:
    liquid = load_liquid_universe()
    bl = load_broadcast_liquid()
    if bl.empty:
        raise SystemExit("broadcast panel empty for liquid IDX")

    last_week = bl["week_end"].max()
    snap = bl[bl["week_end"] == last_week].copy()
    ent = load_entity_latest()

    if not ent.empty:
        snap = snap.merge(
            ent[
                [
                    "yahoo_symbol",
                    "entity_mention_rows",
                    "mean_market_relevance_score",
                    "mean_tone_avg",
                ]
            ],
            on="yahoo_symbol",
            how="left",
        )
    else:
        snap["entity_mention_rows"] = np.nan

    snap["mention_rank"] = snap["entity_mention_rows"].rank(ascending=False, pct=True)
    snap["mom_rank"] = snap["mom_4w"].rank(ascending=False, pct=True)

    # Weekly movers
    movers_up = snap.nlargest(8, "return_1w")[["yahoo_symbol", "return_1w", "mom_4w", "entity_mention_rows"]]
    movers_dn = snap.nsmallest(8, "return_1w")[["yahoo_symbol", "return_1w", "mom_4w", "entity_mention_rows"]]

    # Rules
    picks: list[dict] = []
    avoids: list[dict] = []
    watch: list[dict] = []

    for _, row in snap.iterrows():
        sym = str(row["yahoo_symbol"])
        mom = float(row["mom_4w"]) if pd.notna(row["mom_4w"]) else float("nan")
        ret1 = float(row["return_1w"]) if pd.notna(row["return_1w"]) else float("nan")
        mrank = float(row["mention_rank"]) if pd.notna(row["mention_rank"]) else float("nan")

        reasons: list[str] = []

        if sym in MOM_PICK_BIAS and np.isfinite(mom) and mom > 0:
            picks.append({"ticker": sym, "rule": "mom_bias", "mom_4w": mom, "ret_1w": ret1})
            continue
        if sym in MOM_AVOID_BIAS and np.isfinite(mom) and mom > 0.05:
            avoids.append({"ticker": sym, "rule": "mom_fade_bias", "mom_4w": mom, "ret_1w": ret1})
            continue
        if np.isfinite(mrank) and mrank >= 0.8:
            avoids.append({"ticker": sym, "rule": "fade_headline", "mention_pct": mrank, "ret_1w": ret1})
            continue
        if sym in ATTENTION_PICK_BIAS and np.isfinite(mrank) and mrank >= 0.7:
            picks.append({"ticker": sym, "rule": "attention_pick", "mention_pct": mrank, "ret_1w": ret1})
            continue
        if sym in ATTENTION_AVOID_BIAS and np.isfinite(mrank) and mrank >= 0.5:
            avoids.append({"ticker": sym, "rule": "attention_avoid", "mention_pct": mrank, "ret_1w": ret1})
            continue
        if np.isfinite(mom) and mom > 0.08 and (not np.isfinite(mrank) or mrank < 0.5):
            watch.append({"ticker": sym, "rule": "quiet_momentum", "mom_4w": mom, "ret_1w": ret1})

    # Dynamic mom leaders not in avoid set
    avoid_syms = {a["ticker"] for a in avoids}
    dyn = snap[snap["mom_4w"].notna()].nlargest(12, "mom_4w")
    for _, row in dyn.iterrows():
        sym = str(row["yahoo_symbol"])
        if sym in avoid_syms or sym in {p["ticker"] for p in picks}:
            continue
        if float(row["mom_4w"]) > 0.05:
            picks.append(
                {
                    "ticker": sym,
                    "rule": "mom_leader",
                    "mom_4w": float(row["mom_4w"]),
                    "ret_1w": float(row["return_1w"]),
                }
            )

    # De-dupe picks/avoids, rank picks by mom
    seen: set[str] = set()
    pick_unique = []
    for p in sorted(picks, key=lambda x: -(x.get("mom_4w") or 0)):
        if p["ticker"] not in seen:
            seen.add(p["ticker"])
            pick_unique.append(p)
    picks = pick_unique[:top_n if not aggressive else max(top_n, 8)]

    seen_a: set[str] = set()
    avoid_unique = []
    for a in avoids:
        if a["ticker"] not in seen_a:
            seen_a.add(a["ticker"])
            avoid_unique.append(a)

    # Daily radar (price-only — always fresh)
    end = (datetime.now(UTC).date() + timedelta(days=1)).isoformat()
    close, _ = fetch_history(liquid + [INDEX], "2025-01-01", end)
    spikes = scan_daily_spikes(close) if not close.empty else []

    # IHSG context
    ihsg_line = ""
    if INDEX in close.columns and len(close[INDEX].dropna()) >= 6:
        idx = close[INDEX].dropna()
        ihsg_line = f"IHSG 5d {((idx.iloc[-1]/idx.iloc[-6]-1)*100):+.1f}% | 20d {((idx.iloc[-1]/idx.iloc[-21]-1)*100):+.1f}%"

    entity_weeks_holdout = 0
    entity_holdout_cutoff = None
    if ENTITY.exists():
        e = pd.read_parquet(ENTITY, columns=["week_end", "country_iso3", "yahoo_symbol"])
        e["week_end"] = pd.to_datetime(e["week_end"])
        sub = e[(e.country_iso3 == "IDN") & (e.yahoo_symbol.isin(liquid))]
        if not sub.empty:
            entity_holdout_cutoff = str(time_cutoff(sub["week_end"]).date())
            sub = sub[sub["week_end"] >= entity_holdout_cutoff]
            entity_weeks_holdout = int(sub["week_end"].nunique())

    groups = load_groups()
    theme_hits: list[dict] = []
    for gname, meta in groups.items():
        tickers = meta.get("tickers", [])
        gsub = snap[snap["yahoo_symbol"].isin(tickers)]
        if gsub.empty:
            continue
        theme_hits.append(
            {
                "group": gname,
                "avg_ret_1w_pct": round(float(gsub["return_1w"].mean()) * 100, 2),
                "names": gsub.nlargest(3, "return_1w")["yahoo_symbol"].tolist(),
            }
        )
    theme_hits = sorted(theme_hits, key=lambda x: -x["avg_ret_1w_pct"])

    manifest: dict[str, Any] = {
        "built_at_utc": datetime.now(UTC).isoformat(),
        "mode": "aggressive" if aggressive else "standard",
        "as_of_week": str(last_week.date()),
        "ihsg": ihsg_line,
        "data_freshness": {
            "broadcast_weeks": int(bl["week_end"].nunique()),
            "entity_panel_weeks_holdout_liquid": entity_weeks_holdout,
            "entity_holdout_cutoff": entity_holdout_cutoff,
            "entity_stale_warning": entity_weeks_holdout < 40,
        },
        "movers_up": movers_up.to_dict(orient="records"),
        "movers_down": movers_dn.to_dict(orient="records"),
        "spikes_5d": spikes,
        "theme_groups": theme_hits[:6],
        "pick": picks,
        "avoid": avoid_unique[:12],
        "watch": sorted(watch, key=lambda x: -(x.get("mom_4w") or 0))[:10],
        "philosophy": (
            "Act on opportunity: momentum + quiet names; fade headline chasers. "
            "Paper first — rules from factor screen, not ML."
        ),
    }
    return manifest


def write_md(m: dict[str, Any]) -> str:
    lines = [
        f"# IDX operator brief — {m['as_of_week']}",
        f"- built: {m['built_at_utc']}",
        f"- {m.get('ihsg', '')}",
        "",
    ]
    if m["data_freshness"].get("entity_stale_warning"):
        lines.append(
            f"> **Data:** firm-mention layer thin in OOS holdout ({m['data_freshness']['entity_panel_weeks_holdout_liquid']} weeks "
            f"since {m['data_freshness'].get('entity_holdout_cutoff', 'n/a')}). "
            "Price radar is live; mention fade rules strengthen after entity gather completes."
        )
        lines.append("")

    lines.append("## 🔥 Movers this week")
    for row in m["movers_up"][:6]:
        lines.append(
            f"- **{row['yahoo_symbol']}** {row['return_1w']*100:+.1f}% | mom4w {(row.get('mom_4w') or 0)*100:+.1f}%"
        )
    lines.append("")
    lines.append("## 📉 Laggards")
    for row in m["movers_down"][:5]:
        lines.append(f"- **{row['yahoo_symbol']}** {row['return_1w']*100:+.1f}%")
    lines.append("")

    if m.get("spikes_5d"):
        lines.append("## ⚡ Spike radar (last 5 sessions)")
        for s in m["spikes_5d"][:8]:
            lines.append(f"- **{s['ticker']}** {s['date']} {s['return_pct']:+.1f}%")
        lines.append("")

    lines.append("## ✅ PICK (rules)")
    for p in m["pick"]:
        lines.append(f"- **{p['ticker']}** — {p['rule']}")
    lines.append("")
    lines.append("## 🚫 AVOID")
    for a in m["avoid"]:
        lines.append(f"- **{a['ticker']}** — {a['rule']}")
    lines.append("")
    lines.append("## 👀 WATCH (quiet momentum)")
    for w in m["watch"][:6]:
        lines.append(f"- **{w['ticker']}** mom4w {(w.get('mom_4w') or 0)*100:+.1f}%")
    lines.append("")
    lines.append("## Themes")
    for t in m.get("theme_groups", [])[:4]:
        lines.append(f"- **{t['group']}** avg {t['avg_ret_1w_pct']:+.1f}% | leaders {', '.join(t['names'])}")
    return "\n".join(lines) + "\n"


def _write_agent_md(agent: dict[str, Any]) -> str:
    dec = agent.get("operator_decision") or {}
    lines = [
        "# IDX analyst agent",
        f"- mode: {agent.get('mode')}",
        f"- backend: {agent.get('backend')} ({agent.get('model')})",
        f"- tool_calls: {agent.get('tool_calls')}",
        f"- turns: {agent.get('turns')}",
        f"- as_of: {agent.get('as_of')}",
        "",
    ]
    if dec.get("summary"):
        lines.extend(["## Summary", dec["summary"], ""])
    if dec.get("final_picks"):
        lines.append("## Final picks (tool-reasoned)")
        for p in dec["final_picks"]:
            lines.append(f"- **{p.get('ticker')}** — {p.get('reason', '')}")
        lines.append("")
    lines.append("## Analysis trace (tools invoked)")
    for step in agent.get("trace", []):
        if step.get("type") == "tool":
            lines.append(f"- `{step.get('tool')}` args={json.dumps(step.get('args', {}))}")
        elif step.get("type") == "assistant" and "<tool_call>" in (step.get("text") or ""):
            lines.append(f"- turn {step.get('turn')}: tool calls requested")
    lines.append("")
    body = (agent.get("text") or "").strip()
    if body:
        lines.extend(["---", "", body[:6000], ""])
    return "\n".join(lines)


def write_llm_md(m: dict[str, Any], llm: dict[str, Any]) -> str:
    dec = llm.get("operator_decision") or {}
    lines = [
        f"# IDX operator LLM brief — {m.get('as_of_week')}",
        f"- backend: {llm.get('backend')} ({llm.get('model')})",
        f"- daily as-of: {(m.get('daily_crosscheck') or {}).get('as_of')}",
        "",
    ]
    if dec.get("summary"):
        lines.extend(["## Executive summary", dec["summary"], ""])
    if dec.get("final_picks"):
        lines.append("## Final picks (LLM-reconciled)")
        for p in dec["final_picks"]:
            lines.append(
                f"- **{p.get('ticker')}** — {p.get('primary_driver', 'n/a')}: {p.get('reason', '')}"
            )
        lines.append("")
    if dec.get("evidence_used"):
        lines.append("## Evidence used")
        for e in dec["evidence_used"]:
            lines.append(f"- {e}")
        lines.append("")
    if dec.get("evidence_missing"):
        lines.append("## Evidence missing")
        for e in dec["evidence_missing"]:
            lines.append(f"- {e}")
        lines.append("")
    for section, key in [
        ("Sentiment vs quant", "sentiment_crosscheck"),
        ("Rules vs reality", "rules_vs_reality"),
        ("Reconcile notes", "reconcile_notes"),
    ]:
        if dec.get(key):
            lines.extend([f"## {section}", str(dec[key]), ""])
    if dec.get("kill_conditions"):
        lines.append("## Kill switches")
        for k in dec["kill_conditions"]:
            lines.append(f"- {k}")
        lines.append("")
    body = llm.get("text", "").strip()
    if body:
        lines.extend(["---", "", body, ""])
    return "\n".join(lines)


def emit_portfolio(
    m: dict[str, Any],
    *,
    max_names: int = 8,
    llm_decision: dict | None = None,
    liquid: list[str] | None = None,
) -> dict[str, Any]:
    if llm_decision and liquid:
        llm_port = portfolio_from_decision(llm_decision, m, liquid=liquid, max_names=max_names)
        if llm_port:
            return llm_port

    picks = [p["ticker"] for p in m["pick"]][:max_names]
    avoid = {a["ticker"] for a in m["avoid"]}
    picks = [p for p in picks if p not in avoid]
    if not picks:
        picks = ["BBCA.JK", "BBRI.JK", "BMRI.JK"]
    w = 1.0 / len(picks)
    return {
        "strategy": "idn_operator_rules_aggressive",
        "as_of_week": m["as_of_week"],
        "built_at_utc": m["built_at_utc"],
        "weights": {s: round(w, 4) for s in picks},
        "avoid": sorted(avoid),
        "note": "Equal-weight paper sleeve from operator rules — opportunity-first.",
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aggressive", action="store_true", help="Wider pick list + portfolio tilt.")
    ap.add_argument("--emit-portfolio", action="store_true", help="Write latest_portfolio.json for paper tracker.")
    ap.add_argument("--top-n", type=int, default=6)
    ap.add_argument("--llm", choices=["auto", "deepseek", "openai", "codex", "skip"], default="skip")
    ap.add_argument(
        "--llm-mode",
        choices=["brief", "agent"],
        default="agent",
        help="brief=read evidence pack; agent=multi-turn tool-calling analyst (default).",
    )
    ap.add_argument("--llm-model", default="")
    ap.add_argument("--llm-max-tokens", type=int, default=4000)
    ap.add_argument("--no-refresh-social", action="store_true", help="Skip public sentiment API refresh before LLM.")
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    liquid = load_liquid_universe()
    manifest = build_brief(aggressive=bool(args.aggressive), top_n=int(args.top_n))
    manifest = enrich_daily_crosscheck(manifest, liquid)
    (OUT / "latest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")
    (OUT / "latest.md").write_text(write_md(manifest), encoding="utf-8")
    print((OUT / "latest.md").read_text(encoding="utf-8"))

    llm_decision = None
    if args.llm != "skip":
        if not args.no_refresh_social:
            from idn_social_sentiment_collector import collect, write_outputs

            social = collect(liquid=liquid)
            write_outputs(social)
            manifest["public_sentiment_refreshed_at"] = social.get("collected_at_utc")
        if args.llm_mode == "agent":
            llm_result = synthesize_analyst_agent(
                manifest,
                liquid=liquid,
                backend=args.llm,
                model=args.llm_model,
                out_dir=OUT,
                max_tokens=int(args.llm_max_tokens),
            )
        else:
            pack = build_evidence_pack(manifest, liquid=liquid)
            (OUT / "evidence_pack.json").write_text(json.dumps(pack, indent=2, default=str) + "\n", encoding="utf-8")
            llm_result = synthesize_operator_decision(
                pack,
                backend=args.llm,
                model=args.llm_model,
                out_dir=OUT,
                max_tokens=int(args.llm_max_tokens),
            )
        llm_decision = llm_result.get("operator_decision")
        (OUT / "latest_llm.json").write_text(json.dumps(llm_result, indent=2, default=str) + "\n", encoding="utf-8")
        mode_label = "agent" if args.llm_mode == "agent" else "brief"
        llm_md_name = f"latest_llm_{mode_label}.md" if args.llm_mode == "agent" else "latest_llm.md"
        if args.llm_mode == "agent":
            llm_md_body = _write_agent_md(llm_result)
        else:
            llm_md_body = write_llm_md(manifest, llm_result)
        (OUT / llm_md_name).write_text(llm_md_body, encoding="utf-8")
        (OUT / "latest_llm.md").write_text(llm_md_body, encoding="utf-8")
        if llm_result.get("errors"):
            (OUT / "llm_errors.txt").write_text("\n".join(llm_result["errors"]) + "\n", encoding="utf-8")
        print("\n--- LLM operator brief ---\n")
        print((OUT / "latest_llm.md").read_text(encoding="utf-8")[:4000])
        if llm_decision:
            manifest["llm_decision"] = llm_decision
            (OUT / "latest.json").write_text(json.dumps(manifest, indent=2, default=str) + "\n", encoding="utf-8")

    if args.emit_portfolio:
        rules_port = emit_portfolio(manifest, max_names=8 if args.aggressive else 6, liquid=liquid)
        rules_path = OUT / "latest_rules_portfolio.json"
        rules_path.write_text(json.dumps(rules_port, indent=2) + "\n", encoding="utf-8")
        print(f"\nrules portfolio: {rules_path}")

        primary = rules_port
        if llm_decision and liquid:
            llm_port = portfolio_from_decision(
                llm_decision, manifest, liquid=liquid, max_names=8 if args.aggressive else 6
            )
            if llm_port:
                llm_path = OUT / "latest_llm_portfolio.json"
                llm_path.write_text(json.dumps(llm_port, indent=2) + "\n", encoding="utf-8")
                primary = llm_port
                print(f"llm portfolio: {llm_path}")

        path = OUT / "latest_portfolio.json"
        path.write_text(json.dumps(primary, indent=2) + "\n", encoding="utf-8")
        print(f"primary portfolio: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
