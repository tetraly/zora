"""Per-level mode's per-seed bytes in an Archipelago game's ROM (docs/design/archipelago-items.md piece 6).

asm/flags2/ap-items draws and takes the generic compass, map and Triforce piece far (as level 9's compass
and map and level 8's piece) when the fixed-bank block's first byte, `ApItemsPerLevelMode`, is nonzero, and
draws each per-level item with its level's digit. The far segment starts with the seed's data: the number
the status bar shows for each data level, then the font's digits 1-9 as one bit plane each, taken from the
ROM being written so a custom font carries over."""
from collections.abc import Sequence

from .layout import BOMB_COUNT_OFFSET

Writes = list[tuple[int, bytes]]

PER_LEVEL_MODE = 0x1FD92                # bank 7 $FD82: ApItemsPerLevelMode, the fixed-bank block's first byte
PER_LEVEL_ON = 0x01
SELLER_MODE = 0x1FD93                   # bank 7 $FD83: ApItemsSellerMode, the block's second byte (piece 8)
SELLER_ON = 0x01
BOMB_UPGRADE_COUNT = 0x1FD94            # bank 7 $FD84: ApItemsBombUpgradeCount, the block's third byte
SEED_DATA = 0x19D80                     # bank 6 $9D70: the far segment's start (asm/placements.toml)
# bank 6 $AD80: asm/flags2/level-compass's segment start (asm/placements.toml), LevelCompassRooms: for each data
# level 1-8 the room whose item-taken flag its compass marker follows
COMPASS_ROOMS = 0x1AD90
MARKED_LEVELS = 8                       # level 9's marker is the game's
LEVELS = 9
DIGITS = range(1, 10)
GLYPH_ROWS = 8
TILE_BYTES = 16
# CommonBackgroundPatterns (bank 2): the font's digit n is tile n, its low plane then its high plane
COMMON_BACKGROUND_PATTERNS = 0x0878F


def digit_glyph(rom: bytes | bytearray, digit: int) -> bytes:
    """The font's digit as one bit plane: a pixel is set where either plane is."""
    tile = rom[COMMON_BACKGROUND_PATTERNS + digit * TILE_BYTES:][:TILE_BYTES]
    return bytes(low | high for low, high in zip(tile[:GLYPH_ROWS], tile[GLYPH_ROWS:], strict=True))


def per_level_writes(shown: Sequence[int], rom: bytes | bytearray) -> Writes:
    """Per-level mode on, with the status bar's number of each data level 1-9 and `rom`'s font."""
    if len(shown) != LEVELS or not set(shown) <= set(DIGITS):
        raise ValueError(f"per-level mode needs nine level numbers 1-9, not {tuple(shown)}")
    glyphs = b"".join(digit_glyph(rom, digit) for digit in DIGITS)
    return [(PER_LEVEL_MODE, bytes([PER_LEVEL_ON])), (SEED_DATA, bytes(shown) + glyphs)]


def compass_room_writes(rooms: Sequence[int]) -> Writes:
    """Per-level mode's compass marker (asm/flags2/level-compass): for each data level 1-8, the room whose item it
    blinks until taken, the marked room or the item cellar under it (finish.compass_item_rooms)."""
    if len(rooms) != MARKED_LEVELS or not all(0 <= room < 0x80 for room in rooms):
        raise ValueError(f"the compass marker needs eight rooms $00-$7F, not {tuple(rooms)}")
    return [(COMPASS_ROOMS, bytes(rooms))]


def bomb_upgrade_writes(rom: bytes | bytearray, sellers: bool) -> Writes:
    """Piece 8, in every ROM with the patch: a Bomb Upgrade item ($37) raises MaxBombs by the upgraders' own count,
    read from their code in `rom` (B12, B90 wrote it); with `sellers`, seller mode on: each bomb upgrader's room
    byte holds his place's item, which he shows and gives for his price."""
    writes = [(BOMB_UPGRADE_COUNT, bytes([rom[BOMB_COUNT_OFFSET]]))]
    return [*writes, (SELLER_MODE, bytes([SELLER_ON]))] if sellers else writes
