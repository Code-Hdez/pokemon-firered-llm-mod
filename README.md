# FireRed LLM - Pokemon FireRed Dialog Bridge

## Inspiration & Credits

This project was inspired by **[josh](https://www.youtube.com/@joshycodes)** and his project **[animal-crossing-llm-mod](https://github.com/vuciv/animal-crossing-llm-mod)**.

Special thanks to the **[pret team](https://github.com/pret/pokefirered)** for their incredible work decompiling Pokémon FireRed. Without their reverse engineering efforts, this project would not have been possible.

## Project Structure

```

firered_llm/
├── main.py                       # Top-level entry point
├── requirements.txt
├── .gitignore
├── LICENSE
│
├── lua/                          # mGBA Lua scripts (one per mode)
│   ├── fingerprint_collector.lua # Read-only dialog event collector
│   ├── dialog_injector.lua       # Dialog detection + text injection
│   ├── memory_scan_bridge.lua    # Minimal READ/FIND memory scanner
│   └── lib/                      # Shared Lua library modules
│       ├── commands.lua          # Command definitions
│       ├── config.lua            # Configuration constants
│       ├── dialog.lua            # Dialog detection helpers
│       ├── injector.lua          # Text injection logic
│       ├── ipc.lua               # IPC / socket layer
│       └── utils.lua             # General utilities
│
├── python/                       # Python package root
│   ├── main.py                   # CLI entry point (3-mode menu)
│   ├── config.py                 # Global configuration
│   ├── protocol.py               # IPC message protocol definitions
│   ├── exceptions.py             # Custom exception types
│   ├── pokemon_text/             # Pokemon character encoding
│   │   ├── char_table.py         # DECODE/ENCODE dicts, encode/decode fns
│   │   └── text_formatter.py     # Word-wrap + pagination for dialog boxes
│   ├── classifier/               # Dialog classification engine
│   │   └── dialog_classifier.py  # Two-tier classifier (fingerprint DB + EB8 hints)
│   ├── ipc/                      # IPC server
│   │   └── server.py             # TCP socket server (listens for Lua events)
│   └── apps/                     # Application modules
│       ├── memory_scan_app.py    # Memory scan server + interactive CLI
│       ├── inject_test_app.py    # Text injection test server
│       └── fingerprint_collector_app.py  # Fingerprint collection + per-city storage
│
├── data/                         # All persistent data
│   ├── fingerprints/             # Per-city fingerprint JSON files (generated)
│   ├── info/                     # Documentation & analysis
│   │   ├── technical_analysis.md # Reverse engineering notes
│   │   ├── mGBA_debug_logs_day_1.txt  # Session logs
│   │   ├── oak_sequence.txt      # Professor Oak dialog sequence
│   │   └── PalletTown_Script.txt # Pallet Town script dump
│   └── reference/                # Reference files
│       └── characters.h          # C header with character encoding table
│
└── README.md
```

## Requirements

- **mGBA** 0.10+ with scripting support
- **Python** 3.10+
- No external Python packages needed (stdlib only: `socket`, `json`, `pathlib`)

## Quick Start

### 1. Memory Scanner (explore GBA memory)

```bash
python -m python.main
# Select option 1 - Memory Scan
```

Then in mGBA: **Tools → Scripting → Load Script** → `lua/memory_scan_bridge.lua`

### 2. Text Injection Test (replace NPC dialog)

```bash
python -m python.main
# Select option 2 - Inject Test
```

Then in mGBA: **Tools → Scripting → Load Script** → `lua/dialog_injector.lua`

### 3. Fingerprint Collector (classify every NPC interaction)

```bash
python -m python.main
# Select option 3 - Fingerprint Collector
```

Then in mGBA: **Tools → Scripting → Load Script** → `lua/fingerprint_collector.lua`

## Architecture

### IPC Protocol

- **Transport**: TCP on `127.0.0.1:35600`
- **Direction**: Lua (client) → Python (server)
- **Format**: Line-delimited JSON (`\n` separator)
- **Commands** (Python → Lua): `PING`, `READ`, `FIND`, `INJECT`, `STREAM`, `WATCH`
- **Events** (Lua → Python): `hello`, `pong`, `dialog_open`, `dialog_close`,
  `dialog_page_wait`, `dialog_page_advance`, `map_change`, `read`, `find`, `ack`, `err`

### Memory Addresses (Pokemon FireRed US (NOT REV 1))

| Address        | Size | Description                          |
|----------------|------|--------------------------------------|
| `0x02021D18`   | 256B | Primary text display buffer (EWRAM)  |
| `0x03000EB0`   | 1B   | Script engine state (0/1/2)          |
| `0x03000EB8`   | 4B   | Script command pointer (ROM)         |
| `0x03000EBC`   | 4B   | NPC/event script pointer (ROM)       |
| `0x03005008`   | 4B   | gSaveBlock1Ptr (map detection)       |

### Dialog Detection (AND-gate FSM)

Dialog is detected when **all** conditions hold simultaneously:
1. `engine_state >= 1` (script engine active)
2. Buffer content changed (snapshot of first 32 bytes differs)
3. `0xFF` (EOS) found within first 256 bytes
4. Text length ≥ 2 bytes

### Character Encoding

Pokemon FireRed uses a custom encoding (NOT ASCII/UTF-8). Special bytes:
- `0xFF` - End of String (EOS)
- `0xFE` - Newline
- `0xFA` - Scroll
- `0xFB` - Page break
- `0xFC` - Extended control code prefix
- `0xFD` - Placeholder prefix (StringVar1-4 etc.)

See `python/pokemon_text/char_table.py` for the full encoding table.
