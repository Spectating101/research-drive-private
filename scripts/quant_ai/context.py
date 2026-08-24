from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "scripts"))

from explain_week_move import explain_country  # noqa: E402

from quant_ai.config import AnalystConfig  # noqa: E402


def load_portfolio_context(cfg: AnalystConfig) -> dict:
    ctx: dict = {}
    if cfg.scorecard_path.exists():
        sc = json.loads(cfg.scorecard_path.read_text(encoding="utf-8"))
        ctx["paper_scorecard"] = {
            "period": sc.get("period"),
            "cagr_since_start": sc.get("performance", {}).get("cagr_since_start"),
            "sharpe_daily_252": sc.get("performance", {}).get("sharpe_daily_252"),
            "return_30d": sc.get("performance", {}).get("return_30d"),
            "latest_equity": sc.get("performance", {}).get("latest_equity"),
            "top_weights": sc.get("positioning", {}).get("top_weights"),
            "strategy": sc.get("positioning", {}).get("strategy"),
        }
    if cfg.live_signal_path.exists():
        sig = json.loads(cfg.live_signal_path.read_text(encoding="utf-8"))
        ctx["live_signal"] = {
            "as_of": sig.get("as_of"),
            "strategy": sig.get("strategy"),
            "n_weights": len(sig.get("weights", {})),
        }
    return ctx


def recent_week_explains(cfg: AnalystConfig, n_weeks: int = 2) -> list[dict]:
    if n_weeks <= 0:
        return []
    df = pd.read_parquet(cfg.fused_panel, columns=["week_end", "country_iso3"])
    df["week_end"] = pd.to_datetime(df["week_end"])
    weeks = (
        df.loc[df["country_iso3"] == cfg.country, "week_end"]
        .drop_duplicates()
        .sort_values()
        .tail(n_weeks)
        .tolist()
    )
    out = []
    for w in weeks:
        try:
            out.append(explain_country(cfg.country, pd.Timestamp(w)))
        except SystemExit:
            continue
        except Exception as exc:
            out.append({"week_end": str(w.date()), "error": str(exc)})
    return out


def enrich_pack(pack: dict, cfg: AnalystConfig, recent_weeks: int = 2) -> dict:
    enriched = dict(pack)
    enriched["portfolio_context"] = load_portfolio_context(cfg)
    if recent_weeks > 0:
        enriched["recent_week_explains"] = recent_week_explains(cfg, recent_weeks)
    return enriched
