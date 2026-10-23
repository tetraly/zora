"""The feature data: B10 constants, credits, the refusal text and the title."""

from ...model.game_world import GameWorld
from ...version import PLAYER_NAME
from ..heart_values import PRG0_START_HEART_VALUES, heart_values
from ..layout import (
    CONTINUE_HEARTS_OPERAND_ADDRESS,
    CREDITS_BLANK_TILE,
    CREDITS_FREE_SPACE_ADDRESS,
    CREDITS_LINE_12_INDEX,
    CREDITS_POINTERS_HI_ADDRESS,
    CREDITS_POINTERS_LO_ADDRESS,
    DMC_LEVEL_OPERAND_ADDRESS,
    HEART_METER_BLANK_BRANCH_ADDRESS,
    LEVEL_NAME_DASH_OFFSET,
    LOW_HEALTH_BEEP_OPERAND_ADDRESS,
    NEW_FILE_HEART_VALUES_OPERAND_ADDRESS,
    NORMAL_REFUSAL_TEXT_ADDRESS,
    NORMAL_REFUSAL_TEXT_POINTER,
    Q2_ROOM_3E_TRIGGER_ADDRESS,
    REFUSAL_TEXT_ADDRESS,
    REFUSAL_TEXT_POINTER,
    REFUSAL_TEXT_POINTER_ADDRESS,
    REFUSAL_TEXT_SIZE,
    RESET_BUTTON_OPERAND_ADDRESS,
    SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS,
    TEXT_SPEED_OPERAND_ADDRESS,
    TITLE_ROW_LENGTH,
    TITLE_SEED_DIGITS,
    TITLE_SEED_LABEL,
    TITLE_SEED_ROW_ADDRESS,
    TITLE_VERSION_ROW_ADDRESS,
)
from ..text_encoding import CHAR_TO_BYTE as _CHAR_TO_BYTE
from .patch import Patch
from .text import QUOTE_PAD_CHARS, _encode_quote

# ---------------------------------------------------------------------------
# B10 DATA serialization
# ---------------------------------------------------------------------------

def _serialize_b10_constants(game_world: GameWorld, patch: Patch) -> None:
    """Write the B10 DATA items that are constant under the preset. With level
    encoding on, the encoding (a final ROM step) replaces FP-Q2R-01's byte
    with its key material (the spec allows it: the byte is never read)."""
    patch.add(RESET_BUTTON_OPERAND_ADDRESS, bytes([game_world.reset_controller1]))
    patch.add(TEXT_SPEED_OPERAND_ADDRESS, bytes([game_world.text_speed_value]))
    patch.add(LOW_HEALTH_BEEP_OPERAND_ADDRESS, bytes([game_world.low_health_beep_value]))
    patch.add(DMC_LEVEL_OPERAND_ADDRESS, bytes([game_world.dmc_level_value]))
    if game_world.levels[0].block is not game_world.blocks_2q[0]:
        # FP-Q2R-01; with levels 1-6 second quest (Dungeon Quest) the room is a level-5 room
        # whose trigger the passes set (PS-VAN-02 starts it at $01)
        patch.add(Q2_ROOM_3E_TRIGGER_ADDRESS, bytes([game_world.q2_room_trigger_value]))
    patch.add(LEVEL_NAME_DASH_OFFSET, bytes([game_world.level_dash_tile]))


def _serialize_new_file_hearts(game_world: GameWorld, patch: Patch, start_table_written: bool) -> None:
    """FP-START-01 and FL-ALT-02: the HeartValues a new save file and the second-quest switch
    store. PRG0's routines are left alone at PRG0's $22 (FP-START-01 allows it); another value
    replaces the immediate in both, so every start sets the same hearts. With start items or
    start pieces the routines jump to fp-start-02's table instead, whose hearts byte holds the
    value (the start table, which _serialize_overworld_data writes only with the B10 data:
    start_table_written; without it the immediates carry the hearts, or the ROM would start with
    PRG0's three while the life toll counts the seed's)."""
    # FL-ALT-07: the hearts a Continue restores, and the one-heart meter (PRG0's bytes otherwise)
    patch.add(CONTINUE_HEARTS_OPERAND_ADDRESS, bytes([game_world.continue_hearts_operand]))
    patch.add(HEART_METER_BLANK_BRANCH_ADDRESS, bytes([game_world.heart_meter_blank_branch]))
    value = heart_values(game_world.new_file_heart_containers, game_world.new_file_full_hearts)
    if value == PRG0_START_HEART_VALUES or start_table_written:
        return
    patch.add(NEW_FILE_HEART_VALUES_OPERAND_ADDRESS, bytes([value]))
    patch.add(SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS, bytes([value]))


def _serialize_credits(game_world: GameWorld, patch: Patch) -> None:
    """FP-LOCK-02: replace lines 12-14 with blank records; keep line 15."""
    pointers = game_world.credits_pointers
    lo = bytearray(4)
    hi = bytearray(4)
    for i, ptr in enumerate(pointers):
        lo[i] = ptr & 0xFF
        hi[i] = (ptr >> 8) & 0xFF
    patch.add(CREDITS_POINTERS_LO_ADDRESS + CREDITS_LINE_12_INDEX, bytes(lo))
    patch.add(CREDITS_POINTERS_HI_ADDRESS + CREDITS_LINE_12_INDEX, bytes(hi))

    # Write the three replacement records in bank-2 free space.
    base = CREDITS_FREE_SPACE_ADDRESS
    records = (
        # line 12: one blank tile at column 0, inside the 32-tile row (30 tiles from column 36
        # overran DynTileBuf; docs/reports/ending-text.md); the slot keeps its 32 bytes
        bytes([0x01, 0x00]) + bytes([CREDITS_BLANK_TILE] * 30),
        bytes([0x06, 0x0D]) + bytes([CREDITS_BLANK_TILE] * 6),   # line 13: col 13, length 6
        bytes([0x17, 0x04]) + bytes([CREDITS_BLANK_TILE] * 23),  # line 14: col 4, length 23
    )
    offset = base
    for record in records:
        patch.add(offset, record)
        offset += len(record)


def encoded_refusal_text(refusal_text: str) -> bytes:
    """The level-9 refusal text's bytes: each line centered, at most REFUSAL_TEXT_SIZE. The
    parsed text keeps the centering pad ("~", tile $25); it is stripped, so re-centering a parsed
    world writes the same bytes (round-trip identity). The level word rewrites it with this too
    (player_settings.level_word_in_refusal_text)."""
    lines = (line.strip(QUOTE_PAD_CHARS) for line in refusal_text.split("\n"))
    text = bytes(_encode_quote("|".join(lines), center=True))
    if len(text) > REFUSAL_TEXT_SIZE:
        raise ValueError(f"refusal text takes {len(text)} bytes; {REFUSAL_TEXT_SIZE} fit")
    return text


def _serialize_refusal_text(game_world: GameWorld, patch: Patch, normal_hints: bool = False) -> None:
    """FP-TRIF-01: the level-9 refusal text goes outside the generated hint
    block and person-text slot 34 points at it (hints-behavior.md HT-TEXT-02:
    slot 34's final pointer is replaced by another pass). The pointer lies
    inside the quotes block, so this runs after the quotes. Under normal hints (HT-HINT-05) PRG0's
    block is in use, so the text goes outside it, at the normal-hints place ($B780)."""
    address, pointer = ((NORMAL_REFUSAL_TEXT_ADDRESS, NORMAL_REFUSAL_TEXT_POINTER) if normal_hints
                        else (REFUSAL_TEXT_ADDRESS, REFUSAL_TEXT_POINTER))
    patch.add(address, encoded_refusal_text(game_world.level9_refusal_text))
    patch.add(REFUSAL_TEXT_POINTER_ADDRESS, pointer)


def _encode_title_row(text: str) -> bytes:
    """Centered 24-tile title row using the game's character encoding."""
    cleaned = "".join(
        ch.upper() if ch.isalpha() else ch
        for ch in text
        if ch.upper() in _CHAR_TO_BYTE and ch != ","
    )
    if len(cleaned) > TITLE_ROW_LENGTH:
        cleaned = cleaned[:TITLE_ROW_LENGTH]
    pad = (TITLE_ROW_LENGTH - len(cleaned)) // 2
    tiles = [CREDITS_BLANK_TILE] * pad + [_CHAR_TO_BYTE[ch] for ch in cleaned]
    tiles += [CREDITS_BLANK_TILE] * (TITLE_ROW_LENGTH - len(tiles))
    return bytes(tiles)


def title_seed_digits(seed: int) -> str:
    """The seed number as the title screen shows it: at most TITLE_SEED_DIGITS digits, a longer
    (20-digit) number's first ones, so a blank always follows SEED."""
    return str(seed)[:TITLE_SEED_DIGITS]


def _serialize_title(game_world: GameWorld, patch: Patch) -> None:
    """FP-TITLE-01: SEED on the left, the seed number right-aligned (title_seed_digits), plus
    ZORA's version line."""
    seed_tiles = [_CHAR_TO_BYTE[ch] for ch in title_seed_digits(game_world.title_seed_number)]
    label_tiles = [_CHAR_TO_BYTE[ch] for ch in TITLE_SEED_LABEL]
    blanks = [CREDITS_BLANK_TILE] * (TITLE_ROW_LENGTH - len(label_tiles) - len(seed_tiles))
    patch.add(TITLE_SEED_ROW_ADDRESS, bytes(label_tiles + blanks + seed_tiles))

    version = game_world.title_version_line or PLAYER_NAME
    patch.add(TITLE_VERSION_ROW_ADDRESS, _encode_title_row(version))
