"""Dungeon Room Shuffle's figures (post-shapes-b3.md): the room exchange."""

from collections import Counter
from collections.abc import Callable

from zora.measure.checkpoints.shapes_and_gate import _zelda_room
from zora.measure.checkpoints.summaries import LEVELS_7_9, POOL_ITEMS, Summary, _level9_person_room
from zora.model.enums import RoomAction, Side, WallType
from zora.model.game_world import GameWorld
from zora.model.room_grid import neighbour

# --- B3: the room exchange between dungeons ----------------------------------

GANON_LAYOUT = 0x28
# Level-1 layouts that arrive only through the exchange (low six bits)
LEVEL1_ARRIVING_LAYOUTS = (0x0B, 0x0E, 0x0F, 0x12, 0x27)


def level9_room_progression(gw: GameWorld) -> bool:
    """A progression item (PS-ITEM-01's pool) in a level-9 room."""
    return any(room.item in POOL_ITEMS for room in gw.levels[8].rooms)


def level9_cellar_progression(gw: GameWorld) -> int:
    """Progression items in level 9's staircase cellars."""
    block = gw.blocks[LEVELS_7_9]
    return sum(block.staircase(n).item in POOL_ITEMS for n in gw.levels[8].staircase_nums)


def levels_with_layout(layout: int) -> Callable[[GameWorld], list[bool]]:
    """Per level, whether it holds a room of this layout (low six bits)."""
    return lambda gw: [any(room.room_type == layout for room in level.rooms)
                       for level in gw.levels]


def roms_per_level(values: list[list[bool]]) -> str:
    return " ".join(str(sum(v[i] for v in values)) for i in range(len(values[0])))


ROMS_PER_LEVEL = Summary(roms_per_level, lambda hits: {
    f"L{i + 1}": float(hit) for i, hit in enumerate(hits)
})


def level1_arriving_layouts(gw: GameWorld) -> Counter[int]:
    """Level 1's non-person rooms by layout (low six bits)."""
    return Counter(int(room.room_type) for room in gw.levels[0].rooms if not room.is_person)


def level9_person_any_shutter(gw: GameWorld) -> bool:
    """A45/A47: level 9's $4B room ships at least one shutter side."""
    room = _level9_person_room(gw)
    return room is not None and WallType.SHUTTER_DOOR in (
        room.walls.north, room.walls.east, room.walls.south, room.walls.west
    )


# VA-REJ-19: the $4B room's (north, east, west) sides, as "S" shutter / "W"
# wall, in the spec's order; "other" is any open, bombable or key side, or
# all three walls (0 of 1,000 finals).
LEVEL9_PERSON_SIDE_KEYS = ("SSS", "SSW", "WSS", "SWS", "WSW", "WWS", "SWW", "other")
SIDE_LETTERS = {WallType.SHUTTER_DOOR: "S", WallType.SOLID_WALL: "W"}


def level9_person_sides(gw: GameWorld) -> str:
    """VA-REJ-19: level 9's $4B room's north, east and west sides."""
    room = _level9_person_room(gw)
    if room is None:
        return "other"
    sides = "".join(SIDE_LETTERS.get(side, "?")
                    for side in (room.walls.north, room.walls.east, room.walls.west))
    return sides if sides in LEVEL9_PERSON_SIDE_KEYS else "other"


# VA-REJ-19 (A59): the $4B room's trigger-0 count must lie in 369-461 per
# 1,000; keyed by the number of shutters among its north, east and west
# sides when the trigger is 0; "other" is any trigger but 0 and 1, or
# trigger 0 with no shutter there.
LEVEL9_PERSON_TRIGGER_KEYS = (1, 2, 3, "trigger 1", "other")


def level9_person_trigger(gw: GameWorld) -> int | str:
    """VA-REJ-19: the $4B room's trigger 0 split by its shutter count."""
    room = _level9_person_room(gw)
    if room is None:
        return "other"
    if room.room_action == RoomAction.ALL_DEAD:
        return "trigger 1"
    if room.room_action != RoomAction.NONE:
        return "other"
    shutters = sum(side == WallType.SHUTTER_DOOR
                   for side in (room.walls.north, room.walls.east, room.walls.west))
    return shutters if shutters in LEVEL9_PERSON_TRIGGER_KEYS else "other"


ZELDA_NEIGHBOUR_COUNTS = (1, 2, 3, 4)


def zelda_neighbour_count(gw: GameWorld) -> int:
    """A48: Zelda's same-level neighbours."""
    zelda = _zelda_room(gw)
    if zelda is None:
        return 0
    owned = set(gw.levels[8].room_nums)
    return sum(neighbour(zelda.room_num, side) in owned for side in Side)


def zelda_neighbours_trigger3(gw: GameWorld) -> tuple[int, int]:
    """A48: Zelda's same-level neighbours whose trigger byte is exactly $03."""
    zelda = _zelda_room(gw)
    if zelda is None:
        return 0, 0
    level9 = gw.levels[8]
    owned = set(level9.room_nums)
    neighbours = [gw.blocks[LEVELS_7_9].room(n) for side in Side
                  if (n := neighbour(zelda.room_num, side)) in owned]
    hits = sum(room.room_action == RoomAction.LAST_BOSS
               and room.item_position == 0 for room in neighbours)
    return hits, len(neighbours)
