"""The wooden-sword states' code patches (C07; features-behavior.md FP-WOOD-02 and FP-WOOD-03): fixed
writes made with the code patches, taking no draw. The cave wares the states change (the wooden-
and magical-sword caves) are the world's (generate/steps/sword_states.py).

FP-WOOD-02 (Wood Sword Only and Swordless): item $02, PRG0's white sword, becomes a bomb upgrade.
Aldonunez labels, at the pinned commit:
  - ItemIdToDescriptor's entry for $02 (0x06B4A): $22 to $12, an amount item worth 2;
  - TakeItem's LDA ItemIdToSlot,X (0x06C12) becomes JSR $7EED, a routine in bank 1's copy to RAM
    (file 0x0776D, $FF in PRG0) that loads the slot as before but gives item $02 slot $25 (MaxBombs);
  - SetItemValue's STA Items,Y (0x06C35) stores the value as before and, for item $02, into the
    bomb count (InvBombs) as well. Deviation (docs/deviations.md): the spec places that routine at
    0x1EDA4, where ZORA's fp-fix-04 keeps the Triforce of Power pickup routine; it is ZORA's own
    bank 7 free space instead, $FFC8-$FFD2. With Book is an Atlas (B49) on, fp-book-01 already takes
    the site with SetItemValueAndBookMap ($FFC0-$FFCA): its closing RTS becomes a NOP, so it runs
    on into the bomb-count tail at $FFCB, as the spec's Book routine ends with a jump to the store.
    With B49 off the site jumps to $FFC8, the store, which runs on into the same tail;
  - DrawItemBySlot's CMP #$02 operand (0x1E78B): $01;
  - the sprite patterns: the 32 bytes at 0x0850F become those at 0x083CF (the player's own, so
    modified graphics keep theirs), bytes 0x08528, 0x08529, 0x0852B and 0x0852C ORed with $08 and
    0x0852A with $3E.
FP-WOOD-03 (Swordless): Ganon is harmed by the wand's stab alone:
  - InitGanon's LDA #$FA invincibility mask operand (0x12980): $EA, so magic ($10) harms him;
  - Ganon_CheckCollisions' LDY #$0D / JSR CheckMonsterSwordCollision (0x12F1C) becomes LDY #$12 /
    JSR $AFD0, a routine (file 0x12FE0, $FF in PRG0) that tests a wand stab in slot $12 (state $30
    or more) against Ganon as a magic hit of $20, and otherwise does nothing.
Every site is checked against PRG0's bytes (the player's ROM, in PRG0's layout) before it is written.
"""
from __future__ import annotations

from .base_rom import original_bytes

# FP-WOOD-02
ITEM_02_DESCRIPTOR = 0x06B4A
ITEM_02_DESCRIPTOR_PRG0, BOMB_UPGRADE_DESCRIPTOR = 0x22, 0x12          # unique sword 2 -> amount of 2
TAKE_ITEM_SLOT_LOAD = 0x06C12
TAKE_ITEM_SLOT_LOAD_PRG0 = bytes.fromhex("bda472")                      # LDA ItemIdToSlot,X
TAKE_ITEM_SLOT_CALL = bytes.fromhex("20ed7e")                           # JSR $7EED
SLOT_ROUTINE = 0x0776D                                                  # $7EED in bank 1's RAM copy
SLOT_ROUTINE_BYTES = bytes.fromhex("bda472e002d002a92560")              # item $02 -> slot $25 (MaxBombs)
SET_ITEM_VALUE_STORE = 0x06C35
SET_ITEM_VALUE_STORE_PRG0 = bytes.fromhex("995706")                     # STA Items,Y
STORE_ROUTINE = 0x1FFD8                                                 # $FFC8: STA Items,Y, then the tail
STORE_ROUTINE_JUMP = bytes.fromhex("4cc8ff")                            # JMP $FFC8 (B49 off)
STORE_ROUTINE_BYTES = bytes.fromhex("995706")                           # STA Items,Y
BOMB_COUNT_TAIL = 0x1FFDB                                               # $FFCB
BOMB_COUNT_TAIL_BYTES = bytes.fromhex("e002d0038d580660")               # CPX #$02 / BNE / STA InvBombs / RTS
BOOK_ROUTINE_RTS = 0x1FFDA                                              # fp-book-01's last byte ($FFCA)
RTS, NOP = 0x60, 0xEA
DRAW_ITEM_SWORD_CMP = 0x1E78B
DRAW_ITEM_SWORD_CMP_PRG0, DRAW_ITEM_SWORD_CMP_BOMB_UPGRADE = 0x02, 0x01
PATTERN_TARGET, PATTERN_SOURCE, PATTERN_LENGTH = 0x0850F, 0x083CF, 32
PATTERN_OR_MASKS = {0x08528: 0x08, 0x08529: 0x08, 0x0852A: 0x3E, 0x0852B: 0x08, 0x0852C: 0x08}
FREE = 0xFF
# FP-WOOD-03
GANON_MASK_OPERAND = 0x12980
GANON_MASK_PRG0, GANON_MASK_WAND = 0xFA, 0xEA
GANON_SWORD_TEST = 0x12F1C
GANON_SWORD_TEST_PRG0 = bytes.fromhex("a00d20297d")                     # LDY #$0D / JSR CheckMonsterSwordCollision
GANON_WAND_TEST = bytes.fromhex("a01220d0af")                           # LDY #$12 / JSR $AFD0
GANON_WAND_ROUTINE = 0x12FE0
GANON_WAND_ROUTINE_BYTES = bytes.fromhex("8400b9ac00c9309005a9104c6a7d60")    # FP-WOOD-03's 15 bytes


def _check(offset: int, expected: bytes, what: str) -> None:
    assert original_bytes(offset, len(expected)) == expected, f"{what} is not PRG0's"


def _free(offset: int, length: int, what: str) -> None:
    _check(offset, bytes([FREE]) * length, f"{what}'s free space")


def bomb_upgrade_writes(book_is_an_atlas: bool) -> list[tuple[int, bytes]]:
    """FP-WOOD-02's writes as (file offset, bytes), after the code patches (fp-book-01 included)."""
    _check(ITEM_02_DESCRIPTOR, bytes([ITEM_02_DESCRIPTOR_PRG0]), "item $02's descriptor")
    _check(TAKE_ITEM_SLOT_LOAD, TAKE_ITEM_SLOT_LOAD_PRG0, "TakeItem's slot load")
    _free(SLOT_ROUTINE, len(SLOT_ROUTINE_BYTES), "the slot routine")
    _check(SET_ITEM_VALUE_STORE, SET_ITEM_VALUE_STORE_PRG0, "SetItemValue's store")
    _free(BOMB_COUNT_TAIL, len(BOMB_COUNT_TAIL_BYTES), "the bomb-count tail")
    _check(DRAW_ITEM_SWORD_CMP, bytes([DRAW_ITEM_SWORD_CMP_PRG0]), "DrawItemBySlot's CMP")
    patterns = bytearray(original_bytes(PATTERN_SOURCE, PATTERN_LENGTH))
    for offset, mask in PATTERN_OR_MASKS.items():
        patterns[offset - PATTERN_TARGET] |= mask
    writes = [(ITEM_02_DESCRIPTOR, bytes([BOMB_UPGRADE_DESCRIPTOR])), (TAKE_ITEM_SLOT_LOAD, TAKE_ITEM_SLOT_CALL),
              (SLOT_ROUTINE, SLOT_ROUTINE_BYTES), (BOMB_COUNT_TAIL, BOMB_COUNT_TAIL_BYTES),
              (DRAW_ITEM_SWORD_CMP, bytes([DRAW_ITEM_SWORD_CMP_BOMB_UPGRADE])), (PATTERN_TARGET, bytes(patterns))]
    if book_is_an_atlas:
        # fp-book-01's SetItemValueAndBookMap runs on into the tail instead of returning
        writes.append((BOOK_ROUTINE_RTS, bytes([NOP])))
    else:
        _free(STORE_ROUTINE, len(STORE_ROUTINE_BYTES), "the store routine")
        writes += [(STORE_ROUTINE, STORE_ROUTINE_BYTES), (SET_ITEM_VALUE_STORE, STORE_ROUTINE_JUMP)]
    return writes


def wand_ganon_writes() -> list[tuple[int, bytes]]:
    """FP-WOOD-03's Ganon writes as (file offset, bytes)."""
    _check(GANON_MASK_OPERAND, bytes([GANON_MASK_PRG0]), "InitGanon's mask")
    _check(GANON_SWORD_TEST, GANON_SWORD_TEST_PRG0, "Ganon's sword test")
    _free(GANON_WAND_ROUTINE, len(GANON_WAND_ROUTINE_BYTES), "the wand routine")
    return [(GANON_MASK_OPERAND, bytes([GANON_MASK_WAND])), (GANON_SWORD_TEST, GANON_WAND_TEST),
            (GANON_WAND_ROUTINE, GANON_WAND_ROUTINE_BYTES)]
