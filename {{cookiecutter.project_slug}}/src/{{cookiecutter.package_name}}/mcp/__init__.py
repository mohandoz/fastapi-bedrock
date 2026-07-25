"""Model Context Protocol (MCP) integration: curated tools for AI agents."""

from {{ cookiecutter.package_name }}.mcp.server import create_mcp_app, mcp

__all__ = ["create_mcp_app", "mcp"]
