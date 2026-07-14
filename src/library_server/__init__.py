"""The Library — MCP server for AI-assisted project management."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("the-library")
except PackageNotFoundError:
    # Running from a source checkout without an installed distribution.
    __version__ = "0.0.0.dev0"
