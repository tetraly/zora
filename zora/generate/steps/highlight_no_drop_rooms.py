"""Highlight No-Drop Rooms (ZORA flag highlight_no_drop_rooms; owner decision, 2026-10-18; the
research doc "Highlight No-Drop Rooms: Research and Implementation Plan"): a dungeon room that can
never hold an item draws its blocks in its level's palette 3, and every other room with blocks in
palette 2, so a player can tell at a glance which rooms are worth searching.

The rule (the doc's section 2): a room of level L is a no-drop room when none of L's four item
positions (level information $29-$2C) is on the allowed list for the room's screen type, its
layout with the push-block bit. After the shape stage an item reaches a room only with its layout
and position (the reshuffles move item bytes between rooms that hold one; the late gate's re-deal
and the room exchange move the whole contents), so such a room never receives one.

Owner's decisions: only the inner palette selector (room table B bits 0-1) changes, and only in a
room whose layout has blocks and whose selector is already 2 or 3; no color is written (where a
level's palettes 2 and 3 are the same, the mark simply doesn't show). Water rooms and the entrance
rooms keep their palette; dark rooms are marked like any other. No marking at all when Allow
Universal Drops In Shapes (B91) resolves on. The pass runs on the shipped world, after every pass
that moves rooms, items, layouts or palettes, and before the level encoding; it draws no random
numbers."""
from collections.abc import Iterable

from ...model.enums import Enemy, Item
from ...model.levels import Level
from ...model.rooms import LAYOUT_ID_MASK, Room
from ..shapes.t5_positions import T5_BASE
from .remove_most_open_stairs import PUSH_STAIRS_LAYOUTS

# The doc's section 5: the layouts (layout byte bits 5-0) that draw blocks and no water. Their
# block tiles use color 1, the one color palettes 2 and 3 differ in.
BLOCK_LAYOUTS = frozenset((*range(0x01, 0x0B), *range(0x0C, 0x12), *range(0x1A, 0x20), 0x20, 0x22, 0x27, 0x29))
# Inner palette selectors (LevelBlockAttrsB bits 1-0)
UNMARKED_PALETTE = 2
MARKED_PALETTE = 3
CHANGED_PALETTES = frozenset({UNMARKED_PALETTE, MARKED_PALETTE})
# The doc's section 2: the positions the 2nd Quest dungeons place items at beyond the T5 base list,
# by screen type, added for every level when any level reads a 2nd Quest room block (the room
# exchange carries 2nd Quest contents into other levels). Rebuilt from PRG0's 2nd Quest item rooms
# by tests/test_highlight_no_drop_rooms.py.
SECOND_QUEST_PAIRS: dict[int, tuple[int, ...]] = {
    0x03: (0x87,),
    0x05: (0x49, 0xAC, 0xC9),
    0x0B: (0x56,),
    0x0C: (0x89,),
    0x0E: (0x37, 0x49),
    0x0F: (0xB6,),
    0x10: (0xAC,),
    0x11: (0xAC,),
    0x13: (0xC9,),
    0x14: (0x79,),
    0x15: (0xAC,),
    0x16: (0x79,),
    0x18: (0x57, 0x86, 0xB7),
    0x1B: (0xC9,),
    0x1E: (0xAC, 0xC9),
    0x1F: (0xAC,),
    0x23: (0xAC,),
    0x24: (0x56, 0xAC, 0xC9),
    0x25: (0xAC, 0xC9),
    0x26: (0xAC,),
    0x28: (0xC9,),
    0x41: (0x56, 0x89),
    0x48: (0x89,),
    0x5A: (0xAC,),
    0x5F: (0xAC, 0xC9),
}
# PS-OSTAIR-02: with Remove Most Open Stairs (B30) on, a former open-stairs room takes one of these
# screen types and keeps its item, so they are never marked.
OPEN_STAIRS_SCREEN_TYPES = frozenset(layout.layout_code for layout in PUSH_STAIRS_LAYOUTS)   # $4A, $62, $48


def allowed_positions(second_quest: bool) -> dict[int, frozenset[int]]:
    """The doc's section 2 allowed list: the T5 base list, with the 2nd Quest pairs when any level
    reads a 2nd Quest room block."""
    screen_types = set(T5_BASE) | (set(SECOND_QUEST_PAIRS) if second_quest else set())
    return {screen_type: frozenset((*T5_BASE.get(screen_type, ()),
                                    *(SECOND_QUEST_PAIRS.get(screen_type, ()) if second_quest else ())))
            for screen_type in screen_types}


def is_no_drop_room(level: Level, room: Room, allowed: dict[int, frozenset[int]]) -> bool:
    """None of the level's four item positions is on the room's screen type's row."""
    row = allowed.get(room.layout_code, frozenset())
    return not row.intersection(level.item_position_table)


def is_ganon_room(room: Room) -> bool:
    """Ganon's room holds the Triforce of Power whatever its layout: the game drops it at Ganon's
    ashes, not at a room position (Ganon_ActivateRoomItem)."""
    return room.enemy == Enemy.THE_BEAST or room.item == Item.TRIFORCE_OF_POWER


def takes_part(room: Room) -> bool:
    """The doc's implementation plan, step 5: a room changes only when its layout has blocks and
    its inner selector is 2 or 3 (water rooms, the entrance and other blockless rooms, the person
    rooms on 0 and the original palette-1 rooms keep theirs)."""
    return (room.layout_code & LAYOUT_ID_MASK) in BLOCK_LAYOUTS and room.palette_1 in CHANGED_PALETTES


def is_exception(room: Room, open_stairs_removed: bool) -> bool:
    """Never marked: Ganon's room, and with Remove Most Open Stairs (B30) on its three screen
    types. Quirk: the doc leaves these rooms' selectors as they were, but one already on 3 would
    then look marked while holding an item; owner decision 2 gives every unmarked block room 2,
    so they take 2 like any other unmarked room."""
    return is_ganon_room(room) or (open_stairs_removed and room.layout_code in OPEN_STAIRS_SCREEN_TYPES)


def is_marked(level: Level, room: Room, allowed: dict[int, frozenset[int]], open_stairs_removed: bool) -> bool:
    return is_no_drop_room(level, room, allowed) and not is_exception(room, open_stairs_removed)


def highlight_no_drop_rooms(levels: Iterable[Level], open_stairs_removed: bool) -> None:
    """Every taking-part room of every level gets inner palette 3 when it is marked and inner
    palette 2 otherwise. The caller skips the pass when B91 resolves on."""
    levels = list(levels)
    allowed = allowed_positions(any(level.is_second_quest for level in levels))
    for level in levels:
        for room in level.rooms:
            if takes_part(room):
                marked = is_marked(level, room, allowed, open_stairs_removed)
                room.palette_1 = MARKED_PALETTE if marked else UNMARKED_PALETTE
