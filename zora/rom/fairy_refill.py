"""A bought fairy refills every heart (owner decision, 2026-10-24; docs/deviations.md "Shop prices").

The original randomizer sells no fairies; ZORA's shops do (the spare bait, Shop Items in the Item
Pool; the logo look's shields, Archipelago). In PRG0 taking the fairy item ($23) adds three hearts:
ItemIdToDescriptor's entry is $12, an amount of 2 that TakeHeartsNoSound adds one by one, plus one
(aldonunez labels, Z_01.asm at the pinned commit). A fairy that costs 20-40 rupees now refills
Link completely, as the pond fairy does; a dropped fairy, which takes the same item, keeps its
three hearts, so the change is in the cave's take path, not in the item table:

  1. The cave take (`UpdateCavePersonState_TalkOrShopOrDoorCharge`'s @Take, bank 1 $891E, file
     0x0492E), which every shop and item cave runs from bank 1: `JSR TakeItem` ($7370, the RAM
     copy) becomes `JSR TakeCaveItem`.
  2. TakeCaveItem, 31 bytes in PRG0's unused $FF block (bank 1 $A460-$A47E, file
     0x06470-0x0648E; docs/rom-map.md): it runs TakeItem as before (the lift,
     the tune, the three hearts), then for item $23 sets HeartValues' hearts to its containers and
     HeartPartial full. Any other item returns as before.

Written in every ROM. PRG1 holds the same bytes at both sites.

Not at $A450, where 2.0 beta 9 had it (hotfix, 2026-10-24): randomized music's lozft writes its own
code over bank 1 $A423-$A456, so with Music on every cave take ran 7 bytes of lozft's and then the
rest of the routine, and hung or crashed depending on what was in RAM. tests/test_music.py checks
that lozft's bytes meet no claim of asm/rom_space.toml but the known ones.
"""
from __future__ import annotations

from .base_rom import original_bytes

CAVE_TAKE_ITEM_CALL = 0x0492E                     # bank 1 $891E: JSR TakeItem
JSR_TAKE_ITEM = bytes.fromhex("207073")           # JSR $7370
TAKE_CAVE_ITEM = 0x06470                          # bank 1 $A460, past lozft's $A423-$A456
TAKE_CAVE_ITEM_CPU = 0xA460
FREE_BYTE = 0xFF
FAIRY_ITEM = 0x23
HEART_VALUES, HEART_PARTIAL = 0x066F, 0x0670
CONTAINERS_MASK = 0xF0                            # HeartValues: containers - 1 high, hearts low
FULL_PARTIAL = 0xFF


def _low(address: int) -> int:
    return address & 0xFF


def _high(address: int) -> int:
    return address >> 8


# TakeCaveItem
TAKE_CAVE_ITEM_CODE = bytes([
    0x48,                                                  # PHA            the item ID
    *JSR_TAKE_ITEM,                                        # JSR TakeItem
    0x68,                                                  # PLA
    0xC9, FAIRY_ITEM,                                      # CMP #$23
    0xD0, 0x13,                                            # BNE @Done
    0xAD, _low(HEART_VALUES), _high(HEART_VALUES),         # LDA HeartValues
    0x29, CONTAINERS_MASK,                                 # AND #$F0       containers - 1, high nibble
    0x85, 0x00,                                            # STA $00
    0x4A, 0x4A, 0x4A, 0x4A,                                # LSR x 4        and in the low nibble
    0x05, 0x00,                                            # ORA $00
    0x8D, _low(HEART_VALUES), _high(HEART_VALUES),         # STA HeartValues  every heart full
    0xA9, FULL_PARTIAL,                                    # LDA #$FF
    0x8D, _low(HEART_PARTIAL), _high(HEART_PARTIAL),       # STA HeartPartial
    0x60,                                                  # @Done: RTS
])
JSR_TAKE_CAVE_ITEM = bytes([0x20, _low(TAKE_CAVE_ITEM_CPU), _high(TAKE_CAVE_ITEM_CPU)])


def fairy_refill_writes() -> list[tuple[int, bytes]]:
    """The call and the routine as (file offset, bytes), checked against the player's ROM."""
    assert original_bytes(CAVE_TAKE_ITEM_CALL, len(JSR_TAKE_ITEM)) == JSR_TAKE_ITEM, "the cave take is not PRG0's"
    assert set(original_bytes(TAKE_CAVE_ITEM, len(TAKE_CAVE_ITEM_CODE))) == {FREE_BYTE}, "bank 1's $FF block is in use"
    return [(CAVE_TAKE_ITEM_CALL, JSR_TAKE_CAVE_ITEM), (TAKE_CAVE_ITEM, TAKE_CAVE_ITEM_CODE)]
