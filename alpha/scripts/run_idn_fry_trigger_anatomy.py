#!/usr/bin/env python3
"""Deep fry trigger anatomy — causes, pop predictors, full episode timelines."""

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

from idn_fry_trigger_anatomy_lib import build_trigger_anatomy_research  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="Fry trigger anatomy research")
    ap.parse_args()
    report = build_trigger_anatomy_research()
    # compact stdout — full detail in JSON artifacts
    compact = {
        "n_triggers": report["n_triggers"],
        "overall_pop_rate_pct": report["overall_pop_rate_pct"],
        "by_trigger_cause": report["signature_pop_rates"]["by_trigger_cause"],
        "by_return_5d": report["signature_pop_rates"]["by_return_5d_at_trigger"],
        "phenomenon": report["phenomenon"]["what_actually_triggers"],
        "case_study_episode_ids": report["case_study_episode_ids"],
    }
    print(json.dumps(compact, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
