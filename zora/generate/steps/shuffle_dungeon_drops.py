"""Shuffle Dungeon Drops (B15; PS-DROP-01 to -03): room items within each level."""

from dataclasses import dataclass

from zora.generate.rng import IntRng
from zora.generate.shapes.world import blocks_of
from zora.generate.steps.item_shuffle_result import _level_rooms
from zora.model.enums import Enemy
from zora.model.levels import GANON_ITEM_BYTE, GANON_LIST, ZELDA_LIST, Level
from zora.model.rooms import ITEM_MASK, NO_ITEM_CODE, RoomPlace

# --- PS-DROP ---------------------------------------------------------------

DROP_EXCLUDED_MONSTER = frozenset({0x3B, ZELDA_LIST, GANON_LIST, Enemy.HUNGRY_GORIYA, 0xC0})


# --- PS-DROP ---------------------------------------------------------------

@dataclass
class ShapeSnapshot:
    """Item and monster bytes at the end of the shape stage (PS-DROP-01
    judges eligibility by these, whatever the item shuffle did since)."""
    item: dict[RoomPlace, int]
    monster: dict[RoomPlace, int]


def snapshot_shapes(levels: list[Level]) -> ShapeSnapshot:
    item: dict[RoomPlace, int] = {}
    monster: dict[RoomPlace, int] = {}
    for level_room in _level_rooms(levels):
        item[level_room.key] = level_room.room.item_byte
        monster[level_room.key] = level_room.room.monster_byte
    return ShapeSnapshot(item, monster)


def shuffle_dungeon_drops(levels: list[Level], snapshot: ShapeSnapshot,
                          rng: IntRng) -> None:
    """PS-DROP-01..03: per level (1..9), permute the whole item bytes of the
    eligible rooms with a uniform Fisher-Yates. The level's room list is its
    grid rooms in cell order (item cellars are not level rooms here —
    QUESTIONS #45.3). The triforce pointer (PS-DROP-03) is derived from
    content at write-back; the late gate re-points it anyway."""
    block_index = {id(block): index for index, block in enumerate(blocks_of(levels))}
    for level in sorted(levels, key=lambda level: level.level_num):
        rooms = []
        for room in level.rooms:
            if room.is_person:
                continue
            key = RoomPlace(block_index[id(level.block)], room.room_num)
            item_byte, monster_byte = snapshot.item[key], snapshot.monster[key]
            if item_byte & ITEM_MASK == NO_ITEM_CODE or item_byte == GANON_ITEM_BYTE:
                continue
            if monster_byte in DROP_EXCLUDED_MONSTER:
                continue
            rooms.append(room)
        dealt = [room.item_info for room in rooms]
        count = len(dealt)
        for position in range(count):
            other = position + rng.below(count - position)
            dealt[position], dealt[other] = dealt[other], dealt[position]
        for room, item_info in zip(rooms, dealt, strict=True):
            room.item_info = item_info
