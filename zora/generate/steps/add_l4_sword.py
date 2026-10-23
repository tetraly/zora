"""Add L4 Sword (docs/design/l4-sword.md, owner-agreed 2026-10-07; replaces docs/design/
zora-flags-2.0.md section 2's placement): level 9 holds one extra floor item, a progressive sword
(item $01), which taken at sword level 3 gives sword level 4 (C2's asm/flags2/l4-sword-take).

R4-R5 (owner's rules, with the owner's answer to Q3): exactly one level-9 room gets room item $01,
drawn uniformly with the seeded stream among the rooms that:
  - are not the entrance;
  - hold no item now;
  - are not on a trigger that hides the item: 7, which drops it once the monsters are dead, and 3
    ("last boss"), which never releases it outside Ganon's room (CreateRoomObjects hides a room
    item at load for both; R6: a standing item, present on entry);
  - are not Ganon's room or Zelda's room, nor an item or transport staircase (cellars are no
    level room, but the rule does not depend on that);
  - are reached by the plain walk from level 9's entrance (E3's, VA-WALK) with the last boss's
    shutters closed, so the sword is collectible before Ganon.
The room keeps its action. It runs after every step that changes level 9's rooms, just before
the acceptance check; with no room qualifying the attempt fails (GenerationFailure), never
shipping without the sword.
R6a: the triforce-checker room (one north of the entrance) may be drawn; its item then stands at
the first of level 9's item positions in the top half of the room, behind the person.
Item spots (ZORA, 2026-10-22; zora/generate/item_spots.py): the sword never stands on a block,
statue or staircase. A drawn room with none of level 9's item positions on a square that can
hold it (in the top half, for the triforce-checker room) is dropped and the draw repeated among
the rest; the sword keeps the room's own position when that square can, else takes the first that
can. A seed whose sword stood on such a square before is the only one that changes. Before, the
sword kept the room's position as it stood, which no rule had checked in a room without an item.
R7-R8: the sword is no pool item, place or tracked record, and no hint or rule reads it (the
wooden sword is never tracked, so the acceptance check's item lookups never meet it).
"""
from __future__ import annotations

from ...model.enums import Enemy, Item, ItemPosition, RoomAction, RoomType
from ...model.levels import LEVEL_9, Level
from ...model.rooms import Room
from ..dungeon_walk import walk_level
from ..errors import GenerationFailure
from ..item_spots import is_item_spot, item_spot_positions
from ..late_gate.walk import level9_entry_room
from ..rng import IntRng

L4_SWORD_ITEM = Item.WOOD_SWORD       # $01: one sword upgrade, with Progressive Items
HIDING_TRIGGERS = frozenset({RoomAction.LAST_BOSS, RoomAction.ALL_DEAD_ITEM})
EXCLUDED_MONSTERS = frozenset({Enemy.THE_BEAST, Enemy.THE_KIDNAPPED})      # Ganon, Zelda
STAIRCASE_TYPES = frozenset({RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE})
NO_ROOM_FAILURE = "L4 sword: no level-9 room qualifies"
# An item position byte is $XY in tiles' units of 16 pixels; Y below this is the room's top half
# (the play area spans Y $6 to $C, its middle row $9 included in neither half).
POSITION_Y_MASK = 0x0F
TOP_HALF_Y_BELOW = 0x9


def collectible_rooms(level9: Level) -> set[int]:
    """The rooms the plain walk (VA-WALK, as E3) reaches from level 9's entrance, the last boss's
    shutters closed."""
    walk = walk_level(level9, frozenset({Item.LADDER}), is_last_boss_open=False, uses_families=False,
                      uses_entry_sides=False)
    rooms = set(level9.room_nums)            # the walk also reaches cellars
    return {room for room in walk.reached if room in rooms and walk.accepts(level9, room)}


def qualifies(level: Level, room: Room, collectible: set[int], holding: Item = Item.NOTHING) -> bool:
    """R5 with the owner's exclusions, for a room holding `holding` (no item while choosing; the
    sword when checking a finished seed)."""
    staircases = {staircase.room_num for staircase in level.block.staircases}
    return (room.room_num != level.entrance_room
            and room.item == holding
            and room.room_action not in HIDING_TRIGGERS
            and room.enemy not in EXCLUDED_MONSTERS
            and room.room_type not in STAIRCASE_TYPES
            and room.room_num not in staircases
            and room.room_num in collectible)


def candidate_rooms(level9: Level) -> list[Room]:
    """The rooms R5 allows, in room order."""
    collectible = collectible_rooms(level9)
    return [room for room in sorted(level9.rooms, key=lambda room: room.room_num)
            if qualifies(level9, room, collectible)]


def is_top_half(level: Level, position: ItemPosition) -> bool:
    return level.item_position_table[position] & POSITION_Y_MASK < TOP_HALF_Y_BELOW


def sword_positions(level9: Level, room: Room) -> list[ItemPosition]:
    """The positions the sword may take in the room: those on a square that can hold an item, and
    in the triforce-checker room only those in the top half (R6a)."""
    positions = item_spot_positions(level9, room)
    if room.room_num == level9_entry_room(level9):
        return [position for position in positions if is_top_half(level9, position)]
    return positions


def sword_position(level9: Level, room: Room) -> ItemPosition:
    """R6a's first top-half position in the triforce-checker room; elsewhere the room's own
    position when its square can hold an item, else the first that can."""
    if room.room_num != level9_entry_room(level9) \
            and is_item_spot(room.layout_code, level9.item_position_table[room.item_position]):
        return room.item_position
    return sword_positions(level9, room)[0]


def add_l4_sword(levels: list[Level], rng: IntRng) -> int:
    """Put the progressive sword in one qualifying level-9 room; return its room number."""
    level9 = next(level for level in levels if level.level_num == LEVEL_9)
    rooms = candidate_rooms(level9)
    while True:
        if not rooms:
            raise GenerationFailure(NO_ROOM_FAILURE)
        room = rooms.pop(rng.below(len(rooms)))
        if sword_positions(level9, room):
            break
    room.item = L4_SWORD_ITEM
    room.item_position = sword_position(level9, room)
    return room.room_num
