"""Bait as a count (Shop Items in the Item Pool, docs/zora-extras.md section 10; the two in-place
changes of docs/design/progressive-items-plan.md section 13, "Phase 2A: Bait in the Item Pool").

PRG0 stores bait as 0 or 1 (InvFood, $065D), so a second bait picked up while one is held is lost,
and a hungry Goriya sets the count to 0. With two hungry Goriyas and two baits in the pool, both
changes are needed (aldonunez labels, Z_01.asm at the pinned commit):
  1. ItemIdToDescriptor's bait entry, $01 (unique) to $11 (an amount of 1): each pickup or purchase
     adds one bait, as a key or a bomb adds to its count.
  2. UpdateGrumble3's STA InvFood to DEC InvFood (same operand, three bytes either way): a fed
     Goriya eats one bait. The accumulator, 0 there, is still 0 for the two stores after it.
Throwing bait to lure monsters still uses none, and selecting it as the B item tests only that the
count is not 0.
"""
from __future__ import annotations

from ..model.enums import Item
from .base_rom import original_bytes
from .inventory import AMOUNT, ITEM_ID_TO_DESCRIPTOR

BAIT_DESCRIPTOR = ITEM_ID_TO_DESCRIPTOR + Item.BAIT       # ItemIdToDescriptor + $04 (file offset)
UNIQUE_BAIT, AMOUNT_OF_ONE_BAIT = 0x01, AMOUNT | 0x01
# UpdateGrumble3's STA InvFood (file offset of its opcode; operand $065D after it)
GRUMBLE_FOOD_STORE = 0x04CB5
STA_ABSOLUTE, DEC_ABSOLUTE = 0x8D, 0xCE


def bait_count_writes() -> list[tuple[int, bytes]]:
    """The two one-byte changes as (file offset, bytes), checked against the player's ROM."""
    assert original_bytes(BAIT_DESCRIPTOR, 1)[0] == UNIQUE_BAIT, "bait's descriptor is not PRG0's"
    assert original_bytes(GRUMBLE_FOOD_STORE, 1)[0] == STA_ABSOLUTE, "UpdateGrumble3 is not PRG0's"
    return [(BAIT_DESCRIPTOR, bytes([AMOUNT_OF_ONE_BAIT])), (GRUMBLE_FOOD_STORE, bytes([DEC_ABSOLUTE]))]
