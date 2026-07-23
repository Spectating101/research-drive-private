"""Inventory Drive registry panels for the alpha research flywheel.

Does not import Drive app modules. Uses sharpe_kernel for local resolve,
and optional HTTP :8765 when RQE_URL is set / query engine is up.
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

from sharpe_kernel.platform_bridge import load_registry, resolve_dataset_parquet

DEFAULT_MANIFEST = "alpha/config/alpha_fuel_manifest.json"


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def load_fuel_manifest(repo_root: Path, path: Path | None = None) -> dict[str, Any]:
    manifest_path = path or (repo_root / DEFAULT_MANIFEST)
    if not manifest_path.exists():
        # Fallback when only root config symlink layout is incomplete.
        alt = repo_root / "config" / "alpha_fuel_manifest.json"
        manifest_path = alt if alt.exists() else manifest_path
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _time_col(df: pd.DataFrame) -> str | None:
    for c in ("week_end", "date", "Date", "as_of_month", "week", "timestamp"):
        if c in df.columns:
            return c
    return None


def panel_as_of(path: Path) -> dict[str, Any]:
    """Best-effort as-of date from parquet/csv mtime + content time column."""
    out: dict[str, Any] = {
        "path": str(path),
        "exists": path.exists(),
        "size_bytes": path.stat().st_size if path.exists() else 0,
        "mtime_utc": None,
        "content_as_of": None,
        "age_days_mtime": None,
        "age_days_content": None,
    }
    if not path.exists():
        return out
    mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    out["mtime_utc"] = mtime.isoformat()
    out["age_days_mtime"] = (_utc_now() - mtime).total_seconds() / 86400.0
    try:
        if path.suffix == ".parquet":
            df = pd.read_parquet(path)
        elif path.suffix in {".csv", ".tsv"}:
            df = pd.read_csv(path, nrows=50000)
        else:
            return out
        col = _time_col(df)
        if col is None:
            return out
        series = pd.to_datetime(df[col], errors="coerce").dropna()
        if series.empty:
            return out
        latest = pd.Timestamp(series.max()).tz_localize(None)
        out["content_as_of"] = str(latest.date())
        out["age_days_content"] = float(
            (pd.Timestamp(_utc_now()).tz_localize(None).normalize() - latest.normalize()).days
        )
    except Exception as exc:  # noqa: BLE001 — inventory must be resilient
        out["read_error"] = f"{type(exc).__name__}: {exc}"
    return out


def try_resolve_dataset(repo_root: Path, dataset_id: str, *, registry_path: str | Path | None = None) -> Path | None:
    try:
        return resolve_dataset_parquet(repo_root, dataset_id, registry_path=registry_path)
    except Exception:
        return None


def _http_describe(base_url: str, dataset_id: str, timeout: float = 3.0) -> dict[str, Any] | None:
    url = f"{base_url.rstrip('/')}/datasets/{urllib.parse.quote(dataset_id)}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError, OSError):
        return None


def inventory_fuel(
    repo_root: Path,
    *,
    manifest_path: Path | None = None,
    registry_path: str | Path | None = None,
    query_engine_url: str | None = None,
    probe_http: bool = True,
) -> dict[str, Any]:
    """Resolve each fuel dataset and classify ready / stale / missing."""
    manifest = load_fuel_manifest(repo_root, manifest_path)
    env_key = str(manifest.get("query_engine_url_env") or "RQE_URL")
    base_url = query_engine_url or os.environ.get(env_key) or str(
        manifest.get("default_query_engine_url") or "http://127.0.0.1:8765"
    )

    # Touch registry once so inventory notes registry load failures.
    registry_ok = True
    registry_error = None
    try:
        load_registry(repo_root, registry_path)
    except Exception as exc:  # noqa: BLE001
        registry_ok = False
        registry_error = f"{type(exc).__name__}: {exc}"

    rows: list[dict[str, Any]] = []
    supply_asks: list[dict[str, Any]] = []
    for spec in manifest.get("datasets") or []:
        did = str(spec.get("dataset_id") or "")
        max_age = float(spec.get("max_age_days") or 30)
        path = try_resolve_dataset(repo_root, did, registry_path=registry_path)
        status = "missing"
        detail: dict[str, Any] = {
            "dataset_id": did,
            "priority": spec.get("priority"),
            "role": spec.get("role"),
            "max_age_days": max_age,
            "join_keys": spec.get("join_keys") or [],
            "resolved_path": str(path) if path else None,
            "status": status,
        }
        if path is not None:
            freshness = panel_as_of(path)
            detail["freshness"] = freshness
            age = freshness.get("age_days_content")
            if age is None:
                age = freshness.get("age_days_mtime")
            detail["age_days"] = age
            if age is not None and float(age) <= max_age:
                status = "ready"
            else:
                status = "stale"
            detail["status"] = status
        if probe_http:
            http = _http_describe(base_url, did)
            detail["http_query_engine"] = {
                "url": base_url,
                "reachable": http is not None,
                "dataset_id_match": bool(http and (http.get("dataset_id") == did or http.get("id") == did)),
            }
        rows.append(detail)
        if status in {"missing", "stale"}:
            supply_asks.append(
                {
                    "dataset_id": did,
                    "status": status,
                    "priority": spec.get("priority"),
                    "role": spec.get("role"),
                    "suggested_mcp": [
                        f'research_describe_dataset("{did}")',
                        f'research_query_dataset("{did}", "{{\\"limit\\": 5}}")',
                        "research_discover_search / yzu_submit_job if miss",
                    ],
                }
            )

    ready = sum(1 for r in rows if r["status"] == "ready")
    return {
        "built_at_utc": _utc_now().isoformat(),
        "registry_ok": registry_ok,
        "registry_error": registry_error,
        "query_engine_url": base_url,
        "manifest_version": manifest.get("version"),
        "n_datasets": len(rows),
        "n_ready": ready,
        "n_stale": sum(1 for r in rows if r["status"] == "stale"),
        "n_missing": sum(1 for r in rows if r["status"] == "missing"),
        "datasets": rows,
        "supply_asks": supply_asks,
        "mcp_supply_hints": manifest.get("mcp_supply_hints") or [],
        "flywheel": "supply → research → gates → promote|beta_core → next supply asks",
    }


def write_inventory(report: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    lines = [
        "# Alpha fuel inventory (Drive → engine)",
        "",
        f"- built: `{report.get('built_at_utc')}`",
        f"- ready: **{report.get('n_ready')}** / {report.get('n_datasets')} "
        f"(stale={report.get('n_stale')}, missing={report.get('n_missing')})",
        f"- query_engine: `{report.get('query_engine_url')}`",
        "",
        "## Datasets",
        "",
    ]
    for row in report.get("datasets") or []:
        lines.append(
            f"- `{row['dataset_id']}` · {row.get('priority')} · **{row.get('status')}** · "
            f"age_days={row.get('age_days')}"
        )
    asks = report.get("supply_asks") or []
    if asks:
        lines.extend(["", "## Supply asks (for Drive MCP/API)", ""])
        for ask in asks:
            lines.append(f"- **{ask['status']}** `{ask['dataset_id']}` ({ask.get('priority')}) — {ask.get('role')}")
    lines.append("")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    return {"json": json_path, "md": md_path}
