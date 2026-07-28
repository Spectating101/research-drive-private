"""Research data library — backend package (gateway, bootstrap, HTTP router, MCP)."""

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from scripts.research_data_mcp.bootstrap import ResearchLibraryStack
    from scripts.research_data_mcp.gateway import ResearchDataGateway
    from scripts.research_data_mcp.jobs import JobService

__all__ = ["ResearchDataGateway", "ResearchLibraryStack", "JobService", "create_stack"]


def __getattr__(name: str) -> Any:
    """Load the backend graph only when a public facade object is requested."""
    if name in {"ResearchLibraryStack", "create_stack"}:
        from scripts.research_data_mcp.bootstrap import ResearchLibraryStack, create_stack

        return {"ResearchLibraryStack": ResearchLibraryStack, "create_stack": create_stack}[name]
    if name == "ResearchDataGateway":
        from scripts.research_data_mcp.gateway import ResearchDataGateway

        return ResearchDataGateway
    if name == "JobService":
        from scripts.research_data_mcp.jobs import JobService

        return JobService
    raise AttributeError(name)
