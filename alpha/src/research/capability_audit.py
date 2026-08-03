"""Investment capability audit.

Reads a capability map and checks which local artifacts exist. The output is a
machine-readable JSON report plus a compact operator Markdown report.
"""

from __future__ import annotations

import glob
import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence


STATUS_ORDER = {
    "missing": 0,
    "weak": 1,
    "partial": 2,
    "strong": 3,
}


@dataclass(frozen=True)
class ArtifactCheck:
    pattern: str
    matches: list[str]

    @property
    def present(self) -> bool:
        return bool(self.matches)

    def as_dict(self) -> dict[str, Any]:
        return {
            "pattern": self.pattern,
            "present": self.present,
            "matches": self.matches[:20],
            "n_matches": len(self.matches),
        }


def load_capability_map(path: Path) -> dict[str, Any]:
    data = json.loads(Path(path).read_text())
    if not isinstance(data, dict):
        raise ValueError(f"capability map must be a JSON object: {path}")
    capabilities = data.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("capability map missing capabilities list")
    return data


def check_artifact(repo: Path, pattern: str) -> ArtifactCheck:
    full = repo / pattern
    if any(ch in pattern for ch in "*?[]"):
        matches = sorted(
            str(Path(p).relative_to(repo))
            for p in glob.glob(str(full), recursive=True)
            if Path(p).exists()
        )
    else:
        matches = [pattern] if full.exists() else []
    return ArtifactCheck(pattern=pattern, matches=matches)


def infer_status(checks: Sequence[ArtifactCheck]) -> tuple[str, float, int, int]:
    total = len(checks)
    present = sum(1 for c in checks if c.present)
    coverage = present / total if total else 0.0
    if total == 0 or present == 0:
        status = "missing"
    elif coverage < 0.40:
        status = "weak"
    elif coverage < 0.80:
        status = "partial"
    else:
        status = "strong"
    return status, coverage, present, total


def reconcile_status(capability: Mapping[str, Any], artifact_status: str) -> str:
    """Combine artifact coverage with the human current_read in the map.

    Artifact presence proves code/data exists. It does not prove the capability is
    integrated. The current_read field is intentionally allowed to cap status.
    """
    read = str(capability.get("current_read", "")).strip().lower()
    if read.startswith("gap"):
        declared = "weak"
    elif read.startswith("partial"):
        declared = "partial"
    elif read.startswith("strong"):
        declared = "strong"
    else:
        declared = artifact_status
    if STATUS_ORDER.get(artifact_status, 0) < STATUS_ORDER.get(declared, 0):
        return artifact_status
    return declared


def capability_priority(capability: Mapping[str, Any], status: str) -> str:
    text = " ".join(
        str(capability.get(k, ""))
        for k in ("current_read", "target_state", "stealable_pattern")
    ).lower()
    if status in {"missing", "weak"}:
        return "high"
    if "gap" in text or "not yet" in text or "not unified" in text:
        return "high" if status == "partial" else "medium"
    if status == "partial":
        return "medium"
    return "low"


def audit_capabilities(repo: Path, config_path: Path) -> dict[str, Any]:
    repo = Path(repo)
    cfg = load_capability_map(config_path)
    rows: list[dict[str, Any]] = []
    for cap in cfg["capabilities"]:
        if not isinstance(cap, dict):
            continue
        checks = [check_artifact(repo, str(p)) for p in cap.get("local_artifacts", [])]
        artifact_status, coverage, present, total = infer_status(checks)
        status = reconcile_status(cap, artifact_status)
        rows.append(
            {
                "id": cap.get("id"),
                "area": cap.get("area"),
                "status": status,
                "artifact_status": artifact_status,
                "priority": capability_priority(cap, status),
                "coverage": coverage,
                "present_artifacts": present,
                "total_artifacts": total,
                "target_state": cap.get("target_state"),
                "external_projects": cap.get("external_projects", []),
                "stealable_pattern": cap.get("stealable_pattern"),
                "current_read": cap.get("current_read"),
                "next_actions": cap.get("next_actions", []),
                "artifact_checks": [c.as_dict() for c in checks],
            }
        )

    counts: dict[str, int] = {k: 0 for k in STATUS_ORDER}
    for row in rows:
        counts[str(row["status"])] = counts.get(str(row["status"]), 0) + 1
    priority_counts: dict[str, int] = {}
    for row in rows:
        key = str(row["priority"])
        priority_counts[key] = priority_counts.get(key, 0) + 1

    rows_sorted = sorted(
        rows,
        key=lambda r: (STATUS_ORDER.get(str(r["status"]), 99), {"high": 0, "medium": 1, "low": 2}.get(str(r["priority"]), 9), str(r["id"])),
    )
    top_actions: list[dict[str, str]] = []
    for row in rows_sorted:
        if row.get("priority") not in {"high", "medium"}:
            continue
        actions = row.get("next_actions", [])
        if not isinstance(actions, list) or not actions:
            continue
        top_actions.append(
            {
                "capability": str(row.get("id", "")),
                "priority": str(row.get("priority", "")),
                "status": str(row.get("status", "")),
                "action": str(actions[0]),
            }
        )
        if len(top_actions) >= 10:
            break
    return {
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "repo": str(repo),
        "config_path": str(config_path),
        "scope": cfg.get("scope"),
        "principle": cfg.get("principle"),
        "summary": {
            "n_capabilities": len(rows),
            "status_counts": counts,
            "priority_counts": priority_counts,
            "strong_or_partial": counts.get("strong", 0) + counts.get("partial", 0),
            "missing_or_weak": counts.get("missing", 0) + counts.get("weak", 0),
            "top_actions": top_actions,
        },
        "capabilities": rows_sorted,
    }


def _pct(value: Any) -> str:
    try:
        return f"{float(value) * 100:.0f}%"
    except Exception:
        return "n/a"


def _join(items: Sequence[Any], limit: int = 3) -> str:
    vals = [str(x) for x in items if str(x)]
    if not vals:
        return ""
    if len(vals) <= limit:
        return ", ".join(vals)
    return ", ".join(vals[:limit]) + f", +{len(vals) - limit} more"


def render_markdown(report: Mapping[str, Any]) -> str:
    summary = report.get("summary", {})
    status_counts = summary.get("status_counts", {}) if isinstance(summary, Mapping) else {}
    priority_counts = summary.get("priority_counts", {}) if isinstance(summary, Mapping) else {}
    lines = [
        "# Investment Capability Audit",
        "",
        f"- Generated: `{report.get('generated_at')}`",
        f"- Scope: `{report.get('scope')}`",
        f"- Capabilities: `{summary.get('n_capabilities', 0)}`",
        f"- Status counts: strong `{status_counts.get('strong', 0)}`, partial `{status_counts.get('partial', 0)}`, weak `{status_counts.get('weak', 0)}`, missing `{status_counts.get('missing', 0)}`",
        f"- Priority counts: high `{priority_counts.get('high', 0)}`, medium `{priority_counts.get('medium', 0)}`, low `{priority_counts.get('low', 0)}`",
        "",
        "## Capability Table",
        "",
        "| Capability | Area | Status | Coverage | Learn From | Stealable Pattern | Next Action |",
        "| --- | --- | --- | ---: | --- | --- | --- |",
    ]
    capabilities = report.get("capabilities", [])
    for cap in capabilities if isinstance(capabilities, list) else []:
        actions = cap.get("next_actions", [])
        first_action = actions[0] if isinstance(actions, list) and actions else ""
        lines.append(
            "| {id} | {area} | {status}/{priority} | {coverage} | {projects} | {pattern} | {action} |".format(
                id=cap.get("id", ""),
                area=cap.get("area", ""),
                status=cap.get("status", ""),
                priority=cap.get("priority", ""),
                coverage=_pct(cap.get("coverage", 0)),
                projects=_join(cap.get("external_projects", []), limit=2),
                pattern=str(cap.get("stealable_pattern", "")).replace("|", "/"),
                action=str(first_action).replace("|", "/"),
            )
        )

    high = [
        cap
        for cap in capabilities
        if isinstance(cap, Mapping) and cap.get("priority") == "high"
    ]
    lines.extend(["", "## High-Priority Gaps", ""])
    if not high:
        lines.append("- None.")
    for cap in high:
        lines.append(f"- **{cap.get('id')}** ({cap.get('status')}, {_pct(cap.get('coverage', 0))} coverage): {cap.get('current_read')}")
        actions = cap.get("next_actions", [])
        if isinstance(actions, list):
            for action in actions[:3]:
                lines.append(f"  - {action}")

    lines.extend(["", "## Top Build Queue", ""])
    top_actions = summary.get("top_actions", []) if isinstance(summary, Mapping) else []
    if not top_actions:
        lines.append("- None.")
    for item in top_actions if isinstance(top_actions, list) else []:
        lines.append(
            f"- **{item.get('capability')}** [{item.get('priority')}/{item.get('status')}]: {item.get('action')}"
        )

    lines.extend(["", "## Existing Strengths", ""])
    strengths = [
        cap
        for cap in capabilities
        if isinstance(cap, Mapping) and cap.get("status") == "strong"
    ]
    if not strengths:
        lines.append("- None marked strong yet.")
    for cap in strengths:
        lines.append(f"- **{cap.get('id')}**: {cap.get('current_read')}")

    lines.extend(["", "## Operating Interpretation", ""])
    lines.append(
        "Use this report as the platform upgrade tracker: external projects provide "
        "patterns, local artifacts prove capability, and high-priority gaps become "
        "the next build queue."
    )
    return "\n".join(lines) + "\n"


def write_report(report: Mapping[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "latest.json"
    md_path = out_dir / "latest.md"
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    md_path.write_text(render_markdown(report))
    return {"json": str(json_path), "markdown": str(md_path)}
