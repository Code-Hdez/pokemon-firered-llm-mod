"""
text_formatter.py
Formats arbitrary text into Pokemon FireRed dialog format with
proper line wrapping, pagination, and control codes.

Builds on top of char_table.py for the actual byte encoding.

Usage:
    from python.pokemon_text import format_dialog, format_dialog_hex

    # Auto-wrapped and paginated
    raw = format_dialog("Hello! Welcome to the world of Pokemon!")
    hex_str = format_dialog_hex("Hello! Welcome to the world of Pokemon!")
"""

from .char_table import ENCODE, encode_text, decode_bytes, bytes_to_hex

# FireRed dialog box constraints
MAX_CHARS_PER_LINE = 35    # absolute max observed in decomp
SAFE_CHARS_PER_LINE = 18   # safe for proportional font (worst case)
LINES_PER_PAGE = 2         # standard dialog box shows 2 lines

# Control code bytes
CHAR_NEWLINE     = 0xFE    # \n  — line break within page
CHAR_SCROLL      = 0xFA    # \l  — scroll up 1 line, continue
CHAR_PAGE_BREAK  = 0xFB    # \p  — wait for A, clear, new page
CHAR_EOS         = 0xFF    # $   — end of string


def format_dialog(text: str, *,
                  chars_per_line: int = SAFE_CHARS_PER_LINE,
                  lines_per_page: int = LINES_PER_PAGE,
                  use_scroll: bool = False) -> bytes:
    """
    Convert a plain text string into Pokemon-encoded bytes with proper
    line wrapping and pagination.

    Parameters
    ----------
    text : str
        Plain text (ASCII/Unicode).  Supports explicit markers:
          \\n  -> forced line break
          \\p  -> forced page break (wait for A, clear box)
    chars_per_line : int
        Max characters per line before auto-wrap (default 18).
    lines_per_page : int
        Lines visible in dialog box (default 2).
    use_scroll : bool
        If True, use SCROLL (0xFA) instead of PAGE_BREAK (0xFB) for
        continuation after a full page.  Scrolls text up 1 line.

    Returns
    -------
    bytes
        Pokemon-encoded byte string, terminated with 0xFF.

    Raises
    ------
    ValueError
        If the text contains characters that cannot be encoded.
    """
    # Pre-process: handle explicit control markers
    paragraphs = text.replace("\\p", "\x01").split("\x01")

    output: list[int] = []
    first_paragraph = True

    for para in paragraphs:
        if not first_paragraph:
            output.append(CHAR_PAGE_BREAK)
        first_paragraph = False

        # Split paragraph into explicit lines (\\n or real newlines)
        explicit_lines = para.replace("\\n", "\n").split("\n")
        line_on_page = 0

        for line_idx, line_text in enumerate(explicit_lines):
            line_text = line_text.strip()
            if not line_text:
                continue

            if line_idx > 0:
                line_on_page += 1
                if line_on_page >= lines_per_page:
                    output.append(CHAR_PAGE_BREAK if not use_scroll else CHAR_SCROLL)
                    line_on_page = 0
                else:
                    output.append(CHAR_NEWLINE)

            # Word-wrap this line
            words = line_text.split(" ")
            col = 0

            for word in words:
                word_len = len(word)
                if word_len == 0:
                    continue

                # Check if word fits on current line
                needed = (1 + word_len) if col > 0 else word_len
                if col > 0 and col + needed > chars_per_line:
                    # Word doesn't fit -> wrap to next line
                    line_on_page += 1
                    if line_on_page >= lines_per_page:
                        output.append(CHAR_PAGE_BREAK if not use_scroll else CHAR_SCROLL)
                        line_on_page = 0
                    else:
                        output.append(CHAR_NEWLINE)
                    col = 0

                # Add space between words (if not at line start)
                if col > 0:
                    output.append(ENCODE[" "])  # 0x00
                    col += 1

                # Encode each character of the word
                for ch in word:
                    if ch in ENCODE:
                        output.append(ENCODE[ch])
                        col += 1
                    else:
                        raise ValueError(
                            f"Cannot encode character {ch!r} (U+{ord(ch):04X}). "
                            f"Not in Pokemon character table."
                        )

    output.append(CHAR_EOS)
    return bytes(output)


def format_dialog_hex(text: str, **kwargs) -> str:
    """
    Same as format_dialog() but returns an uppercase hex string
    ready to send via IPC INJECT command.

    Example:
        >>> format_dialog_hex("Hello!")
        'C2D9E0E0E3ABFF'
    """
    return bytes_to_hex(format_dialog(text, **kwargs))


# Quick test
if __name__ == "__main__":
    print("=== Text Formatter Test ===\n")

    # Test 1: Short text (fits on one page)
    test1 = "Hello, there!"
    r1 = format_dialog(test1)
    print(f"Input:   {test1!r}")
    print(f"Hex:     {bytes_to_hex(r1)}")
    print(f"Decoded: {decode_bytes(r1)!r}")
    print(f"Bytes:   {len(r1)}")
    print()

    # Test 2: Auto-wrapped text (should split across pages)
    test2 = "This is a longer text that should be automatically wrapped across multiple lines and pages."
    r2 = format_dialog(test2, chars_per_line=18)
    print(f"Input:   {test2!r}")
    print(f"Decoded: {decode_bytes(r2)!r}")
    print(f"Bytes:   {len(r2)}")
    print()

    # Test 3: Explicit line/page breaks
    test3 = "Line one.\\nLine two.\\pPage two line one.\\nPage two line two."
    r3 = format_dialog(test3)
    print(f"Input:   {test3!r}")
    print(f"Decoded: {decode_bytes(r3)!r}")
    print(f"Bytes:   {len(r3)}")
    print()

    # Test 4: Round-trip verify
    test4 = "Hello!"
    r4 = format_dialog(test4)
    d4 = decode_bytes(r4)
    assert d4 == "Hello!", f"Round-trip failed: {d4!r}"
    print(f"Round-trip OK: {test4!r} -> {bytes_to_hex(r4)} -> {d4!r}")
