"""Post-shapes pass B5: the dungeon color sets (docs/spec/post-shapes-b5.md
@ a123227, PS-COLOR-01..03).

Runs after the hint assignment and immediately before the boss shuffle.
Nine of 23 candidate color-set pairs are drawn without replacement and
given to levels 1-9. Room palette selectors are never touched
(PS-COLOR-01). The draw is staged and written into the GameWorld when the
generation pass ships (generation_pass.py), so candidates are always built from the
base ROM's own sets.
"""
from collections.abc import Iterable
from dataclasses import dataclass

from ...model.enums import Enemy, RoomType
from ...model.game_world import GameWorld
from ...model.levels import LevelBlock
from ...model.rooms import Room
from ..rng import IntRng, discard

ColorPair = tuple[bytes, bytes]                  # (set 1: 32 bytes, set 2: 96 bytes)

DISCARDED_DRAWS = 3
CANDIDATE_LEVELS = range(1, 9)                   # levels 1-8's own pairs
LOW_NIBBLE = 0x0F
RAISED_FROM, RAISED_TO = 0x0C, 0x04              # the clone: low nibble $C -> $4
# Template variants: set 1 bytes 8-15, set 2 bytes 0-7 and 64-71 take the
# eight colors; set 1 bytes 28-31 the first four.
EIGHT_COLOR_SPANS = ((0, slice(8, 16)), (1, slice(0, 8)), (1, slice(64, 72)))
FOUR_COLOR_SPAN = (0, slice(28, 32))
# Then every position whose ORIGINAL first-pair byte is 12, 28 or 44 takes
# the template's 2nd, 3rd or 4th color (last, so it wins).
VALUE_TO_TEMPLATE_INDEX = {12: 1, 28: 2, 44: 3}
TEMPLATES = (
    (15, 17, 33, 60, 15, 18, 33, 60),
    (15, 17, 33, 60, 15, 17, 33, 60),
    (15, 11, 26, 41, 15, 24, 26, 41),
    (15, 11, 26, 41, 15, 18, 26, 41),
    (15, 24, 40, 56, 15, 22, 40, 56),
    (15, 24, 40, 56, 15, 24, 40, 56),
    (15, 4, 21, 38, 15, 4, 21, 38),
    (15, 14, 45, 61, 15, 10, 45, 61),
    (15, 14, 45, 61, 15, 7, 45, 61),
    (15, 0, 29, 19, 15, 4, 29, 19),
    (15, 29, 24, 61, 15, 9, 24, 61),
    (15, 61, 34, 32, 15, 49, 34, 32),
    (15, 5, 36, 48, 15, 50, 36, 48),
    (15, 1, 45, 61, 15, 15, 1, 61),
)
DUNGEON_LEVELS = range(1, 10)


def _raised_clone(pair: ColorPair) -> ColorPair:
    def raise_bytes(data: bytes) -> bytes:
        return bytes((value & ~LOW_NIBBLE) | RAISED_TO if value & LOW_NIBBLE == RAISED_FROM else value
                     for value in data)
    return raise_bytes(pair[0]), raise_bytes(pair[1])


def _template_variant(first: ColorPair, template: tuple[int, ...]) -> ColorPair:
    sets = [bytearray(first[0]), bytearray(first[1])]
    for which, span in EIGHT_COLOR_SPANS:
        sets[which][span] = bytes(template)
    which, span = FOUR_COLOR_SPAN
    sets[which][span] = bytes(template[:4])
    for original, current in zip(first, sets, strict=True):
        for position, value in enumerate(original):
            if value in VALUE_TO_TEMPLATE_INDEX:
                current[position] = template[VALUE_TO_TEMPLATE_INDEX[value]]
    return bytes(sets[0]), bytes(sets[1])


def color_candidates(gw: GameWorld) -> list[ColorPair]:
    """PS-COLOR-02's 23 candidates: levels 1-8's pairs as read, the first
    pair's raised clone, and 14 template variants of the first pair."""
    level_pairs = [gw.levels[level - 1].color_sets for level in CANDIDATE_LEVELS]
    first = level_pairs[0]
    return (level_pairs + [_raised_clone(first)]
            + [_template_variant(first, template) for template in TEMPLATES])


@dataclass
class DungeonPaletteResult:
    picks: list[int]                             # candidate index per level 1-9
    pairs: list[ColorPair]


def shuffle_dungeon_palettes(gw: GameWorld, rng: IntRng) -> DungeonPaletteResult:
    """PS-COLOR-02: nine distinct candidates, uniformly without
    replacement, for levels 1-9 in order. Stream note (non-normative): a
    full Fisher-Yates over the 23 indices whose position 0 is unused."""
    candidates = color_candidates(gw)
    discard(rng, DISCARDED_DRAWS)
    order = list(range(len(candidates)))
    for position in range(len(order) - 1, 0, -1):
        other = rng.below(position + 1)
        order[position], order[other] = order[other], order[position]
    picks = order[1:1 + len(DUNGEON_LEVELS)]
    return DungeonPaletteResult(picks, [candidates[pick] for pick in picks])


def apply_dungeon_palettes(gw: GameWorld, state: DungeonPaletteResult) -> None:
    for level, pair in zip(DUNGEON_LEVELS, state.pairs, strict=True):
        gw.levels[level - 1].set_color_sets(*pair)


# --- PS-COLOR-04: Blackout (B50) -------------------------------------------------------------------
# Level 1's two sets as they stand (PRG0's), darkened: these bytes become $0E first, then every
# colour of the $xC column ($0C, $1C, $2C) its $xE neighbour
BLACKOUT_FIRST_SET_DARKENED = (13,)               # in the 32-byte set
BLACKOUT_SECOND_SET_DARKENED = (5, 69)            # in the 96-byte set
BLACKOUT_DARK = 0x0E
DARKENED_COLUMN = {0x0C: 0x0E, 0x1C: 0x1E, 0x2C: 0x2E}
# One accent per level, uniform over these, at byte 11 of the 32-byte set and byte 3 of the 96-byte set
BLACKOUT_ACCENTS = (0x21, 0x1A, 0x28, 0x15, 0x3B, 0x18, 0x22, 0x24, 0x0C, 0x08, 0x11)
FIRST_SET_ACCENT, SECOND_SET_ACCENT = 11, 3
# The inner palette selector every room takes, but the three layouts below
BLACKOUT_INNER_SELECTOR = 3
LAYOUTS_KEEPING_THEIR_SELECTOR = frozenset({RoomType.BLACK_ROOM, RoomType.TRANSPORT_STAIRCASE,
                                            RoomType.ITEM_STAIRCASE})
GANON_MONSTER_BYTE = Enemy.THE_BEAST


def _darkened(data: bytes, darkened: tuple[int, ...]) -> bytearray:
    out = bytearray(data)
    for position in darkened:
        out[position] = BLACKOUT_DARK
    return bytearray(DARKENED_COLUMN.get(value, value) for value in out)


def blackout_palettes(gw: GameWorld, rng: IntRng) -> DungeonPaletteResult:
    """PS-COLOR-04's colour sets, in the colour pass's place (whatever B27 is): level 1's pair
    darkened, then for each of levels 1 to 9 one accent drawn uniformly from BLACKOUT_ACCENTS, after
    three discarded draws. The nine levels share the darkened pair and differ only in their accent."""
    first, second = gw.levels[0].color_sets
    dark_first = _darkened(first, BLACKOUT_FIRST_SET_DARKENED)
    dark_second = _darkened(second, BLACKOUT_SECOND_SET_DARKENED)
    discard(rng, DISCARDED_DRAWS)
    pairs: list[ColorPair] = []
    for _level in DUNGEON_LEVELS:
        accent = BLACKOUT_ACCENTS[rng.below(len(BLACKOUT_ACCENTS))]
        dark_first[FIRST_SET_ACCENT] = dark_second[SECOND_SET_ACCENT] = accent
        pairs.append((bytes(dark_first), bytes(dark_second)))
    return DungeonPaletteResult([], pairs)


def _keeps_its_dark_flag(room: Room) -> bool:
    """PS-COLOR-04's one exception: Ganon's room, its monster byte exactly $3E with the layout
    byte's bit 7 clear."""
    return room.monster_byte == GANON_MONSTER_BYTE and not room.has_monster_bit


def black_out_rooms(blocks: Iterable[LevelBlock]) -> None:
    """PS-COLOR-04's room writes: every room loses its dark flag (Ganon's aside), and every room whose
    layout byte without bit 7 is not a person room, a transport staircase or an item cellar takes
    inner palette selector 3. The outer selectors are not written."""
    for block in blocks:
        for room in block.rooms:
            if not _keeps_its_dark_flag(room):
                room.is_dark = False
            if room.movable_block or room.room_type not in LAYOUTS_KEEPING_THEIR_SELECTOR:
                room.palette_1 = BLACKOUT_INNER_SELECTOR
