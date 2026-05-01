"""
Server package — re-exports create_server for backward compatibility.

All existing imports of `from .server import create_server` or
`from src.server import create_server` continue to work unchanged.
"""
from .core import create_server

__all__ = ["create_server"]
