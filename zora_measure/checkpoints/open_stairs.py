"""Remove Most Open Stairs (B30; post-shapes-b9.md PS-OSTAIR): the Checks measured on finished
ROMs, against the original randomizer's b30 corpus (corpus("b30"); hash manifest in docs/spec/).
Both read the two room blocks the levels read. The spec's Checks read the two first-quest blocks,
which are the same blocks unless a set is second quest; a block no level reads keeps its base
bytes in ZORA (owner ruling 2026-10-11, docs/deviations.md), so it is left out on both sides, as
the Zol-bit row does. The rules are written out here from the spec, apart from the generator's
code, so the measure does not grade itself."""
from collections import Counter

from zora.model.enums import RoomAction, WallType
from zora.model.game_world import GameWorld
from zora.model.rooms import Room

SPEC_PS_OSTAIR = "post-shapes-b9.md @ 3a9a4dd"
# The b30 corpus's flag string: the MVP baseline's with B30 on
OPEN_STAIRS_FLAGS = "8hq4BeSx5aHLXfTldoscyDouW!UJ3A"
OPEN_STAIRS_LAYOUTS = frozenset({0x5A, 0x1B, 0x1C})
PUSH_STAIRS_LAYOUTS = (0x48, 0x4A, 0x62)
GLEEOK_MONSTER_BYTES = range(0x02, 0x06)
MONSTER_BYTE_LOW_SEVEN = 0x7F
OPEN_STAIRS_KEYS = ("left", "exempt")
PUSH_STAIRS_KEYS = (*(f"${layout:02X} t5" for layout in PUSH_STAIRS_LAYOUTS),
                    *(f"${layout:02X} t4" for layout in PUSH_STAIRS_LAYOUTS))


def _read_rooms(gw: GameWorld) -> list[Room]:
    """Every room of the two blocks the levels read."""
    return [room for block in gw.level_blocks for room in block.rooms]


def _exempt(room: Room) -> bool:
    """PS-OSTAIR-01's exemptions: trigger 4, a shutter, a Gleeok."""
    walls = room.walls
    shutter = WallType.SHUTTER_DOOR in (walls.north, walls.east, walls.south, walls.west)
    gleeok = room.has_monster_bit and (room.monster_byte & MONSTER_BYTE_LOW_SEVEN) in GLEEOK_MONSTER_BYTES
    return room.room_action == RoomAction.BLOCK_DOOR or shutter or gleeok


def open_stairs_rooms(gw: GameWorld) -> Counter[str]:
    """PS-OSTAIR-01's Check: open-stairs rooms left without an exemption, and the exempt ones."""
    counts: Counter[str] = Counter()
    for room in _read_rooms(gw):
        if room.layout_code in OPEN_STAIRS_LAYOUTS:
            counts["exempt" if _exempt(room) else "left"] += 1
    return counts


def push_stairs_rooms(gw: GameWorld) -> Counter[str]:
    """PS-OSTAIR-02's Check: rooms with layouts $48, $4A and $62, on trigger 5 and on trigger 4."""
    counts: Counter[str] = Counter()
    for room in _read_rooms(gw):
        if room.layout_code in PUSH_STAIRS_LAYOUTS and room.room_action in (RoomAction.BLOCK_STAIRS,
                                                                            RoomAction.BLOCK_DOOR):
            counts[f"${room.layout_code:02X} t{int(room.room_action)}"] += 1
    return counts
