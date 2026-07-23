#!/usr/bin/env python3
"""Combine IDN + Taiwan + crypto satellite into one personal book view.

Default sleeve mix (of total book):
  IDN 55% · Taiwan 35% · Crypto satellite ≤10% (already capped in crypto sheet)

Reads latest_portfolio.json from each sleeve; writes focused_personal_book/.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)

IDN = REPO / "backtests/outputs/idn_weekly_position_sheet/latest_portfolio.json"
TW = REPO / "backtests/outputs/taiwan_weekly_position_sheet/latest_portfolio.json"
CRYPTO = REPO / "backtests/outputs/crypto_satellite_book/latest.json"
OUT = REPO / "backtests/outputs/focused_personal_book"

DEFAULT_SLEEVES = {"idn": 0.55, "taiwan": 0.35, "crypto": 0.10}


def _load(path: Path) -> dict:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def scale_sleeve(weights: dict, sleeve_pct: float) -> dict[str, float]:
    """Scale non-CASH weights by sleeve_pct; sleeve CASH becomes unallocated within sleeve."""
    out: dict[str, float] = {}
    cash = float(weights.get("CASH", 0.0))
    risky = {k: float(v) for k, v in weights.items() if k != "CASH"}
    risky_sum = sum(risky.values())
    # Treat sleeve CASH as reducing deployed capital inside the sleeve budget
    deploy = sleeve_pct * (1.0 - cash) if risky_sum > 0 else 0.0
    # Actually: weights already sum to 1 including CASH. Deploy sleeve_pct * (1-CASH) into names,
    # and sleeve_pct * CASH stays as book cash contribution.
    for k, v in risky.items():
        out[k] = sleeve_pct * v
    out["__sleeve_cash__"] = sleeve_pct * cash
    return out


def main() -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--idn", type=float, default=DEFAULT_SLEEVES["idn"])
    ap.add_argument("--taiwan", type=float, default=DEFAULT_SLEEVES["taiwan"])
    ap.add_argument("--crypto", type=float, default=DEFAULT_SLEEVES["crypto"])
    args = ap.parse_args()
    mix = {"idn": args.idn, "taiwan": args.taiwan, "crypto": args.crypto}
    s = sum(mix.values())
    mix = {k: v / s for k, v in mix.items()}

    idn = _load(IDN)
    tw = _load(TW)
    crypto = _load(CRYPTO)

    # Crypto sheet already exposes weights_in_total_book at book_cap; re-scale to sleeve
    crypto_w = crypto.get("weights_within_satellite") or {}
    if not crypto_w and CRYPTO.exists():
        crypto_w = (crypto.get("weights_in_total_book") or {})
        # strip prior cap: renormalize non-cash
        risky = {k: v for k, v in crypto_w.items() if k != "CASH"}
        rs = sum(risky.values())
        if rs > 0:
            crypto_w = {k: v / rs for k, v in risky.items()}
            crypto_w["CASH"] = 0.0

    parts = {
        "idn": scale_sleeve(idn.get("weights") or {}, mix["idn"]),
        "taiwan": scale_sleeve(tw.get("weights") or {}, mix["taiwan"]),
        "crypto": scale_sleeve(crypto_w or {"CASH": 1.0}, mix["crypto"]),
    }

    combined: dict[str, float] = {}
    book_cash = 0.0
    for sleeve, wmap in parts.items():
        for k, v in wmap.items():
            if k == "__sleeve_cash__":
                book_cash += v
            else:
                combined[k] = combined.get(k, 0.0) + v
    combined["CASH"] = book_cash
    # renormalize tiny float drift
    tot = sum(combined.values())
    if tot > 0:
        combined = {k: v / tot for k, v in combined.items()}

    report = {
        "strategy": "focused_personal_book",
        "sleeves": mix,
        "as_of": {
            "idn": idn.get("as_of_week") or idn.get("as_of"),
            "taiwan": tw.get("as_of_week") or tw.get("as_of"),
            "crypto": crypto.get("as_of"),
        },
        "modes": {
            "idn": idn.get("weight_mode"),
            "taiwan": tw.get("weight_mode"),
            "crypto": crypto.get("best_strategy"),
        },
        "verdicts": {
            "idn_group_sync": "see idn_alpha_proof",
            "taiwan": crypto and None,
            "taiwan_research": (_load(REPO / "backtests/outputs/taiwan_alpha_research/latest.json") or {}).get("verdict"),
            "crypto": crypto.get("verdict"),
            "idn_proof": (_load(REPO / "backtests/outputs/idn_alpha_proof/latest.json") or {}).get("verdict"),
        },
        "weights": combined,
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "note": "Paper/research book for IDN+TW+crypto personal universe. Not a live broker order.",
    }
    # fix taiwan verdict key
    twr = _load(REPO / "backtests/outputs/taiwan_alpha_research/latest.json")
    report["verdicts"]["taiwan"] = twr.get("verdict")
    del report["verdicts"]["taiwan_research"]

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "latest.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    (OUT / "latest_portfolio.json").write_text(json.dumps({
        "strategy": "focused_personal_book",
        "as_of_week": max(x for x in report["as_of"].values() if x) if any(report["as_of"].values()) else None,
        "as_of": report["as_of"],
        "weight_mode": "idn_tw_crypto_sleeves",
        "weights": combined,
        "sleeves": mix,
    }, indent=2) + "\n", encoding="utf-8")

    lines = [
        "# Focused personal book (IDN + Taiwan + crypto)",
        "",
        f"- sleeves: IDN {mix['idn']:.0%} · TW {mix['taiwan']:.0%} · crypto {mix['crypto']:.0%}",
        f"- as_of: IDN `{report['as_of'].get('idn')}` · TW `{report['as_of'].get('taiwan')}` · crypto `{report['as_of'].get('crypto')}`",
        f"- verdicts: IDN proof `{report['verdicts'].get('idn_proof')}` · TW `{report['verdicts'].get('taiwan')}` · crypto `{report['verdicts'].get('crypto')}`",
        "",
        "| Symbol | Weight |",
        "|--------|-------:|",
    ]
    for k, v in sorted(combined.items(), key=lambda x: -x[1]):
        if v < 0.005:
            continue
        lines.append(f"| {k} | {v:.1%} |")
    lines.append("")
    (OUT / "latest.md").write_text("\n".join(lines), encoding="utf-8")
    print((OUT / "latest.md").read_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
