#!/usr/bin/env python3
"""IDX empirical research hub — sentiment, validation, live scorecard, unified brief.

Wires together:
  - Public sentiment collector (daily)
  - Signal validation backtests (weekly full, daily quick)
  - Three-way live scorecard (position sheet vs rules vs LLM)
  - Human-readable research brief for operator decisions

Outputs:
  backtests/outputs/platform/idn_empirical_research/latest.json
  backtests/outputs/platform/idn_empirical_research/latest.md
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "scripts"))

from idn_empirical_scorecard import build_scorecard, write_research_brief  # noqa: E402
from run_idn_invest_trial import load_liquid_universe  # noqa: E402

OUT = REPO / "backtests/outputs/platform/idn_empirical_research"
DEFAULT_VAL = REPO / "backtests/outputs/platform/idn_sentiment_validation/latest.json"


def _file_age_days(path: Path) -> float | None:
    if not path.exists():
        return None
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=UTC)
    return (datetime.now(UTC) - mtime).total_seconds() / 86400


def _run(cmd: list[str], *, label: str) -> dict[str, Any]:
    print(f"\n==> {label}")
    print("   ", " ".join(cmd))
    proc = subprocess.run(cmd, cwd=str(REPO), capture_output=True, text=True)
    if proc.stdout:
        print(proc.stdout[-3000:])
    if proc.returncode != 0 and proc.stderr:
        print(proc.stderr[-2000:], file=sys.stderr)
    return {"label": label, "cmd": cmd, "ok": proc.returncode == 0, "returncode": proc.returncode}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--config", type=Path, default=REPO / "config/platform_integration.json")
    ap.add_argument("--skip-social", action="store_true")
    ap.add_argument("--skip-validation", action="store_true")
    ap.add_argument("--force-validation", action="store_true")
    ap.add_argument("--full-validation", action="store_true", help="Include retail event studies + API RSI.")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    er = cfg.get("idn_empirical_research", {})
    idn = cfg.get("idn_sleeve", {})
    py = REPO / ".venv/bin/python"
    if not py.is_file():
        py = Path(sys.executable)

    steps: list[dict[str, Any]] = []

    if er.get("enabled", True) and not args.skip_social:
        social_age = _file_age_days(REPO / "data_lake/sentiment/idn_public_sentiment_latest.json")
        max_age = float(er.get("refresh_social_days", 1))
        if social_age is None or social_age > max_age:
            cmd = [str(py), "scripts/idn_social_sentiment_collector.py"]
            if args.dry_run:
                steps.append({"label": "idn_social_sentiment", "ok": True, "dry_run": True, "cmd": cmd})
            else:
                steps.append(_run(cmd, label="idn_social_sentiment"))
        else:
            steps.append({"label": "idn_social_sentiment", "ok": True, "skipped": "fresh"})

    val_path = REPO / er.get("validation_out", "backtests/outputs/platform/idn_sentiment_validation/latest.json")
    val_age = _file_age_days(val_path)
    refresh_days = float(er.get("refresh_validation_days", 7))
    need_val = args.force_validation or val_age is None or val_age > refresh_days
    full_val = args.full_validation or bool(er.get("full_validation", True))

    if er.get("enabled", True) and not args.skip_validation and need_val:
        cmd = [str(py), "scripts/run_idn_sentiment_signal_validation.py"]
        if not full_val:
            cmd.extend(["--skip-retail", "--skip-api-rsi"])
        if args.dry_run:
            steps.append({"label": "idn_sentiment_validation", "ok": True, "dry_run": True, "cmd": cmd})
        else:
            steps.append(_run(cmd, label="idn_sentiment_validation"))
    elif not args.skip_validation:
        steps.append({"label": "idn_sentiment_validation", "ok": True, "skipped": "fresh"})

    bt_path = REPO / er.get("analyst_backtest_out", "backtests/outputs/platform/idn_analyst_backtest/latest.json")
    bt_age = _file_age_days(bt_path)
    bt_refresh = float(er.get("refresh_analyst_backtest_days", 7))
    need_bt = args.force_validation or bt_age is None or bt_age > bt_refresh
    if er.get("enabled", True) and need_bt:
        cmd = [str(py), "scripts/run_idn_analyst_backtest.py", "--mode", "deterministic", "--era", "oos_holdout"]
        if args.dry_run:
            steps.append({"label": "idn_analyst_backtest", "ok": True, "dry_run": True, "cmd": cmd})
        else:
            steps.append(_run(cmd, label="idn_analyst_backtest"))
    else:
        steps.append({"label": "idn_analyst_backtest", "ok": True, "skipped": "fresh"})

    disc_path = REPO / er.get("signal_discovery_out", "backtests/outputs/platform/idn_signal_discovery/latest.json")
    disc_age = _file_age_days(disc_path)
    disc_refresh = float(er.get("refresh_signal_discovery_days", 7))
    need_disc = args.force_validation or disc_age is None or disc_age > disc_refresh
    if er.get("enabled", True) and need_disc:
        cmd = [str(py), "scripts/run_idn_signal_discovery.py", "--mode", "scan"]
        if args.dry_run:
            steps.append({"label": "idn_signal_discovery", "ok": True, "dry_run": True, "cmd": cmd})
        else:
            steps.append(_run(cmd, label="idn_signal_discovery"))
    else:
        steps.append({"label": "idn_signal_discovery", "ok": True, "skipped": "fresh"})

    initial_equity = float(idn.get("initial_equity", 10_000))
    scorecard = build_scorecard(
        position_ledger=REPO / idn.get("ledger", "backtests/outputs/idn_weekly_position_sheet/paper/ledger.csv"),
        operator_rules_ledger=REPO / er.get(
            "operator_rules_ledger",
            "backtests/outputs/idn_operator/paper/rules_ledger.csv",
        ),
        operator_llm_ledger=REPO / er.get(
            "operator_llm_ledger",
            "backtests/outputs/idn_operator/paper/llm_ledger.csv",
        ),
        validation_json=val_path if val_path.exists() else DEFAULT_VAL,
        rules_portfolio=REPO / er.get(
            "operator_rules_portfolio",
            "backtests/outputs/idn_operator/latest_rules_portfolio.json",
        ),
        llm_portfolio=REPO / er.get(
            "operator_llm_portfolio",
            "backtests/outputs/idn_operator/latest_llm_portfolio.json",
        ),
        position_portfolio=REPO / idn.get(
            "portfolio",
            "backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json",
        ),
        initial_equity=initial_equity,
    )
    scorecard["steps"] = steps
    scorecard["liquid_universe"] = len(load_liquid_universe())

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(scorecard, indent=2, default=str) + "\n", encoding="utf-8")
    brief = write_research_brief(scorecard)
    (OUT / "latest.md").write_text(brief, encoding="utf-8")

    print(brief)
    print(f"\nWrote {OUT / 'latest.md'}")
    return 0 if all(s.get("ok", True) for s in steps) else 1


if __name__ == "__main__":
    raise SystemExit(main())
