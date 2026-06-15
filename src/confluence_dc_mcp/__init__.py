"""MCP server for Confluence Data Center raw storage operations."""

from importlib.metadata import PackageNotFoundError, version

__all__ = ["__version__"]

try:
    __version__ = version("confluence-dc-mcp")
except PackageNotFoundError:
    __version__ = "0.0.0"
