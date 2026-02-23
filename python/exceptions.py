"""
exceptions.py — Custom exception hierarchy for the mGBA bridge.

Every failure mode has a specific exception type so callers can
handle them selectively instead of catching generic ``RuntimeError``.

Hierarchy::

    BridgeError
    ├── ConnectionError_        (name avoids shadowing builtins)
    │   ├── HandshakeError
    │   └── DisconnectedError
    ├── ProtocolError
    │   ├── MessageTooLarge
    │   └── InvalidPayload
    ├── InjectionError
    │   ├── EncodingError
    │   └── InjectionRejected
    └── CommandTimeout
"""

from __future__ import annotations


class BridgeError(Exception):
    """Base for all mGBA bridge errors."""


# Connection errors


class ConnectionFailed(BridgeError):
    """Could not establish or maintain a TCP connection."""


class HandshakeError(ConnectionFailed):
    """The hello / PING / PONG handshake did not complete."""


class DisconnectedError(ConnectionFailed):
    """The Lua client dropped the connection mid-session."""


# Protocol errors


class ProtocolError(BridgeError):
    """The remote peer sent data that violates the protocol."""


class MessageTooLarge(ProtocolError):
    """A single message exceeds ``MAX_MSG_SIZE``."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"Message size {size} bytes exceeds limit of {limit} bytes"
        )
        self.size = size
        self.limit = limit


class InvalidPayload(ProtocolError):
    """JSON parse failed or required fields are missing."""


# Injection errors


class InjectionError(BridgeError):
    """Writing to the emulator text buffer failed."""


class EncodingError(InjectionError):
    """Text contains characters outside the Pokemon character table."""


class InjectionRejected(InjectionError):
    """
    The Lua side refused the INJECT (e.g. payload too large,
    wrong engine state, invalid hex).
    """

    def __init__(self, reason: str) -> None:
        super().__init__(f"Injection rejected: {reason}")
        self.reason = reason


# Timeout


class CommandTimeout(BridgeError):
    """A command did not receive a response within the deadline."""

    def __init__(self, command: str, timeout: float) -> None:
        super().__init__(
            f"No response to {command!r} within {timeout:.1f}s"
        )
        self.command = command
        self.timeout = timeout


# Buffer overflow


class BufferOverflow(BridgeError):
    """The internal receive buffer exceeded its safety limit."""

    def __init__(self, size: int, limit: int) -> None:
        super().__init__(
            f"Receive buffer ({size} bytes) exceeded limit ({limit} bytes)"
        )
        self.size = size
        self.limit = limit
