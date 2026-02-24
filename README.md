# FireRed LLM - Pokemon FireRed Dialog Bridge

A bridge between **mGBA** and a **Large Language Model** that gives every NPC in Pokémon FireRed a unique personality. When you talk to an NPC, the original dialog is intercepted, sent to an LLM (Gemini), and replaced in real-time with a fresh, character-consistent response - so no two conversations are ever the same.

### Current state

In this version the LLM takes the original NPC message and **paraphrases** it into a new line of dialog, keeping the meaning but varying the wording each time you talk to that character.

### Roadmap

The next milestone is to tag every player interaction with a **fingerprint** so the system can distinguish between NPCs and objects (signs, bookshelves, item balls, etc.). Once that classification is in place, only NPCs will receive an LLM-generated personality - objects will keep their original text unchanged.

## Getting Started

### Prerequisites

| Tool | Version |
|------|---------|
| **mGBA** | 0.10+ (with scripting support) |
| **Python** | 3.10+ |
| **Pokémon FireRed ROM** | US version (NOT Rev 1) |

### Installation

```bash
# 1. Clone the repo
git clone https://github.com/<your-user>/firered_llm.git
cd firered_llm

# 2. Create a virtual environment and activate it
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set up your environment variables
cp .env.example .env
# Open .env and paste your Gemini API key
```

### How to Use

> **Follow these steps in order every time you play.**

1. **Open mGBA** and load your Pokémon FireRed ROM.
2. On the **title screen** (before pressing Start), open the scripting console:
   **Tools → Scripting**.
3. In the Scripting window click **File → Load Script…** and pick the Lua script for the mode you want:
   | Mode | Lua script |
   |------|------------|
   | Memory Scan | `lua/memory_scan_bridge.lua` |
   | Inject Test | `lua/dialog_injector.lua` |
   | Fingerprint Collector | `lua/fingerprint_collector.lua` |
   | **LLM Inject** | `lua/dialog_injector.lua` |
4. **Run the Python side** in a terminal (with the virtual environment activated):
   ```bash
   python main.py
   ```
5. Select the matching option from the menu (e.g. `4` for LLM Inject).
6. Press **Start** on the title screen and play normally - every NPC conversation will now be rewritten by the LLM.

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
- **Gemini API key** - needed for LLM Inject mode (option 4). See [`.env.example`](.env.example) for setup.
- Modes 1-3 use the standard library only; mode 4 additionally requires `google-genai` and `python-dotenv` (listed in `requirements.txt`).

## Modes

### 1. Memory Scanner (explore GBA memory)

```bash
python main.py
# Select option 1 - Memory Scan
```
Lua script: `lua/memory_scan_bridge.lua`

### 2. Text Injection Test (replace NPC dialog)

```bash
python main.py
# Select option 2 - Inject Test
```
Lua script: `lua/dialog_injector.lua`

### 3. Fingerprint Collector (classify every NPC interaction)

```bash
python main.py
# Select option 3 - Fingerprint Collector
```
Lua script: `lua/fingerprint_collector.lua`

### 4. LLM Inject (Gemini-powered dialog rewrite)

```bash
python main.py
# Select option 4 - LLM Inject
```
Lua script: `lua/dialog_injector.lua`

> Requires a valid `GEMINI_API_KEY` in your `.env` file.

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
