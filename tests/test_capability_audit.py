from __future__ import annotations

import json
from pathlib import Path

from src.research.capability_audit import audit_capabilities, render_markdown, write_report


def test_capability_audit_scores_artifact_coverage(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "src").mkdir()
    (repo / "src" / "one.py").write_text("x = 1\n")
    (repo / "reports").mkdir()
    (repo / "reports" / "summary.json").write_text("{}\n")

    cfg = {
        "scope": "test",
        "principle": "test principle",
        "capabilities": [
            {
                "id": "cap_strong",
                "area": "A",
                "target_state": "All artifacts exist.",
                "external_projects": ["project/a"],
                "stealable_pattern": "pattern",
                "local_artifacts": ["src/one.py", "reports/*.json"],
                "current_read": "Strong local coverage.",
                "next_actions": ["keep it healthy"],
            },
            {
                "id": "cap_weak",
                "area": "B",
                "target_state": "Most artifacts missing.",
                "external_projects": ["project/b"],
                "stealable_pattern": "pattern",
                "local_artifacts": ["missing/a.py", "missing/b.py", "reports/*.json"],
                "current_read": "Gap remains.",
                "next_actions": ["build missing pieces"],
            },
        ],
    }
    config = tmp_path / "capabilities.json"
    config.write_text(json.dumps(cfg))

    report = audit_capabilities(repo, config)
    by_id = {row["id"]: row for row in report["capabilities"]}

    assert by_id["cap_strong"]["status"] == "strong"
    assert by_id["cap_weak"]["status"] == "weak"
    assert by_id["cap_weak"]["priority"] == "high"
    assert report["summary"]["status_counts"]["strong"] == 1
    assert report["summary"]["status_counts"]["weak"] == 1


def test_capability_audit_writes_json_and_markdown(tmp_path: Path):
    repo = tmp_path / "repo"
    repo.mkdir()
    config = tmp_path / "capabilities.json"
    config.write_text(
        json.dumps(
            {
                "scope": "test",
                "principle": "p",
                "capabilities": [
                    {
                        "id": "missing_cap",
                        "area": "A",
                        "target_state": "x",
                        "external_projects": ["project/a"],
                        "stealable_pattern": "learn this",
                        "local_artifacts": ["missing.txt"],
                        "current_read": "Gap.",
                        "next_actions": ["create missing.txt"],
                    }
                ],
            }
        )
    )

    report = audit_capabilities(repo, config)
    paths = write_report(report, tmp_path / "out")
    md = render_markdown(report)

    assert Path(paths["json"]).exists()
    assert Path(paths["markdown"]).exists()
    assert "Investment Capability Audit" in md
    assert "missing_cap" in md
