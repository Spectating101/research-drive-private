from __future__ import annotations

from pathlib import Path

from scripts.research_data_mcp import desk_auth
from scripts.research_data_mcp.desk_principal import DeskPrincipal
from scripts.research_data_mcp.research_profile import (
    personal_profile,
    profile_storage_root,
    update_personal_profile,
)


def test_runtime_drive_is_profile_storage_authority(monkeypatch, tmp_path: Path):
    checkout = tmp_path / "candidate-checkout"
    runtime = tmp_path / "runtime-drive"
    checkout.mkdir()
    runtime.mkdir()
    monkeypatch.setenv("YZU_RUNTIME_DRIVE_ROOT", str(runtime))
    alice = DeskPrincipal(
        principal_id="cf-alice-0123456789abcdef0123456789abcdef",
        email="alice@example.edu",
        display_name="Alice",
        role="public_member",
    )

    assert profile_storage_root(checkout) == runtime / "data_lake/research_drive/profiles"
    with desk_auth.desk_principal_context(alice):
        update_personal_profile(checkout, {"research_topics": ["market liquidity"]})
        assert personal_profile(checkout)["research_topics"] == ["market liquidity"]

    assert list((runtime / "data_lake/research_drive/profiles").glob("*.json"))
    assert not (checkout / "data_lake/research_drive/profiles").exists()
