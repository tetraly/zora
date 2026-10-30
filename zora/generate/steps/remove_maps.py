"""Remove Maps (B92; features-behavior.md FP-MAP-01): no dungeon room holds a map.

Every room and item cellar of the four level blocks whose item is the map holds no item instead;
the dark and boss-sound bits, the compasses, the other items and the item positions stay. ZORA
leaves nothing in the map's place (FP-MAP-01's MAY), not PRG0's four-bomb pickup the spec's own
build writes. A room that releases its item when its last foe dies (trigger 7) would still switch
the item on then, and show item 3, the magical sword: such a room takes trigger 1 instead, which
opens its shutters the same way and releases nothing (FP-MAP-01's MUST; docs/deviations.md).
Ganon's trigger 3 never holds a map: Ganon's room holds the Triforce of Power."""
from collections.abc import Iterable

from ...model.enums import Item, RoomAction, RoomType
from ...model.levels import LevelBlock


def remove_maps(blocks: Iterable[LevelBlock]) -> None:
    """FP-MAP-01: the map leaves every room and item cellar of the blocks given."""
    for block in blocks:
        for room in block.rooms:
            if room.item is not Item.MAP:
                continue
            assert room.room_action is not RoomAction.LAST_BOSS, f"FP-MAP-01: a map in room ${room.room_num:02X}"
            room.item = Item.NOTHING
            if room.room_action is RoomAction.ALL_DEAD_ITEM:
                room.room_action = RoomAction.ALL_DEAD
        for cellar in block.staircases:
            if cellar.room_type is RoomType.ITEM_STAIRCASE and cellar.item is Item.MAP:
                cellar.item = Item.NOTHING
