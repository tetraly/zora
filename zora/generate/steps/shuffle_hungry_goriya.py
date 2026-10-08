"""Shuffle Hungry Goriya (B28; PS-GRUM-01 to -03)."""

from zora.generate.rng import IntRng
from zora.generate.shapes.world import GRID_COLS, blocks_of
from zora.generate.steps.item_shuffle_result import ItemShuffleResult, LevelRoom, _level_rooms
from zora.model.enums import Enemy
from zora.model.levels import LEVEL_9, Level
from zora.model.rooms import RoomPlace

# --- PS-GRUM ---------------------------------------------------------------

# PS-GRUM-03: the goriya's first sprite tile, ObjAnimFrameHeap + 171.
GORIYA_TILE_INDEX = 171
_TILES_A = (0xA0, 0xA8, 0xAC, 0xB0)
# PS-GRUM-03: the pre-shapes draw's value mod 4 picks from this order.
PRE_SHAPES_TILES = (0xAC, 0xA0, 0xA8, 0xB0)
GORIYA_TILES = {1: _TILES_A, 2: _TILES_A, 7: _TILES_A,
                3: (0xA4, 0xB0), 5: (0xA4, 0xB0), 8: (0xA4, 0xB0),
                4: (0xB4,), 6: (0xB4,), 9: (0xB4,)}


# --- PS-GRUM ---------------------------------------------------------------

def _level9_entry_north(levels: list[Level]) -> RoomPlace | None:
    """The cell one row north of level 9's entrance."""
    for block_index, block in enumerate(blocks_of(levels)):
        for level in levels:
            if level.block is block and level.level_num == LEVEL_9:
                return RoomPlace(block_index, level.entrance_room - GRID_COLS)
    return None


def shuffle_hungry_goriya(levels: list[Level], state: ItemShuffleResult, rng: IntRng) -> None:
    """PS-GRUM-01..03: one uniform draw over eligible person rooms, then
    grumble rooms (scan order); an eligible pick swaps whole monster and
    layout bytes with the FIRST grumble room, then the goriya's first
    sprite tile is redrawn from its new level's list."""
    skip = _level9_entry_north(levels)
    eligible: list[LevelRoom] = []
    grumble: list[LevelRoom] = []
    for level_room in _level_rooms(levels):
        room = level_room.room
        if room.enemy == Enemy.HUNGRY_GORIYA:
            grumble.append(level_room)
        elif room.is_person and level_room.key != skip:
            eligible.append(level_room)
    combined = eligible + grumble
    if not combined:
        return
    pick = rng.below(len(combined))
    if pick >= len(eligible) or not grumble:
        return
    person, goriya = combined[pick].room, grumble[0].room
    # the monster byte (list and count bits) and the layout byte (layout,
    # push bit and the person flag, which belongs to the enemy code) travel
    # together
    person.enemy_info, goriya.enemy_info = goriya.enemy_info, person.enemy_info
    person.layout_info, goriya.layout_info = goriya.layout_info, person.layout_info
    state.goriya_swapped = True
    new_level = combined[pick].level.level_num
    state.goriya_level = new_level
    tiles = GORIYA_TILES.get(new_level, _TILES_A)
    state.goriya_tile = tiles[rng.below(len(tiles))]
