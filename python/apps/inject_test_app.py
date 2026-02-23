"""
inject_test_app.py — Test harness for mGBA dialog text injection.

Listens on localhost TCP, receives JSON events from dialog_injector.lua,
and on ``dialog_open`` responds with an INJECT command carrying a
Pokemon-encoded replacement message.

Uses the shared :class:`MGBAServer` for TCP communication.

Lua counterpart: ``lua/dialog_injector.lua``
"""

from __future__ import annotations

import logging

from ..config import DEFAULT_HOST, DEFAULT_PORT
from ..ipc.server import MGBAServer
from ..pokemon_text import decode_bytes, format_dialog_hex, hex_to_bytes

logger = logging.getLogger(__name__)

DEFAULT_TEST_MESSAGE = "Hola Carlos, bienvenido a esta nueva aventura."


def run(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    test_message: str = DEFAULT_TEST_MESSAGE,
) -> None:
    """Main entry point for inject test mode."""

    print("=" * 56)
    print("  Inject Test — Pokemon FireRed Dialog Injection")
    print(f"  Server: {host}:{port}")
    print(f"  Test message: {test_message!r}")
    print("=" * 56)
    print()
    print("Instructions:")
    print("  1. Load lua/dialog_injector.lua in mGBA")
    print("     (MANUAL_INJECT_ENABLED = false)")
    print("  2. Talk to any NPC — text will be replaced")
    print()
    print("Waiting for mGBA to connect...\n")

    def on_message(msg: dict, server: MGBAServer) -> None:
        msg_type = msg.get("type", "")

        if msg_type == "hello":
            title = msg.get("title", "?")
            code = msg.get("code", "?")
            proto = msg.get("proto", 1)
            mode = msg.get("mode", "?")
            print(f"[HELLO] Game: {title}  Code: {code}  Proto: v{proto}  Mode: {mode}")
            server.send_command("PING")

        elif msg_type == "pong":
            print("[PONG]  Link verified OK")

        elif msg_type == "dialog_open":
            npc = msg.get("npc", msg.get("ptr_EBC", "?"))
            text_hex = msg.get("textHex", "")
            text_len = msg.get("len", 0)

            try:
                original = decode_bytes(hex_to_bytes(text_hex))
            except Exception:
                original = "(decode error)"

            print(f"\n[DIALOG_OPEN]  NPC={npc}  len={text_len}")
            print(f"  Original: {original!r}")

            try:
                inject_hex = format_dialog_hex(
                    test_message, chars_per_line=18
                )
            except ValueError as exc:
                print(f"  [ERR] Cannot encode: {exc}")
                return

            print(f"  Injecting: {test_message!r}")
            print(f"  Hex ({len(inject_hex) // 2} bytes): {inject_hex[:64]}...")
            server.send_command(f"INJECT {inject_hex}")

        elif msg_type == "dialog_page_wait":
            print("[PAGE_WAIT]  Waiting for A press...")

        elif msg_type == "dialog_page_advance":
            print("[PAGE_ADVANCE]")

        elif msg_type == "dialog_close":
            print("[DIALOG_CLOSE]")

        elif msg_type == "ack":
            detail = msg.get("msg", "")
            extra = (
                f"  ({msg.get('len', '?')} bytes)" if "injected" in detail else ""
            )
            print(f"[ACK]  {detail}{extra}")

        elif msg_type == "err":
            print(f"[ERR]  {msg.get('msg', '?')}")

        elif msg_type == "frame":
            pass  # suppress streaming frames

        else:
            print(f"[???]  {msg}")

    server = MGBAServer(host=host, port=port)
    # Wrap the handler to pass the server reference
    server.run_loop(on_message=lambda msg: on_message(msg, server))


if __name__ == "__main__":
    run()
