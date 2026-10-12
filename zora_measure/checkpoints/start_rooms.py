"""Shuffle Dungeon Start Room (B26; post-shapes-b9.md PS-START, acceptance.md VA-REJ-21): the
Checks measured on finished ROMs, against the original randomizer's b26 corpus
(corpus("b26"); hash manifest in docs/spec/)."""
from collections import Counter

from zora.generate.acceptance_check import start_room_is_own_door
from zora.model import room_grid
from zora.model.enums import Side, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import Level
from zora.rom.code_patches import EXIT_ROOM_COUNT_FLAG, LEVEL_INFO_ARRIVAL_CODE, LEVEL_INFO_EXIT_ROOM_COUNT

SPEC_PS_START = "post-shapes-b9.md @ 52de2dd"
SPEC_E9 = "acceptance.md @ 2a3bf70"
# The b26 corpus's flag string: the MVP baseline's with B26 on
START_ROOM_SWAP_FLAGS = "8hq4BeR2oTx3ebLWKBddefzLRrUJ3A"
ARRIVAL_SIDES = {1: Side.NORTH, 2: Side.SOUTH, 3: Side.WEST, 4: Side.EAST}
STAIRWAY_DATA_START = 0x34            # Level.stairway_data_raw holds level information $34-$3D
LEVEL_9 = 9
ARRIVAL_KEYS = (*(f"L1-8 code {code}" for code in ARRIVAL_SIDES), "L9 code 2", "L9 bottom row", "L9 higher")


def arrival_code(level: Level) -> int:
    """Level information +$3D, FP-ENTR-01's arrival code."""
    return level.stairway_data_raw[LEVEL_INFO_ARRIVAL_CODE - STAIRWAY_DATA_START]


def stored_exit_room(level: Level) -> int:
    """Level information +$23 without its bit 7 (FP-ENTR-02, PS-START-03)."""
    return level.palette_raw[LEVEL_INFO_EXIT_ROOM_COUNT] & ~EXIT_ROOM_COUNT_FLAG


def arrival_codes(gw: GameWorld) -> Counter[str]:
    """PS-START-01's Check: the arrival codes of levels 1-8, level 9's, and level 9's start row."""
    counts: Counter[str] = Counter()
    for level in gw.levels:
        code = arrival_code(level)
        if level.level_num != LEVEL_9:
            counts[f"L1-8 code {code}"] += 1
            continue
        counts[f"L9 code {code}"] += 1
        on_bottom = room_grid.row(level.entrance_room) == room_grid.ROWS - 1
        counts["L9 bottom row" if on_bottom else "L9 higher"] += 1
    return counts


def _open_side(level: Level) -> Side | None:
    return ARRIVAL_SIDES.get(arrival_code(level))


def start_rooms_open_on_their_side(gw: GameWorld) -> tuple[int, int]:
    """PS-START-02's Check: levels whose start room is in the level, with the arrival side's door
    open."""
    hits = 0
    for level in gw.levels:
        side = _open_side(level)
        room = level.block.room(level.entrance_room)
        hits += (side is not None and level.entrance_room in level.room_nums
                 and room.walls[side] == WallType.OPEN_DOOR)
    return hits, len(gw.levels)


def exit_counts(gw: GameWorld) -> Counter[str]:
    """PS-START-03's Check: levels whose room through the open side either has bit 7 set (a move
    past row 0 or row 7) or is the stored exit room; and the levels that store the fallback room
    (another level's first room, when that move leaves the block)."""
    counts: Counter[str] = Counter()
    for level in gw.levels:
        side = _open_side(level)
        if side is None:
            continue
        reached = level.entrance_room + side.delta
        stored = stored_exit_room(level)
        counts["levels"] += 1
        counts["leaves"] += not 0 <= reached < room_grid.ROOMS or reached == stored
        counts["fallback"] += reached != stored
    return counts


def start_room_on_own_door(gw: GameWorld) -> bool:
    """VA-REJ-21's Check: a level whose start-room number is the screen of its own door (E9)."""
    return start_room_is_own_door(gw.levels, gw.overworld)
