from __future__ import annotations

import json
import sys
from dataclasses import asdict
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from promote_signal import GateThresholds, run_gates  # noqa: E402
from run_asia_news_market_modeling_trial import perf, ridge_fit_predict  # noqa: E402
from run_research_sprint_v2 import attach_macro_baselines  # noqa: E402
from src.research.fingerprint import make_fingerprint  # noqa: E402

from quant_ai.config import AnalystConfig  # noqa: E402

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


def weekly_to_monthly_equity(weekly: pd.Series) -> pd.Series:
    s = weekly.copy()
    s.index = pd.to_datetime(s.index)
    s = s.sort_index().fillna(0.0)
    return (1.0 + s).cumprod().resample("ME").last().dropna()


def write_curve(path: Path, weekly: pd.Series) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    weekly_to_monthly_equity(weekly).to_frame("equity").to_csv(path)


def country_frame(cfg: AnalystConfig) -> pd.DataFrame:
    df = pd.read_parquet(cfg.fused_panel)
    df["week_end"] = pd.to_datetime(df["week_end"])
    df = df[df["country_iso3"] == cfg.country].copy()
    df = attach_macro_baselines(df)
    for c in ["epu", "gpr_country", "vix_close"]:
        if c not in df.columns:
            continue
        s = pd.to_numeric(df[c], errors="coerce")
        sd = float(s.std(ddof=0))
        df[f"z_{c}"] = (s - s.mean()) / sd if sd > 0 else 0.0
    for shock in SHOCKS:
        col = f"{shock}_per_1k_rows"
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.sort_values("week_end")


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


def country_strategies(wf: pd.DataFrame, prefix: str) -> dict[str, pd.Series]:
    idx = pd.to_datetime(wf["week_end"])
    ret = wf.set_index(idx)[TARGET]
    pred = wf.set_index(idx)["pred_fwd_return_1w"]
    risk_cols = [f"{s}_per_1k_rows" for s in SHOCKS if f"{s}_per_1k_rows" in wf.columns]
    risk = wf.set_index(idx)[risk_cols].fillna(0)
    risk_score = risk.apply(lambda col: (col - col.mean()) / col.std(ddof=0) if col.std(ddof=0) > 0 else 0).sum(axis=1)
    long_pred = ret.where(pred > 0, 0.0)
    avoid_high_risk = ret.where(risk_score < risk_score.quantile(0.75), 0.0)
    return {
        f"{prefix}_index_buy_hold": ret,
        f"{prefix}_ridge_long_flat": long_pred,
        f"{prefix}_avoid_high_news_risk": avoid_high_risk,
    }


def stock_universe(cfg: AnalystConfig) -> list[str]:
    b = pd.read_parquet(cfg.broadcast_panel, columns=["yahoo_symbol", "country_iso3", "row_count_daily"])
    sub = b[b["country_iso3"] == cfg.country]
    top = sub.groupby("yahoo_symbol")["row_count_daily"].median().sort_values(ascending=False)
    return top.head(cfg.stock_universe).index.tolist()


def walkforward_stocks(cfg: AnalystConfig, symbols: list[str], min_train: int, alpha: float) -> pd.DataFrame:
    b = pd.read_parquet(cfg.broadcast_panel)
    b["week_end"] = pd.to_datetime(b["week_end"])
    b = b[(b["country_iso3"] == cfg.country) & (b["yahoo_symbol"].isin(symbols))].copy()
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


def stock_portfolio_strategies(preds: pd.DataFrame, prefix: str) -> tuple[pd.Series, pd.Series]:
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
    return w["top_tercile"].rename(f"{prefix}_stocks_top_tercile"), w["equal_weight"].rename(f"{prefix}_stocks_equal_weight")


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


def sample_articles(cfg: AnalystConfig, limit: int = 8) -> list[dict]:
    rows = []
    for path in sorted(cfg.processed_news.glob("*/sample_high_priority.csv"), reverse=True):
        try:
            df = pd.read_csv(path, usecols=["date", "country_iso3", "canonical_url", "shock_hints"], nrows=5000)
        except Exception:
            continue
        sub = df[df["country_iso3"] == cfg.country].head(3)
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


def run_quant_pipeline(cfg: AnalystConfig, out_dir: Path | None = None) -> tuple[dict, Path]:
    run_id = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    prefix = cfg.country.lower()
    root = out_dir or (cfg.out_root / cfg.country / run_id)
    grid_dir = root / "strategy_grid"
    grid_dir.mkdir(parents=True, exist_ok=True)

    country = country_frame(cfg)
    wf = walkforward_country(country, cfg.min_train_weeks, cfg.ridge_alpha)
    wf.to_csv(root / f"{prefix}_country_walkforward.csv", index=False)

    strategies = country_strategies(wf, prefix)
    symbols = stock_universe(cfg)
    stock_preds = walkforward_stocks(cfg, symbols, cfg.min_train_weeks, cfg.ridge_alpha)
    stock_preds.to_csv(root / f"{prefix}_stock_walkforward_preds.csv", index=False)
    if not stock_preds.empty:
        top, eq = stock_portfolio_strategies(stock_preds, prefix)
        strategies[top.name] = top
        strategies[eq.name] = eq

    perf_rows = []
    for name, weekly in strategies.items():
        if weekly is None or weekly.dropna().empty:
            continue
        write_curve(grid_dir / name / "equity_curve.csv", weekly)
        perf_rows.append({"strategy": name, **asdict(perf(weekly))})
    perf_df = pd.DataFrame(perf_rows).sort_values("sharpe", ascending=False)
    perf_df.to_csv(root / "strategy_perf.csv", index=False)

    gate_rows = []
    thresholds = GateThresholds()
    for name in strategies:
        curve = grid_dir / name / "equity_curve.csv"
        if not curve.exists():
            continue
        out = run_gates(
            candidate_curve=curve,
            grid_dir=grid_dir,
            grid_pattern="*/equity_curve.csv",
            thresholds=thresholds,
            factors_csv=None,
        )
        gate_rows.append({"strategy": name, "passed": out.passed, "reasons": " | ".join(out.reasons), **out.metrics})
    gates_df = pd.DataFrame(gate_rows).sort_values("sharpe_per_period", ascending=False, na_position="last")
    gates_df.to_csv(root / "promotion_gates.csv", index=False)

    pack = {
        "country": cfg.country,
        "country_label": cfg.country_label,
        "run_id": run_id,
        "built_at_utc": datetime.now(UTC).isoformat(),
        "country_weeks": int(len(country)),
        "date_range": [str(country["week_end"].min().date()), str(country["week_end"].max().date())],
        "walkforward_country_rows": len(wf),
        "stock_universe_size": len(symbols),
        "stock_walkforward_rows": len(stock_preds),
        "shock_correlations": shock_correlations(country),
        "sample_articles": sample_articles(cfg),
        "strategies": perf_df.to_dict(orient="records"),
        "promotion": {
            "n_strategies": len(gate_rows),
            "n_passed": int(gates_df["passed"].sum()) if not gates_df.empty else 0,
            "gates": gates_df.to_dict(orient="records"),
        },
        "fingerprint": make_fingerprint(panel_path=cfg.fused_panel, config={"country": cfg.country, "run_id": run_id}),
        "paths": {"out_dir": str(root), "grid_dir": str(grid_dir)},
    }
    (root / "evidence_pack.json").write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")
    return pack, root
