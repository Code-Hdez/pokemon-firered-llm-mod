"""
memory_scan_app.py — Memory scanner for Pokemon FireRed.

Connects to mGBA via the Lua TCP bridge (memory_scan_bridge.lua) and
scans GBA memory to find Pokemon-encoded text.

Uses the shared :class:`MGBAServer` in polling mode for the interactive
CLI.

Lua counterpart: ``lua/memory_scan_bridge.lua``
"""

from __future__ import annotations

import logging
import sys

from ..config import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    EWRAM_END,
    EWRAM_START,
    IWRAM_END,
    IWRAM_START,
    KNOWN_STRING_ADDRS,
)
from ..ipc.server import MGBAServer
from ..pokemon_text import bytes_to_hex, decode_bytes, encode_text, hex_to_bytes

logger = logging.getLogger(__name__)


# Helpers


def _do_read(server: MGBAServer, addr: int, length: int) -> bytes:
    """Send READ, block for response, return raw bytes."""
    server.send_command(f"READ 0x{addr:08X} {length}")
    msg = server.recv_one(timeout=10.0)
    if not msg or msg.get("type") != "read":
        raise RuntimeError(f"Unexpected READ response: {msg}")
    return hex_to_bytes(msg["hex"])


def _do_find(
    server: MGBAServer,
    pattern_hex: str,
    start: int,
    end_addr: int,
) -> list[int]:
    """Send FIND, block for response, return list of addresses."""
    server.send_command(
        f"FIND {pattern_hex} 0x{start:08X} 0x{end_addr:08X}"
    )
    msg = server.recv_one(timeout=10.0)
    if not msg or msg.get("type") != "find":
        raise RuntimeError(f"Unexpected FIND response: {msg}")
    return [int(a, 16) for a in msg.get("addrs", [])]


# Interactive commands


def scan_for_text(server: MGBAServer, search_text: str) -> list[tuple[str, int]]:
    """Encode *search_text* into Pokemon bytes and scan GBA memory."""
    encoded = encode_text(search_text)
    pat_hex = bytes_to_hex(encoded)
    print(f"\n[*] Searching for: {search_text!r}")
    print(f"    Pokemon-encoded hex: {pat_hex}")
    print(f"    ({len(encoded)} bytes)")

    all_hits: list[tuple[str, int]] = []

    print(f"\n-- Scanning EWRAM  0x{EWRAM_START:08X} – 0x{EWRAM_END:08X} --")
    for addr in _do_find(server, pat_hex, EWRAM_START, EWRAM_END):
        all_hits.append(("EWRAM", addr))
        print(f"    FOUND at 0x{addr:08X}")
    if not [h for h in all_hits if h[0] == "EWRAM"]:
        print("    (no matches)")

    print(f"\n-- Scanning IWRAM  0x{IWRAM_START:08X} – 0x{IWRAM_END:08X} --")
    for addr in _do_find(server, pat_hex, IWRAM_START, IWRAM_END):
        all_hits.append(("IWRAM", addr))
        print(f"    FOUND at 0x{addr:08X}")
    if not [h for h in all_hits if h[0] == "IWRAM"]:
        print("    (no matches)")

    return all_hits


def check_known_addresses(server: MGBAServer) -> None:
    """Read known string buffers and print their contents."""
    print("\n" + "=" * 52)
    print("  Known string buffer addresses (FireRed US (NOT REV 1))")
    print("=" * 52)
    for name, addr in KNOWN_STRING_ADDRS.items():
        data = _do_read(server, addr, 256)
        decoded = decode_bytes(data, stop_at_eos=True)
        preview = decoded[:120].replace("\n", "\\n")
        status = "(empty)" if not preview.strip() else preview
        print(f"  {name}  @ 0x{addr:08X}:  {status}")


# Main


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Main entry point for memory scan mode."""
    print("=" * 52)
    print("  Memory Scanner — Pokemon FireRed")
    print(f"  Server: {host}:{port}")
    print("=" * 52)
    print()
    print("Instructions:")
    print("  1. Load lua/memory_scan_bridge.lua in mGBA")
    print("  2. Make sure the game is running (NOT paused)")
    print("  3. The scanner will connect automatically")
    print()

    with MGBAServer(host=host, port=port) as server:
        try:
            print(f"[*] Listening on {host}:{port}  —  waiting for mGBA ...")
            server.wait_for_connection(timeout=30.0)

            # Read hello
            hello = server.recv_one(timeout=5.0)
            if hello:
                print(f"[+] Hello: {hello}")

            # Ping
            server.send_command("PING")
            pong = server.recv_one(timeout=5.0)
            print(f"[+] Ping response: {pong}")

            check_known_addresses(server)

            # Interactive mode
            print("\n" + "-" * 45)
            print("Interactive mode.  Commands:")
            print("  find <text>         Search for text in EWRAM+IWRAM")
            print("  findh <hex_bytes>   Search for raw hex pattern")
            print("  read <hex_addr> <n> Read & decode N bytes at address")
            print("  quit                Exit")
            print("-" * 45)

            while True:
                try:
                    cmd = input("\n> ").strip()
                except (EOFError, KeyboardInterrupt):
                    break
                if not cmd:
                    continue

                parts = cmd.split(None, 2)
                verb = parts[0].lower()

                if verb in ("quit", "exit", "q"):
                    break

                elif verb == "read" and len(parts) >= 3:
                    addr = int(parts[1], 16)
                    length = int(parts[2])
                    data = _do_read(server, addr, length)
                    decoded = decode_bytes(data, stop_at_eos=True)
                    hex_str = " ".join(f"{b:02X}" for b in data)
                    print(f"  Hex:  {hex_str}")
                    print(f"  Text: {decoded!r}")

                elif verb == "find" and len(parts) >= 2:
                    text = " ".join(parts[1:])
                    try:
                        hits = scan_for_text(server, text)
                        for region, addr in hits:
                            data = _do_read(server, addr, 96)
                            decoded = decode_bytes(data, stop_at_eos=True)
                            print(f"    0x{addr:08X}: {decoded[:120]!r}")
                    except ValueError as exc:
                        print(f"  Error: {exc}")

                elif verb == "findh" and len(parts) >= 2:
                    pat = parts[1].replace(" ", "")
                    print(f"\n[*] Searching for hex pattern: {pat}")
                    hits_ew = _do_find(server, pat, EWRAM_START, EWRAM_END)
                    hits_iw = _do_find(server, pat, IWRAM_START, IWRAM_END)
                    for a in hits_ew:
                        print(f"    EWRAM: 0x{a:08X}")
                    for a in hits_iw:
                        print(f"    IWRAM: 0x{a:08X}")
                    if not hits_ew and not hits_iw:
                        print("    (no matches)")

                else:
                    print("  Unknown command. Try: find, findh, read, quit")

        except (TimeoutError, ConnectionError) as exc:
            print(f"[!] {exc}")
            sys.exit(1)

    print("\n[*] Done.")


if __name__ == "__main__":
    run()
