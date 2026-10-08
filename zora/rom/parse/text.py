"""Quotes and hint texts."""

from zora.model.overworld import Quote
from zora.rom.layout import EXT_BANK1_ROM_START, NUM_QUOTES
from zora.rom.text_encoding import (
    BYTE_TO_CHAR as _BYTE_TO_CHAR,
)
from zora.rom.text_encoding import (
    QUOTE_BLANK,
    QUOTE_CHAR_MASK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)

# ---------------------------------------------------------------------------
# Quotes parsing
# ---------------------------------------------------------------------------

def _decode_quote(data: bytes, offset: int) -> str:
    """Decode one quote starting at data[offset]. Returns pipe-separated lines."""
    if offset >= len(data) or data[offset] == QUOTE_BLANK:
        return ""
    lines: list[str] = []
    current: list[str] = []
    while offset < len(data):
        raw = data[offset]
        offset += 1
        char = _BYTE_TO_CHAR.get(raw & QUOTE_CHAR_MASK, "?")
        current.append(char)
        high = raw & QUOTE_END_BITS
        if high == QUOTE_LINE1_BIT:
            lines.append("".join(current))
            current = []
        elif high == QUOTE_LINE2_BIT:
            lines.append("".join(current))
            current = []
        elif high == QUOTE_END_BITS:
            lines.append("".join(current))
            break
    return "|".join(lines)


def _parse_hint_text_bytes(rom_bytes: bytes) -> tuple[bytes, ...]:
    """Split the extended hint bank (and its overflow region) into encoded bodies in slot order.

    Each body ends with a byte that has the quote-end bits set (0xC0) or is
    the blank sentinel 0xFF.  ZORA's generated hint text has 45 bodies, in slot
    order (HT-TEXT-03).
    """
    from zora.rom.layout import CONSTERNATION_HINT_SLOTS, hint_text_regions
    bodies: list[bytes] = []
    # The bank first, then (when the serializer spilled, filling the bank's
    # tail with a byte that ends no text) the overflow region (PI-HINT-02).
    for start, end in hint_text_regions(CONSTERNATION_HINT_SLOTS):
        pos = start
        while pos < end and len(bodies) < 45:
            term = pos
            while term < end:
                b = rom_bytes[term]
                if b == 0xFF or (b & 0xC0) == 0xC0:
                    break
                term += 1
            if term >= end:
                break
            bodies.append(rom_bytes[pos:term + 1])
            pos = term + 1
    while len(bodies) < 45:
        bodies.append(bytes([0xFF]))
    return tuple(bodies)


def _parse_person_text(quotes_data: bytes, rom_bytes: bytes | None = None
                       ) -> tuple[list[Quote], tuple[int, ...], tuple[bytes, ...] | None]:
    """Parse the person-text pointer table and decode each slot's text.

    With generated hint text, ZORA's serializer writes a 45-entry table in
    place of PRG0's 38-entry `PersonTextAddrs` and keeps the bodies in the
    extended hint bank (HT-TEXT-03).  When `rom_bytes` is provided we try to
    decode those slots from the full ROM as well.  Returns the decoded quotes,
    the logical CPU pointer for each slot, and (for generated hint text) the
    encoded bodies in slot order.
    """
    from zora.rom.layout import EXT_HINT_CPU_BASE
    count = NUM_QUOTES
    # Generated hint text has a 45-entry pointer table (HT-TEXT-03).  PRG0
    # keeps the 38-entry table; bytes after it are text, not pointers.  Only
    # read the extra seven slots when their high bytes look like bank-1
    # pointers (bit 7 set), which text bytes never do.
    if rom_bytes is not None and len(quotes_data) >= NUM_QUOTES * 2 + 14:
        extra_high = quotes_data[NUM_QUOTES * 2 + 1:NUM_QUOTES * 2 + 14:2]
        if all(b & 0x80 for b in extra_high):
            count = NUM_QUOTES + 7

    def text_at(data_offset: int) -> str:
        if data_offset < len(quotes_data):
            return _decode_quote(quotes_data, data_offset)
        if rom_bytes is not None:
            file_offset = EXT_BANK1_ROM_START + data_offset
            if file_offset < len(rom_bytes):
                return _decode_quote(rom_bytes, file_offset)
        return ""

    quotes: list[Quote] = []
    pointers: list[int] = []
    for i in range(count):
        if i * 2 + 1 >= len(quotes_data):
            quotes.append(Quote(quote_id=i, text=""))
            pointers.append(0)
            continue
        low = quotes_data[i * 2]
        high = quotes_data[i * 2 + 1]
        data_offset = (high & 0x7F) * 0x100 + low
        pointers.append(data_offset + EXT_HINT_CPU_BASE)
        quotes.append(Quote(quote_id=i, text=text_at(data_offset)))

    hint_text_bytes: tuple[bytes, ...] | None = None
    if count == NUM_QUOTES + 7 and rom_bytes is not None:
        # Only treat it as generated hint text if the extended bank looks populated.
        hint_text_bytes = _parse_hint_text_bytes(rom_bytes)

    # If the extra slots are all blank, trim back to the vanilla 38.
    if count == NUM_QUOTES + 7 and all(not q.text for q in quotes[NUM_QUOTES:]):
        return quotes[:NUM_QUOTES], tuple(pointers[:NUM_QUOTES]), None
    return quotes, tuple(pointers), hint_text_bytes


REFUSAL_SLOT = 34                  # person-text slot of the level-9 refusal (FP-TRIF-01)


def _slot_text(quotes: list[Quote], slot: int) -> str:
    return quotes[slot].text if slot < len(quotes) else ""
