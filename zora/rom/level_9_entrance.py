"""Level 9's entrance check (features-behavior.md FP-TRIF-01 to FP-TRIF-06): the bytes each
Level9Gate writes. PRG0's gate, all eight pieces, writes none: PRG0's own check already admits Link
only with InvTriforce $FF.

Aldonunez labels, at the pinned commit (file offsets, PRG0). InitUnderworldPersonC (bank 1) sets up
the level 9 entrance person ($4B), then:
    LDA InvTriforce / CMP #$FF / BNE @Exit       ; 0x04AB1-0x04AB7
    ; open the shutters and destroy the person (DestroyMonster, which reads X, the person's slot)
The counts (FP-TRIF-02 to FP-TRIF-04) and the chosen levels (FP-TRIF-05) replace the load with
`JSR $9F00`, a routine in bank 1's free block after DemoBackgroundPatterns ($9ED4-$9FFF,
docs/rom-map.md; ht-book-01 starts at $9F30), which returns $FF to admit and $00 to refuse, so
PRG0's CMP #$FF / BNE @Exit stays. The open level (FP-TRIF-03) also turns that comparison into
no-operations. The item (FP-TRIF-06) keeps PRG0's load, pointed at the item's inventory byte, and
admits when it is not zero.

ZORA's routines are its own; the spec fixes what they do and, for the chosen levels, where the
mask lies (0x05F14 and 0x05F16). The counting routine keeps X, so its count byte is at 0x05F20,
not FP-TRIF-02's 0x05F27 (docs/deviations.md).
"""
from ..model.enums import Item
from ..model.level_9_gate import (
    EIGHT_PIECES,
    GATE_ITEMS,
    OPEN_GATE,
    TRIFORCE_LEVELS,
    GateKind,
    Level9Gate,
    item_gate,
    levels_gate,
    pieces_gate,
)
from .start_items import START_ITEM_SLOTS

ENTRANCE_CHECK = 0x04AB1             # InitUnderworldPersonC's LDA InvTriforce
ENTRANCE_COMPARISON = 0x04AB4        # its CMP #$FF / BNE @Exit
ENTRANCE_ITEM_OPERAND = 0x04AB2      # the load's low address byte (PRG0 $71, InvTriforce)
ENTRANCE_ZERO_TEST = 0x04AB5         # the CMP's operand and the branch's opcode
ROUTINE = 0x05F10                    # bank 1 $9F00
ROUTINE_CPU = 0x9F00
NOP = 0xEA
JSR, LDA_ABSOLUTE = 0x20, 0xAD
ITEMS_PAGE = 0x06                    # Items, RAM $0657-$067E
ITEMS_LOW = 0x57
INV_TRIFORCE_LOW = 0x71              # InvTriforce, RAM $0671
BEQ = 0xF0

CALL_ROUTINE = bytes([JSR, ROUTINE_CPU & 0xFF, ROUTINE_CPU >> 8])
# FP-TRIF-03: the comparison after the call never refuses
NO_COMPARISON = bytes([NOP] * 4)
# FP-TRIF-06: CMP #$00 / BEQ @Exit in place of CMP #$FF / BNE @Exit: admit when the byte is not zero
ZERO_REFUSES = bytes([0x00, BEQ])


def counting_routine(pieces: int) -> bytes:
    """FP-TRIF-02: $FF when InvTriforce has at least `pieces` bits set, else $00; X kept."""
    return bytes([
        0x8A,                        # TXA               keep X, the person's slot
        0x48,                        # PHA
        0xA2, 0x00,                  # LDX #0            the pieces counted
        LDA_ABSOLUTE, INV_TRIFORCE_LOW, ITEMS_PAGE,     # LDA InvTriforce
        0x0A,                        # @Next: ASL A      the next piece into carry
        0x90, 0x01,                  # BCC @Counted
        0xE8,                        # INX
        0x09, 0x00,                  # @Counted: ORA #0  any pieces left?
        0xD0, 0xF8,                  # BNE @Next
        0xE0, pieces,                # CPX #pieces       carry set: that many or more
        0x68,                        # PLA               X back (PLA and TAX keep the carry)
        0xAA,                        # TAX
        0xA9, 0x00,                  # LDA #$00          refused
        0x90, 0x02,                  # BCC @Done
        0xA9, 0xFF,                  # LDA #$FF          admitted
        0x60,                        # @Done: RTS
    ])


def mask_routine(levels: frozenset[int]) -> bytes:
    """FP-TRIF-05: $FF when every chosen level's piece is held (bit 0 for level 1), else $00. The
    mask is its fifth and seventh byte (0x05F14 and 0x05F16)."""
    mask = sum(1 << (level - 1) for level in levels)
    return bytes([
        LDA_ABSOLUTE, INV_TRIFORCE_LOW, ITEMS_PAGE,     # LDA InvTriforce
        0x29, mask,                  # AND #mask
        0xC9, mask,                  # CMP #mask
        0xD0, 0x03,                  # BNE @Refused
        0xA9, 0xFF,                  # LDA #$FF
        0x60,                        # RTS
        0xA9, 0x00,                  # @Refused: LDA #$00
        0x60,                        # RTS
    ])


COUNT_OPERAND = ROUTINE + counting_routine(0).index(0xE0) + 1           # 0x05F20
MASK_OPERANDS = (ROUTINE + 4, ROUTINE + 6)                             # 0x05F14, 0x05F16


DEFAULT_LEVEL_WORD = "LEVEL"            # player_settings.DEFAULT_LEVEL_WORD (FP-LEVEL-01)


def chosen_levels_text(levels: frozenset[int], word: str = DEFAULT_LEVEL_WORD) -> str:
    """FP-TRIF-05's refusal text for the chosen levels, with the level word the player chose (a
    player setting, FP-LEVEL-01, which rewrites it on the finished ROM:
    player_settings.level_word_in_refusal_text). Plural by an S, unless the word ends in one."""
    numbers = " ".join(str(level) for level in sorted(levels))
    if len(levels) == 1:
        return f"YOU NEED THE TRIFORCE\nPIECE OF {word}\n{numbers}."
    plural = word if word.endswith("S") else f"{word}S"
    return f"YOU NEED THE TRIFORCE\nPIECES OF {plural}\n{numbers}."


def chosen_levels(rom: bytes | bytearray) -> frozenset[int] | None:
    """The levels a finished ROM's entrance asks for under Specific Triforces (its call and mask
    test, in PRG0's layout), or None when it asks for anything else."""
    if rom[ENTRANCE_CHECK:ENTRANCE_CHECK + len(CALL_ROUTINE)] != CALL_ROUTINE:
        return None
    mask = rom[MASK_OPERANDS[0]]
    levels = frozenset(level for level in TRIFORCE_LEVELS if mask >> (level - 1) & 1)
    routine = mask_routine(levels)
    return levels if rom[ROUTINE:ROUTINE + len(routine)] == routine else None


def parsed_gate(rom: bytes | bytearray) -> Level9Gate:
    """The gate a ROM's entrance check asks for, as this module writes it (in PRG0's layout).
    Anything else (PRG0's check, the level-4-sword entrance, another program's routine) reads as
    PRG0's eight pieces, so serializing the parsed world leaves it as it was."""
    if rom[ENTRANCE_CHECK:ENTRANCE_CHECK + len(CALL_ROUTINE)] == CALL_ROUTINE:
        pieces = rom[COUNT_OPERAND]
        routine = counting_routine(pieces)
        if rom[ROUTINE:ROUTINE + len(routine)] == routine:
            open_check = rom[ENTRANCE_COMPARISON:ENTRANCE_COMPARISON + len(NO_COMPARISON)] == NO_COMPARISON
            return OPEN_GATE if open_check and pieces == 0 else pieces_gate(pieces)
        levels = chosen_levels(rom)
        return EIGHT_PIECES if levels is None else levels_gate(levels)
    items = {inventory_low_address(item): item for item in GATE_ITEMS}
    if (rom[ENTRANCE_CHECK] == LDA_ABSOLUTE and rom[ENTRANCE_ITEM_OPERAND + 1] == ITEMS_PAGE
            and rom[ENTRANCE_ZERO_TEST:ENTRANCE_ZERO_TEST + len(ZERO_REFUSES)] == ZERO_REFUSES
            and rom[ENTRANCE_ITEM_OPERAND] in items):
        return item_gate(items[rom[ENTRANCE_ITEM_OPERAND]])
    return EIGHT_PIECES


def inventory_low_address(item: Item) -> int:
    """The low byte of the item's inventory byte's address (FP-TRIF-06: $57 the sword ... $65 the
    power bracelet)."""
    slot, _value = START_ITEM_SLOTS[item]
    return ITEMS_LOW + slot


def level_9_entrance_writes(gate: Level9Gate) -> list[tuple[int, bytes]]:
    """The gate's bytes as (file offset, bytes); none for PRG0's eight pieces."""
    if gate.is_eight_pieces:
        return []
    if gate.kind is GateKind.ITEM:
        assert gate.item is not None
        return [(ENTRANCE_ITEM_OPERAND, bytes([inventory_low_address(gate.item)])),
                (ENTRANCE_ZERO_TEST, ZERO_REFUSES)]
    if gate.kind is GateKind.LEVELS:
        return [(ENTRANCE_CHECK, CALL_ROUTINE), (ROUTINE, mask_routine(gate.levels))]
    writes = [(ENTRANCE_CHECK, CALL_ROUTINE), (ROUTINE, counting_routine(gate.pieces))]
    if gate.kind is GateKind.OPEN:
        writes.append((ENTRANCE_COMPARISON, NO_COMPARISON))
    return writes
