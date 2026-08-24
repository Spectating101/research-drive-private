#!/usr/bin/env python3
"""Indonesia (IDN) single-country lab: quant pipeline + LLM synthesis.

Runs walk-forward models, strategy grid, promotion gates, article samples,
then asks an LLM (OpenAI if keyed, else Codex CLI) to interpret results
against the evidence pack — narrative layer on top of computed metrics.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import subprocess
import sys
import urllib.request
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd
from dotenv import load_dotenv

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from promote_signal import GateThresholds, run_gates  # noqa: E402
from run_asia_news_market_modeling_trial import (  # noqa: E402
    perf,
    ridge_fit_predict,
    zscore_from_train,
)
from run_research_sprint_v2 import attach_macro_baselines  # noqa: E402
from src.research.fingerprint import make_fingerprint  # noqa: E402

COUNTRY = "IDN"
FUSED = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"
CRYPTO = REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"
BROADCAST = REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"
PROCESSED = REPO / "data_lake/news_shock_taxonomy/processed"
OUT = REPO / "backtests/outputs/indonesia_lab"

SHOCKS = [
    "financial_stress",
    "geopolitical_security",
    "governance_corruption",
    "health",
    "macro_policy",
    "natural_environment",
    "political_instability",
    "trade_supply_chain",
]
FEATURES = [
    "mean_tone_weighted",
    "market_relevant_share",
    *SHOCKS,
    "z_epu",
    "z_gpr_country",
    "z_vix_close",
]
TARGET = "fwd_return_1w"


def _load_env() -> None:
    for p in [REPO / ".env.local", REPO / ".env", REPO.parent / ".env.local", REPO.parent / ".env"]:
        if p.exists():
            load_dotenv(p, override=False)


def _ask_deepseek(system: str, user: str, model: str, max_tokens: int = 1200) -> str:
    api_key = os.getenv("DEEPSEEK_API_KEY", "")
    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY not set")
    body = json.dumps(
        {
            "model": model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            "temperature": 0.2,
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        }
    ).encode("utf-8")
    req = urllib.request.Request(
        base_url,
        data=body,
        headers={"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=90) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    return payload["choices"][0]["message"]["content"]


def weekly_to_monthly_equity(weekly: pd.Series) -> pd.Series:
    s = weekly.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().fillna(0.0)
    return (1.0 + s).cumprod().resample("ME").last().dropna()


def write_curve(path: Path, weekly: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    weekly_to_monthly_equity(weekly).to_frame("equity").to_csv(path)


def idn_country_frame() -> pd.DataFrame:
    df = pd.read_parquet(FUSED)
    df["week_end"] = pd.to_datetime(df["week_end"])
    df = df[df["country_iso3"] == COUNTRY].copy()
    df = attach_macro_baselines(df)
    for c in ["epu", "gpr_country", "vix_close"]:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        sd = float(s.std(ddof=0))
        df[f"z_{c}"] = (s - s.mean()) / sd if sd > 0 else 0.0
    shock_cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in df.columns]
    for col in shock_cols:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("week_end")


def idn_crypto_overlay() -> pd.DataFrame:
    c = pd.read_parquet(CRYPTO)
    c["week_end"] = pd.to_datetime(c["week_end"])
    c = c[c["country_iso3"] == COUNTRY].copy()
    cols = [x for x in c.columns if x.endswith("_per_1k_crypto_rows")]
    return c[["week_end", *cols]]


def walkforward_country(df: pd.DataFrame, min_train: int, alpha: float) -> pd.DataFrame:
    feat = [c for c in FEATURES if c in df.columns]
    feat += [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in df.columns]
    feat = list(dict.fromkeys(feat))
    weeks = sorted(df["week_end"].dropna().unique())
    rows = []
    for i, week in enumerate(weeks):
        if i < min_train:
            continue
        train = df[df["week_end"] < week]
        test = df[df["week_end"] == week]
        if test.empty:
            continue
        pred = ridge_fit_predict(train, test, feat, TARGET, alpha)
        row = test.iloc[0].to_dict()
        row["pred_fwd_return_1w"] = float(pred[0]) if len(pred) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows)


def country_strategies(wf: pd.DataFrame) -> dict[str, pd.Series]:
    idx = pd.to_datetime(wf["week_end"])
    ret = wf.set_index(idx)[TARGET]
    pred = wf.set_index(idx)["pred_fwd_return_1w"]
    risk = wf.set_index(idx)[[f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in wf.columns]].fillna(0)
    risk_score = risk.apply(lambda col: (col - col.mean()) / col.std(ddof=0) if col.std(ddof=0) > 0 else 0).sum(axis=1)

    long_pred = ret.where(pred > 0, 0.0)
    short_flat = ret.where(pred > 0, 0.0)  # same as long flat — long-only timing
    avoid_high_risk = ret.where(risk_score < risk_score.quantile(0.75), 0.0)
    return {
        "idn_index_buy_hold": ret,
        "idn_ridge_long_flat": long_pred,
        "idn_avoid_high_news_risk": avoid_high_risk,
    }


def idn_stock_universe(n: int = 40) -> list[str]:
    b = pd.read_parquet(BROADCAST, columns=["yahoo_symbol", "country_iso3", "row_count_daily"])
    sub = b[b["country_iso3"] == COUNTRY]
    top = sub.groupby("yahoo_symbol")["row_count_daily"].median().sort_values(ascending=False)
    return top.head(n).index.tolist()


def walkforward_idn_stocks(symbols: list[str], min_train: int, alpha: float) -> pd.DataFrame:
    b = pd.read_parquet(BROADCAST)
    b["week_end"] = pd.to_datetime(b["week_end"])
    b = b[(b["country_iso3"] == COUNTRY) & (b["yahoo_symbol"].isin(symbols))].copy()
    feat = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in b.columns]
    weeks = sorted(b["week_end"].dropna().unique())
    pred_rows = []
    for i, week in enumerate(weeks):
        if i < min_train:
            continue
        train = b[b["week_end"] < week]
        test = b[b["week_end"] == week]
        if len(test) < 5:
            continue
        for sym, grp in test.groupby("yahoo_symbol"):
            tr = train[train["yahoo_symbol"] == sym]
            if len(tr) < 30:
                continue
            p = ridge_fit_predict(tr, grp, feat, TARGET, alpha)
            pred_rows.append(
                {
                    "week_end": week,
                    "yahoo_symbol": sym,
                    TARGET: float(grp[TARGET].iloc[0]),
                    "pred_fwd_return_1w": float(p[0]),
                }
            )
    return pd.DataFrame(pred_rows)


def stock_top_tercile_strategy(preds: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    weekly = []
    for week, g in preds.groupby("week_end"):
        sub = g.dropna(subset=[TARGET, "pred_fwd_return_1w"])
        if len(sub) < 6:
            continue
        k = max(1, len(sub) // 3)
        top = sub.nlargest(k, "pred_fwd_return_1w")[TARGET].mean()
        eq = sub[TARGET].mean()
        weekly.append({"week_end": week, "top_tercile": top, "equal_weight": eq})
    w = pd.DataFrame(weekly)
    if w.empty:
        return pd.Series(dtype=float), pd.Series(dtype=float)
    w["week_end"] = pd.to_datetime(w["week_end"])
    w = w.set_index("week_end")
    return w["top_tercile"], w["equal_weight"]


def shock_correlations(df: pd.DataFrame) -> list[dict]:
    rows = []
    for shock in SHOCKS:
        col = f"{shock}_per_1k_rows"
        if col not in df.columns:
            continue
        sub = df[[col, TARGET, "fwd_return_4w", "fwd_vol_4w"]].dropna()
        if len(sub) < 50:
            continue
        rows.append(
            {
                "shock": shock,
                "n": len(sub),
                "corr_return_1w": float(sub[col].corr(sub[TARGET])),
                "corr_return_4w": float(sub[col].corr(sub["fwd_return_4w"])),
                "corr_vol_4w": float(sub[col].corr(sub["fwd_vol_4w"])),
            }
        )
    return sorted(rows, key=lambda x: abs(x["corr_return_1w"]), reverse=True)


def sample_idn_articles(limit: int = 8) -> list[dict]:
    rows = []
    for path in sorted(PROCESSED.glob("*/sample_high_priority.csv"), reverse=True):
        try:
            df = pd.read_csv(path, usecols=["date", "country_iso3", "canonical_url", "shock_hints"], nrows=5000)
        except Exception:
            continue
        sub = df[df["country_iso3"] == COUNTRY].head(3)
        for _, r in sub.iterrows():
            rows.append(
                {
                    "date": str(r["date"]),
                    "url": str(r["canonical_url"]),
                    "shocks": str(r.get("shock_hints", "")),
                }
            )
        if len(rows) >= limit:
            break
    return rows[:limit]


def _pack_for_llm(pack: dict) -> dict:
    """Compact evidence for LLM context limits."""
    return {
        "country": pack.get("country"),
        "date_range": pack.get("date_range"),
        "strategies": pack.get("strategies"),
        "promotion": pack.get("promotion"),
        "shock_correlations": pack.get("shock_correlations", [])[:6],
        "sample_articles": pack.get("sample_articles", [])[:6],
        "stock_universe_size": pack.get("stock_universe_size"),
    }


def llm_synthesize(pack: dict, backend: str, model: str, out_dir: Path | None = None) -> dict:
    system = (
        "You are a senior Indonesia equity research analyst. "
        "Use ONLY the evidence JSON provided. Separate: (1) facts from data, "
        "(2) plausible narratives, (3) what would falsify the thesis, "
        "(4) whether this is tradable vs explanatory. "
        "Be direct; no hype. If promotion gates failed, say so clearly."
    )
    slim = _pack_for_llm(pack)
    user = (
        "Analyze Indonesia (IDN) news-to-market evidence for a quant desk.\n\n"
        f"EVIDENCE_JSON:\n{json.dumps(slim, indent=2, default=str)}\n\n"
        "Structure your reply:\n"
        "## Executive summary\n## What the data actually shows\n"
        "## Best usable signal (if any)\n## Why gates passed/failed\n"
        "## Indonesia-specific story\n## Next 3 pre-registered tests\n"
        "## Tradable vs explain-only verdict"
    )
    _load_env()
    errors = []
    prompt = f"{system}\n\n{user}"

    if backend in {"auto", "deepseek"} and os.getenv("DEEPSEEK_API_KEY"):
        try:
            ds_model = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
            text = _ask_deepseek(system, user, ds_model, max_tokens=1200)
            return {"backend": "deepseek", "model": ds_model, "text": text, "errors": errors}
        except Exception as exc:
            errors.append(f"deepseek: {exc}")

    if backend in {"auto", "openai"} and os.getenv("OPENAI_API_KEY"):
        try:
            from openai import OpenAI

            client = OpenAI()
            resp = client.chat.completions.create(
                model=model or os.getenv("OPENAI_MODEL", "gpt-4o-mini"),
                messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                temperature=0.3,
                max_tokens=1200,
            )
            text = resp.choices[0].message.content or ""
            return {"backend": "openai", "model": model, "text": text, "errors": errors}
        except Exception as exc:
            errors.append(f"openai: {exc}")

    if backend in {"auto", "codex"}:
        prompt_path = (out_dir or OUT) / "llm_prompt.txt"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(prompt, encoding="utf-8")
        try:
            proc = subprocess.run(
                ["codex", "exec", "-"],
                input=prompt,
                capture_output=True,
                text=True,
                timeout=180,
                cwd=str(REPO),
            )
            if proc.returncode == 0 and proc.stdout.strip():
                return {"backend": "codex", "model": "codex-exec", "text": proc.stdout.strip(), "errors": errors}
            errors.append(f"codex rc={proc.returncode} stderr={proc.stderr[:800]}")
        except Exception as exc:
            errors.append(f"codex: {exc}")

    # Deterministic fallback
    fallback = (
        f"## Executive summary\nLLM backends unavailable ({errors}).\n\n"
        f"Promotion passed: {pack.get('promotion', {}).get('n_passed', 0)}/"
        f"{pack.get('promotion', {}).get('n_strategies', 0)}.\n"
        f"Best weekly Sharpe: {pack.get('strategies', [{}])[0] if pack.get('strategies') else 'n/a'}.\n"
        "See evidence_pack.json for full metrics."
    )
    return {"backend": "fallback", "model": None, "text": fallback, "errors": errors}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--min-train-weeks", type=int, default=78)
    ap.add_argument("--ridge-alpha", type=float, default=10.0)
    ap.add_argument("--stock-universe", type=int, default=40)
    ap.add_argument("--llm", choices=["auto", "deepseek", "openai", "codex", "skip"], default="auto")
    ap.add_argument("--llm-model", default="")
    ap.add_argument(
        "--evidence-pack",
        type=Path,
        help="Skip quant; load existing evidence_pack.json and run LLM synthesis only.",
    )
    args = ap.parse_args()

    if args.evidence_pack:
        pack = json.loads(Path(args.evidence_pack).read_text(encoding="utf-8"))
        out_dir = Path(args.evidence_pack).parent
        llm_result = llm_synthesize(pack, args.llm, args.llm_model, out_dir=out_dir)
        (out_dir / "llm_analysis.md").write_text(
            f"# Indonesia lab LLM analysis\n\nBackend: {llm_result['backend']}\n\n{llm_result['text']}\n",
            encoding="utf-8",
        )
        print(llm_result["text"])
        return 0

    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    out_dir = OUT / run_id
    grid_dir = out_dir / "strategy_grid"
    grid_dir.mkdir(parents=True, exist_ok=True)

    country = idn_country_frame()
    wf = walkforward_country(country, args.min_train_weeks, args.ridge_alpha)
    wf.to_csv(out_dir / "idn_country_walkforward.csv", index=False)

    strategies = country_strategies(wf)
    symbols = idn_stock_universe(args.stock_universe)
    stock_preds = walkforward_idn_stocks(symbols, args.min_train_weeks, args.ridge_alpha)
    stock_preds.to_csv(out_dir / "idn_stock_walkforward_preds.csv", index=False)
    if not stock_preds.empty:
        top, eq = stock_top_tercile_strategy(stock_preds)
        strategies["idn_stocks_top_tercile"] = top
        strategies["idn_stocks_equal_weight"] = eq

    perf_rows = []
    for name, weekly in strategies.items():
        if weekly is None or weekly.dropna().empty:
            continue
        write_curve(grid_dir / name / "equity_curve.csv", weekly)
        perf_rows.append({"strategy": name, **asdict(perf(weekly))})
    perf_df = pd.DataFrame(perf_rows).sort_values("sharpe", ascending=False)
    perf_df.to_csv(out_dir / "strategy_perf.csv", index=False)

    gate_rows = []
    thresholds = GateThresholds()
    for name in strategies:
        curve = grid_dir / name / "equity_curve.csv"
        if not curve.exists():
            continue
        out = run_gates(candidate_curve=curve, grid_dir=grid_dir, grid_pattern="*/equity_curve.csv", thresholds=thresholds, factors_csv=None)
        gate_rows.append({"strategy": name, "passed": out.passed, "reasons": " | ".join(out.reasons), **out.metrics})
    gates_df = pd.DataFrame(gate_rows).sort_values("sharpe_per_period", ascending=False, na_position="last")
    gates_df.to_csv(out_dir / "promotion_gates.csv", index=False)

    pack = {
        "country": COUNTRY,
        "run_id": run_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "country_weeks": int(len(country)),
        "date_range": [str(country["week_end"].min().date()), str(country["week_end"].max().date())],
        "walkforward_country_rows": len(wf),
        "stock_universe_size": len(symbols),
        "stock_walkforward_rows": len(stock_preds),
        "shock_correlations": shock_correlations(country),
        "sample_articles": sample_idn_articles(),
        "strategies": perf_df.to_dict(orient="records"),
        "promotion": {
            "n_strategies": len(gate_rows),
            "n_passed": int(gates_df["passed"].sum()) if not gates_df.empty else 0,
            "gates": gates_df.to_dict(orient="records"),
        },
        "fingerprint": make_fingerprint(panel_path=FUSED, config={"country": COUNTRY, "run_id": run_id}),
    }
    (out_dir / "evidence_pack.json").write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")

    llm_result = {"backend": "skip", "text": ""}
    if args.llm != "skip":
        llm_result = llm_synthesize(pack, args.llm, args.llm_model, out_dir=out_dir)
        (out_dir / "llm_analysis.md").write_text(
            f"# Indonesia lab LLM analysis\n\nBackend: {llm_result['backend']}\n\n{llm_result['text']}\n",
            encoding="utf-8",
        )
        if llm_result.get("errors"):
            (out_dir / "llm_errors.txt").write_text("\n".join(llm_result["errors"]), encoding="utf-8")

    print(json.dumps({"run_id": run_id, "out_dir": str(out_dir), "n_passed": pack["promotion"]["n_passed"]}, indent=2))
    print(perf_df.to_string(index=False))
    print("\nPromotion:")
    print(gates_df[["strategy", "passed", "sharpe_per_period", "dsr", "pbo"]].to_string(index=False))
    if llm_result.get("text"):
        print("\n--- LLM (first 2000 chars) ---\n")
        print(llm_result["text"][:2000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
