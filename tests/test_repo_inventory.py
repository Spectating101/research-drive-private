from __future__ import annotations

from pathlib import Path

from src.research.repo_inventory import build_repo_inventory


def test_repo_inventory_classifies_core_and_environment_artifacts(tmp_path: Path):
    core = tmp_path / "src" / "research"
    core.mkdir(parents=True)
    (core / "investment_cockpit.py").write_text("# core\n")
    venv_file = tmp_path / ".venv-refinitiv" / "lib" / "python" / "site-packages" / "cryptography.py"
    venv_file.parent.mkdir(parents=True)
    venv_file.write_text("# env\n")
    shot = tmp_path / "research-drive-current-desktop.png"
    shot.write_bytes(b"png")

    report = build_repo_inventory(tmp_path)
    cats = report["category_counts"]
    assert cats["active_investment_core"]["count"] == 1
    assert cats["local_environment_artifact"]["count"] == 1
    assert cats["root_generated_clutter"]["count"] == 1
    assert report["root_quarantine_candidates"][0]["path"] == "research-drive-current-desktop.png"
