"""
server.py — Shared TCP server for the mGBA Lua IPC bridge.

Handles:
  - Bind / listen / accept (one mGBA connection at a time)
  - Non-blocking receive with JSON-line parsing
  - Command sending (plain-text with optional ``#id`` tracking)
  - Automatic reconnection in the event loop
  - Callback-based and polling-based message dispatch
  - Receive-buffer overflow protection
  - Rate-limiting on outbound commands
  - Context-manager support (``with MGBAServer() as srv: ...``)

Every Python application module (inject, scan, collect) uses this
instead of duplicating TCP boilerplate.

Protocol:
  Lua → Python :  JSON lines  (events + command responses)
  Python → Lua :  plain-text commands, one per line
                  optional trailing  ``#<id>``  for correlation
"""

from __future__ import annotations

import json
import logging
import select
import socket
import time
from collections import deque
from typing import Callable

from ..config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    MAX_MSG_SIZE,
    PROTO_VERSION,
    RECV_CHUNK,
    RX_BUF_LIMIT,
    BURST_LIMIT,
    BURST_WINDOW,
    BridgeConfig,
)
from ..exceptions import (
    BufferOverflow,
    ConnectionFailed,
    DisconnectedError,
    MessageTooLarge,
    InvalidPayload,
)

logger = logging.getLogger(__name__)


class MGBAServer:
    """
    TCP server that accepts a connection from an mGBA Lua script.

    Supports two consumption styles:

    **Event-loop** (for apps with continuous message processing)::

        server = MGBAServer(host="127.0.0.1", port=35600)
        server.run_loop(on_message=my_handler)

    **Polling** (for interactive / blocking apps)::

        server = MGBAServer()
        server.start()
        server.wait_for_connection()
        server.send_command("PING")
        msg = server.recv_one(timeout=5.0)

    **Context manager**::

        with MGBAServer() as srv:
            srv.wait_for_connection()
            ...

    Parameters
    ----------
    host : str
        TCP bind address.
    port : int
        TCP bind port.
    config : BridgeConfig | None
        Optional override for buffer limits and protocol tunables.
    """

    __slots__ = (
        "host",
        "port",
        "_cfg",
        "_server",
        "_conn",
        "_rx_buf",
        "_cmd_counter",
        "_running",
        "_send_timestamps",
    )

    def __init__(
        self,
        host: str = DEFAULT_HOST,
        port: int = DEFAULT_PORT,
        *,
        config: BridgeConfig | None = None,
    ):
        self.host = host
        self.port = port
        self._cfg = config or BridgeConfig(host=host, port=port)
        self._server: socket.socket | None = None
        self._conn: socket.socket | None = None
        self._rx_buf: str = ""
        self._cmd_counter: int = 0
        self._running: bool = False
        self._send_timestamps: deque[float] = deque()

    # Context manager

    def __enter__(self) -> MGBAServer:
        self.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.stop()

    # Properties

    @property
    def is_connected(self) -> bool:
        return self._conn is not None

    @property
    def proto_version(self) -> int:
        return PROTO_VERSION

    # Lifecycle

    def start(self) -> None:
        """Bind and listen (does not block)."""
        self._server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.settimeout(None)
        self._server.bind((self.host, self.port))
        self._server.listen(1)
        logger.info("Listening on %s:%d (proto v%d)", self.host, self.port, PROTO_VERSION)

    def wait_for_connection(self, timeout: float = 60.0) -> None:
        """Block until mGBA connects.

        Raises
        ------
        ConnectionFailed
            If no connection arrives within *timeout*.
        RuntimeError
            If the server has not been started.
        """
        if self._server is None:
            raise RuntimeError("Server not started — call start() first")
        self._server.settimeout(timeout)
        try:
            conn, addr = self._server.accept()
        except socket.timeout as exc:
            raise ConnectionFailed(
                "No mGBA connection within timeout.  "
                "Is the Lua script loaded?"
            ) from exc
        finally:
            self._server.settimeout(None)

        conn.setblocking(False)
        try:
            conn.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        except OSError:
            pass
        try:
            conn.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
        except OSError:
            pass

        self._conn = conn
        self._rx_buf = ""
        self._send_timestamps.clear()
        logger.info("mGBA connected from %s", addr)

    def stop(self) -> None:
        """Close everything — safe to call multiple times."""
        self._close_conn()
        if self._server:
            try:
                self._server.close()
            except Exception:
                pass
            self._server = None
        self._running = False

    # Sending

    def send_command(self, command: str) -> None:
        """Send a plain-text command terminated by ``\\n``.

        Raises
        ------
        DisconnectedError
            If not connected.
        """
        if not self._conn:
            raise DisconnectedError("Not connected to mGBA")
        self._enforce_rate_limit()
        self._conn.sendall((command + "\n").encode("utf-8"))
        logger.debug("TX: %s", command)

    def send_command_with_id(self, command: str) -> str:
        """Send a command with a trailing ``#<id>``.  Returns the id."""
        cmd_id = self._next_id()
        self.send_command(f"{command} #{cmd_id}")
        return cmd_id

    # Receiving

    def recv_messages(self, timeout: float = 0.25) -> list[dict]:
        """
        Non-blocking receive.  Returns a (possibly empty) list of
        parsed JSON messages.

        If the connection drops, closes cleanly and returns ``[]``.
        If the receive buffer overflows, raises ``BufferOverflow``.
        """
        # Drain any complete lines already sitting in the buffer
        # BEFORE doing another recv — avoids data loss.
        buffered = self._drain_lines()
        if buffered:
            return buffered

        if not self._conn:
            return []

        try:
            ready, _, _ = select.select([self._conn], [], [], timeout)
        except (ValueError, OSError):
            self._close_conn()
            return []

        if not ready:
            return []

        try:
            chunk = self._conn.recv(self._cfg.recv_chunk)
        except BlockingIOError:
            return []
        except (ConnectionResetError, ConnectionAbortedError, OSError) as exc:
            logger.warning("Connection lost: %s", exc)
            self._close_conn()
            return []

        if not chunk:
            logger.info("mGBA disconnected (EOF)")
            self._close_conn()
            return []

        self._rx_buf += chunk.decode("utf-8", errors="replace")

        # Guard: prevent unbounded buffer growth
        if len(self._rx_buf) > self._cfg.rx_buf_limit:
            size = len(self._rx_buf)
            self._rx_buf = ""
            logger.error(
                "Receive buffer overflow (%d bytes > %d limit), cleared",
                size,
                self._cfg.rx_buf_limit,
            )
            raise BufferOverflow(size, self._cfg.rx_buf_limit)

        return self._drain_lines()

    def recv_one(self, timeout: float = 10.0) -> dict | None:
        """Block until *one* JSON message arrives (or timeout).

        Unlike a naive implementation, surplus messages consumed during
        the wait are **not lost** — they stay in ``_rx_buf`` for the
        next ``recv_messages()`` / ``recv_one()`` call.
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            remaining = max(0.05, deadline - time.time())
            msgs = self.recv_messages(timeout=min(0.5, remaining))
            if msgs:
                # Push the excess back into the buffer as JSON lines so
                # the next recv_messages picks them up.
                if len(msgs) > 1:
                    leftover = "".join(
                        json.dumps(m) + "\n" for m in msgs[1:]
                    )
                    self._rx_buf = leftover + self._rx_buf
                return msgs[0]
        return None

    # Event loop

    def run_loop(
        self,
        on_message: Callable[[dict], None],
        on_connect: Callable[[], None] | None = None,
        on_disconnect: Callable[[], None] | None = None,
    ) -> None:
        """
        Main event loop.  Accepts connections and dispatches messages
        until ``KeyboardInterrupt``.  Automatically waits for
        reconnection when the Lua script disconnects.
        """
        if self._server is None:
            self.start()
        self._running = True
        was_connected = False

        try:
            while self._running:
                # Accept connection if needed
                if not self.is_connected:
                    if was_connected:
                        was_connected = False
                        if on_disconnect:
                            on_disconnect()
                    try:
                        self.wait_for_connection(timeout=2.0)
                        was_connected = True
                        if on_connect:
                            on_connect()
                    except (ConnectionFailed, TimeoutError):
                        continue

                # Dispatch messages
                try:
                    for msg in self.recv_messages(timeout=0.25):
                        on_message(msg)
                except BufferOverflow:
                    logger.warning("Buffer overflow in event loop; continuing")

        except KeyboardInterrupt:
            logger.info("Shutting down (Ctrl+C)")
        finally:
            if was_connected and on_disconnect:
                on_disconnect()
            self._running = False
            self.stop()

    def shutdown(self) -> None:
        """Signal ``run_loop`` to exit cleanly."""
        self._running = False

    # Internals

    def _next_id(self) -> str:
        self._cmd_counter += 1
        return str(self._cmd_counter)

    def _close_conn(self) -> None:
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
        self._conn = None
        self._rx_buf = ""

    def _drain_lines(self) -> list[dict]:
        """Parse all complete JSON lines sitting in ``_rx_buf``.

        Validates individual message sizes and drops oversized lines
        with a warning instead of crashing the whole pipeline.
        """
        messages: list[dict] = []
        while "\n" in self._rx_buf:
            line, self._rx_buf = self._rx_buf.split("\n", 1)
            line = line.strip()
            if not line:
                continue
            if len(line) > self._cfg.max_msg_size:
                logger.warning(
                    "Dropping oversized message (%d bytes > %d limit)",
                    len(line),
                    self._cfg.max_msg_size,
                )
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                logger.warning("Invalid JSON from mGBA: %.120s", line)
        return messages

    def _enforce_rate_limit(self) -> None:
        """Simple sliding-window rate limiter for outbound commands."""
        now = time.monotonic()
        # Expire old timestamps
        while self._send_timestamps and self._send_timestamps[0] < now - BURST_WINDOW:
            self._send_timestamps.popleft()
        if len(self._send_timestamps) >= BURST_LIMIT:
            sleep_time = self._send_timestamps[0] + BURST_WINDOW - now
            if sleep_time > 0:
                logger.debug("Rate-limiting: sleeping %.3fs", sleep_time)
                time.sleep(sleep_time)
        self._send_timestamps.append(now)
