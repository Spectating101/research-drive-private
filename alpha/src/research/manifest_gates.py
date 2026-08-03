"""Candidate manifest integrity gates for investment runs."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

import pandas as pd

from src.research.investment_cockpit import STATUS_VALUES


DEFAULT_STRICT_STATUSES = {"paper_candidate", "deployable_sleeve"}
DEFAULT_REQUIRED_PARAMS = ("universe_id", "benchmark_id", "validation_protocol")
DEFAULT_REQUIRED_ARTIFACT_GROUPS = {
    "signal": ("signal", "target_signal", "weights", "target_weights"),
    "performance": ("scorecard", "summary", "backtest", "edge_readiness"),
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    obj = json.loads(Path(path).read_text())
    if not isinstance(obj, dict):
        raise ValueError(f"expected JSON object: {path}")
    return obj


def _resolve_path(repo: Path, path_value: Any) -> Path | None:
    if path_value is None or str(path_value).strip() == "":
        return None
    path = Path(str(path_value))
    if path.is_absolute():
        return path
    if path.parts and path.parts[0] == repo.name:
        path = Path(*path.parts[1:]) if len(path.parts) > 1 else Path(".")
    return (repo / path).resolve()


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _artifact_has_any(artifacts: Mapping[str, Any], names: Sequence[str]) -> bool:
    for name in names:
        ref = artifacts.get(name)
        if isinstance(ref, Mapping) and ref.get("path"):
            return True
    return False


def _requires_factor_tearsheet(manifest: Mapping[str, Any]) -> bool:
    params = manifest.get("params", {}) if isinstance(manifest, Mapping) else {}
    value = str(params.get("requires_factor_tearsheet", "")).strip().lower()
    if value in {"1", "true", "yes"}:
        return True
    selector = str(params.get("selector_type", "")).strip().lower()
    return selector in {"factor", "rank", "ranking", "stock_selector", "equity_selector"}


def _has_factor_tearsheet(repo: Path, manifest: Mapping[str, Any]) -> bool:
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest, Mapping) else {}
    for name in ("factor_tearsheet", "factor_tearsheet_summary", "alphalens_tearsheet"):
        ref = artifacts.get(name) if isinstance(artifacts, Mapping) else None
        if isinstance(ref, Mapping):
            path = _resolve_path(repo, ref.get("path"))
            if path and path.exists():
                return True
    run_dir = _resolve_path(repo, manifest.get("run_dir"))
    if run_dir and (run_dir / "factor_tearsheet" / "summary.json").exists():
        return True
    return False


def _evaluated_decision_exists(decision_log: Path | None, run_id: str) -> bool:
    if not decision_log or not Path(decision_log).exists():
        return False
    df = pd.read_csv(decision_log, dtype=str).fillna("")
    if df.empty or "decision_id" not in df.columns:
        return False
    hit = df[df["decision_id"].astype(str).str.startswith(f"{run_id}-")]
    if hit.empty:
        return False
    return bool((hit.get("evaluated_at", "").astype(str).str.strip() != "").any())


def check_candidate_manifest(
    manifest_path: Path,
    *,
    repo: Path,
    decision_log: Path | None = None,
    strict_statuses: set[str] | None = None,
) -> dict[str, Any]:
    """Check one candidate manifest for provenance and promotion evidence."""

    strict_statuses = strict_statuses or set(DEFAULT_STRICT_STATUSES)
    repo = Path(repo).resolve()
    manifest_path = Path(manifest_path)
    reasons: list[str] = []
    warnings: list[str] = []

    try:
        manifest = _load_json(manifest_path)
    except Exception as exc:
        return {
            "manifest_path": str(manifest_path),
            "run_id": None,
            "strategy": None,
            "status": None,
            "strict": False,
            "passed": False,
            "reasons": [f"manifest_unreadable: {exc}"],
            "warnings": [],
            "artifact_checks": [],
        }

    run_id = str(manifest.get("run_id", "") or "")
    strategy = str(manifest.get("strategy", "") or "")
    status = str(manifest.get("status", "") or "")
    params = manifest.get("params", {}) if isinstance(manifest.get("params", {}), Mapping) else {}
    artifacts = manifest.get("artifacts", {}) if isinstance(manifest.get("artifacts", {}), Mapping) else {}
    strict = status in strict_statuses

    for field in ("manifest_version", "run_id", "strategy", "status", "created_at"):
        if not str(manifest.get(field, "")).strip():
            reasons.append(f"missing_{field}")
    if status and status not in STATUS_VALUES:
        reasons.append(f"invalid_status={status}")
    if status == "blocked" and not str(manifest.get("notes", "")).strip():
        reasons.append("blocked_manifest_missing_notes")

    run_dir = _resolve_path(repo, manifest.get("run_dir"))
    if manifest.get("run_dir") and (not run_dir or not run_dir.exists()):
        reasons.append("run_dir_missing")

    artifact_checks: list[dict[str, Any]] = []
    for name, ref in artifacts.items():
        if not isinstance(ref, Mapping):
            reasons.append(f"artifact_ref_invalid:{name}")
            continue
        path = _resolve_path(repo, ref.get("path"))
        exists = bool(path and path.exists())
        check = {
            "name": str(name),
            "path": str(path) if path else "",
            "declared_exists": bool(ref.get("exists")),
            "actual_exists": exists,
            "sha256_ok": None,
            "bytes_ok": None,
        }
        if not path:
            reasons.append(f"artifact_path_missing:{name}")
        elif not exists:
            reasons.append(f"artifact_missing:{name}")
        else:
            declared_bytes = ref.get("bytes")
            if declared_bytes is not None:
                actual_bytes = int(path.stat().st_size)
                check["bytes_ok"] = actual_bytes == int(declared_bytes)
                if not check["bytes_ok"]:
                    reasons.append(f"artifact_bytes_mismatch:{name}")
            declared_hash = str(ref.get("sha256") or "")
            if declared_hash and path.is_file() and path.stat().st_size <= 64 * 1024 * 1024:
                actual_hash = _sha256(path)
                check["sha256_ok"] = actual_hash == declared_hash
                if not check["sha256_ok"]:
                    reasons.append(f"artifact_sha256_mismatch:{name}")
        artifact_checks.append(check)

    if strict:
        for key in DEFAULT_REQUIRED_PARAMS:
            if not str(params.get(key, "")).strip():
                reasons.append(f"missing_param:{key}")
        for group, names in DEFAULT_REQUIRED_ARTIFACT_GROUPS.items():
            if not _artifact_has_any(artifacts, names):
                reasons.append(f"missing_artifact_group:{group}")
        if not manifest.get("metrics"):
            reasons.append("missing_metrics")
        if _requires_factor_tearsheet(manifest) and not _has_factor_tearsheet(repo, manifest):
            reasons.append("missing_factor_tearsheet")

    if status == "deployable_sleeve":
        for key in ("cost_model_id", "risk_model_id", "execution_safety_config"):
            if not str(params.get(key, "")).strip():
                reasons.append(f"missing_deployable_param:{key}")
        if not _evaluated_decision_exists(decision_log, run_id):
            reasons.append("deployable_without_evaluated_frozen_decision")
    elif status in {"paper_candidate", "deployable_sleeve"} and not _evaluated_decision_exists(decision_log, run_id):
        warnings.append("no_evaluated_frozen_decision_yet")

    return {
        "manifest_path": str(manifest_path),
        "run_id": run_id,
        "strategy": strategy,
        "status": status,
        "strict": strict,
        "passed": not reasons,
        "reasons": reasons,
        "warnings": warnings,
        "artifact_checks": artifact_checks,
    }


def manifest_gate_report(
    registry_csv: Path,
    *,
    repo: Path,
    decision_log: Path | None = None,
    strict_statuses: set[str] | None = None,
) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    missing_registry = not Path(registry_csv).exists()
    if not missing_registry:
        registry = pd.read_csv(registry_csv, dtype=str).fillna("")
        for _, row in registry.iterrows():
            manifest_value = str(row.get("manifest_path", "") or "")
            manifest_path = _resolve_path(Path(repo).resolve(), manifest_value)
            if manifest_path:
                rows.append(
                    check_candidate_manifest(
                        manifest_path,
                        repo=repo,
                        decision_log=decision_log,
                        strict_statuses=strict_statuses,
                    )
                )
    failing = [r for r in rows if not r["passed"]]
    warnings = [w for r in rows for w in r.get("warnings", [])]
    reasons = ["candidate_registry_missing"] if missing_registry else []
    reasons.extend(f"{r.get('run_id')}: {reason}" for r in failing for reason in r.get("reasons", []))
    return {
        "generated_at": _utc_now(),
        "repo": str(Path(repo).resolve()),
        "registry_csv": str(registry_csv),
        "decision_log": str(decision_log) if decision_log else None,
        "n_manifests": len(rows),
        "n_failing": len(failing) + (1 if missing_registry else 0),
        "n_warnings": len(warnings),
        "passed": not reasons,
        "reasons": reasons,
        "results": rows,
    }


def render_manifest_gate_markdown(report: Mapping[str, Any]) -> str:
    lines = [
        "# Candidate Manifest Gates",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Registry: `{report.get('registry_csv')}`",
        f"- Manifests: `{report.get('n_manifests')}`",
        f"- Failing: `{report.get('n_failing')}`",
        f"- Passed: `{report.get('passed')}`",
        "",
        "## Results",
        "",
        "| Run | Strategy | Status | Strict | Passed | Reasons | Warnings |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    results = report.get("results", [])
    if not isinstance(results, list):
        results = []
    for row in results:
        lines.append(
            f"| {row.get('run_id')} | {row.get('strategy')} | {row.get('status')} | "
            f"{row.get('strict')} | {row.get('passed')} | {', '.join(row.get('reasons', []))} | "
            f"{', '.join(row.get('warnings', []))} |"
        )
    reasons = report.get("reasons") or []
    lines.extend(["", "## Reasons", ""])
    if reasons:
        for reason in reasons:
            lines.append(f"- {reason}")
    else:
        lines.append("- none")
    return "\n".join(lines) + "\n"


def write_manifest_gate_report(report: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    jp = out_dir / "latest.json"
    mp = out_dir / "latest.md"
    jp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    mp.write_text(render_manifest_gate_markdown(report))
    return {"json": str(jp), "markdown": str(mp)}
