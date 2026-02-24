"""
inject_test_app.py — Test harness for mGBA dialog text injection.

Listens on localhost TCP, receives JSON events from dialog_injector.lua,
and on ``dialog_open`` responds with an INJECT command carrying a
Pokemon-encoded replacement message.

Also handles ``intro_text`` events (Oak intro / cutscenes) with a
sequence of replacement messages that map 1:1 to the original Oak
speech dialog blocks.

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

# Oak intro replacement messages.  Each entry replaces one text block
# in the Oak intro sequence (in order of appearance).  Edit these to
# customise what Oak says.  When the LLM integration is ready, this
# list will be replaced by live generation.
#
# Original sequence labels (from oak_sequence.txt):
#   0: gOakSpeech_Text_WelcomeToTheWorld
#   1: gOakSpeech_Text_ThisWorld
#   2: gOakSpeech_Text_IsInhabitedFarAndWide
#   3: gOakSpeech_Text_IStudyPokemon
#   4: gOakSpeech_Text_TellMeALittleAboutYourself
#   5: gOakSpeech_Text_YourNameWhatIsIt
#   6: gOakSpeech_Text_SoYourNameIsPlayer
#   7: gOakSpeech_Text_WhatWasHisName
#   8: gOakSpeech_Text_YourRivalsNameWhatWasIt
#   9: gOakSpeech_Text_ConfirmRivalName
#   10: gOakSpeech_Text_RememberRivalsName
#   11: gOakSpeech_Text_LetsGo
OAK_INTRO_REPLACEMENTS: list[str] = [
    "INTRO MSG 0\\nWelcomeToTheWorld",
    "INTRO MSG 1\\nThisWorld",
    "INTRO MSG 2\\nIsInhabitedFarAndWide",
    "INTRO MSG 3\\nIStudyPokemon",
    "INTRO MSG 4\\nTellMeAboutYourself",
    "INTRO MSG 5\\nYourNameWhatIsIt",
    "INTRO MSG 6\\nSoYourNameIsPlayer",
    "INTRO MSG 7\\nWhatWasHisName",
    "INTRO MSG 8\\nYourRivalsName",
    "INTRO MSG 9\\nConfirmRivalName",
    "INTRO MSG 10\\nRememberRivalsName",
    "INTRO MSG 11\\nLetsGo",
]


def run(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    test_message: str = DEFAULT_TEST_MESSAGE,
    intro_messages: list[str] | None = None,
) -> None:
    """Main entry point for inject test mode."""

    oak_messages = intro_messages or OAK_INTRO_REPLACEMENTS
    intro_idx = 0  # tracks position in the Oak intro sequence

    print("=" * 56)
    print("  Inject Test — Pokemon FireRed Dialog Injection")
    print(f"  Server: {host}:{port}")
    print(f"  NPC test message: {test_message!r}")
    print(f"  Intro messages:   {len(oak_messages)} prepared")
    print("=" * 56)
    print()
    print("Instructions:")
    print("  1. Load lua/dialog_injector.lua in mGBA")
    print("     (MANUAL_INJECT_ENABLED = false)")
    print("  2. Talk to any NPC — text will be replaced")
    print("  3. Start a New Game — Oak intro will be replaced")
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

        elif msg_type == "intro_text":
            nonlocal intro_idx
            text_hex = msg.get("textHex", "")
            text_len = msg.get("len", 0)
            frame = msg.get("frame", 0)

            try:
                original = decode_bytes(hex_to_bytes(text_hex))
            except Exception:
                original = "(decode error)"

            print(f"\n[INTRO_TEXT #{intro_idx}]  len={text_len}  frame={frame}")
            print(f"  Original: {original!r}")

            # Pick the next replacement from the sequence
            if intro_idx < len(oak_messages):
                replacement = oak_messages[intro_idx]
            else:
                replacement = test_message  # fallback beyond sequence

            intro_idx += 1

            try:
                inject_hex = format_dialog_hex(
                    replacement, chars_per_line=18
                )
            except ValueError as exc:
                print(f"  [ERR] Cannot encode: {exc}")
                return

            print(f"  Injecting [{intro_idx - 1}]: {replacement!r}")
            print(f"  Hex ({len(inject_hex) // 2} bytes): {inject_hex[:64]}...")
            server.send_command(f"INJECT {inject_hex}")

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
