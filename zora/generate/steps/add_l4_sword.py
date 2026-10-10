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
the first of level 9's item positions in the top half of the room, behind the old man.
R7-R8: the sword is no pool item, place or tracked record, and no hint or rule reads it (the
wooden sword is never tracked, so the acceptance check's item lookups never meet it).
"""
from __future__ import annotations

from ...model.enums import Enemy, Item, ItemPosition, RoomAction, RoomType
from ...model.levels import LEVEL_9, Level
from ...model.rooms import Room
from ..dungeon_walk import walk_level
from ..errors import GenerationFailure
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


def top_half_position(level9: Level) -> ItemPosition:
    """R6a: the first of the level's item positions in the top half of the room."""
    return next(ItemPosition(index) for index, packed in enumerate(level9.item_position_table)
                if packed & POSITION_Y_MASK < TOP_HALF_Y_BELOW)


def add_l4_sword(levels: list[Level], rng: IntRng) -> int:
    """Put the progressive sword in one qualifying level-9 room; return its room number."""
    level9 = next(level for level in levels if level.level_num == LEVEL_9)
    rooms = candidate_rooms(level9)
    if not rooms:
        raise GenerationFailure(NO_ROOM_FAILURE)
    room = rooms[rng.below(len(rooms))]
    room.item = L4_SWORD_ITEM
    if room.room_num == level9_entry_room(level9):
        room.item_position = top_half_position(level9)
    return room.room_num
