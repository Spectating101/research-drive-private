"""Research data library — backend package (gateway, bootstrap, HTTP router, MCP)."""

from scripts.research_data_mcp.bootstrap import ResearchLibraryStack, create_stack
from scripts.research_data_mcp.gateway import ResearchDataGateway
from scripts.research_data_mcp.jobs import JobService

__all__ = ["ResearchDataGateway", "ResearchLibraryStack", "JobService", "create_stack"]
