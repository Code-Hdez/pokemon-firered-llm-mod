"""
pokemon_text — Pokemon GBA character encoding/decoding & dialog formatting.

This is the SINGLE SOURCE OF TRUTH for all text encoding used in
Pokemon FireRed (US (NOT REV 1)).  Every module that needs to encode or decode
Pokemon text MUST import from here.

Public API:
    # Encoding tables
    DECODE, ENCODE

    # Encode / decode helpers
    encode_text(text) -> bytes
    decode_bytes(data) -> str
    hex_to_bytes(hex_str) -> bytes
    bytes_to_hex(data) -> str

    # Dialog formatting (line-wrap + pagination)
    format_dialog(text, ...) -> bytes
    format_dialog_hex(text, ...) -> str
"""

from .char_table import (
    DECODE,
    ENCODE,
    encode_text,
    decode_bytes,
    hex_to_bytes,
    bytes_to_hex,
)

from .text_formatter import (
    format_dialog,
    format_dialog_hex,
    MAX_CHARS_PER_LINE,
    SAFE_CHARS_PER_LINE,
    LINES_PER_PAGE,
    CHAR_NEWLINE,
    CHAR_SCROLL,
    CHAR_PAGE_BREAK,
    CHAR_EOS,
)

__all__ = [
    "DECODE", "ENCODE",
    "encode_text", "decode_bytes", "hex_to_bytes", "bytes_to_hex",
    "format_dialog", "format_dialog_hex",
    "MAX_CHARS_PER_LINE", "SAFE_CHARS_PER_LINE", "LINES_PER_PAGE",
    "CHAR_NEWLINE", "CHAR_SCROLL", "CHAR_PAGE_BREAK", "CHAR_EOS",
]
