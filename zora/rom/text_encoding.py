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
QUOTE_BLANK     = 0xFF   # sentinel for an empty quote
