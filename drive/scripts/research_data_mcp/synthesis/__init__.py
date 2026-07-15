"""Multi-source dataset synthesis — join lab holdings on explicit keys."""

from scripts.research_data_mcp.synthesis.engine import (
    get_latest_synthesis,
    list_synthesis_profiles,
    run_synthesis,
    run_synthesis_pair,
)
from scripts.research_data_mcp.synthesis.registry_pair import run_registry_pair

__all__ = [
    "get_latest_synthesis",
    "list_synthesis_profiles",
    "run_registry_pair",
    "run_synthesis",
    "run_synthesis_pair",
]
