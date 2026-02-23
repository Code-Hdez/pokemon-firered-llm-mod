"""
fingerprint_collector_app.py — Fingerprint collector for Pokemon FireRed.

Receives JSON events from ``fingerprint_collector.lua``, classifies
dialog interactions interactively, detects duplicates, and stores
per-city/zone fingerprint databases.

Uses the shared :class:`MGBAServer` event loop for TCP communication.

Refactored: all mutable session state is encapsulated in
``CollectorSession`` instead of module-level globals — making
the app testable, reentrant, and easier to reason about.

Lua counterpart: ``lua/fingerprint_collector.lua``
"""

from __future__ import annotations

import json
import re
import sys
from datetime import datetime
from pathlib import Path

from ..config import DEFAULT_HOST, DEFAULT_PORT
from ..ipc.server import MGBAServer
from ..pokemon_text import decode_bytes, hex_to_bytes

# Config defaults

# Data directory (relative to project root)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
FP_DIR = PROJECT_ROOT / "data" / "fingerprints"
ALIASES_FILE = FP_DIR / "map_aliases.json"

# ptr_EB8 handler hints (47-sample calibration)
EB8_HINTS: dict[str, tuple[str, str]] = {
    "0x081A4E51": ("BG_EVENT",    "NON-NPC: sign/object/env       (0/13 NPC)"),
    "0x081A4E5A": ("OBJ_EVENT",   "MIXED: NPC or object/sign     (13/20 NPC)"),
    "0x081A4E47": ("SCRIPT_CTX",  "Mostly NPC                     (6/7  NPC)"),
    "0x081A4E62": ("SPECIAL_EVT", "Mixed: starter/naming/misc      (1/5  NPC)"),
    "0x081A658C": ("NPC_SPECIAL", "NPC: special handler            (1/1  NPC)"),
    "0x081A6817": ("ITEM_PICKUP", "NON-NPC: found item on ground   (0/1  NPC)"),
}


# Utilities


def slugify(name: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", name.lower().strip())
    return s.strip("_") or "unknown"


def decode_preview(hex_str: str) -> str:
    if not hex_str:
        return ""
    try:
        return decode_bytes(hex_to_bytes(hex_str))[:80]
    except Exception:
        return "(decode error)"


# Session state (encapsulated)


class CollectorSession:
    """Encapsulates all mutable state for one collection session."""

    __slots__ = (
        "map_aliases",
        "current_map_key",
        "current_city",
        "city_db",
        "stats",
        "_stop_requested",
    )

    def __init__(self) -> None:
        self.map_aliases: dict[str, str] = {}
        self.current_map_key: str = ""
        self.current_city: str = ""
        self.city_db: dict[str, dict] = {}
        self.stats: dict[str, int] = {
            "opens": 0, "dups": 0, "new": 0, "ignored": 0,
        }
        self._stop_requested: bool = False

    # Alias persistence

    def load_aliases(self) -> None:
        if ALIASES_FILE.exists():
            with open(ALIASES_FILE, encoding="utf-8") as f:
                self.map_aliases = json.load(f)

    def save_aliases(self) -> None:
        FP_DIR.mkdir(parents=True, exist_ok=True)
        with open(ALIASES_FILE, "w", encoding="utf-8") as f:
            json.dump(self.map_aliases, f, indent=2, ensure_ascii=False)

    # City DB persistence

    @staticmethod
    def _fp_path(city: str) -> Path:
        return FP_DIR / slugify(city) / "fingerprints.json"

    def load_city(self, city: str) -> None:
        p = self._fp_path(city)
        if p.exists():
            with open(p, encoding="utf-8") as f:
                self.city_db = json.load(f)
        else:
            self.city_db = {}

    def save_city(self, city: str) -> None:
        if not city:
            return
        p = self._fp_path(city)
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self.city_db, f, indent=2, ensure_ascii=False)

    # Map change handler

    def on_map_change(self, msg: dict) -> None:
        mg = msg.get("map_group", -1)
        mn = msg.get("map_num", -1)
        valid = msg.get("map_valid", False)
        key = f"{mg}_{mn}" if valid else "unknown"

        if key == self.current_map_key:
            return

        if self.current_city and self.city_db:
            self.save_city(self.current_city)

        self.current_map_key = key

        if key in self.map_aliases:
            self.current_city = self.map_aliases[key]
            self.load_city(self.current_city)
            print(f"\n  [MAP] {self.current_city}  (key={key}, {len(self.city_db)} fps loaded)")
        else:
            print(f"\n{'─' * 55}")
            if valid:
                print(f"  NEW MAP: group={mg}  num={mn}  key={key}")
            else:
                print("  MAP DETECTION FAILED (map_valid=false)")
                print("  Fallback: manual naming required")
            print(f"{'─' * 55}")

            name = ""
            while True:
                try:
                    name = input("  Zone name (e.g. 'Pallet Town'): ").strip()
                except EOFError:
                    name = f"map_{key}"
                if name:
                    break
                print("  (enter a name, or Ctrl+C to quit)")

            self.current_city = name
            self.map_aliases[key] = name
            self.save_aliases()
            self.load_city(self.current_city)
            print(f"  >> Saved: {key} = {self.current_city}  ({len(self.city_db)} fps)")

    # Dialog open handler

    def on_dialog_open(self, msg: dict) -> None:
        self.stats["opens"] += 1

        ebc = msg.get("ptr_EBC", "?")
        eb8 = msg.get("ptr_EB8", "?")
        ebc_ok = msg.get("ebc_valid", False)
        estate = msg.get("engine_state", 0)
        hex_str = msg.get("textHex", "")
        tlen = msg.get("text_len", 0)
        frame = msg.get("frame", 0)
        text = decode_preview(hex_str)

        if not ebc_ok:
            print(f"  [SKIP] EBC={ebc} not a ROM pointer — ignoring")
            return

        if not self.current_city:
            self.on_map_change(msg)
        city = self.current_city or "unknown"

        # Duplicate check
        if ebc in self.city_db:
            entry = self.city_db[ebc]
            entry["seen_count"] = entry.get("seen_count", 1) + 1
            entry["last_seen"] = datetime.now().isoformat()
            self.save_city(city)
            self.stats["dups"] += 1
            kind = entry.get("kind", "?")
            label = entry.get("label", "?")
            count = entry["seen_count"]
            print(f"  [DUP] {ebc}  {kind:6s} | {label}  (x{count})")
            return

        # New fingerprint — interactive classification
        h_name, h_hint = EB8_HINTS.get(eb8, ("UNKNOWN", "unknown handler — new!"))

        print(f"\n{'=' * 55}")
        print(f"  NEW FINGERPRINT — {city}")
        print(f"{'=' * 55}")
        print(f"  ptr_EBC:  {ebc}")
        print(f"  ptr_EB8:  {eb8}  =  {h_name}")
        print(f"  hint:     {h_hint}")
        print(f"  state:    {estate}     len: {tlen}")
        if text:
            print(f"  text:     {text!r}")
        else:
            print(f"  hex:      {hex_str[:64]}{'...' if len(hex_str) > 64 else ''}")
        print(f"{'─' * 55}")
        print("  [N]PC   [S]IGN   [O]BJECT   [G]IFT   [I]gnore   [Q]uit")
        print(f"{'─' * 55}")

        kind = None
        while True:
            try:
                c = input("  category >> ").strip().upper()
            except EOFError:
                c = "I"

            if c in ("Q", "QUIT"):
                self._stop_requested = True
                self.shutdown()
                return

            kind_map = {
                "N": "NPC", "NPC": "NPC",
                "S": "SIGN", "SIGN": "SIGN",
                "O": "OBJECT", "OBJ": "OBJECT", "OBJECT": "OBJECT",
                "G": "GIFT", "GIFT": "GIFT",
            }

            if c in ("I", "IGNORE", ""):
                kind = None
                break
            if c in kind_map:
                kind = kind_map[c]
                break
            print("  ? N / S / O / G / I / Q")

        if kind is None:
            self.stats["ignored"] += 1
            print("  >> skipped")
            return

        try:
            label = input("  label >> ").strip()
        except EOFError:
            label = ""
        if not label:
            label = text[:40] if text else f"fp_{ebc[-4:]}"

        now = datetime.now().isoformat()
        self.city_db[ebc] = {
            "kind": kind,
            "label": label,
            "ptr_EB8_observed": eb8,
            "handler": h_name,
            "engine_state": estate,
            "text_hex": hex_str[:256],
            "text_len": tlen,
            "preview": (text or "")[:60],
            "first_seen": now,
            "last_seen": now,
            "seen_count": 1,
            "frame": frame,
            "map_key": self.current_map_key,
        }
        self.save_city(city)
        self.stats["new"] += 1
        print(f"  >> Saved: {ebc} = {kind} ({label})")
        print(f"  >> {city}: {len(self.city_db)} total fingerprints")

    # Message dispatcher

    def handle_msg(self, msg: dict, server: MGBAServer) -> None:
        t = msg.get("type", "")

        if t == "hello":
            title = msg.get("title", "?")
            code = msg.get("code", "?")
            proto = msg.get("proto", 1)
            mode = msg.get("mode", "?")
            print(f"  [HELLO] {title} ({code})  proto=v{proto}  mode={mode}")
            server.send_command("PING")

        elif t == "pong":
            print("  [PONG]  Link OK")

        elif t == "map_change":
            self.on_map_change(msg)

        elif t == "dialog_open":
            self.on_dialog_open(msg)

        elif t in ("dialog_close", "page_wait", "page_advance"):
            pass  # silent

        elif t == "map_info":
            mg = msg.get("map_group", -1)
            mn = msg.get("map_num", -1)
            v = msg.get("map_valid", False)
            print(f"  [MAP_INFO] group={mg} num={mn} valid={v}")

        else:
            print(f"  [???] {msg}")

    # Shutdown

    def shutdown(self) -> None:
        if self.current_city and self.city_db:
            self.save_city(self.current_city)
        self.save_aliases()
        print(f"\n  Final stats: {self.stats}")
        print("  Bye.")


# Main


def run(host: str = DEFAULT_HOST, port: int = DEFAULT_PORT) -> None:
    """Main entry point for fingerprint collector mode."""
    session = CollectorSession()
    session.load_aliases()

    server = MGBAServer(host=host, port=port)

    print("=" * 55)
    print("  Fingerprint Collector — Pokemon FireRed")
    print(f"  Server: {host}:{port}")
    print(f"  Data dir: {FP_DIR.resolve()}")
    print(f"  Known maps: {len(session.map_aliases)}")
    print("=" * 55)
    print()
    print("Instructions:")
    print("  1. Load lua/fingerprint_collector.lua in mGBA")
    print("  2. Walk around and interact with NPCs, signs, objects")
    print("  3. Label each new interaction when prompted")
    print("  4. Ctrl+C to save and exit")
    print()
    print("Waiting for mGBA...\n")

    def on_message(msg: dict) -> None:
        session.handle_msg(msg, server)

    def on_disconnect() -> None:
        if session.current_city and session.city_db:
            session.save_city(session.current_city)
        print(f"\n  Session stats: {session.stats}")
        print("  Waiting for reconnection...\n")

    try:
        server.run_loop(
            on_message=on_message,
            on_disconnect=on_disconnect,
        )
    except KeyboardInterrupt:
        pass
    finally:
        session.shutdown()


if __name__ == "__main__":
    run()
