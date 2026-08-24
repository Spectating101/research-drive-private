#!/usr/bin/env python3
"""Job 0: Probe Refinitiv value-first entitlement across representative RICs."""

from __future__ import annotations

import argparse
import json
import sys
import traceback
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

REPO = Path(__file__).resolve().parents[1]
DEFAULT_PRIORITY = REPO / "config/refinitiv_collection_priority.json"
DEFAULT_OUT = REPO / "docs/status/generated/refinitiv_value_entitlement_map.json"

sys.path.insert(0, str(REPO / "scripts"))
from refinitiv_lseg_session import load_env, platform_session  # noqa: E402

PROBE_RICS = [
    "NVDA.O",
    "AAPL.O",
    "2330.TW",
    "7203.T",
    "005930.KS",
    "D05.SI",
    "BBCA.JK",
    ".SPX",
    ".JKSE",
    "EIDO",
    "LCOc1",
    "USDJPY=",
]

CATEGORY_SPECS: dict[str, dict[str, Any]] = {
    "B1_B6_security_master": {
        "description": "Security master / identifiers / TRBC",
        "rics": ["NVDA.O", "AAPL.O", "2330.TW", "BBCA.JK"],
        "method": "get_data",
        "fields": [
            "TR.CommonName",
            "TR.ISIN",
            "TR.ExchangeTicker",
            "TR.TRBCEconomicSector",
            "TR.TRBCIndustry",
            "TR.CompanyMarketCap",
            "TR.SharesOutstanding",
            "TR.FreeFloatPct",
            "TR.ExchangeCountryCode",
            "TR.Currency",
        ],
    },
    "B7_B8_index_constituents": {
        "description": "Current + PIT index constituent fields",
        "rics": [".SPX", ".JKSE"],
        "method": "index_constituent",
        "fields": ["TR.IndexConstituentRIC", "TR.IndexConstituentName"],
        "pit_ric": "0#.SPX",
        "sdate": "20180115",
        "extra_pit_rics": {
            ".SPX": "0#.SPX",
            ".JKSE": "0#.JKSE",
        },
    },
    "C1_C5_corporate_actions": {
        "description": "Corporate actions / adjustment factors",
        "rics": ["NVDA.O", "AAPL.O", "BBCA.JK"],
        "method": "get_data",
        "fields": [
            "TR.DividendExDate",
            "TR.DividendAmount",
            "TR.SplitFactor",
            "TR.CAAdjustmentFactor",
        ],
    },
    "A9_A11_risk": {
        "description": "Vol / skew / put-call / short interest",
        "rics": ["NVDA.O", "AAPL.O", "2330.TW", "BBCA.JK", ".SPX"],
        "method": "get_data_and_history",
        "fields": [
            "TR.Volatility30D",
            "TR.Volatility90D",
            "TR.Volatility360D",
            "TR.ImpVolPutDelta25",
            "TR.ImpVolDelta25",
            "TR.PutCallRatio",
            "TR.ShortInterestRatio",
        ],
        "history_start": "2024-01-01",
        "history_interval": "daily",
    },
    "D8_pit_fundamentals": {
        "description": "Point-in-time fundamentals (fundamental_and_reference)",
        "rics": ["NVDA.O", "AAPL.O", "BBCA.JK"],
        "method": "fundamental_multi",
        "fields": ["TR.Revenue", "TR.NetIncome", "TR.F.TotRevenue"],
    },
    "E4_estimate_revisions": {
        "description": "Estimate revisions / EPS mean history",
        "rics": ["NVDA.O", "AAPL.O", "BBCA.JK"],
        "method": "get_data_history_params",
        "fields": ["TR.EPSMean"],
        "parameters": {"SDate": "0", "EDate": "-1"},
        "history_start": "2023-01-01",
        "history_interval": "daily",
    },
    "G1_ownership": {
        "description": "Institutional ownership",
        "rics": ["NVDA.O", "AAPL.O"],
        "method": "get_data",
        "fields": [
            "TR.InstitutionalHolders",
            "TR.InstitutionalOwnershipPct",
            "TR.InsiderOwnershipPct",
        ],
    },
    "I1_supply_chain": {
        "description": "Supply chain suppliers / customers",
        "rics": ["NVDA.O", "AAPL.O"],
        "method": "get_data",
        "fields": ["TR.SupplyChainSuppliers", "TR.SupplyChainCustomers"],
    },
    "B8_asia_pit_indices": {
        "description": "Asia PIT index constituents (0# pattern)",
        "rics": [".TWII", ".N225", ".KS11", ".STI"],
        "method": "index_constituent",
        "fields": ["TR.IndexConstituentRIC", "TR.IndexConstituentName"],
        "pit_ric": "0#.TWII",
        "sdate": "20200115",
        "extra_pit_rics": {
            ".TWII": "0#.TWII",
            ".N225": "0#.N225",
            ".KS11": "0#.KSE",
            ".STI": "0#.STI",
        },
    },
    "E1_E3_consensus_snapshot": {
        "description": "Analyst consensus snapshot (E1-E3)",
        "rics": ["NVDA.O", "AAPL.O", "2330.TW", "BBCA.JK"],
        "method": "get_data",
        "fields": [
            "TR.EPSMean",
            "TR.RevenueMean",
            "TR.PriceTargetMean",
            "TR.PriceTargetHigh",
            "TR.PriceTargetLow",
        ],
    },
    "H1_esg_snapshot": {
        "description": "ESG pillar scores",
        "rics": ["NVDA.O", "AAPL.O", "2330.TW", "BBCA.JK"],
        "method": "get_data",
        "fields": [
            "TR.TRESGScore",
            "TR.ESGScore",
            "TR.EnvironmentPillarScore",
            "TR.SocialPillarScore",
            "TR.GovernancePillarScore",
        ],
    },
    "F1_starmine_probe": {
        "description": "StarMine / SmartEstimate probe",
        "rics": ["NVDA.O", "AAPL.O"],
        "method": "get_data",
        "fields": [
            "TR.SmartEstimate",
            "TR.StarMineEQ",
            "TR.StarMineARM",
            "TR.StarMineAccruals",
        ],
    },
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_priority(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _frame_ok(frame: pd.DataFrame | None) -> tuple[bool, dict[str, Any]]:
    if frame is None or frame.empty:
        return False, {"rows": 0, "cols": 0, "columns": []}
    non_null = int(frame.notna().sum().sum())
    return non_null > 0, {
        "rows": int(len(frame)),
        "cols": int(len(frame.columns)),
        "columns": [str(c) for c in frame.columns[:25]],
        "non_null_cells": non_null,
    }


def _probe_get_data(ld: object, rics: list[str], fields: list[str]) -> dict[str, Any]:
    try:
        frame = ld.get_data(universe=rics, fields=fields)  # type: ignore[attr-defined]
        ok, summary = _frame_ok(frame)
        return {"ok": ok, "method": "get_data", "summary": summary, "error": None if ok else "empty"}
    except Exception as exc:
        return {
            "ok": False,
            "method": "get_data",
            "summary": {"rows": 0, "cols": 0, "columns": []},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=2),
        }


def _probe_get_history(
    ld: object,
    rics: list[str],
    fields: list[str],
    *,
    start: str,
    interval: str,
    parameters: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        kwargs: dict[str, Any] = {
            "universe": rics,
            "fields": fields,
            "start": start,
            "interval": interval,
        }
        if parameters:
            kwargs["parameters"] = parameters
        frame = ld.get_history(**kwargs)  # type: ignore[attr-defined]
        ok, summary = _frame_ok(frame)
        return {"ok": ok, "method": "get_history", "summary": summary, "error": None if ok else "empty"}
    except Exception as exc:
        return {
            "ok": False,
            "method": "get_history",
            "summary": {"rows": 0, "cols": 0, "columns": []},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=2),
        }


def _probe_index_constituent(ld: object, spec: dict[str, Any]) -> dict[str, Any]:
    fields = list(spec["fields"])
    results: list[dict[str, Any]] = []

    # Current membership on index RICs.
    for ric in spec.get("rics", [".SPX"]):
        snap = _probe_get_data(ld, [ric], fields)
        snap["ric"] = ric
        snap["variant"] = "current_on_index"
        results.append(snap)

    # PIT pattern 0#.SPX with SDate.
    pit_ric = str(spec.get("pit_ric", "0#.SPX"))
    sdate = str(spec.get("sdate", "20180115"))
    extra_pit = dict(spec.get("extra_pit_rics") or {})
    pit_targets = extra_pit if extra_pit else {spec.get("rics", [".SPX"])[0]: pit_ric}
    if not extra_pit:
        pit_targets = {str(spec.get("rics", [".SPX"])[0]): pit_ric}

    for index_ric, pit_pattern in pit_targets.items():
        try:
            frame = ld.get_data(  # type: ignore[attr-defined]
                universe=[pit_pattern],
                fields=fields,
                parameters={"SDate": sdate},
            )
            ok, summary = _frame_ok(frame)
            results.append(
                {
                    "ok": ok,
                    "method": "get_data",
                    "variant": "pit_0hash_sdate",
                    "ric": pit_pattern,
                    "index_ric": index_ric,
                    "parameters": {"SDate": sdate},
                    "summary": summary,
                    "error": None if ok else "empty",
                }
            )
        except Exception as exc:
            results.append(
                {
                    "ok": False,
                    "method": "get_data",
                    "variant": "pit_0hash_sdate",
                    "ric": pit_pattern,
                    "index_ric": index_ric,
                    "parameters": {"SDate": sdate},
                    "summary": {"rows": 0, "cols": 0, "columns": []},
                    "error": f"{type(exc).__name__}: {exc}",
                }
            )

    ok_count = sum(1 for r in results if r.get("ok"))
    pit = next((r for r in results if r.get("ok") and r.get("variant") == "pit_0hash_sdate"), None)
    best = pit or next((r for r in results if r.get("ok")), results[0] if results else None)
    return {
        "ok": ok_count > 0,
        "method": "index_constituent",
        "variants": results,
        "best_variant": best,
    }


def _fundamental_response_to_df(response: Any) -> pd.DataFrame:
    if response is None:
        return pd.DataFrame()
    if isinstance(response, pd.DataFrame):
        return response.copy()
    if hasattr(response, "data") and hasattr(response.data, "df"):
        return response.data.df.copy()
    return pd.DataFrame()


def _probe_fundamental_definition(ld: object, rics: list[str], fields: list[str], parameters: dict[str, Any]) -> dict[str, Any]:
    try:
        from lseg.data.content import fundamental_and_reference as fr  # type: ignore

        frames: list[pd.DataFrame] = []
        errors: list[str] = []
        for ric in rics:
            try:
                definition = fr.Definition(universe=ric, fields=fields, parameters=parameters)
                frame = _fundamental_response_to_df(definition.get_data())
                if frame is not None and not frame.empty:
                    frames.append(frame)
            except Exception as exc:
                errors.append(f"{ric}: {type(exc).__name__}: {exc}")
        if frames:
            merged = pd.concat(frames, ignore_index=True)
            ok, summary = _frame_ok(merged)
            return {
                "ok": ok,
                "method": "fundamental_and_reference.Definition",
                "summary": summary,
                "errors": errors,
                "error": None if ok else "empty",
            }
        return {
            "ok": False,
            "method": "fundamental_and_reference.Definition",
            "summary": {"rows": 0, "cols": 0, "columns": []},
            "errors": errors,
            "error": errors[0] if errors else "empty",
        }
    except Exception as exc:
        return {
            "ok": False,
            "method": "fundamental_and_reference.Definition",
            "summary": {"rows": 0, "cols": 0, "columns": []},
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(limit=2),
        }


def _status_from_probe(probe: dict[str, Any]) -> str:
    if probe.get("ok"):
        return "pass"
    # Partial: some sub-variants or history worked.
    variants = probe.get("variants") or []
    if variants:
        ok_n = sum(1 for v in variants if v.get("ok"))
        if ok_n > 0:
            return "partial"
    hist = probe.get("history")
    if hist and hist.get("ok"):
        return "partial"
    snap = probe.get("snapshot")
    if snap and snap.get("ok"):
        return "partial"
    return "fail"


def _probe_fundamental_multi(ld: object, rics: list[str], fields: list[str]) -> dict[str, Any]:
    """Try multiple Period/FRQ parameter sets for fundamentals."""
    from lseg.data.content import fundamental_and_reference as fr  # type: ignore

    param_sets = [
        {"label": "frq_fy", "parameters": {"SDate": "0", "EDate": "-20", "FRQ": "FY"}},
        {"label": "fy0", "parameters": {"Period": "FY0"}},
        {"label": "ltm", "parameters": {"Period": "LTM"}},
        {"label": "fq", "parameters": {"Period": "FQ"}},
    ]
    variants: list[dict[str, Any]] = []
    for ps in param_sets:
        variants.append(
            {
                "label": ps["label"],
                "parameters": dict(ps["parameters"]),
                **_probe_fundamental_definition(ld, rics, fields, dict(ps["parameters"])),
            }
        )
    # Also try get_data snapshot fundamentals
    snap = _probe_get_data(ld, rics, fields)
    variants.append({"label": "get_data_snapshot", **snap, "method": "get_data"})
    ok = [v for v in variants if v.get("ok")]
    fundamental_ok = [v for v in ok if v.get("label") not in {"get_data_snapshot"}]
    best = fundamental_ok[0] if fundamental_ok else (ok[0] if ok else (variants[0] if variants else {}))
    return {
        "ok": bool(ok),
        "method": "fundamental_multi",
        "variants": variants,
        "best_variant": best,
    }


def probe_category(ld: object, category_id: str, spec: dict[str, Any]) -> dict[str, Any]:
    method = spec.get("method", "get_data")
    rics = list(spec.get("rics", PROBE_RICS))
    fields = list(spec.get("fields", []))

    if method == "index_constituent":
        probe = _probe_index_constituent(ld, spec)
    elif method == "fundamental_multi":
        probe = _probe_fundamental_multi(ld, rics, fields)
    elif method == "fundamental_definition":
        probe = _probe_fundamental_definition(ld, rics, fields, dict(spec.get("parameters") or {}))
    elif method == "get_data_and_history":
        snap = _probe_get_data(ld, rics, fields)
        hist = _probe_get_history(
            ld,
            rics[:3],
            fields[:2],
            start=str(spec.get("history_start", "2024-01-01")),
            interval=str(spec.get("history_interval", "daily")),
        )
        probe = {"snapshot": snap, "history": hist, "ok": bool(snap.get("ok")) or bool(hist.get("ok"))}
    elif method == "get_data_history_params":
        snap = _probe_get_data(ld, rics, fields)
        hist = _probe_get_history(
            ld,
            rics[:2],
            fields,
            start=str(spec.get("history_start", "2023-01-01")),
            interval=str(spec.get("history_interval", "daily")),
            parameters=dict(spec.get("parameters") or {}),
        )
        probe = {"snapshot": snap, "history": hist, "ok": bool(snap.get("ok")) or bool(hist.get("ok"))}
    else:
        probe = _probe_get_data(ld, rics, fields)

    status = _status_from_probe(probe)
    return {
        "category_id": category_id,
        "description": spec.get("description", ""),
        "status": status,
        "rics": rics,
        "fields": fields,
        "probe": probe,
    }


def run_probe(priority_path: Path) -> dict[str, Any]:
    priority = load_priority(priority_path)
    categories: dict[str, Any] = {}
    constituent_api: dict[str, Any] | None = None

    with platform_session() as ld:
        for cat_id, spec in CATEGORY_SPECS.items():
            result = probe_category(ld, cat_id, spec)
            categories[cat_id] = result
            if cat_id == "B7_B8_index_constituents":
                best = (result.get("probe") or {}).get("best_variant")
                if best and best.get("ok"):
                    constituent_api = {
                        "method": best.get("method"),
                        "variant": best.get("variant"),
                        "ric_pattern": best.get("ric"),
                        "parameters": best.get("parameters"),
                        "fields": spec.get("fields"),
                    }
            if cat_id == "D8_pit_fundamentals":
                best = (result.get("probe") or {}).get("best_variant")
                if best and best.get("ok"):
                    categories[cat_id]["recommended_harvest"] = {
                        "method": best.get("method", "fundamental_and_reference.Definition"),
                        "label": best.get("label"),
                        "parameters": best.get("parameters") if "parameters" in best else {},
                        "fields": spec.get("fields"),
                    }

    status_counts = {"pass": 0, "partial": 0, "fail": 0}
    for cat in categories.values():
        status_counts[str(cat.get("status", "fail"))] = status_counts.get(str(cat.get("status")), 0) + 1

    return {
        "generated_at": utc_now(),
        "priority_path": str(priority_path),
        "probe_rics": PROBE_RICS,
        "summary": {
            "categories_total": len(categories),
            **status_counts,
        },
        "constituent_api_recommendation": constituent_api,
        "categories": categories,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Refinitiv value-first entitlement probe (Job 0).")
    ap.add_argument("--priority", default=str(DEFAULT_PRIORITY))
    ap.add_argument("--env", default=".env.local")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    args = ap.parse_args()

    load_env(args.env)
    priority_path = Path(args.priority)
    if not priority_path.is_absolute():
        priority_path = REPO / priority_path
    out_path = Path(args.out)
    if not out_path.is_absolute():
        out_path = REPO / out_path
    out_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        report = run_probe(priority_path)
    except Exception as exc:
        report = {
            "generated_at": utc_now(),
            "summary": {"error": f"{type(exc).__name__}: {exc}"},
            "categories": {},
        }
        out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Probe failed: {exc}", file=sys.stderr)
        traceback.print_exc()
        return 1

    summary = report.get("summary") or {}
    if int(summary.get("pass", 0)) == 0 and int(summary.get("partial", 0)) == 0 and out_path.exists():
        prior = json.loads(out_path.read_text(encoding="utf-8"))
        prior_summary = prior.get("summary") or {}
        if int(prior_summary.get("pass", 0)) > 0 or int(prior_summary.get("partial", 0)) > 0:
            prior["probe_aborted"] = {
                "reason": "All categories failed; retaining prior entitlement map.",
                "attempted_at": utc_now(),
            }
            out_path.write_text(json.dumps(prior, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print(json.dumps({**prior_summary, "retained_prior": True}, indent=2))
            print(f"Retained prior map at {out_path}")
            return 1

    out_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(report["summary"], indent=2))
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
