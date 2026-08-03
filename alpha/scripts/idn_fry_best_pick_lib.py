"""Selective fry best-pick radar — gated shortlist, not buy-everything.

Pipeline:
  1. Universe scan (fry names on latest day)
  2. Hard gates (empirics-backed pass/fail)
  3. Rank survivors
  4. Emit top-N picks with full audit trail

Still 0% portfolio weight — picks are the *best checks* for manual / paper incubation.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

import importlib.util as _ilu
from pathlib import Path as _Path

_bspec = _ilu.spec_from_file_location("sr_bootstrap", _Path(__file__).resolve().parent / "_repo_bootstrap.py")
_bmod = _ilu.module_from_spec(_bspec)
_bspec.loader.exec_module(_bmod)
REPO = _bmod.repo_root_from_file(__file__)
FRY_DIR = REPO / "data_lake/research_panels/idn_fry_episode"
OUT_JSON = FRY_DIR / "fry_best_picks_latest.json"

# Empirics-backed thresholds (see fry_outcome_certainty_report.json)
T1_R5_MAX = -0.08
T1_VOL_MIN = 1.6
QUIET_ACC_MAX = 2
CS_RANK_MAX = 0.35
SYMBOL_PRIOR_MIN = 0.15
POP_SCORE_ALT = 1.2


@dataclass
class GateResult:
    gate_id: str
    passed: bool
    detail: str
    hard: bool = True


@dataclass
class PickCandidate:
    yahoo_symbol: str
    as_of: str
    pick_rank: int | None
    pick_tier: str  # pick | watch | pass
    rank_score: float
    gates: list[GateResult] = field(default_factory=list)
    features: dict[str, Any] = field(default_factory=dict)

    def hard_failures(self) -> list[str]:
        return [g.gate_id for g in self.gates if g.hard and not g.passed]

    def n_passed(self) -> int:
        return sum(1 for g in self.gates if g.passed)

    def to_dict(self) -> dict[str, Any]:
        return {
            "yahoo_symbol": self.yahoo_symbol,
            "as_of": self.as_of,
            "pick_rank": self.pick_rank,
            "pick_tier": self.pick_tier,
            "rank_score": round(self.rank_score, 2),
            "gates_passed": self.n_passed(),
            "gates_total": len(self.gates),
            "hard_failures": self.hard_failures(),
            "gates": [
                {"id": g.gate_id, "passed": g.passed, "hard": g.hard, "detail": g.detail} for g in self.gates
            ],
            "features": self.features,
        }


def _gate(gate_id: str, passed: bool, detail: str, *, hard: bool = True) -> GateResult:
    return GateResult(gate_id=gate_id, passed=passed, detail=detail, hard=hard)


def evaluate_gates(row: dict[str, Any], *, dead_syms: set[str], sym_prior: float | None) -> list[GateResult]:
    """Run empirics-backed checklist on one fry symbol-day."""
    sym = row.get("yahoo_symbol", "")
    if row.get("return_5d") is not None and pd.notna(row.get("return_5d")):
        r5 = float(row["return_5d"])
    elif row.get("return_5d_pct") is not None:
        r5 = float(row["return_5d_pct"]) / 100.0
    else:
        r5 = 0.0
    vol = float(row.get("vol_ratio_20d") or 0)
    if row.get("return_1d") is not None and pd.notna(row.get("return_1d")):
        r1 = float(row["return_1d"])
    elif row.get("return_1d_pct") is not None:
        r1 = float(row["return_1d_pct"]) / 100.0
    else:
        r1 = 0.0
    label = str(row.get("bandar_lite_label") or "")
    cause = str(row.get("pop_trigger_cause") or row.get("trigger_cause") or "")
    quiet = label == "quiet_volume_build"
    vol_dd = vol >= 1.6 and r5 <= -0.04
    pop_score = float(row.get("multi_year_pop_score") or row.get("pop_score") or 0)
    sink_tier = str(row.get("sink_risk_tier") or "low")
    quiet_acc = row.get("quiet_acc_score_5d")
    cs = row.get("cs_move_pct_rank")

    gates: list[GateResult] = [
        _gate("is_fry", row.get("name_type") == "fry", f"name_type={row.get('name_type')}"),
        _gate("not_dead_name", sym not in dead_syms, "on dead-name blocklist" if sym in dead_syms else "ok"),
        _gate("not_pop_today", r1 < 0.08, f"return_1d={r1:.1%}" + (" already popped" if r1 >= 0.08 else "")),
        _gate(
            "t1_deep_dd_vol",
            r5 <= T1_R5_MAX and vol >= T1_VOL_MIN,
            f"r5={r5:.1%} vol={vol:.1f}x (need r5<={T1_R5_MAX:.0%} vol>={T1_VOL_MIN})",
        ),
        _gate(
            "not_quiet_only",
            not (quiet and not vol_dd),
            "ok" if not (quiet and not vol_dd) else "quiet_volume_build without vol-dd — ~23% pop, mostly stale",
        ),
        _gate(
            "drawdown_vol_spike",
            cause in ("drawdown_vol_spike", "both_quiet_and_vol_dd", ""),
            f"trigger_cause={cause or 'unknown'}",
            hard=False,
        ),
        _gate(
            "sink_risk_not_high",
            sink_tier != "high",
            f"sink_risk_tier={sink_tier}",
        ),
        _gate(
            "quiet_acc_low",
            quiet_acc is None or pd.isna(quiet_acc) or float(quiet_acc) <= QUIET_ACC_MAX,
            f"quiet_acc={quiet_acc} (high → flat_noise)",
            hard=False,
        ),
        _gate(
            "cs_rank_not_chasing",
            cs is None or pd.isna(cs) or float(cs) <= CS_RANK_MAX,
            f"cs_rank={cs} (poppers trigger on low-rank days)",
            hard=False,
        ),
        _gate(
            "hot_name_or_pattern",
            (sym_prior is not None and sym_prior >= SYMBOL_PRIOR_MIN) or pop_score >= POP_SCORE_ALT,
            f"prior={sym_prior} pop_score={pop_score:.2f}",
            hard=False,
        ),
    ]
    return gates


def rank_score(row: dict[str, Any], gates: list[GateResult]) -> float:
    """Higher = better pick among gate survivors."""
    score = float(row.get("action_score") or 0)
    score += float(row.get("multi_year_pop_score") or row.get("pop_score") or 0) * 20
    prior = row.get("symbol_pop_prior_wf")
    if prior is not None and not pd.isna(prior):
        score += float(prior) * 0.5
    r5 = float(row.get("return_5d") or 0)
    vol = float(row.get("vol_ratio_20d") or 0)
    if r5 <= -0.12:
        score += 12
    elif r5 <= -0.08:
        score += 8
    score += min(vol, 4.0) * 3
    sink = str(row.get("sink_risk_tier") or "low")
    if sink == "high":
        score -= 40
    elif sink == "elevated":
        score -= 15
    for g in gates:
        if g.passed:
            score += 3 if g.hard else 1
    if row.get("broker_data_available"):
        boost = row.get("broker_tags") or []
        if "more_buying_brokers" in boost:
            score += 10
        if "foreign_sell_heavy" in boost:
            score -= 15
    return score


def classify_pick_tier(gates: list[GateResult], rank_score: float) -> str:
    hard_fails = [g for g in gates if g.hard and not g.passed]
    if hard_fails:
        return "pass"
    soft_pass = sum(1 for g in gates if not g.hard and g.passed)
    if rank_score >= 45 and soft_pass >= 1:
        return "pick"
    if rank_score >= 25:
        return "watch"
    return "pass"


def pick_best_fry_candidates(
    watchlist: list[dict[str, Any]] | None = None,
    *,
    top_k: int = 3,
    as_of: str | None = None,
) -> dict[str, Any]:
    """Gate + rank fry monitors; return top picks with audit trail."""
    if watchlist is None:
        from idn_fry_actionable_lib import build_watchlist
        from idn_fry_gdelt_crossref_lib import load_idn_country_shocks

        watchlist = build_watchlist(load_idn_country_shocks())

    from idn_fry_actionable_lib import _load_symbol_prior_maps

    prior_map, dead_syms = _load_symbol_prior_maps()

    candidates: list[PickCandidate] = []
    for row in watchlist:
        sym = row["yahoo_symbol"]
        dt = str(row.get("as_of") or as_of or "")
        gates = evaluate_gates(row, dead_syms=dead_syms, sym_prior=prior_map.get(sym))
        rs = rank_score(row, gates)
        tier = classify_pick_tier(gates, rs)
        candidates.append(
            PickCandidate(
                yahoo_symbol=sym,
                as_of=dt,
                pick_rank=None,
                pick_tier=tier,
                rank_score=rs,
                gates=gates,
                features={
                    "return_5d_pct": row.get("return_5d_pct"),
                    "vol_ratio_20d": row.get("vol_ratio_20d"),
                    "action_score": row.get("action_score"),
                    "watch_tier": row.get("tier"),
                    "pop_trigger_cause": row.get("pop_trigger_cause"),
                    "sink_risk_tier": row.get("sink_risk_tier"),
                    "symbol_pop_prior_wf": row.get("symbol_pop_prior_wf"),
                    "multi_year_pop_score": row.get("multi_year_pop_score"),
                    "historical_pop_rate_prior": row.get("historical_pop_rate_prior"),
                    "outcome_certainty_menu": row.get("outcome_certainty_menu"),
                },
            )
        )

    picks = [c for c in candidates if c.pick_tier == "pick"]
    picks.sort(key=lambda c: -c.rank_score)
    watches = [c for c in candidates if c.pick_tier == "watch"]
    watches.sort(key=lambda c: -c.rank_score)

    for i, c in enumerate(picks[:top_k], start=1):
        c.pick_rank = i

    report: dict[str, Any] = {
        "as_of": as_of or (watchlist[0].get("as_of") if watchlist else None),
        "n_scanned": len(candidates),
        "n_pick": len(picks),
        "n_watch": len(watches),
        "n_pass": sum(1 for c in candidates if c.pick_tier == "pass"),
        "top_picks": [c.to_dict() for c in picks[:top_k]],
        "runner_up_watch": [c.to_dict() for c in watches[:5]],
        "gate_definitions": {
            "hard": [
                "is_fry",
                "not_dead_name",
                "not_pop_today",
                "t1_deep_dd_vol",
                "not_quiet_only",
                "sink_risk_not_high",
            ],
            "soft": [
                "drawdown_vol_spike",
                "quiet_acc_low",
                "cs_rank_not_chasing",
                "hot_name_or_pattern",
            ],
        },
        "playbook": {
            "pick": "Passed all hard gates + strong rank — top selective watch / paper incubation candidate.",
            "watch": "T1 viable but softer profile — monitor, do not size up.",
            "pass": "Failed a hard gate — skip despite fry activity.",
            "hold_rule": "Do not buy at trigger close. Wait 3–5 sessions for no-sink, or ARA pop day.",
            "cut_rule": "Sink day, day-14/30 no pop, or high sink-risk → drop.",
            "weight": "0% on position sheet until paper incubation sim validates.",
        },
    }
    return report


def build_and_save_best_picks(*, top_k: int = 3) -> dict[str, Any]:
    FRY_DIR.mkdir(parents=True, exist_ok=True)
    report = pick_best_fry_candidates(top_k=top_k)
    OUT_JSON.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def load_best_picks() -> dict[str, Any]:
    if not OUT_JSON.exists():
        return build_and_save_best_picks()
    return json.loads(OUT_JSON.read_text(encoding="utf-8"))
