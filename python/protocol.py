"""
protocol.py — Data models and helpers for the IPC protocol.

Defines typed containers for every message that crosses the TCP wire
so the rest of the codebase never works with unvalidated ``dict``s.
Uses stdlib ``dataclasses`` only — no external dependencies.

Also provides:
- ``CommandBuilder``: safe construction of Python→Lua commands with
  optional ``#id`` tracking.
- ``validate_inject_hex()``: pre-flight validation before sending
  INJECT payloads.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from .config import MAX_INJECT_SIZE, PROTO_VERSION

# Enums


class EventType(str, Enum):
    """Known event types sent from Lua → Python."""

    HELLO = "hello"
    PONG = "pong"
    DIALOG_OPEN = "dialog_open"
    DIALOG_CLOSE = "dialog_close"
    PAGE_WAIT = "dialog_page_wait"
    PAGE_ADVANCE = "dialog_page_advance"
    MAP_CHANGE = "map_change"
    MAP_INFO = "map_info"
    READ = "read"
    FIND = "find"
    ACK = "ack"
    ERR = "err"
    FRAME = "frame"


class CommandName(str, Enum):
    """Known command names sent from Python → Lua."""

    PING = "PING"
    READ = "READ"
    FIND = "FIND"
    INJECT = "INJECT"
    STREAM = "STREAM"
    WATCH = "WATCH"
    MAP = "MAP"


# Response models


@dataclass(slots=True)
class Ack:
    """Successful acknowledgement from Lua."""

    msg: str = ""
    length: int = 0
    cmd_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> Ack:
        return cls(
            msg=d.get("msg", ""),
            length=d.get("len", 0),
            cmd_id=d.get("id"),
        )


@dataclass(slots=True)
class ErrorResponse:
    """Error response from Lua."""

    msg: str = ""
    cmd_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> ErrorResponse:
        return cls(msg=d.get("msg", ""), cmd_id=d.get("id"))


@dataclass(slots=True)
class ReadResponse:
    """Response to a READ command."""

    address: str = ""
    length: int = 0
    hex_data: str = ""
    cmd_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> ReadResponse:
        return cls(
            address=d.get("addr", ""),
            length=d.get("len", 0),
            hex_data=d.get("hex", ""),
            cmd_id=d.get("id"),
        )


@dataclass(slots=True)
class FindResponse:
    """Response to a FIND command."""

    addresses: list[str] = field(default_factory=list)
    cmd_id: str | None = None

    @classmethod
    def from_dict(cls, d: dict) -> FindResponse:
        return cls(addresses=d.get("addrs", []), cmd_id=d.get("id"))


@dataclass(slots=True)
class HelloInfo:
    """Parsed hello handshake data."""

    title: str = ""
    code: str = ""
    proto: int = 1
    mode: str = ""

    @classmethod
    def from_dict(cls, d: dict) -> HelloInfo:
        return cls(
            title=d.get("title", ""),
            code=d.get("code", ""),
            proto=d.get("proto", 1),
            mode=d.get("mode", ""),
        )


@dataclass(slots=True)
class DialogEvent:
    """Parsed dialog_open event."""

    npc: str = ""
    ptr_eb8: str = ""
    ptr_ebc: str = ""
    text_hex: str = ""
    text_len: int = 0
    engine_state: int = 0
    ebc_valid: bool = False
    frame: int = 0
    raw: dict = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict) -> DialogEvent:
        return cls(
            npc=d.get("npc", d.get("ptr_EBC", "")),
            ptr_eb8=d.get("ptr_EB8", ""),
            ptr_ebc=d.get("ptr_EBC", ""),
            text_hex=d.get("textHex", ""),
            text_len=d.get("len", d.get("text_len", 0)),
            engine_state=d.get("engine_state", 0),
            ebc_valid=d.get("ebc_valid", False),
            frame=d.get("frame", 0),
            raw=d,
        )


# Write operation (for batch API)


@dataclass(slots=True)
class WriteOp:
    """A single memory-write operation."""

    address: int
    data: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.data, (bytes, bytearray)):
            raise TypeError(f"data must be bytes, got {type(self.data).__name__}")
        if self.address < 0:
            raise ValueError(f"address must be non-negative, got 0x{self.address:X}")


# Validators

_HEX_RE = re.compile(r"^[0-9A-Fa-f]+$")


def validate_inject_hex(hex_str: str, *, max_size: int = MAX_INJECT_SIZE) -> str:
    """
    Validate a hex string before sending as an INJECT payload.

    Returns the uppercased, cleaned hex string.

    Raises
    ------
    ValueError
        On empty string, odd length, invalid chars, or oversized payload.
    """
    clean = hex_str.strip().replace(" ", "")
    if not clean:
        raise ValueError("INJECT payload is empty")
    if len(clean) % 2 != 0:
        raise ValueError(
            f"INJECT hex must be even length (got {len(clean)} chars)"
        )
    if not _HEX_RE.match(clean):
        raise ValueError("INJECT hex contains non-hex characters")
    byte_count = len(clean) // 2
    if byte_count > max_size:
        raise ValueError(
            f"INJECT payload {byte_count} bytes exceeds limit of {max_size}"
        )
    return clean.upper()


def validate_address(address: int, *, label: str = "address") -> None:
    """
    Basic sanity check for a GBA address.

    Raises ``ValueError`` if obviously invalid.
    """
    if not isinstance(address, int):
        raise TypeError(f"{label} must be int, got {type(address).__name__}")
    if address < 0 or address > 0x0FFF_FFFF:
        raise ValueError(
            f"{label} 0x{address:08X} is outside valid GBA address space"
        )
