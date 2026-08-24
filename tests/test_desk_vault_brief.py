from pathlib import Path

from scripts.research_data_mcp.desk_vault_brief import build_vault_brief


def test_build_vault_brief_has_ready_section() -> None:
    repo = Path(__file__).resolve().parents[1]
    brief = build_vault_brief(repo)
    assert "Desk vault brief" in brief
    assert "Ready now" in brief or "On disk" in brief
