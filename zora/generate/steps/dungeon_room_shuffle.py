"""Post-shapes pass, batch B3 (docs/spec/post-shapes-b3.md @ 8ab6fa9).

PS-XCHG, the room exchange between dungeons, runs after the enemy- and
boss-group passes (generation_pass.STEPS) and just before
the late gate:
  PS-XCHG-01  the pool: level cells of both quest-1 blocks, in scan order
  PS-XCHG-02  what moves: the room's *contents* (layout and push bit, the
              whole item byte, the whole trigger byte); monster and doors stay
  PS-XCHG-03  stair-type contents trade only with stair-type (re-draw)
  PS-XCHG-04  one walk over the pool; a swap that breaks a rule is skipped
  PS-XCHG-05  the second drop shuffle: each level's item bytes re-dealt

Omitted: PS-XCHG-05's level Triforce-room pointer. The late gate rewrites
the pointer before the ROM ships (its pointer fix), so the value this pass
would store never survives.
"""
from dataclasses import dataclass

from zora.generate.rng import IntRng, discard
from zora.generate.shapes.tables import (
    BLADE_TRAP_BAD_LAYOUTS,
    DODONGO_BAD_LAYOUTS,
    GLEEOK4_EXTRA_BAD,
    GLEEOK_BAD_LAYOUTS,
    GOHMA_BAD_LAYOUTS,
    LANMOLA_BAD_LAYOUTS,
    RUPEE_STASH_BAD_LAYOUTS,
)
from zora.generate.shapes.world import blocks_of
from zora.generate.steps.shuffle_dungeon_monsters import GANON_BAD_LAYOUTS
from zora.model.enums import Enemy, Item, ItemPosition, RoomAction, RoomType
from zora.model.levels import GANON_LIST, ZELDA_LIST, Level
from zora.model.rooms import (
    DIAMOND_STAIRS_PUSH,
    NO_ITEM_CODE,
    SPIRAL_STAIRS_PUSH,
    TURNSTILE_PUSH,
    ItemInfo,
    LayoutInfo,
    Room,
    SecretInfo,
)

# --- PS-XCHG-01: the pool ---------------------------------------------------------

DISCARDED_DRAWS = 2
# Layout byte, monster bit ignored (push bit kept): the staircases $3E/$3F,
# $20, $21 and $60 ($20 with a push block). $61 is NOT skipped.
SKIPPED_LAYOUT_CODES = frozenset({RoomType.TRANSPORT_STAIRCASE, RoomType.ITEM_STAIRCASE,
                                  RoomType.TURNSTILE_ROOM, RoomType.ENTRANCE_ROOM, TURNSTILE_PUSH})
COMBINED_MONSTER_BIT = 0x80      # the monster bit in a combined monster value
# Combined values $8A-$92: the corner traps and the person lists.
SKIPPED_FLAGGED_LISTS = range(0x8A, 0x93)
# Item low five bits never in the pool: compass, map, heart container,
# triforce, Triforce of Power, the twelve progression items, the power
# bracelet, the white sword and $1C.
PROGRESSION_ITEMS = frozenset({Item.RECORDER, Item.RED_CANDLE, Item.SILVER_ARROWS, Item.BOW, Item.MAGICAL_KEY,
                               Item.RAFT, Item.LADDER, Item.WAND, Item.BOOK, Item.RED_RING, Item.WOOD_BOOMERANG,
                               Item.MAGICAL_BOOMERANG})
GUARDED_ITEMS = frozenset({Item.COMPASS, Item.MAP, Item.HEART_CONTAINER, Item.TRIFORCE, Item.TRIFORCE_OF_POWER,
                           Item.POWER_BRACELET, Item.WHITE_SWORD, Item.MAGICAL_SHIELD}) | PROGRESSION_ITEMS


def combined_monster(room: Room) -> int:
    """The combined value PS-XCHG tests: the monster bit as $80 plus the
    monster byte's low six bits (count bits stripped)."""
    return room.monster_list | (COMBINED_MONSTER_BIT if room.has_monster_bit else 0)


def takes_part(room: Room) -> bool:
    """PS-XCHG-01: does this level room join the pool?"""
    if room.layout_code in SKIPPED_LAYOUT_CODES:
        return False
    monster = combined_monster(room)
    if monster in SKIPPED_FLAGGED_LISTS or monster == Enemy.HUNGRY_GORIYA:
        return False
    # Zelda and Ganon take part ("shuffle Ganon and Zelda" is on); Ganon's
    # room holds the Triforce of Power by now, so the item test drops it.
    return room.item_info.item_code not in GUARDED_ITEMS


def exchange_pool(levels: list[Level]) -> list[tuple[Level, Room]]:
    """PS-XCHG-01: the level rooms that take part, with their levels, in
    scan order: the levels 1-6 block's rooms 0-127, then the levels 7-9
    block's."""
    pool: list[tuple[Level, Room]] = []
    for block in blocks_of(levels):
        owned = sorted(((room.room_num, level, room) for level in levels if level.block is block
                        for room in level.rooms), key=lambda entry: entry[0])
        pool.extend((level, room) for _room_num, level, room in owned if takes_part(room))
    return pool


# --- PS-XCHG-02: the contents ------------------------------------------------------

@dataclass
class Contents:
    """What moves between rooms (PS-XCHG-02): the layout with its push bit,
    the whole item byte and the trigger, with the item-position VALUE the
    room carries from the level it started in. The monsters and the sides
    stay."""
    layout_info: LayoutInfo
    item_info: ItemInfo
    trigger: RoomAction
    position_value: int

    @property
    def has_item(self) -> bool:
        return self.item_info.item_code != NO_ITEM_CODE

    @property
    def has_push_block(self) -> bool:
        return self.layout_info.movable_block

    @property
    def layout_low_six(self) -> int:
        return self.layout_info.room_type

    @property
    def layout_low_seven(self) -> int:
        return self.layout_info.layout_code


def take_contents(level: Level, room: Room) -> Contents:
    return Contents(room.layout_info, room.item_info, room.room_action,
                    level.item_position_table[room.item_position])


def put_contents(level: Level, room: Room, contents: Contents) -> None:
    """Write contents back. The item-position index is renumbered to the
    FIRST index of the room's level whose value equals the carried value,
    or 0 when none does; a room with no item writes index 0, with no
    random draw (PS-XCHG-02, R6)."""
    room.layout_info = contents.layout_info
    room.item_info = contents.item_info
    positions = level.item_position_table
    index = (positions.index(contents.position_value)
             if contents.has_item and contents.position_value in positions else 0)
    room.secret_info = SecretInfo(contents.trigger, ItemPosition(index))


# --- PS-XCHG-03: stair-type contents ------------------------------------------

STAIR_LAYOUT_CODES = frozenset({RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM, DIAMOND_STAIRS_PUSH,
                                SPIRAL_STAIRS_PUSH})   # $5B is NOT stair-type
PUSH_REVEALS_STAIRS = RoomAction.BLOCK_STAIRS


def is_stair_type(contents: Contents) -> bool:
    """PS-XCHG-03: layout (monster bit ignored) $1B/$1C/$5A/$5C, or trigger
    bits 2-0 = 5 (a push block reveals stairs)."""
    return (contents.layout_low_seven in STAIR_LAYOUT_CODES
            or contents.trigger == PUSH_REVEALS_STAIRS)


# --- PS-XCHG-04: the swap rules -------------------------------------------------

LANMOLAS = (0x3A, 0x3B)
RUPEE_STASH = 0x35
GLEEOKS = range(0x82, 0x86)      # monster bit + Gleeok lists $02-$05, any head count
FOUR_HEAD_GLEEOK = 0x85
GOHMAS = (0x33, 0x34)
DODONGOS = (0x31, 0x32)
TRAPS = frozenset(COMBINED_MONSTER_BIT | low for low in (0x09, 0x0A, 0x2D, 0x2E, 0x36, 0x37))
# Zelda's plain rule, matched on the layout's LOW SEVEN bits ($5A = 90 is
# live although the push bit itself is not banned). Quirk: no push-bit ban,
# no $1B/$1C ban and no cellar-exit test here, unlike the gate's rule.
ZELDA_XCHG_BAD_LAYOUT_CODES = frozenset({RoomType.CIRCLE_WALL, RoomType.HORIZONTAL_CHUTE_ROOM,
                                         RoomType.VERTICAL_ROWS, RoomType.SINGLE_SIX_BLOCK_ROOM,
                                         DIAMOND_STAIRS_PUSH})


def monster_refuses(monster: int, arriving: Contents, dodongo_checked: bool) -> bool:
    """PS-XCHG-04: does the monster that STAYS in a cell bar the layout
    arriving in it? The Ganon, $35, Lanmola, Gohma, Dodongo and trap lists
    test the arriving layout's low six bits; Zelda and Gleeok its low seven.
    Quirk: the Dodongo test is made for the first cell of a swap only."""
    low_six, low_seven = arriving.layout_low_six, arriving.layout_low_seven
    if monster == GANON_LIST:
        return low_six in GANON_BAD_LAYOUTS
    if monster == ZELDA_LIST:
        return low_seven in ZELDA_XCHG_BAD_LAYOUT_CODES
    if monster == RUPEE_STASH:
        return low_six in RUPEE_STASH_BAD_LAYOUTS
    if monster in LANMOLAS:
        return low_six in LANMOLA_BAD_LAYOUTS
    if monster in GLEEOKS:
        barred = GLEEOK_BAD_LAYOUTS | (GLEEOK4_EXTRA_BAD if monster == FOUR_HEAD_GLEEOK
                                       else frozenset())
        return arriving.has_push_block or low_seven in barred
    if monster in GOHMAS:
        return low_six in GOHMA_BAD_LAYOUTS
    if monster in DODONGOS:
        return dodongo_checked and low_six in DODONGO_BAD_LAYOUTS
    if monster in TRAPS:
        return low_six in BLADE_TRAP_BAD_LAYOUTS
    return False


def position_refuses(arriving: Contents, receiving_positions: list[int]) -> bool:
    """PS-XCHG-02: contents holding an item move only to a level whose four
    position values include the value they carry."""
    return arriving.has_item and arriving.position_value not in receiving_positions


@dataclass
class DungeonRoomShuffleResult:
    pool: int = 0
    swaps: int = 0
    skipped: int = 0
    stair_redraws: int = 0


def exchange_rooms(levels: list[Level], rng: IntRng) -> DungeonRoomShuffleResult:
    """PS-XCHG-01..04: the pool in scan order (block 0 rooms 0-127, then
    block 1); for each position a partner uniform over position..end,
    re-drawn while it pairs stair-type with non-stair-type contents; a swap
    that breaks a rule is skipped (quirk: no re-draw). Contents are written
    back at the end."""
    discard(rng, DISCARDED_DRAWS)
    pool = exchange_pool(levels)
    contents = [take_contents(level, room) for level, room in pool]
    monsters = [combined_monster(room) for _level, room in pool]
    positions = [level.item_position_table for level, _room in pool]
    stats = DungeonRoomShuffleResult(pool=len(pool))
    for position in range(len(pool)):
        partner = position + rng.below(len(pool) - position)
        while is_stair_type(contents[position]) != is_stair_type(contents[partner]):
            stats.stair_redraws += 1
            partner = position + rng.below(len(pool) - position)
        refused = (monster_refuses(monsters[position], contents[partner], dodongo_checked=True)
                   or monster_refuses(monsters[partner], contents[position], dodongo_checked=False)
                   or position_refuses(contents[partner], positions[position])
                   or position_refuses(contents[position], positions[partner]))
        if refused:
            stats.skipped += 1
            continue
        contents[position], contents[partner] = contents[partner], contents[position]
        stats.swaps += 1
    for (level, room), moved in zip(pool, contents, strict=True):
        put_contents(level, room, moved)
    return stats


# --- PS-XCHG-05: the second drop shuffle ---------------------------------------

DROP_SKIPPED_ITEMS = frozenset({NO_ITEM_CODE, Item.TRIFORCE_OF_POWER, Item.WOOD_SWORD})


def second_drop_shuffle(levels: list[Level], rng: IntRng) -> None:
    """PS-XCHG-05: for each level 1-9 in order, a Fisher-Yates over its
    rooms (cell order) whose item low five bits are not $03, $0E or $01;
    whole item bytes (dark and boss-sound bits ride along) are exchanged.
    Staircase cellars belong to no level and keep their items."""
    for level in sorted(levels, key=lambda level: level.level_num):
        rooms = [room for room in level.rooms
                 if room.item_info.item_code not in DROP_SKIPPED_ITEMS]
        dealt = [room.item_info for room in rooms]
        for position, room in enumerate(rooms):
            other = position + rng.below(len(rooms) - position)
            dealt[position], dealt[other] = dealt[other], dealt[position]
            room.item_info = dealt[position]

