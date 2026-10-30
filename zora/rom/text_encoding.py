"""Character encoding and text format constants for Zelda 1 in-game text (quotes/hints).

CHAR_TO_BYTE is the canonical definition. BYTE_TO_CHAR is derived from it,
guaranteeing the two are always inverses of each other.

Quote byte format: low 6 bits = character code, high 2 bits = line-break flags.
"""

CHAR_TO_BYTE: dict[str, int] = {
    "0": 0x00, "1": 0x01, "2": 0x02, "3": 0x03, "4": 0x04,
    "5": 0x05, "6": 0x06, "7": 0x07, "8": 0x08, "9": 0x09,
    "A": 0x0A, "B": 0x0B, "C": 0x0C, "D": 0x0D, "E": 0x0E,
    "F": 0x0F, "G": 0x10, "H": 0x11, "I": 0x12, "J": 0x13,
    "K": 0x14, "L": 0x15, "M": 0x16, "N": 0x17, "O": 0x18,
    "P": 0x19, "Q": 0x1A, "R": 0x1B, "S": 0x1C, "T": 0x1D,
    "U": 0x1E, "V": 0x1F, "W": 0x20, "X": 0x21, "Y": 0x22,
    "Z": 0x23, " ": 0x24, "~": 0x25, ",": 0x28, "!": 0x29,
    "'": 0x2A, "&": 0x2B, ".": 0x2C, '"': 0x2D, "?": 0x2E,
    "-": 0x2F,
}

BYTE_TO_CHAR: dict[int, str] = {v: k for k, v in CHAR_TO_BYTE.items()}

# High-2-bit flags on the last byte of each line in a quote.
# Set on the last character of lines 0 and 1; end-of-text on the last byte overall.
QUOTE_LINE1_BIT = 0x80   # end of line 0 → line 1 follows  (high bits: 0b10)
QUOTE_LINE2_BIT = 0x40   # end of line 1 → line 2 follows  (high bits: 0b01)
QUOTE_END_BITS  = 0xC0   # end of text                      (high bits: 0b11)
QUOTE_CHAR_MASK = 0x3F   # mask to extract character code from a quote byte
QUOTE_BLANK     = 0xFF   # an empty quote as the spec writes it (HT-HINT-07): the game still draws its character $3F
# An empty text as ZORA writes it: one space with the end mark, so the text box shows nothing (a lone
# $FF draws tile $3F, a stray mark, at the start of the box; seen in the emulator, beta 8)
QUOTE_EMPTY     = CHAR_TO_BYTE[" "] | QUOTE_END_BITS

# The person text drawer (Z_01.asm @WriteChar: AND #$3F / CMP #$25 / BEQ @WriteChar) skips the pad
# tile before it reads a tile's line or end bits, so a line ending on one runs on past the box's
# right edge, and a text whose end bits fall on one never ends (aa19038). A space looks the same.
PAD_TILE = CHAR_TO_BYTE["~"]
LINE_END_TILE = CHAR_TO_BYTE[" "]


def closed_line(tiles: list[int]) -> list[int]:
    """A text line's tiles (before its bits) whose last tile is never the pad tile: a last pad tile
    becomes a space, keeping the line's length and centering. Every writer of person text encodes
    each line through this; player_settings.end_padded_hint_line does the same on a line's text."""
    if tiles and tiles[-1] == PAD_TILE:
        return [*tiles[:-1], LINE_END_TILE]
    return tiles
