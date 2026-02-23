"""
char_table.py
Pokemon GBA character encoding / decoding utilities.
Derived from characters.h (pokefirered decompilation).

Pokemon GBA games do NOT use ASCII/UTF-8.  They use a custom character
encoding where e.g. 'A' = 0xBB, 'a' = 0xD5, '0' = 0xA1, etc.

This file is the SINGLE SOURCE OF TRUTH for all Pokemon text encoding
in this project.  All other modules import from here.
"""

#  Byte value -> display character   (decode: GBA memory → text)

DECODE: dict[int, str] = {
    0x00: " ",
    # accented uppercase
    0x01: "À", 0x02: "Á", 0x03: "Â", 0x04: "Ç",
    0x05: "È", 0x06: "É", 0x07: "Ê", 0x08: "Ë",
    0x09: "Ì", 0x0B: "Î", 0x0C: "Ï",
    0x0D: "Ò", 0x0E: "Ó", 0x0F: "Ô",
    0x10: "Œ", 0x11: "Ù", 0x12: "Ú", 0x13: "Û",
    0x14: "Ñ", 0x15: "ß",
    # accented lowercase
    0x16: "à", 0x17: "á", 0x19: "ç",
    0x1A: "è", 0x1B: "é", 0x1C: "ê", 0x1D: "ë",
    0x1E: "ì", 0x20: "î", 0x21: "ï",
    0x22: "ò", 0x23: "ó", 0x24: "ô",
    0x25: "œ", 0x26: "ù", 0x27: "ú", 0x28: "û",
    0x29: "ñ",
    # misc symbols
    0x2A: "º", 0x2B: "ª",
    0x2D: "&", 0x2E: "+",
    0x34: "Lv", 0x35: "=", 0x36: ";",
    # special positions
    0x51: "¿", 0x52: "¡",
    0x53: "PK", 0x54: "MN",
    0x5A: "Í",
    0x5B: "%", 0x5C: "(", 0x5D: ")",
    0x68: "â",
    0x6F: "í",
    # digits
    0xA1: "0", 0xA2: "1", 0xA3: "2", 0xA4: "3", 0xA5: "4",
    0xA6: "5", 0xA7: "6", 0xA8: "7", 0xA9: "8", 0xAA: "9",
    # punctuation
    0xAB: "!", 0xAC: "?", 0xAD: ".", 0xAE: "-",
    0xAF: "·",  # bullet
    0xB0: "…",  # ellipsis
    0xB1: "\u201C",  # "
    0xB2: "\u201D",  # "
    0xB3: "\u2018",  # '
    0xB4: "\u2019",  # '
    0xB5: "♂", 0xB6: "♀",
    0xB7: "¤",  # currency
    0xB8: ",",
    0xB9: "×",  # multiplication sign
    0xBA: "/",
    # uppercase A-Z  (0xBB .. 0xD4)
    **{0xBB + i: chr(ord("A") + i) for i in range(26)},
    # lowercase a-z  (0xD5 .. 0xEE)
    **{0xD5 + i: chr(ord("a") + i) for i in range(26)},
    # more symbols
    0xEF: "▶",
    0xF0: ":",
    0xF1: "Ä", 0xF2: "Ö", 0xF3: "Ü",
    0xF4: "ä", 0xF5: "ö", 0xF6: "ü",
    # control / special
    0xFA: "⏎",   # PROMPT_SCROLL  (wait + scroll)
    0xFB: "⏏",   # PROMPT_CLEAR   (wait + clear)
    0xFE: "\n",   # NEWLINE
    0xFF: "",     # EOS (end of string) — no visible char
}

#  Display character -> byte value   (encode: text → GBA bytes)

# Build reverse mapping (first match wins for duplicates)
ENCODE: dict[str, int] = {}
for _byte, _char in sorted(DECODE.items()):
    if _char and _char not in ENCODE:
        ENCODE[_char] = _byte
# Add common fallback aliases
ENCODE.setdefault("'", 0xB4)  # straight quote → right single
ENCODE.setdefault('"', 0xB1)  # straight double quote → left double


#  Public helpers

def encode_text(text: str) -> bytes:
    """Convert a regular string into Pokemon GBA encoded bytes."""
    out: list[int] = []
    for ch in text:
        if ch in ENCODE:
            out.append(ENCODE[ch])
        else:
            raise ValueError(f"Cannot encode character {ch!r} (U+{ord(ch):04X})")
    return bytes(out)


def decode_bytes(data: bytes | list[int], *, stop_at_eos: bool = True) -> str:
    """
    Convert Pokemon GBA encoded bytes into a readable string.
    Stops at EOS (0xFF) by default.
    Skips EXT_CTRL_CODE_BEGIN (0xFC) + 1-2 parameter bytes.
    Skips PLACEHOLDER_BEGIN (0xFD) + 1 parameter byte.
    """
    result: list[str] = []
    i = 0
    raw = data if isinstance(data, (bytes, bytearray)) else bytes(data)
    while i < len(raw):
        b = raw[i]
        if b == 0xFF and stop_at_eos:
            break
        if b == 0xFC:
            # Extended control code: skip the sub-code byte
            # Some sub-codes have an additional parameter byte
            i += 1  # skip 0xFC
            if i < len(raw):
                sub = raw[i]
                i += 1  # skip sub-code
                # Sub-codes that take an extra parameter byte:
                if sub in (0x01, 0x02, 0x03, 0x05, 0x06, 0x08,
                           0x0D, 0x0E, 0x0F, 0x10, 0x11, 0x13, 0x14):
                    i += 1  # skip parameter
                elif sub == 0x04:
                    i += 3  # color + highlight + shadow
            continue
        if b == 0xFD:
            # Placeholder: skip placeholder id byte
            i += 2
            result.append("{…}")  # placeholder marker
            continue
        ch = DECODE.get(b)
        if ch is not None:
            result.append(ch)
        else:
            result.append(f"[{b:02X}]")
        i += 1
    return "".join(result)


def hex_to_bytes(hex_str: str) -> bytes:
    """'C2D9E0E0' -> b'\\xc2\\xd9\\xe0\\xe0'"""
    return bytes.fromhex(hex_str.replace(" ", ""))


def bytes_to_hex(data: bytes) -> str:
    """b'\\xc2\\xd9' -> 'C2D9'"""
    return data.hex().upper()


#  Quick sanity check
if __name__ == "__main__":
    sample = "Hello, there!"
    encoded = encode_text(sample)
    print(f"Text:    {sample!r}")
    print(f"Encoded: {bytes_to_hex(encoded)}")
    print(f"Decoded: {decode_bytes(encoded, stop_at_eos=False)!r}")

    # Full round-trip
    assert decode_bytes(encoded, stop_at_eos=False) == sample, "Round-trip failed!"
    print("Round-trip OK")
