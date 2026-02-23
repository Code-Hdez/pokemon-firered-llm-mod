"""
config.py — Centralised, immutable configuration for the mGBA bridge.

Reads defaults from this module, overridable via environment variables.
Every other module that needs host/port/memory addresses imports from
here — **no more duplicated magic numbers**.

Environment variables (all optional):
    MGBA_HOST           default 127.0.0.1
    MGBA_PORT           default 35600
    MGBA_TIMEOUT        default 10.0 (seconds)
    MGBA_LOG_LEVEL      default INFO
    MGBA_MAX_MSG_SIZE   default 8192
    MGBA_MAX_INJECT     default 256
    MGBA_RX_BUF_LIMIT   default 65536
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default)


def _env_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError:
        return default


# IPC defaults

DEFAULT_HOST: str = _env("MGBA_HOST", "127.0.0.1")
DEFAULT_PORT: int = _env_int("MGBA_PORT", 35600)
DEFAULT_TIMEOUT: float = _env_float("MGBA_TIMEOUT", 10.0)
LOG_LEVEL: str = _env("MGBA_LOG_LEVEL", "INFO")

# Protocol limits

PROTO_VERSION: int = 2
MAX_MSG_SIZE: int = _env_int("MGBA_MAX_MSG_SIZE", 8192)
MAX_INJECT_SIZE: int = _env_int("MGBA_MAX_INJECT", 256)
RX_BUF_LIMIT: int = _env_int("MGBA_RX_BUF_LIMIT", 65_536)
MAX_EVENT_QUEUE: int = 256
RECV_CHUNK: int = 4096

# Rate limiting

COMMAND_MIN_INTERVAL: float = 0.001  # 1 ms between commands
BURST_LIMIT: int = 50  # max commands in a sliding window
BURST_WINDOW: float = 1.0  # window size in seconds

# GBA memory regions (FireRed US (NOT REV 1))

EWRAM_START: int = 0x0200_0000
EWRAM_END: int = 0x0203_FFFF
IWRAM_START: int = 0x0300_0000
IWRAM_END: int = 0x0300_7FFF

# Known memory addresses

TEXT_BUF: int = 0x0202_1D18
STATE_ADDR: int = 0x0300_0EB0
SCRIPT_CMD_PTR: int = 0x0300_0EB8
NPC_SCRIPT_PTR: int = 0x0300_0EBC
SAVE_BLOCK1_PTR: int = 0x0300_5008

# String buffer addresses (pokefirered)

KNOWN_STRING_ADDRS: dict[str, int] = {
    "gStringVar1": 0x0202_1CC4,
    "gStringVar2": 0x0202_1DC4,
    "gStringVar3": 0x0202_1EC4,
    "gStringVar4": 0x0202_1FC4,
}


@dataclass(frozen=True, slots=True)
class BridgeConfig:
    """
    Runtime configuration bundle.

    Create with defaults::

        cfg = BridgeConfig()

    Override selectively::

        cfg = BridgeConfig(port=12345, timeout=5.0)
    """

    host: str = DEFAULT_HOST
    port: int = DEFAULT_PORT
    timeout: float = DEFAULT_TIMEOUT
    max_msg_size: int = MAX_MSG_SIZE
    max_inject_size: int = MAX_INJECT_SIZE
    rx_buf_limit: int = RX_BUF_LIMIT
    max_event_queue: int = MAX_EVENT_QUEUE
    recv_chunk: int = RECV_CHUNK
    log_level: str = LOG_LEVEL
