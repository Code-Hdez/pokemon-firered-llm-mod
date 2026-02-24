"""
llm_inject_app.py — Minimal LLM-powered dialog injection for Pokemon FireRed.

Listens for dialog_open events from mGBA, sends the original text to
Gemini (or uses a stub), formats the response into Pokemon-encoded bytes,
and injects it back via the INJECT IPC command.

Writer / Formatter separation:
  - Formatter: python.pokemon_text.format_dialog_hex (text → Pokemon hex)
  - Writer:    lua/lib/injector.lua (hex → EWRAM TEXT_BUF bytes)

Lua counterpart: lua/dialog_injector.lua
"""

from __future__ import annotations

import logging
import os

from ..config import DEFAULT_HOST, DEFAULT_PORT
from ..ipc.server import MGBAServer
from ..pokemon_text import decode_bytes, format_dialog_hex, hex_to_bytes

logger = logging.getLogger(__name__)

# Minimal LLM stub / Gemini caller

USE_LLM = True  # Set False to use hardcoded stub for circuit testing

STUB_RESPONSE = "AI TEST 123. This is a test from the LLM pipeline."

SYSTEM_PROMPT = (
    "You are rewriting NPC dialogue for Pokemon FireRed. "
    "Given the original line, produce a short replacement (max 120 chars). "
    "Keep it fun, in-character, one short paragraph. "
    "Output ONLY the replacement text, nothing else. No quotes."
)


def _call_gemini(original_text: str) -> str:
    """Call Gemini API with minimal prompt. Returns replacement text."""
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        logger.warning("No GEMINI_API_KEY / GOOGLE_API_KEY set — using stub")
        return STUB_RESPONSE

    try:
        from google import genai

        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-2.5-flash-lite",
            contents=f"Original NPC dialogue: \"{original_text}\"\n\nRewrite it:",
            config=genai.types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.9,
                max_output_tokens=100,
            ),
        )
        text = response.text.strip()
        if not text:
            logger.warning("Gemini returned empty — using stub")
            return STUB_RESPONSE
        # Clamp length (Pokemon text buffer is 256 bytes max)
        if len(text) > 200:
            text = text[:197] + "..."
        return text

    except Exception as exc:
        logger.error("Gemini call failed: %s — using stub", exc)
        return STUB_RESPONSE


def generate_replacement(original_text: str) -> str:
    """Generate replacement text. Uses LLM if enabled, else stub."""
    if USE_LLM:
        return _call_gemini(original_text)
    return STUB_RESPONSE


# Minimal safe encoder — strips chars that Pokemon can't encode

# Characters the Pokemon encoder supports (from char_table.py ENCODE keys)

_SAFE_CHARS: set[str] | None = None


def _get_safe_chars() -> set[str]:
    global _SAFE_CHARS
    if _SAFE_CHARS is None:
        from ..pokemon_text.char_table import ENCODE
        _SAFE_CHARS = set(ENCODE.keys())
    return _SAFE_CHARS


def sanitize_for_pokemon(text: str) -> str:
    """Strip or replace characters that can't be Pokemon-encoded."""
    safe = _get_safe_chars()
    out = []
    for ch in text:
        if ch in safe:
            out.append(ch)
        elif ch in ("\n", "\r"):
            out.append(" ")
        elif ch == "\u2019" or ch == "\u2018":  # smart quotes
            out.append("'")
        elif ch == "\u201c" or ch == "\u201d":
            out.append('"')
        elif ch == "\u2014" or ch == "\u2013":  # em/en dash
            out.append("-")
        elif ch == "\u2026":  # ellipsis
            out.append("...")
        else:
            # Skip unencodable chars silently
            pass
    return "".join(out)


# App entry point

def run(
    host: str = DEFAULT_HOST,
    port: int = DEFAULT_PORT,
    use_llm: bool = True,
) -> None:
    """Main entry point for LLM inject mode."""

    global USE_LLM
    USE_LLM = use_llm

    mode_label = "Gemini LLM" if use_llm else "Stub (hardcoded)"

    print("=" * 56)
    print("  LLM Inject — Pokemon FireRed Dialog Replacement")
    print(f"  Server: {host}:{port}")
    print(f"  Mode:   {mode_label}")
    if use_llm:
        try:
            from dotenv import load_dotenv
            load_dotenv()
        except ImportError:
            pass
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        print(f"  API Key: {'SET' if key else 'MISSING!'}")
    print("=" * 56)
    print()
    print("Instructions:")
    print("  1. Load lua/dialog_injector.lua in mGBA")
    print("  2. Talk to any NPC — text will be replaced by LLM output")
    print("  3. Watch this console for logs")
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

            # Decode original text
            try:
                original = decode_bytes(hex_to_bytes(text_hex))
            except Exception:
                original = "(decode error)"

            print(f"\n[DIALOG_OPEN]  NPC={npc}  len={text_len}")
            print(f"  Original: {original!r}")

            # Generate replacement via LLM or stub
            print(f"  Generating replacement...")
            replacement = generate_replacement(original)
            print(f"  LLM says:  {replacement!r}")

            # Sanitize for Pokemon encoding
            safe_text = sanitize_for_pokemon(replacement)
            if safe_text != replacement:
                print(f"  Sanitized: {safe_text!r}")

            if not safe_text.strip():
                print("  [SKIP] Empty after sanitization")
                return

            # Format with line wrapping + pagination
            try:
                inject_hex = format_dialog_hex(safe_text, chars_per_line=18)
            except ValueError as exc:
                print(f"  [ERR] Cannot encode: {exc}")
                # Fallback to stub
                inject_hex = format_dialog_hex(
                    sanitize_for_pokemon(STUB_RESPONSE), chars_per_line=18
                )
                print(f"  [FALLBACK] Using stub message")

            byte_count = len(inject_hex) // 2
            print(f"  Injecting ({byte_count} bytes): {inject_hex[:80]}...")
            server.send_command(f"INJECT {inject_hex}")

        elif msg_type == "intro_text":
            text_hex = msg.get("textHex", "")
            try:
                original = decode_bytes(hex_to_bytes(text_hex))
            except Exception:
                original = "(decode error)"

            print(f"\n[INTRO_TEXT]")
            print(f"  Original: {original!r}")

            replacement = generate_replacement(original)
            safe_text = sanitize_for_pokemon(replacement)
            if not safe_text.strip():
                return

            try:
                inject_hex = format_dialog_hex(safe_text, chars_per_line=18)
            except ValueError:
                inject_hex = format_dialog_hex(
                    sanitize_for_pokemon(STUB_RESPONSE), chars_per_line=18
                )

            print(f"  Injecting: {safe_text!r}")
            server.send_command(f"INJECT {inject_hex}")

        elif msg_type == "dialog_close":
            print("[DIALOG_CLOSE]")

        elif msg_type == "dialog_page_wait":
            print("[PAGE_WAIT]")

        elif msg_type == "ack":
            detail = msg.get("msg", "")
            extra = (
                f"  ({msg.get('len', '?')} bytes)" if "injected" in detail else ""
            )
            print(f"[ACK]  {detail}{extra}")

        elif msg_type == "err":
            print(f"[ERR]  {msg.get('msg', '?')}")

        elif msg_type == "frame":
            pass

        else:
            print(f"[???]  {msg}")

    server = MGBAServer(host=host, port=port)
    server.run_loop(on_message=lambda msg: on_message(msg, server))
