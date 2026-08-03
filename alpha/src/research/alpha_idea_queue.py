"""Alpha idea queue.

Ideas are allowed to be speculative. Promotion is not. This module gives human
or agent-generated stock alpha ideas a controlled lifecycle before they become
validated factors or strategy candidates.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd


IDEA_COLUMNS = [
    "idea_id",
    "source",
    "created_at",
    "hypothesis",
    "universe",
    "feature_recipe",
    "expected_mechanism",
    "risk_of_leakage",
    "status",
    "validation_artifact",
    "owner",
    "updated_at",
    "notes",
]

IDEA_STATUSES = {
    "idea",
    "feature_ready",
    "backtest_ready",
    "validated",
    "rejected",
    "paper_candidate",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def init_idea_queue(path: Path, *, overwrite: bool = False) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and not overwrite:
        return path
    pd.DataFrame(columns=IDEA_COLUMNS).to_csv(path, index=False)
    return path


def load_idea_queue(path: Path) -> pd.DataFrame:
    if not Path(path).exists():
        init_idea_queue(path)
    return pd.read_csv(path, dtype=str).fillna("")


def upsert_idea(path: Path, row: Mapping[str, Any]) -> Path:
    if "idea_id" not in row or not str(row.get("idea_id", "")).strip():
        raise ValueError("idea_id is required")
    status = str(row.get("status", "idea") or "idea")
    if status not in IDEA_STATUSES:
        raise ValueError(f"status must be one of {sorted(IDEA_STATUSES)}")
    df = load_idea_queue(path)
    now = _utc_now()
    out = {col: str(row.get(col, "")) for col in IDEA_COLUMNS}
    out["status"] = status
    out["created_at"] = out["created_at"] or now
    out["updated_at"] = now
    df = df[df["idea_id"].astype(str) != out["idea_id"]] if "idea_id" in df.columns else df
    df = pd.concat([df, pd.DataFrame([out])], ignore_index=True)
    df = df[IDEA_COLUMNS].sort_values(["status", "updated_at", "idea_id"], na_position="last")
    df.to_csv(path, index=False)
    return Path(path)


def promote_idea(path: Path, idea_id: str, status: str, *, validation_artifact: str = "", notes: str = "") -> Path:
    if status not in IDEA_STATUSES:
        raise ValueError(f"status must be one of {sorted(IDEA_STATUSES)}")
    df = load_idea_queue(path)
    mask = df["idea_id"].astype(str) == str(idea_id)
    if not mask.any():
        raise ValueError(f"idea_id not found: {idea_id}")
    df.loc[mask, "status"] = status
    if validation_artifact:
        df.loc[mask, "validation_artifact"] = validation_artifact
    if notes:
        existing = df.loc[mask, "notes"].astype(str)
        df.loc[mask, "notes"] = existing.apply(lambda v: f"{v} | {notes}" if v else notes)
    df.loc[mask, "updated_at"] = _utc_now()
    df.to_csv(path, index=False)
    return Path(path)


def idea_queue_report(path: Path) -> dict[str, Any]:
    df = load_idea_queue(path)
    status_counts = df["status"].value_counts().to_dict() if "status" in df.columns else {}
    stale_validation = []
    if not df.empty:
        needs_validation = df[df["status"].isin(["feature_ready", "backtest_ready", "validated", "paper_candidate"])]
        missing = needs_validation[needs_validation["validation_artifact"].astype(str).str.strip() == ""]
        stale_validation = missing["idea_id"].astype(str).tolist()
    return {
        "path": str(path),
        "n_ideas": int(len(df)),
        "status_counts": {str(k): int(v) for k, v in status_counts.items()},
        "ideas_missing_validation_artifact": stale_validation,
    }
