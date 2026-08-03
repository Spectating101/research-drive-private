#!/usr/bin/env python3
"""Probe RapidAPI IDX endpoints and write capability report."""

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

from idn_rapidapi_idx import CAPABILITY_OUT, probe_capabilities  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--symbols", nargs="+", default=["BBCA", "BUMI", "TPIA", "BBRI"])
    args = ap.parse_args()
    out = probe_capabilities(focus_symbols=[s.replace(".JK", "").upper() for s in args.symbols])
    print(json.dumps({"out": str(CAPABILITY_OUT), "working": out["working"], "failed_n": len(out["failed"])}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
