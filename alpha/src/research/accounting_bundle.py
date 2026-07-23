"""Canonical accounting bundle for investment strategy runs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from src.research.accounting_reconciliation import reconcile_accounting


CORE_ARTIFACTS = (
    "target_weights",
    "target_signal",
    "orders",
    "fills",
    "positions",
    "equity_ledger",
    "scorecard",
    "safety_config",
)


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _resolve(repo: Path, path: Path | str | None) -> Path | None:
    if path is None or str(path).strip() == "":
        return None
    p = Path(path)
    if p.is_absolute():
        return p
    if p.parts and p.parts[0] == repo.name:
        p = Path(*p.parts[1:]) if len(p.parts) > 1 else Path(".")
    return (repo / p).resolve()


def _sha256(path: Path) -> str | None:
    if not path.exists() or not path.is_file():
        return None
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact(repo: Path, path: Path | str | None) -> dict[str, Any]:
    p = _resolve(repo, path)
    exists = bool(p and p.exists())
    return {
        "path": str(p) if p else None,
        "exists": exists,
        "sha256": _sha256(p) if p and exists and p.is_file() and p.stat().st_size <= 64 * 1024 * 1024 else None,
        "bytes": int(p.stat().st_size) if p and exists and p.is_file() else None,
    }


def build_accounting_bundle(
    *,
    repo: Path,
    strategy: str,
    run_id: str,
    as_of: str | None = None,
    target_weights_path: Path | None = None,
    target_signal_path: Path | None = None,
    orders_path: Path | None = None,
    fills_path: Path | None = None,
    positions_path: Path | None = None,
    equity_ledger_path: Path | None = None,
    scorecard_path: Path | None = None,
    safety_config_path: Path | None = None,
) -> dict[str, Any]:
    """Build a machine-readable bundle for execution/accounting artifacts."""

    repo = Path(repo).resolve()
    target_for_reconcile = target_weights_path or target_signal_path
    reconciliation = reconcile_accounting(
        target_weights_path=_resolve(repo, target_for_reconcile),
        orders_path=_resolve(repo, orders_path),
        fills_path=_resolve(repo, fills_path),
        positions_path=_resolve(repo, positions_path),
        equity_ledger_path=_resolve(repo, equity_ledger_path),
        scorecard_path=_resolve(repo, scorecard_path),
    )
    artifacts = {
        "target_weights": _artifact(repo, target_weights_path),
        "target_signal": _artifact(repo, target_signal_path),
        "orders": _artifact(repo, orders_path),
        "fills": _artifact(repo, fills_path),
        "positions": _artifact(repo, positions_path),
        "equity_ledger": _artifact(repo, equity_ledger_path),
        "scorecard": _artifact(repo, scorecard_path),
        "safety_config": _artifact(repo, safety_config_path),
    }
    present = {k: bool(v.get("exists")) for k, v in artifacts.items()}
    has_target = present["target_weights"] or present["target_signal"]
    complete = all(
        [
            has_target,
            present["orders"],
            present["fills"],
            present["positions"],
            present["equity_ledger"],
            present["scorecard"],
            present["safety_config"],
            bool(reconciliation.get("passed")),
        ]
    )
    legacy_partial = bool(present["equity_ledger"] and present["scorecard"] and reconciliation.get("passed"))
    if complete:
        status = "complete"
    elif reconciliation.get("passed") and legacy_partial:
        status = "legacy_partial"
    elif reconciliation.get("passed"):
        status = "partial"
    else:
        status = "fail"

    missing = [
        name
        for name, ok in present.items()
        if not ok and name not in {"target_weights", "target_signal"}
    ]
    if not has_target:
        missing.append("target_weights_or_signal")

    return {
        "schema_version": 1,
        "generated_at": _utc_now(),
        "repo": str(repo),
        "strategy": strategy,
        "run_id": run_id,
        "as_of": as_of,
        "status": status,
        "complete": complete,
        "missing_artifacts": sorted(set(missing)),
        "artifacts": artifacts,
        "reconciliation": reconciliation,
        "checks": {
            "has_target_weights_or_signal": has_target,
            "has_orders": present["orders"],
            "has_fills": present["fills"],
            "has_positions": present["positions"],
            "has_equity_ledger": present["equity_ledger"],
            "has_scorecard": present["scorecard"],
            "has_safety_config": present["safety_config"],
            "reconciliation_passed": bool(reconciliation.get("passed")),
        },
    }


def render_accounting_bundle_markdown(bundle: Mapping[str, Any]) -> str:
    lines = [
        "# Accounting Bundle",
        "",
        f"- Generated: `{bundle.get('generated_at')}`",
        f"- Strategy: `{bundle.get('strategy')}`",
        f"- Run: `{bundle.get('run_id')}`",
        f"- Status: `{bundle.get('status')}`",
        f"- Complete: `{bundle.get('complete')}`",
        "",
        "## Checks",
        "",
    ]
    checks = bundle.get("checks", {})
    if isinstance(checks, Mapping):
        for key, value in checks.items():
            lines.append(f"- {key}: `{value}`")
    missing = bundle.get("missing_artifacts") or []
    lines.extend(["", "## Missing Artifacts", ""])
    if missing:
        for item in missing:
            lines.append(f"- {item}")
    else:
        lines.append("- none")
    recon = bundle.get("reconciliation", {})
    if isinstance(recon, Mapping):
        lines.extend(["", "## Reconciliation", "", f"- Passed: `{recon.get('passed')}`"])
        for reason in recon.get("reasons", []) or []:
            lines.append(f"- {reason}")
    return "\n".join(lines) + "\n"


def write_accounting_bundle(bundle: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    run_id = str(bundle.get("run_id") or "run")
    run_dir = out_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    run_json = run_dir / "bundle.json"
    run_md = run_dir / "bundle.md"
    latest_json = out_dir / "latest.json"
    latest_md = out_dir / "latest.md"
    payload = json.dumps(bundle, indent=2, sort_keys=True) + "\n"
    markdown = render_accounting_bundle_markdown(bundle)
    run_json.write_text(payload)
    latest_json.write_text(payload)
    run_md.write_text(markdown)
    latest_md.write_text(markdown)

    index_path = out_dir / "index.csv"
    row = {
        "generated_at": bundle.get("generated_at"),
        "strategy": bundle.get("strategy"),
        "run_id": bundle.get("run_id"),
        "status": bundle.get("status"),
        "complete": bundle.get("complete"),
        "bundle_json": str(run_json),
    }
    if index_path.exists():
        df = pd.read_csv(index_path)
        df = df[df["run_id"].astype(str) != str(bundle.get("run_id"))] if "run_id" in df.columns else df
        df = pd.concat([df, pd.DataFrame([row])], ignore_index=True)
    else:
        df = pd.DataFrame([row])
    df.sort_values(["generated_at", "run_id"], na_position="last").to_csv(index_path, index=False)
    return {
        "json": str(run_json),
        "markdown": str(run_md),
        "latest_json": str(latest_json),
        "latest_markdown": str(latest_md),
        "index": str(index_path),
    }
