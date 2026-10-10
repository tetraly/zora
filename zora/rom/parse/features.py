"""The feature data: starting items and the B10 DATA values."""

from typing import Any

from ..heart_values import PRG0_START_HEART_VALUES, heart_counts
from ..layout import (
    BANK_2_FILE_START,
    CAVE_PERSON_ANIMATION_SLOTS,
    CREDITS_BANK_2_CPU_TO_FILE,
    CREDITS_LINE_12_INDEX,
    CREDITS_POINTERS_HI_ADDRESS,
    CREDITS_POINTERS_LO_ADDRESS,
    DMC_LEVEL_OPERAND_ADDRESS,
    LEVEL_NAME_DASH_OFFSET,
    LOW_HEALTH_BEEP_OPERAND_ADDRESS,
    NEW_FILE_START_STATE_ADDRESS,
    Q2_ROOM_3E_TRIGGER_ADDRESS,
    RESET_BUTTON_OPERAND_ADDRESS,
    SECOND_QUEST_START_STATE_ADDRESS,
    TEXT_SPEED_OPERAND_ADDRESS,
    TITLE_ROW_LENGTH,
    TITLE_SEED_ROW_ADDRESS,
    TITLE_VERSION_ROW_ADDRESS,
)
from ..text_encoding import BYTE_TO_CHAR as _BYTE_TO_CHAR

ITEMS_BLOCK_SIZE = 40                # Items, RAM $0657-$067E
HEART_VALUES_INDEX = 0x18            # HeartValues, RAM $066F
HEART_PARTIAL_INDEX = 0x19           # HeartPartial, RAM $0670
MAX_BOMBS_INDEX = 0x25               # MaxBombs, RAM $067C
JMP_ABSOLUTE = 0x4C
TABLE_COPY_PREFIX = bytes([0xA0, 0x27, 0xB9])   # LDY #$27 / LDA table, Y
# PRG0's immediate forms; None marks an operand byte
NEW_FILE_STORES = (0xA0, 0x18, 0xA9, None, 0x91, 0xC0, 0xC8, 0xA9, None, 0x91, 0xC0,
                   0xA0, 0x25, 0xA9, None, 0x91, 0xC0)
NEW_FILE_OPERANDS = {HEART_VALUES_INDEX: 3, HEART_PARTIAL_INDEX: 8, MAX_BOMBS_INDEX: 14}
SECOND_QUEST_STORES = (0xA9, None, 0x8D, 0x6F, 0x06, 0xCE, 0x70, 0x06, 0xA9, None, 0x8D, 0x7C, 0x06)
SECOND_QUEST_OPERANDS = {HEART_VALUES_INDEX: 1, MAX_BOMBS_INDEX: 9}
DEC_FROM_ZERO = 0xFF                 # DEC HeartPartial on the cleared block


def _bank2_offset(cpu_address: int) -> int:
    return BANK_2_FILE_START + cpu_address - 0x8000


def _starting_items(rom_bytes: bytes, site: int, stores: tuple[int | None, ...],
                    operands: dict[int, int]) -> bytes | None:
    """FP-START-01: the 40-byte Items block one starting-state routine sets.
    PRG0's routine clears the block and stores immediates; a routine that
    jumps to a table copy sets the table. None when the site is neither."""
    code = rom_bytes[site:site + len(stores)]
    if code[0] == JMP_ABSOLUTE:
        target = _bank2_offset(code[1] | code[2] << 8)
        copy = rom_bytes[target:target + len(TABLE_COPY_PREFIX) + 2]
        if copy[:len(TABLE_COPY_PREFIX)] != TABLE_COPY_PREFIX:
            return None
        table = _bank2_offset(copy[-2] | copy[-1] << 8)
        return rom_bytes[table:table + ITEMS_BLOCK_SIZE]
    if any(want is not None and got != want for got, want in zip(code, stores, strict=True)):
        return None
    items = bytearray(ITEMS_BLOCK_SIZE)
    if HEART_PARTIAL_INDEX not in operands:
        items[HEART_PARTIAL_INDEX] = DEC_FROM_ZERO
    for index, at in operands.items():
        items[index] = code[at]
    return bytes(items)


def _parse_b10_data(rom_bytes: bytes | None, tile_mapping_pointers: bytes,
                    refusal_quote: str) -> dict[str, Any]:
    """Read back the B10 DATA fields that checkpoints need from a finished ROM."""
    if rom_bytes is None:
        return {
            "credits_pointers": (0xAD33, 0xAD4D, 0xAD59, 0xAD72),
            "title_seed_number": 0,
            "title_version_line": "",
            "cave_person_animations": (),
            "level9_refusal_text": "",
            "starting_items_new_file": None,
            "new_file_heart_containers": 3,
            "new_file_full_hearts": 3,
            "starting_items_second_quest": None,
            "reset_controller1": 0xFB,
            "text_speed_value": 0x06,
            "low_health_beep_value": 0x40,
            "dmc_level_value": 0x7F,
            "q2_room_trigger_value": 0x06,
            "level_dash_tile": 0x62,
        }

    lo_start = CREDITS_POINTERS_LO_ADDRESS + CREDITS_LINE_12_INDEX
    hi_start = CREDITS_POINTERS_HI_ADDRESS + CREDITS_LINE_12_INDEX
    credits_pointers = tuple(
        rom_bytes[lo_start + i] | (rom_bytes[hi_start + i] << 8)
        for i in range(4)
    )

    # FP-LOCK-02's Check: the record line 15 addresses (its length byte, column byte and tiles)
    line_15 = CREDITS_BANK_2_CPU_TO_FILE + credits_pointers[3]
    line_15_record = bytes(rom_bytes[line_15:line_15 + 2 + rom_bytes[line_15]])

    cave_person_animations = tuple(
        tile_mapping_pointers[slot] for slot in CAVE_PERSON_ANIMATION_SLOTS
    )

    # Title row 1: a label on the left, then the seed number right-aligned.
    row1 = rom_bytes[TITLE_SEED_ROW_ADDRESS:TITLE_SEED_ROW_ADDRESS + TITLE_ROW_LENGTH]
    seed_digits: list[int] = []
    for tile in reversed(row1):
        if 0x00 <= tile <= 0x09:
            seed_digits.append(tile)
        elif tile == 0x24:
            if seed_digits:
                break
        else:
            break
    seed_num = int("".join(str(d) for d in reversed(seed_digits))) if seed_digits else 0

    # Title row 2: centered version line.
    row2 = rom_bytes[TITLE_VERSION_ROW_ADDRESS:TITLE_VERSION_ROW_ADDRESS + TITLE_ROW_LENGTH]
    # Blank tiles inside the line are spaces; only the centering is stripped.
    version_line = "".join(_BYTE_TO_CHAR.get(b, "") for b in row2).strip()

    # Level-9 refusal text: whatever person-text slot 34 points at (FP-TRIF-01).
    refusal = refusal_quote.replace("|", "\n")

    # FP-START-01 and FL-ALT-02: HeartValues as a new file starts (PRG0's when unrecognized)
    new_file_items = _starting_items(rom_bytes, NEW_FILE_START_STATE_ADDRESS, NEW_FILE_STORES, NEW_FILE_OPERANDS)
    new_file_hearts = heart_counts(PRG0_START_HEART_VALUES if new_file_items is None
                                   else new_file_items[HEART_VALUES_INDEX])

    return {
        "credits_pointers": credits_pointers,
        "credits_line_15_record": line_15_record,
        "title_seed_number": seed_num,
        "title_version_line": version_line,
        "cave_person_animations": cave_person_animations,
        "level9_refusal_text": refusal,
        "starting_items_new_file": new_file_items,
        "new_file_heart_containers": new_file_hearts[0],
        "new_file_full_hearts": new_file_hearts[1],
        "starting_items_second_quest": _starting_items(
            rom_bytes, SECOND_QUEST_START_STATE_ADDRESS, SECOND_QUEST_STORES, SECOND_QUEST_OPERANDS
        ),
        "reset_controller1": rom_bytes[RESET_BUTTON_OPERAND_ADDRESS],
        "text_speed_value": rom_bytes[TEXT_SPEED_OPERAND_ADDRESS],
        "low_health_beep_value": rom_bytes[LOW_HEALTH_BEEP_OPERAND_ADDRESS],
        "dmc_level_value": rom_bytes[DMC_LEVEL_OPERAND_ADDRESS],
        "q2_room_trigger_value": rom_bytes[Q2_ROOM_3E_TRIGGER_ADDRESS],
        "level_dash_tile": rom_bytes[LEVEL_NAME_DASH_OFFSET],
    }
