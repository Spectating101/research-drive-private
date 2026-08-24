#!/usr/bin/env python3
"""Export professor-simple stablecoin CSVs from a frozen package directory."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from stablecoin_skynet.professor_simple import publish_professor_simple

REPO = Path(__file__).resolve().parents[1]


def _repo_root() -> Path:
    here = Path(__file__).resolve().parent
    for candidate in (here.parent, here.parent.parent):
        if (candidate / "stablecoin_skynet").is_dir():
            return candidate
    return here.parent


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--package-dir",
        type=Path,
        default=REPO / "data/datasets/stablecoin_trust_engagement/latest",
        help="Frozen stablecoin package (default: latest symlink)",
    )
    args = parser.parse_args()
    package_dir = args.package_dir.resolve()
    counts = publish_professor_simple(package_dir)
    print(json.dumps({"package_dir": str(package_dir), "counts": counts}, indent=2))


if __name__ == "__main__":
    main()
