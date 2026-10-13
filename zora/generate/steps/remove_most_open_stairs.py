"""Remove Most Open Stairs (B30; post-shapes-b9.md PS-OSTAIR-01 to PS-OSTAIR-03): after the late
gate, a room whose stairs stand open (the Diamond stair room with a push block, the Narrow and
Spiral stair rooms) takes a push-block layout instead, and its stairs appear only once the block
is pushed."""
from collections.abc import Sequence

from ...model.enums import RoomAction, RoomType, WallType
from ...model.levels import LevelBlock
from ...model.rooms import DIAMOND_STAIRS_PUSH, LayoutInfo, Room
from ..rng import IntRng

# PS-OSTAIR-01: the open-stairs layouts (layout byte bits 6-0)
OPEN_STAIRS_LAYOUTS = frozenset({DIAMOND_STAIRS_PUSH, RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM})
# PS-OSTAIR-01: a Gleeok, by its monster byte's low seven bits (with the monster bit set). The
# seven bits take in bit 6, the count index's low bit, so a Gleeok on an odd count index changes.
MONSTER_BYTE_LOW_SEVEN = 0x7F
GLEEOK_MONSTER_BYTES = range(0x02, 0x06)
# PS-OSTAIR-02: the push-block layouts drawn in their place, the draw's order
REVERSE_C_PUSH = LayoutInfo(RoomType.REVERSE_C, movable_block=True)              # $48
DOUBLE_BLOCK_PUSH = LayoutInfo(RoomType.DOUBLE_BLOCK, movable_block=True)        # $4A
SINGLE_BLOCK_PUSH = LayoutInfo(RoomType.SINGLE_BLOCK_ROOM, movable_block=True)   # $62
PUSH_STAIRS_LAYOUTS = (DOUBLE_BLOCK_PUSH, SINGLE_BLOCK_PUSH, REVERSE_C_PUSH)
REDRAWN_LAYOUTS = (DOUBLE_BLOCK_PUSH, SINGLE_BLOCK_PUSH)
# PS-OSTAIR-02: a trap room (monster bit set) holds one of these by its monster byte's low seven
# bits, or one of the others by its low six bits
TRAP_MONSTER_BYTES = frozenset({0x09, 0x0A})
TRAP_MONSTER_LISTS = frozenset({0x2D, 0x2E, 0x36, 0x37})
# PS-OSTAIR-02: the item positions (level information $29-$2C) that keep a drawn $48; any other
# draws again. A room of no level reads level 0's, the overworld's ($57 $49 $99 $69 in PRG0),
# none of which is one of them (quirk: the room is never seen).
REVERSE_C_ITEM_POSITIONS = frozenset({0x89, 0xD6})


def remove_most_open_stairs(blocks: Sequence[LevelBlock], rng: IntRng) -> None:
    """PS-OSTAIR-01 and PS-OSTAIR-02: every open-stairs room of the blocks, in block and room
    order, takes a drawn push-block layout and trigger 5 ("a push block reveals the stairs").

    The spec scans all four room blocks. ZORA takes the blocks the levels read: a block no level
    reads keeps PRG0's bytes in ZORA's output (ship._ship_sets), and its rooms are never seen."""
    for block in blocks:
        for room in block.rooms:
            if _has_most_open_stairs(room):
                room.layout_info = _push_stairs_layout(block, room, rng)
                room.room_action = RoomAction.BLOCK_STAIRS


def _has_most_open_stairs(room: Room) -> bool:
    """PS-OSTAIR-01: an open-stairs layout, not on the push-block-door trigger (4), no shutter,
    no Gleeok."""
    return (room.layout_code in OPEN_STAIRS_LAYOUTS
            and room.room_action != RoomAction.BLOCK_DOOR
            and WallType.SHUTTER_DOOR not in (room.walls.north, room.walls.east, room.walls.south, room.walls.west)
            and not _holds_gleeok(room))


def _holds_gleeok(room: Room) -> bool:
    return room.has_monster_bit and (room.monster_byte & MONSTER_BYTE_LOW_SEVEN) in GLEEOK_MONSTER_BYTES


def _is_trap_room(room: Room) -> bool:
    """PS-OSTAIR-02: the monster bit with a trap's monster list."""
    return room.has_monster_bit and ((room.monster_byte & MONSTER_BYTE_LOW_SEVEN) in TRAP_MONSTER_BYTES
                                     or room.monster_list in TRAP_MONSTER_LISTS)


def _push_stairs_layout(block: LevelBlock, room: Room, rng: IntRng) -> LayoutInfo:
    """PS-OSTAIR-02: one of $4A, $62 and $48, uniformly; a trap room that drew $48 draws again
    from $4A and $62, and a room whose item position is neither $89 nor $D6 draws again from
    them whatever it drew. The room's monster bit stays with its monster."""
    layout = rng.choice(PUSH_STAIRS_LAYOUTS)
    if _is_trap_room(room) and layout == REVERSE_C_PUSH:
        layout = rng.choice(REDRAWN_LAYOUTS)
    level = block.owner_of(room.room_num)
    position = None if level is None else level.item_position_table[room.item_position]
    if position not in REVERSE_C_ITEM_POSITIONS:
        layout = rng.choice(REDRAWN_LAYOUTS)
    return layout

