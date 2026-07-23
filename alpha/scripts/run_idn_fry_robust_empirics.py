#!/usr/bin/env python3
"""Run robust fry trigger empirical analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
sys.path.insert(0, str(REPO / "scripts"))

from idn_fry_robust_empirics_lib import build_robust_empirics  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry robust empirics").parse_args()
    report = build_robust_empirics()
    compact = {
        "baseline_pop_rate_pct": report["meta"]["baseline_pop_rate_pct"],
        "robustness_verdict": report["mechanism_summary"]["robustness_verdict"],
        "top_fdr_indicators": report["mechanism_summary"]["strongest_fdr_indicators"][:5],
        "best_oos_rule": report["mechanism_summary"]["best_oos_rule"],
        "logistic_oos_auc": report["logistic_model"].get("oos_auc"),
        "placebo": report["placebo_baselines"],
        "era_yearly_range": report["era_stability"].get("yearly_rate_range"),
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
