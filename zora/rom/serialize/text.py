"""Quotes and hint texts."""

from zora.model.game_world import GameWorld
from zora.model.overworld import Quote
from zora.rom.game_config import HintMode
from zora.rom.layout import (
    CONSTERNATION_HINT_SLOTS,
    EXT_HINT_DATA_ROM_END,
    EXT_HINT_DATA_ROM_START,
    HINT_SHOP_QUOTES_ADDRESS,
    HINT_TEXT_SPILL_FILL,
    OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS,
    QUOTE_DATA_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
    UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE,
    VANILLA_HINT_TEXT_MAX_BYTES,
    cpu_address_in_bank1,
    place_hint_texts,
    write_le16,
)
from zora.rom.serialize.patch import Patch, log
from zora.rom.text_encoding import (
    CHAR_TO_BYTE as _CHAR_TO_BYTE,
)
from zora.rom.text_encoding import (
    QUOTE_BLANK,
    QUOTE_END_BITS,
    QUOTE_LINE1_BIT,
    QUOTE_LINE2_BIT,
)

# ---------------------------------------------------------------------------
# Quotes serialization
# ---------------------------------------------------------------------------

_QUOTE_PAD_BYTE = 0x25   # '~' tile — renders as blank space in-game
QUOTE_PAD_CHARS = "~ "    # how centering pad decodes, and plain blanks
_NES_LINE_WIDTH = 24     # total rendered columns per line on the NES
_QUOTE_MAX_TEXT_COLS = 22  # usable text columns per line (24 total minus 2 border cols)


def _center_line(line: str) -> list[int]:
    """Return the encoded bytes for one centered hint line, with leading pad bytes."""
    line = line.rstrip()[:_QUOTE_MAX_TEXT_COLS]
    line_len = len(line)
    left_padding = (_NES_LINE_WIDTH - line_len) // 2

    result = [_QUOTE_PAD_BYTE] * left_padding
    for char in line:
        result.append(_CHAR_TO_BYTE.get(char.upper(), _QUOTE_PAD_BYTE))
    return result


def _encode_quote(text: str, center: bool = False) -> list[int]:
    """Encode a pipe-separated quote string into ROM bytes.

    When center=True each line is padded with leading 0x25 bytes to visually
    center it in the 24-column hint display. Use this for randomized hints
    (COMMUNITY / HELPFUL modes). Leave False for vanilla text, which already
    has its own hand-crafted spacing.
    """
    if not text:
        return [QUOTE_BLANK]
    lines = text.split("|")
    result: list[int] = []
    for line_idx, line in enumerate(lines):
        if center:
            if not line.strip():
                continue
            result.extend(_center_line(line))
        else:
            result.extend(_CHAR_TO_BYTE.get(char.upper(), _QUOTE_PAD_BYTE) for char in line)
        if result and line_idx < len(lines) - 1:
            if line_idx == 0:
                result[-1] |= QUOTE_LINE1_BIT
            elif line_idx == 1:
                result[-1] |= QUOTE_LINE2_BIT
    if result:
        result[-1] |= QUOTE_END_BITS
    return result


def _serialize_quotes(quotes: list[Quote],
                      max_text_bytes: int | None = None,
                      center: bool = False) -> bytes:
    """Produce the full quotes_data block: pointer table (n*2 bytes) + encoded text.

    The pointer table is indexed by quote_id (not by list position), so quote_ids
    must be unique and contiguous from 0 to max_id. Gaps (e.g. id=38 missing when
    ids 39-43 exist) receive a pointer to a blank quote.
    """
    if not quotes:
        return b""
    max_id = max(q.quote_id for q in quotes)
    ptr_table_size = (max_id + 1) * 2
    ptr_table = bytearray(ptr_table_size)
    text_data = bytearray()

    # Build a lookup by quote_id
    by_id: dict[int, Quote] = {q.quote_id: q for q in quotes}

    for qid in range(max_id + 1):
        quote = by_id.get(qid)
        if quote is not None:
            raw_text = quote.text
        else:
            raw_text = ""  # gap — write blank pointer
        encoded = _encode_quote(raw_text, center=center)
        projected = len(text_data) + len(encoded)
        if max_text_bytes is not None and projected > max_text_bytes:
            # No silent fallback: a text is never replaced by a blank one.
            raise ValueError(
                f"quote id={qid} would overflow the vanilla hint bank at byte "
                f"{projected}/{max_text_bytes}"
            )
        data_offset = ptr_table_size + len(text_data)
        ptr_table[qid * 2]     = data_offset & 0xFF
        ptr_table[qid * 2 + 1] = ((data_offset >> 8) & 0xFF) | 0x80
        text_data.extend(encoded)

    return bytes(ptr_table) + bytes(text_data)


def _serialize_hints(game_world: GameWorld, patch: Patch,
                     hint_mode: HintMode) -> None:
    """Write hint data to patch, branching on hint_mode."""
    if not game_world.quotes:
        return

    # Passthrough: when the original quotes block was captured at parse time
    # (GameWorld.quotes_raw), vanilla-mode serialization re-emits it verbatim
    # instead of re-encoding through the character table. This keeps
    # parse → serialize byte-identical for randomized and vanilla ROMs alike.
    if hint_mode == HintMode.VANILLA and game_world.quotes_raw:
        patch.add(QUOTE_DATA_ADDRESS, game_world.quotes_raw)
        return

    use_extended_hint_bank = hint_mode in (HintMode.COMMUNITY, HintMode.HELPFUL,
                                           HintMode.CONSTERNATION)

    if not use_extended_hint_bank:
        patch.add(
            QUOTE_DATA_ADDRESS,
            _serialize_quotes(game_world.quotes,
                              max_text_bytes=VANILLA_HINT_TEXT_MAX_BYTES,
                              center=False),
        )
        return

    if hint_mode == HintMode.CONSTERNATION:
        _serialize_consternation_hints(game_world, patch)
        return

    # PI-HINT-02: the texts in quote order, the extended bank first, then the
    # old text area after the pointer table; place_hint_texts raises rather
    # than truncate (a text is never replaced by a blank one).
    pointer_count = max(q.quote_id for q in game_world.quotes) + 1
    by_id: dict[int, Quote] = {q.quote_id: q for q in game_world.quotes}
    encoded = [bytes(_encode_quote(by_id[qid].text or "" if qid in by_id else "", center=True))
               for qid in range(pointer_count)]
    offsets = place_hint_texts([len(text) for text in encoded], pointer_count)
    ptr_table = bytearray(pointer_count * 2)
    for qid, offset in enumerate(offsets):
        write_le16(ptr_table, qid, cpu_address_in_bank1(offset))
    patch.add(QUOTE_DATA_ADDRESS, bytes(ptr_table))
    for offset, text in zip(offsets, encoded, strict=True):
        patch.add(offset, text)


def _serialize_consternation_hints(game_world: GameWorld, patch: Patch) -> None:
    """Hints-behavior.md: write the generated 45-slot block and selector tables."""
    pointers = game_world.hint_pointers
    text_bytes = game_world.hint_text_bytes
    if pointers is None or text_bytes is None:
        raise ValueError("CONSTERNATION hint mode requires HintTextResult output")

    ptr_table = bytearray(len(pointers) * 2)
    for i, cpu in enumerate(pointers):
        ptr_table[i * 2] = cpu & 0xFF
        ptr_table[i * 2 + 1] = (cpu >> 8) & 0xFF
    patch.add(QUOTE_DATA_ADDRESS, bytes(ptr_table))

    # Encoded slot texts (HT-TEXT-01/03/04), in slot order: the extended
    # bank, then the overflow region; place_hint_texts raises rather than
    # truncate. The pointer table above may permute them.
    offsets = place_hint_texts([len(data) for data in text_bytes], CONSTERNATION_HINT_SLOTS)
    for offset, data in zip(offsets, text_bytes, strict=True):
        patch.add(offset, data)
    spilled = [offset < EXT_HINT_DATA_ROM_START for offset in offsets]
    if any(spilled):
        # Fill the bank's unused tail so a reader stops there (rom_layout).
        bank_end = max((offset + len(data)
                        for offset, data, out in zip(offsets, text_bytes, spilled, strict=True) if not out),
                       default=EXT_HINT_DATA_ROM_START)
        patch.add(bank_end, bytes([HINT_TEXT_SPILL_FILL]) * (EXT_HINT_DATA_ROM_END - bank_end))

    # Selector tables (HT-SEL-01/02).
    if game_world.white_sword_text_selector is not None:
        patch.add(OVERWORLD_PERSON_TEXT_SELECTORS_ADDRESS + 2,
                  bytes([game_world.white_sword_text_selector]))
    if game_world.hint_shop_offer_selectors is not None:
        patch.add(HINT_SHOP_QUOTES_ADDRESS,
                  bytes(game_world.hint_shop_offer_selectors))
    if game_world.underworld_text_selectors_a is not None:
        patch.add(UNDERWORLD_PERSON_TEXT_SELECTORS_A_ADDRESS,
                  bytes(game_world.underworld_text_selectors_a[:UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE]))
    if game_world.underworld_text_selectors_b is not None:
        patch.add(UNDERWORLD_PERSON_TEXT_SELECTORS_B_ADDRESS,
                  bytes(game_world.underworld_text_selectors_b[:UNDERWORLD_PERSON_TEXT_SELECTORS_SIZE]))

    log.info("Consternation hint texts: %d bytes, %d in the overflow region.",
             sum(len(data) for data in text_bytes),
             sum(len(data) for data, out in zip(text_bytes, spilled, strict=True) if out))
