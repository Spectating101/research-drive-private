#!/usr/bin/env python3
"""Bridge quant_ai panels into Composer / MCP — bounded summaries and optional full brief."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any
from sharpe_kernel.paths import repo_root_from_file

_REPO = repo_root_from_file(__file__)
_SCRIPTS = _REPO / "scripts"
for p in (_REPO, _SCRIPTS):
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))


def _panel_exists(path: Path) -> bool:
    return path.is_file() and path.stat().st_size > 0


def quant_panel_summary(repo_root: Path, *, country: str = "IDN") -> dict[str, Any]:
    """Fast fused-panel stats without running the full walk-forward pipeline."""
    from quant_ai.config import load_config

    repo_root = Path(repo_root).resolve()
    cfg = load_config(country=country)
    fused = cfg.fused_panel if cfg.fused_panel.is_absolute() else repo_root / cfg.fused_panel
    out: dict[str, Any] = {
        "country": country.upper(),
        "fused_panel": str(fused.relative_to(repo_root)) if fused.is_relative_to(repo_root) else str(fused),
        "panel_exists": _panel_exists(fused),
    }
    if not out["panel_exists"]:
        out["note"] = "Fused panel missing — run cross-asset research panel build or hydrate research-panels partition."
        return out

    try:
        import pandas as pd  # type: ignore

        df = pd.read_parquet(fused)
        iso = country.upper()
        if "country_iso3" in df.columns:
            sub = df[df["country_iso3"].astype(str).str.upper() == iso]
        else:
            sub = df
        out["rows_total"] = int(len(df))
        out["rows_country"] = int(len(sub))
        out["columns"] = list(df.columns)[:40]
        if "week_end" in sub.columns:
            weeks = pd.to_datetime(sub["week_end"], errors="coerce").dropna()
            if len(weeks):
                out["week_range"] = {
                    "min": str(weeks.min().date()),
                    "max": str(weeks.max().date()),
                }
        if "fwd_return_1w" in sub.columns and len(sub) > 4:
            r = pd.to_numeric(sub["fwd_return_1w"], errors="coerce").dropna()
            if len(r):
                out["fwd_return_1w"] = {
                    "mean": round(float(r.mean()), 6),
                    "std": round(float(r.std(ddof=0)), 6),
                    "n": int(len(r)),
                }
        out["tool"] = "research_quant_brief(mode=summary|evidence|brief)"
    except Exception as exc:  # noqa: BLE001
        out["error"] = str(exc)[:300]
    return out


def run_quant_brief(
    repo_root: Path,
    *,
    country: str = "IDN",
    mode: str = "summary",
    evidence_pack: str = "",
    llm: str = "skip",
    min_train_weeks: int | None = None,
) -> dict[str, Any]:
    """MCP entry — summary (fast), evidence (walk-forward), brief (+ LLM when configured)."""
    repo_root = Path(repo_root).resolve()
    mode = str(mode or "summary").lower().strip()

    if mode == "summary":
        return quant_panel_summary(repo_root, country=country)

    from quant_ai.config import load_config

    cfg = load_config(country=country)
    if min_train_weeks is not None:
        cfg.min_train_weeks = min_train_weeks

    if mode == "brief" and evidence_pack:
        pack_path = Path(evidence_pack)
        if not pack_path.is_absolute():
            pack_path = repo_root / pack_path
        pack = json.loads(pack_path.read_text(encoding="utf-8"))
        out_dir = pack_path.parent
        if llm == "skip":
            return {
                "mode": "brief",
                "country": country.upper(),
                "evidence_pack": str(pack_path.relative_to(repo_root)),
                "pack_keys": list(pack.keys())[:20],
                "note": "Set llm=auto or deepseek for narrative decision brief.",
            }
        from quant_ai.context import enrich_pack
        from quant_ai.llm import synthesize_brief

        enriched = enrich_pack(pack, cfg)
        brief = synthesize_brief(enriched, cfg, backend=llm)
        return {
            "mode": "brief",
            "country": country.upper(),
            "evidence_pack": str(pack_path.relative_to(repo_root)),
            "brief": brief,
            "out_dir": str(out_dir.relative_to(repo_root)),
        }

    if mode in {"evidence", "brief"}:
        from quant_ai.pipeline import run_quant_pipeline

        pack, out_dir = run_quant_pipeline(cfg)
        result: dict[str, Any] = {
            "mode": mode,
            "country": country.upper(),
            "out_dir": str(out_dir.relative_to(repo_root)),
            "evidence_pack": str((out_dir / "evidence_pack.json").relative_to(repo_root)),
            "promotion": pack.get("promotion"),
            "walkforward_rows": len(pack.get("walkforward") or []),
        }
        if mode == "brief" and llm != "skip":
            from quant_ai.context import enrich_pack
            from quant_ai.llm import synthesize_brief

            enriched = enrich_pack(pack, cfg)
            result["brief"] = synthesize_brief(enriched, cfg, backend=llm)
        return result

    raise ValueError(f"unknown quant brief mode: {mode}")
