"""MCP server for California ASSIST (assist.org) articulation agreements."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("assist-mcp")
except PackageNotFoundError:  # running from a source tree, not installed
    __version__ = "0+unknown"

__all__ = ["__version__"]
