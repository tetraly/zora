"""The feature data: B10 constants, credits, the refusal text and the title."""

from zora.model.game_world import GameWorld
from zora.rom.heart_values import PRG0_START_HEART_VALUES, heart_values
from zora.rom.layout import (
    CREDITS_BLANK_TILE,
    CREDITS_FREE_SPACE_ADDRESS,
    CREDITS_LINE_12_INDEX,
    CREDITS_POINTERS_HI_ADDRESS,
    CREDITS_POINTERS_LO_ADDRESS,
    DMC_LEVEL_OPERAND_ADDRESS,
    LEVEL_NAME_DASH_OFFSET,
    LOW_HEALTH_BEEP_OPERAND_ADDRESS,
    NEW_FILE_HEART_VALUES_OPERAND_ADDRESS,
    Q2_ROOM_3E_TRIGGER_ADDRESS,
    REFUSAL_TEXT_ADDRESS,
    REFUSAL_TEXT_POINTER,
    REFUSAL_TEXT_POINTER_ADDRESS,
    REFUSAL_TEXT_SIZE,
    RESET_BUTTON_OPERAND_ADDRESS,
    SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS,
    TEXT_SPEED_OPERAND_ADDRESS,
    TITLE_ROW_LENGTH,
    TITLE_SEED_ROW_ADDRESS,
    TITLE_VERSION_ROW_ADDRESS,
)
from zora.rom.serialize.patch import Patch
from zora.rom.serialize.text import QUOTE_PAD_CHARS, _encode_quote
from zora.rom.text_encoding import CHAR_TO_BYTE as _CHAR_TO_BYTE
from zora.version import PLAYER_NAME

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
    patch.add(Q2_ROOM_3E_TRIGGER_ADDRESS, bytes([game_world.q2_room_trigger_value]))
    patch.add(LEVEL_NAME_DASH_OFFSET, bytes([game_world.level_dash_tile]))


def _serialize_new_file_hearts(game_world: GameWorld, patch: Patch) -> None:
    """FP-START-01 and FL-ALT-02: the HeartValues a new save file and the second-quest switch
    store. PRG0's routines are left alone at PRG0's $22 (FP-START-01 allows it); another value
    replaces the immediate in both, so every start sets the same hearts."""
    value = heart_values(game_world.new_file_heart_containers, game_world.new_file_full_hearts)
    if value == PRG0_START_HEART_VALUES:
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
        bytes([0x1E, 0x24]) + bytes([CREDITS_BLANK_TILE] * 30),  # line 12: col 36, length 30
        bytes([0x06, 0x0D]) + bytes([CREDITS_BLANK_TILE] * 6),   # line 13: col 13, length 6
        bytes([0x17, 0x04]) + bytes([CREDITS_BLANK_TILE] * 23),  # line 14: col 4, length 23
    )
    offset = base
    for record in records:
        patch.add(offset, record)
        offset += len(record)


def _serialize_refusal_text(game_world: GameWorld, patch: Patch) -> None:
    """FP-TRIF-01: the level-9 refusal text goes outside the generated hint
    block and person-text slot 34 points at it (hints-behavior.md HT-TEXT-02:
    slot 34's final pointer is replaced by another pass). The pointer lies
    inside the quotes block, so this runs after the quotes."""
    # The parsed text keeps the centering pad ("~", tile $25); strip it so
    # re-centering a parsed world writes the same bytes (round-trip identity).
    lines = (line.strip(QUOTE_PAD_CHARS) for line in game_world.level9_refusal_text.split("\n"))
    text = bytes(_encode_quote("|".join(lines), center=True))
    if len(text) > REFUSAL_TEXT_SIZE:
        raise ValueError(f"refusal text takes {len(text)} bytes; {REFUSAL_TEXT_SIZE} fit")
    patch.add(REFUSAL_TEXT_ADDRESS, text)
    patch.add(REFUSAL_TEXT_POINTER_ADDRESS, REFUSAL_TEXT_POINTER)


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


def _serialize_title(game_world: GameWorld, patch: Patch) -> None:
    """FP-TITLE-01: seed number right-aligned, plus ZORA's version line."""
    seed_str = str(game_world.title_seed_number)
    # short label on the left; seed number right-aligned
    label = "SEED"
    available = TITLE_ROW_LENGTH - len(label)
    seed_tiles = [_CHAR_TO_BYTE[ch] for ch in seed_str]
    leading = available - len(seed_tiles)
    row1 = ([_CHAR_TO_BYTE[ch] for ch in label]
            + [CREDITS_BLANK_TILE] * leading
            + seed_tiles)
    if len(row1) > TITLE_ROW_LENGTH:
        row1 = row1[:TITLE_ROW_LENGTH]
    patch.add(TITLE_SEED_ROW_ADDRESS, bytes(row1))

    version = game_world.title_version_line or PLAYER_NAME
    patch.add(TITLE_VERSION_ROW_ADDRESS, _encode_title_row(version))
