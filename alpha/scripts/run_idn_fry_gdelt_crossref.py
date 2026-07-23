#!/usr/bin/env python3
"""Fry episodes × GDELT news dots × literature crosswalk."""

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

from idn_fry_gdelt_crossref_lib import build_gdelt_literature_crossref  # noqa: E402


def main() -> int:
    argparse.ArgumentParser().parse_args()
    report = build_gdelt_literature_crossref()
    print(json.dumps(report["synthesis"], indent=2))
    print(json.dumps(report["meta"], indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
