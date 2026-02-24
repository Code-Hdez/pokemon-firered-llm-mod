"""
main.py — Pokemon FireRed mGBA Tools

CLI menu logic.  Called from the root ``main.py`` entry point.

Options:
    1) Memory Scan    — find text/bytes in GBA memory
    2) Inject Test    — replace NPC dialog text in-game
    3) FP Collector   — collect & classify dialog fingerprints
    0) Exit
"""

from __future__ import annotations

import logging
import sys

from .config import DEFAULT_HOST, DEFAULT_PORT


def _configure_logging() -> None:
    from .config import LOG_LEVEL

    logging.basicConfig(
        level=getattr(logging, LOG_LEVEL, logging.INFO),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_banner() -> None:
    print()
    print("=" * 56)
    print("  Pokemon FireRed — mGBA Tools  (v4.0)")
    print("=" * 56)
    print()
    print("  Select a mode:")
    print()
    print("    [1]  Memory Scan")
    print("         Scan GBA RAM for Pokemon-encoded text.")
    print("         Lua: lua/memory_scan_bridge.lua")
    print()
    print("    [2]  Inject Test")
    print("         Replace NPC dialog text with a test message.")
    print("         Lua: lua/dialog_injector.lua")
    print()
    print("    [3]  Fingerprint Collector")
    print("         Collect & classify dialog fingerprints by zone.")
    print("         Lua: lua/fingerprint_collector.lua")
    print()
    print("    [4]  LLM Inject")
    print("         Replace NPC dialog with Gemini-generated text.")
    print("         Lua: lua/dialog_injector.lua")
    print()
    print("    [0]  Exit")
    print()
    print("-" * 56)


def get_connection_params() -> tuple[str, int]:
    """Ask for host/port or use defaults."""
    host = input(f"  Host [{DEFAULT_HOST}]: ").strip() or DEFAULT_HOST
    port_str = input(f"  Port [{DEFAULT_PORT}]: ").strip() or str(DEFAULT_PORT)
    try:
        port = int(port_str)
    except ValueError:
        print(f"  Invalid port '{port_str}', using {DEFAULT_PORT}")
        port = DEFAULT_PORT
    return host, port


def run_memory_scan() -> None:
    print("\n--- Memory Scan Mode ---\n")
    host, port = get_connection_params()
    from .apps.memory_scan_app import run

    run(host=host, port=port)


def run_inject_test() -> None:
    print("\n--- Inject Test Mode ---\n")
    host, port = get_connection_params()
    msg = input("  Test message [default]: ").strip()
    if not msg:
        msg = "Hola Carlos, bienvenido a esta nueva aventura."
    from .apps.inject_test_app import run

    run(host=host, port=port, test_message=msg)


def run_fingerprint_collector() -> None:
    print("\n--- Fingerprint Collector Mode ---\n")
    host, port = get_connection_params()
    from .apps.fingerprint_collector_app import run

    run(host=host, port=port)


def run_llm_inject() -> None:
    print("\n--- LLM Inject Mode ---\n")
    host, port = get_connection_params()
    use_llm_input = input("  Use Gemini LLM? [Y/n]: ").strip().lower()
    use_llm = use_llm_input != "n"
    from .apps.llm_inject_app import run

    run(host=host, port=port, use_llm=use_llm)


def main() -> None:
    _configure_logging()

    while True:
        print_banner()
        try:
            choice = input("  >> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye.")
            sys.exit(0)

        if choice == "0":
            print("\nBye.")
            sys.exit(0)
        elif choice == "1":
            run_memory_scan()
        elif choice == "2":
            run_inject_test()
        elif choice == "3":
            run_fingerprint_collector()
        elif choice == "4":
            run_llm_inject()
        else:
            print(f"\n  Invalid option: {choice!r}. Enter 0\u20134.\n")


if __name__ == "__main__":
    main()
