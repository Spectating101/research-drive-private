from __future__ import annotations

from sharpe_kernel.paths import registry_path


def test_mcp_server_uses_the_same_configured_registry_authority_as_the_desk():
    """A staged checkout may lack the legacy root-level config link."""
    from scripts.research_data_mcp import server

    assert server.REGISTRY == registry_path()
