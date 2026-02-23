"""
ipc — Shared TCP server for the mGBA ↔ Python bridge.

Provides :class:`MGBAServer`: a reusable connection manager that all
application modules (inject, scan, collect) build on top of.
"""

from .server import MGBAServer

__all__ = ["MGBAServer"]
