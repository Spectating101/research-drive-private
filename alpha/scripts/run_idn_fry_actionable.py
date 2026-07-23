#!/usr/bin/env python3
"""Build actionable fry watchlist + publication case book."""

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

from idn_fry_actionable_lib import build_actionable_pack  # noqa: E402


def main() -> int:
    argparse.ArgumentParser(description="Fry actionable pack").parse_args()
    pack = build_actionable_pack()
    print(json.dumps({
        "watchlist_summary": pack["watchlist_summary"],
        "watchlist": pack["watchlist"][:10],
        "case_book_symbols": [c["yahoo_symbol"] for c in pack["pop_case_book"]],
        "entity_noise": pack["entity_noise_filter"],
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
