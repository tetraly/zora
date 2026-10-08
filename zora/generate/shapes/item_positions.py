"""Usable item positions per room layout (SH-ROOM-11).

Fitted from 1000 corpus ROMs by scripts/fit_item_positions.py
(QUESTIONS item 3 "resolved from corpus": layouts cluster onto
subsets of the level's 4 standard positions; a position kept here
appears on >=2% of that layout's item rooms).
Key: full layout code (0x40 bit = push block). Missing keys fall
back to all four positions (SPEC-GAP 3 kept for unknown layouts).
"""

USABLE_ITEM_POSITIONS: dict[int, tuple[int, ...]] = {
    0x00: (0, 1, 2, 3),
    0x02: (0, 1, 2, 3),
    0x03: (0, 1, 2, 3),
    0x04: (0, 2, 3),
    0x05: (0, 3),
    0x06: (0, 3),
    0x08: (0, 3),
    0x0A: (0, 2, 3),
    0x0C: (2,),
    0x0D: (1,),
    0x0E: (0, 3),
    0x0F: (0, 3),
    0x11: (0, 2, 3),
    0x12: (0, 1, 2),
    0x13: (0, 2, 3),
    0x14: (0, 2, 3),
    0x15: (0, 2, 3),
    0x16: (0, 2, 3),
    0x17: (0, 2, 3),
    0x18: (0, 1, 2, 3),
    0x19: (0, 3),
    0x1B: (0, 2, 3),
    0x1C: (0, 1),
    0x1D: (0, 2, 3),
    0x1E: (1, 2),
    0x1F: (0,),
    0x23: (0, 2, 3),
    0x24: (0, 2, 3),
    0x25: (0, 2, 3),
    0x26: (0, 3),
    0x28: (0, 3),
    0x29: (0, 2, 3),
    0x5A: (1,),
}


def usable_positions(layout_full: int) -> tuple[int, ...]:
    """Allowed item positions for a full layout code (0x40 bit = block).

    Falls back to the non-block variant, then to all four positions
    (SPEC-GAP 3 for layouts never observed holding an item)."""
    v = USABLE_ITEM_POSITIONS.get(layout_full)
    if v is None and layout_full >= 0x40:
        v = USABLE_ITEM_POSITIONS.get(layout_full & 0x3F)
    return v if v else (0, 1, 2, 3)

