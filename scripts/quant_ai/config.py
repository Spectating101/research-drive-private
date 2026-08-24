from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = REPO / "config/quant_ai_analyst.json"


@dataclass
class AnalystConfig:
    repo: Path = REPO
    country: str = "IDN"
    fused_panel: Path = field(default_factory=lambda: REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet")
    crypto_panel: Path = field(default_factory=lambda: REPO / "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet")
    broadcast_panel: Path = field(default_factory=lambda: REPO / "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet")
    processed_news: Path = field(default_factory=lambda: REPO / "data_lake/news_shock_taxonomy/processed")
    min_train_weeks: int = 78
    ridge_alpha: float = 10.0
    stock_universe: int = 25
    country_label: str = "Indonesia"
    analyst_persona: str = "senior Indonesia equity research analyst"
    scorecard_path: Path = field(default_factory=lambda: REPO / "backtests/outputs/alpha_paper/scorecard_latest.json")
    live_signal_path: Path = field(default_factory=lambda: REPO / "backtests/outputs/signals/alpha_live_signal.json")
    out_root: Path = field(default_factory=lambda: REPO / "backtests/outputs/quant_ai")


def load_config(country: str | None = None, config_path: Path | None = None) -> AnalystConfig:
    path = config_path or DEFAULT_CONFIG
    raw = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    data = raw.get("data", {})
    quant = raw.get("quant", {})
    portfolio = raw.get("portfolio_context", {})
    iso = (country or raw.get("default_country", "IDN")).upper()
    country_cfg = raw.get("countries", {}).get(iso, {})

    def _p(key: str, default: str) -> Path:
        return REPO / data.get(key, default)

    return AnalystConfig(
        country=iso,
        fused_panel=_p("fused_panel", "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/cross_asset_fused_primary_panel.parquet"),
        crypto_panel=_p("crypto_panel", "data_lake/research_panels/cross_asset_fused/fused_20260610_v2/country_week_crypto_news_panel.parquet"),
        broadcast_panel=_p("broadcast_panel", "data_lake/research_panels/ticker_news_market/ticker_20260610/ticker_week_country_broadcast_panel.parquet"),
        processed_news=_p("processed_news", "data_lake/news_shock_taxonomy/processed"),
        min_train_weeks=int(quant.get("min_train_weeks", 78)),
        ridge_alpha=float(quant.get("ridge_alpha", 10.0)),
        stock_universe=int(country_cfg.get("stock_universe", quant.get("stock_universe", 25))),
        country_label=str(country_cfg.get("label", iso)),
        analyst_persona=str(country_cfg.get("analyst_persona", f"senior {iso} equity research analyst")),
        scorecard_path=REPO / portfolio.get("scorecard_path", "backtests/outputs/alpha_paper/scorecard_latest.json"),
        live_signal_path=REPO / portfolio.get("live_signal_path", "backtests/outputs/signals/alpha_live_signal.json"),
    )
