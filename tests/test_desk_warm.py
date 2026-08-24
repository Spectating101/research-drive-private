from pathlib import Path
from unittest.mock import MagicMock, patch

from scripts.research_data_mcp.desk_warm import build_prime_prompt, warm_desk_session

REPO = Path(__file__).resolve().parents[1]


def test_build_prime_prompt_includes_brief() -> None:
    text = build_prime_prompt("Desk vault brief\nReady now:\n- TWSE")
    assert "Desk vault brief" in text
    assert "Reply with exactly: Ready" in text


def test_warm_skips_when_already_primed() -> None:
    gateway = MagicMock()
    gateway.repo_root = REPO
    orch = MagicMock()
    gateway._procurement_chat_orchestrator.return_value = orch
    orch.sessions.get_or_create.return_value = {
        "id": "sess1",
        "state": {"desk_primed": True, "cursor_agent_id": "a1", "vault_brief": "brief"},
    }
    out = warm_desk_session(gateway, user_email="drkong@saturn.yzu.edu.tw", session_id="sess1", background=False)
    assert out["primed"] is True
    assert out["session_id"] == "sess1"


def test_warm_background_starts_priming() -> None:
    gateway = MagicMock()
    gateway.repo_root = REPO
    orch = MagicMock()
    gateway._procurement_chat_orchestrator.return_value = orch
    orch.sessions.get_or_create.return_value = {"id": "sess2", "state": {"vault_brief": "loaded"}}
    with patch("scripts.research_data_mcp.desk_brain.cursor_composer_available", return_value=True):
        out = warm_desk_session(gateway, background=True)
    assert out["priming"] is True
    assert out["session_id"] == "sess2"
    orch.sessions.update_state.assert_called()
