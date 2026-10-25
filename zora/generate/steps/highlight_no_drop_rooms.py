"""Highlight No-Drop Rooms (ZORA flag highlight_no_drop_rooms; owner decision, 2026-10-18; the
research doc "Highlight No-Drop Rooms: Research and Implementation Plan"; reworked 2026-10-24 after
a bug report, docs/zora-extras.md section 16): a dungeon room that can never hold an item draws
the tiles that use palette color 1 (blocks, water, statues, stairs) in red, and every other room
as the level always looked, so a player can tell at a glance which rooms are worth searching.

The rule (the doc's section 2): a room of level L is a no-drop room when none of L's four item
positions (level information $29-$2C) is on the allowed list for the room's screen type, its
layout with the push-block bit. After the shape stage an item reaches a room only with its layout
and position (the reshuffles move item bytes between rooms that hold one; the late gate's re-deal
and the room exchange move the whole contents), so such a room never receives one. (The engine
itself places a room's item wherever its position byte says, in any room: the rule is the
generator's, measured on its output.)

The display (owner decisions, 2026-10-24): the inner palette selector (room table B bits 0-1) of
every room that uses palette 2 or 3 becomes 3 when the room is a no-drop room and 2 otherwise,
and each level's palette 3 has color 1 (the color of block faces, water, statues and stairs)
NO_DROP_COLOR, red, in the palette and in the dark-room fade steps. Palette 2 stays the level's
own, so a room that can drop, its walls and its doors look as the level always looked. (A room can
pick only the level's four palettes, two of them the status bar's: a vanilla moat on palette 3
that can drop therefore takes palette 2, and shows the level's block-face color rather than its
water color.) Rooms on palette 0 (the person rooms) and 1 (sand) keep theirs, unmarked. Dark
rooms are marked like any other. No marking at all when Allow Universal Drops In Shapes (B91)
resolves on. The pass runs on the shipped world, after every pass that moves rooms, items,
layouts or palettes, and before the level encoding; it draws no random numbers."""
from collections.abc import Iterable

from ...model.enums import Enemy, Item
from ...model.levels import Level
from ...model.rooms import Room
from ..shapes.t5_positions import T5_BASE
from .remove_most_open_stairs import PUSH_STAIRS_LAYOUTS

# Inner palette selectors (LevelBlockAttrsB bits 1-0)
UNMARKED_PALETTE = 2
MARKED_PALETTE = 3
CHANGED_PALETTES = frozenset({UNMARKED_PALETTE, MARKED_PALETTE})
# The no-drop color (owner, 2026-10-24): NES $16, the plain red. No dungeon color set (PS-COLOR-02)
# uses it as palette 2's color 1, so it differs from a level's block face whatever Shuffle Dungeon
# Colors draws.
NO_DROP_COLOR = 0x16
PALETTE_SIZE = 4                     # a background palette: the backdrop, then colors 1 to 3
ACCENT_SLOT = 1                      # color 1: block faces, water, statues, stairs
BRIGHTNESS_ROW = 0x10                # one NES brightness row; the dark-room fade steps down rows
BLACK = 0x0F
# fade_palette_raw (level information +$7C, 96 bytes): 12 steps of 8 bytes, palette 2's four
# colors then palette 3's (AnimateWorldFading writes them to PPU $3F08). Steps 0 to 3 and 8 to 11
# are the fade from the full colors to black (the dark room's light); steps 4 to 7 are grey.
FADE_STEP_SIZE = 2 * PALETTE_SIZE
FADE_GROUP_STARTS = (0, 8)           # in steps
FADE_STEPS_PER_GROUP = 4
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
    """A room on palette 2 or 3 takes the mark; the person rooms (0) and the original palette-1
    rooms keep theirs."""
    return room.palette_1 in CHANGED_PALETTES


def is_exception(room: Room, open_stairs_removed: bool) -> bool:
    """Never marked: Ganon's room, and with Remove Most Open Stairs (B30) on its three screen
    types. Quirk: the doc leaves these rooms' selectors as they were, but one already on 3 would
    then look marked while holding an item; owner decision 2 gives every unmarked block room 2,
    so they take 2 like any other unmarked room."""
    return is_ganon_room(room) or (open_stairs_removed and room.layout_code in OPEN_STAIRS_SCREEN_TYPES)


def is_marked(level: Level, room: Room, allowed: dict[int, frozenset[int]], open_stairs_removed: bool) -> bool:
    return is_no_drop_room(level, room, allowed) and not is_exception(room, open_stairs_removed)


def darker(color: int, rows: int) -> int:
    """`color` `rows` brightness rows darker, black past the bottom row."""
    return color - rows * BRIGHTNESS_ROW if color - rows * BRIGHTNESS_ROW >= 0 else BLACK


def write_no_drop_color(level: Level) -> None:
    """Palette 3's color 1 becomes NO_DROP_COLOR, in the level's palette and in the steps of its
    dark-room fade (each step one brightness row darker)."""
    palette_bytes, fade_bytes = level.color_sets
    palette, fade = bytearray(palette_bytes), bytearray(fade_bytes)
    palette[MARKED_PALETTE * PALETTE_SIZE + ACCENT_SLOT] = NO_DROP_COLOR
    for group_start in FADE_GROUP_STARTS:
        for step in range(FADE_STEPS_PER_GROUP):
            offset = (group_start + step) * FADE_STEP_SIZE + PALETTE_SIZE + ACCENT_SLOT
            fade[offset] = darker(NO_DROP_COLOR, step)
    level.set_color_sets(bytes(palette), bytes(fade))


def highlight_no_drop_rooms(levels: Iterable[Level], open_stairs_removed: bool) -> None:
    """Every level's palette 3 takes the no-drop color; every room on palette 2 or 3 gets inner
    palette 3 when it is marked and inner palette 2 otherwise. The caller skips the pass when B91
    resolves on."""
    levels = list(levels)
    allowed = allowed_positions(any(level.is_second_quest for level in levels))
    for level in levels:
        write_no_drop_color(level)
        for room in level.rooms:
            if takes_part(room):
                marked = is_marked(level, room, allowed, open_stairs_removed)
                room.palette_1 = MARKED_PALETTE if marked else UNMARKED_PALETTE
