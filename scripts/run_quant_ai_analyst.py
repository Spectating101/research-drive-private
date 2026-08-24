#!/usr/bin/env python3
"""Quant-AI analyst: country quant pipeline → evidence pack → LLM decision brief.

Architecture:
  Data panels → walk-forward + promotion gates → evidence_pack.json
  → portfolio + recent-week context → LLM brief (stance, size, falsifiers)
  → human decision

Examples:
  python scripts/run_quant_ai_analyst.py --country IDN --brief --llm deepseek
  python scripts/run_quant_ai_analyst.py --evidence-pack backtests/outputs/quant_ai/IDN/.../evidence_pack.json --brief-only
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from quant_ai.config import load_config  # noqa: E402
from quant_ai.context import enrich_pack  # noqa: E402
from quant_ai.llm import synthesize_analysis, synthesize_brief  # noqa: E402
from quant_ai.pipeline import run_quant_pipeline  # noqa: E402


def _write_brief_outputs(out_dir: Path, result: dict, country: str) -> None:
    text = result.get("text", "")
    (out_dir / "decision_brief.md").write_text(
        f"# Quant-AI Decision Brief — {country}\n\n"
        f"Backend: {result.get('backend')} ({result.get('model')})\n\n{text}\n",
        encoding="utf-8",
    )
    if result.get("decision_brief"):
        (out_dir / "decision_brief.json").write_text(
            json.dumps(result["decision_brief"], indent=2),
            encoding="utf-8",
        )
    if result.get("errors"):
        (out_dir / "llm_errors.txt").write_text("\n".join(result["errors"]), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--country", default="IDN", help="ISO3 country code (default: IDN)")
    ap.add_argument("--config", type=Path, help="quant_ai_analyst.json path")
    ap.add_argument("--min-train-weeks", type=int)
    ap.add_argument("--ridge-alpha", type=float)
    ap.add_argument("--stock-universe", type=int)
    ap.add_argument("--recent-weeks", type=int, default=2, help="Attach N recent explain-week snapshots")
    ap.add_argument("--llm", choices=["auto", "deepseek", "openai", "codex", "skip"], default="auto")
    ap.add_argument("--llm-model", default="")
    ap.add_argument("--brief", action="store_true", help="Emit structured decision brief (stance/size/falsifiers)")
    ap.add_argument("--analysis-only", action="store_true", help="Skip decision brief; narrative analysis only")
    ap.add_argument("--evidence-pack", type=Path, help="Load existing pack; skip quant")
    ap.add_argument("--brief-only", action="store_true", help="With --evidence-pack: LLM only, no quant")
    ap.add_argument("--out-dir", type=Path, help="Override output directory")
    args = ap.parse_args()

    cfg = load_config(country=args.country, config_path=args.config)
    if args.min_train_weeks is not None:
        cfg.min_train_weeks = args.min_train_weeks
    if args.ridge_alpha is not None:
        cfg.ridge_alpha = args.ridge_alpha
    if args.stock_universe is not None:
        cfg.stock_universe = args.stock_universe

    if args.evidence_pack:
        pack = json.loads(Path(args.evidence_pack).read_text(encoding="utf-8"))
        out_dir = args.out_dir or Path(args.evidence_pack).parent
    elif args.brief_only:
        ap.error("--brief-only requires --evidence-pack")
    else:
        pack, out_dir = run_quant_pipeline(cfg, out_dir=args.out_dir)
        print(f"Quant pipeline complete: {out_dir}")

    pack = enrich_pack(pack, cfg, recent_weeks=args.recent_weeks)
    (out_dir / "evidence_pack_enriched.json").write_text(json.dumps(pack, indent=2, default=str), encoding="utf-8")

    use_brief = args.brief and not args.analysis_only
    llm_result: dict = {"backend": "skip", "text": ""}
    if args.llm != "skip":
        if use_brief:
            llm_result = synthesize_brief(pack, cfg, args.llm, args.llm_model, out_dir=out_dir)
            _write_brief_outputs(out_dir, llm_result, cfg.country)
        else:
            llm_result = synthesize_analysis(pack, cfg, args.llm, args.llm_model, out_dir=out_dir)
            (out_dir / "llm_analysis.md").write_text(
                f"# Quant-AI Analysis — {cfg.country}\n\n"
                f"Backend: {llm_result['backend']}\n\n{llm_result['text']}\n",
                encoding="utf-8",
            )

    summary = {
        "country": cfg.country,
        "out_dir": str(out_dir),
        "n_passed": pack.get("promotion", {}).get("n_passed"),
        "n_strategies": pack.get("promotion", {}).get("n_strategies"),
        "llm_backend": llm_result.get("backend"),
        "decision_brief_parsed": llm_result.get("decision_brief") is not None,
    }
    (out_dir / "run_summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(json.dumps(summary, indent=2))

    if llm_result.get("decision_brief"):
        print("\n--- Decision brief (parsed) ---")
        print(json.dumps(llm_result["decision_brief"], indent=2))
    elif llm_result.get("text"):
        print("\n--- LLM (first 2500 chars) ---\n")
        print(llm_result["text"][:2500])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
