# Pokémon FireRed - Dialog Technical Analysis

**Target:** Pokémon FireRed (NOT REV 1) on mGBA. 
**Architecture:** GBA ARM7TDMI (ARM / Thumb).  
**Goal:** Detect NPC dialog opening with ZERO false positives, inject LLM-generated text.

## A. Evidence Extracted from Source Files

### A.1 - Text Buffer (EWRAM)

| Address        | Region | Purpose                        | Evidence Source                    |
|----------------|--------|--------------------------------|------------------------------------|
| `0x02021D18`   | EWRAM  | Primary text display buffer    | oak_sequence.txt, debugger dumps   |
| `0x02021CC4`   | EWRAM  | gStringVar1                    | pokefirered decomp, memory_scanner |
| `0x02021DC4`   | EWRAM  | gStringVar2                    | pokefirered decomp                 |
| `0x02021EC4`   | EWRAM  | gStringVar3                    | pokefirered decomp                 |
| `0x02021FC4`   | EWRAM  | gStringVar4                    | pokefirered decomp                 |

**Key observation:** All dialog text strings - regardless of NPC - are written starting at `0x02021D18`. This buffer is **reused** for every new dialog; it is NOT cleared when the text box closes (stale data persists).

Evidence from oak_sequence.txt - every labeled text block begins at `0x02021D18`:
```
gOakSpeech_Text_WelcomeToTheWorld::
    "Hello, there!\n"          -> 0x02021D18
    "Glad to meet you!\p"      -> 0x02021D26
    "Welcome to the world …\p" -> 0x02021D38
```

Evidence from debugger dump at breakpoint `0x080694D2` (post-copy):
```
0x02021D18: BB 00 E4 E0 D5 ED D9 D8 00 EB DD E8 DC 00 E8 DC
0x02021D28: D9 00 C8 BF CD AD FB B0 C9 DF D5 ED AB FE C3 E8
0x02021D38: B4 E7 00 E8 DD E1 D9 00 E8 E3 00 DB E3 AB FF 00
```
Decodes to: `A aything kin the·` … terminated by `0xFF` at offset `+0x2F`.

### A.2 - Script Engine State (IWRAM)

| Address        | Size   | Purpose                | Values observed            |
|----------------|--------|------------------------|----------------------------|
| `0x03000EB0`   | 1 byte | Script context state   | `0x00`, `0x01`, `0x02`     |
| `0x03000EB1`   | 1 byte | Script sub-state       | mirrors EB0 in some cases  |
| `0x03000EB8`   | 4 bytes| Script pointer (ROM)   | `0x0806xxxx` etc.          |
| `0x03000EBC`   | 4 bytes| Script data pointer    | varies per NPC             |

**State machine values for `0x03000EB0`:**

| Value | Meaning                                  | When                                     |
|-------|------------------------------------------|-------------------------------------------|
| `0`   | IDLE - player has control                | No script running                         |
| `1`   | ACTIVE - executing script command        | Text printing, movement, any script cmd   |
| `2`   | WAIT_INPUT - waiting for A button press  | Multi-page dialog (after `\p` / 0xFB)    |

**CRITICAL FINDING:** `0x03000EB0` is NOT a "dialog open" flag. It is a **general script engine busy flag** that activates for:
- Text dialogs (`message`, `waitmessage`)
- Movement commands (`applymovement`, `waitmovement`)
- Event triggers, delays, animations
- **Any** command in the scripting engine

Evidence - Oak outdoor cutscene (from day_1_logs.txt):
```
ExclamationMark appears  → 0x03000EB0 = 01  (movement, NOT text)
Oak walks to player      → stays 01          (still movement)
Oak arrives              → 0x03000EB0 = 00   (brief idle)
Text box opens           → 0x03000EB0 = 01   (NOW it's text)
```

### A.3 - Text Copy Routine (ROM)

| PC Address       | Function                         |
|------------------|----------------------------------|
| `0x08008FCE`     | `StringExpandPlaceholders` entry |
| `0x0800908C`     | Copy loop: `ldrb r0,[r5]; strb r0,[r4]; add r5,#1; add r4,#1` |
| `0x080090AC`     | EOS write: `mov r0,#255; strb r0,[r4]` |
| `0x080090B6`     | Return: `bx r1` (to LR)         |
| `0x080694D2`     | Caller return (breakpoint-safe)  |

**Register usage during copy:**
- `r4` = destination pointer (starts at `0x02021D18`, increments per byte)
- `r5` = source pointer (ROM `0x08xxxxxx` or RAM `0x020xxxxx` for expanded strings)
- `r0` = current byte being copied
- `r3` = `0x03000EB0` (script context base address)

**Control code detection inside copy loop** (at `0x08008FD2`):
```asm
sub  r0, #250        ; r0 -= 0xFA
cmp  r0, #5          ; if result <= 5 → byte was 0xFA..0xFF
bhi  copy_normal     ; else: regular printable character
```
Bytes `0xFA`–`0xFF` are intercepted as control codes:
- `0xFA` → PROMPT_SCROLL (scroll 1 line, wait for A)
- `0xFB` → PROMPT_CLEAR (clear textbox, wait for A)
- `0xFC` → EXT_CTRL_CODE (followed by sub-code + params)
- `0xFD` → PLACEHOLDER (followed by placeholder ID, expanded to gStringVar etc.)
- `0xFE` → NEWLINE
- `0xFF` → EOS (end of string) - **written as final byte, always**

### A.4 - Script Interpreter (ROM)

| PC Address       | Function                          |
|------------------|-----------------------------------|
| `0x08069806`     | `ScriptContext_Main` (main loop)  |
| `0x080698D6`     | Command handler dispatch          |
| `0x08069886`     | State writer (`0x03000EB0`)       |
| `0x080698A2`     | Specific write: `mov r0,#0` then store to EB0 |
| `0x080698BA`     | State reader: `ldrb r1,[r2,#0]` where r2=EB0 |

**NPC identification via `r3` at watchpoint hits:**
Each NPC's script entry point appears in `r3` when state transitions from 0→1:

| r3 value       | NPC / Event                               |
|----------------|-------------------------------------------|
| `0x08168CDA`   | Generic overworld NPC (Pallet Town)       |
| `0x08168C20`   | Mom (PalletTown_PlayersHouse_1F)          |
| `0x08165658`   | Another NPC interaction                   |
| `0x0816927F`   | Another NPC interaction                   |

These ROM pointers serve as **unique NPC fingerprints** - they point to each NPC's script data in ROM.

### A.5 - Text Source: ROM vs RAM

The source pointer `r5` holds either:
- **ROM address** (`0x08xxxxxx`) - literal text from ROM, no variable expansion needed
- **RAM address** (`0x020xxxxx`) - text was first expanded to a temp RAM buffer (e.g., replacing `{PLAYER}`, `{RIVAL}` placeholders), then copied to final buffer

Evidence from watchpoint hit:
```
First text:  r5 = 0x0818D50D  (ROM - direct)
Other text:  r1 = 0x020245FC  (RAM - pre-expanded)
```

### A.6 - Character Encoding Summary

Pokemon FireRed uses a **custom character encoding** (NOT ASCII/UTF-8).

Key mappings:
```
Space = 0x00    'A' = 0xBB    'a' = 0xD5    '0' = 0xA1
'!' = 0xAB      '?' = 0xAC    '.' = 0xAD    ',' = 0xB8
'-' = 0xAE      ':' = 0xF0    '/' = 0xBA    '\n'= 0xFE
EOS = 0xFF      SCROLL = 0xFA  CLEAR = 0xFB
```

Full encode/decode tables are implemented in `char_table.py`.


## B. Text Engine Mental Model

### B.1 - Pipeline: From Press-A to Pixels

```
┌─────────────────────────────────────────────────────────────────┐
│  1. PLAYER PRESSES A IN FRONT OF NPC                           │
│     ↓                                                          │
│  2. Overworld engine detects interaction                       │
│     ↓                                                          │
│  3. ScriptContext_Main (0x08069806) activates                  │
│     → writes 0x01 to 0x03000EB0 (state = ACTIVE)              │
│     → stores script ROM pointer at 0x03000EB8                  │
│     ↓                                                          │
│  4. Script command handler (0x080698D6) dispatches `message`   │
│     ↓                                                          │
│  5. StringExpandPlaceholders (0x08008FCE) is called            │
│     r4 = 0x02021D18 (dst buffer)                               │
│     r5 = ROM/RAM source pointer                                │
│     ↓                                                          │
│  6. Copy loop (0x0800908C) copies byte-by-byte                 │
│     - Regular bytes (< 0xFA): strb to buffer, advance          │
│     - Control codes (0xFA-0xFF): dispatch special handling      │
│     - 0xFD: expand placeholder (PLAYER name, etc.)             │
│     - 0xFE: write newline byte to buffer                       │
│     - 0xFA/0xFB: write scroll/clear code to buffer             │
│     - 0xFF: write terminator, RETURN                           │
│     ↓                                                          │
│  7. Return to caller (0x080694D2)                              │
│     → buffer at 0x02021D18 now contains COMPLETE text          │
│     → terminated by 0xFF                                       │
│     ↓                                                          │
│  8. Text printer reads buffer byte-by-byte, renders to screen  │
│     ↓                                                          │
│  9. On 0xFB (page break): state → 0x02 (WAIT_INPUT)           │
│     Player presses A → state → 0x01 (ACTIVE)                  │
│     New page of text printed from continued buffer position    │
│     ↓                                                          │
│ 10. On 0xFF (end): state → 0x00 (IDLE)                        │
│     Text box closes, player regains control                    │
└─────────────────────────────────────────────────────────────────┘
```

### B.2 - State Transition Diagram

```
                    script cmd starts
         ┌──────────── (any cmd) ─────────────┐
         │                                     ▼
     ┌───┴───┐                           ┌─────────┐
     │ IDLE  │                           │ ACTIVE  │
     │  (0)  │                           │  (1)    │
     └───▲───┘                           └────┬────┘
         │                                     │
         │     script cmd ends                 │  0xFB page break
         │◄────────────────────────────────────│  encountered
         │                                     │
         │               ┌─────────────────────▼──┐
         │               │  WAIT_INPUT  (2)       │
         │               │  (waiting for A press) │
         │               └─────────┬──────────────┘
         │                         │
         │                         │ player presses A
         │                         ▼
         │                   ┌─────────┐
         └───────────────────│ ACTIVE  │
            (if last page)   │  (1)    │
                             └─────────┘
```

**Multi-page dialog lifetime** (Mom example from logs):
```
0→1  (script starts, first page built & printed)
1→2  (page 1 done, waiting for A - \p encountered)
2→1  (A pressed, page 2 starts printing)
1→0  (page 2 was last page, dialog closes)
```

### B.3 - Buffer Layout

```
0x02021D18  ┌─ Text data starts here (always)
            │  [printable bytes in Pokemon encoding]
            │  [0xFE = newline within page]
            │  [0xFB = page break → wait for A, clear box]
            │  [0xFA = scroll → wait for A, scroll 1 line]
            │  [0xFC + sub + params = formatting control]
            │  [0xFD + id = placeholder expansion]
            │  ...
            │  [0xFF = END OF STRING]
            ├─ Zero padding / garbage after EOS
            │  ...
0x02021E18  └─ ≈256 bytes max observed (safe range)
```

Observed text sizes: 20–80 bytes typical, max ~256 bytes per dialog string.