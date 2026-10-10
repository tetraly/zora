"""Shuffle Dungeon Monsters (B32; PS-MONRD-01 to -03): the per-level monster
re-deal, which writes the room lists into the rooms."""

from dataclasses import dataclass

from ...model.enums import BossSound, Enemy, ItemPosition, RoomAction, RoomType, Side
from ...model.levels import GANON_ITEM_BYTE, GANON_LIST, ZELDA_LIST, Level, LevelBlock
from ...model.rooms import EnemyInfo, ItemInfo, RoomPlace, SecretInfo
from ..errors import GenerationFailure
from ..rng import IntRng
from ..shapes.enemies import LANMOLA_VALUES, RUPEE_VALUE, TRAP_LISTS
from ..shapes.tables import (
    BLADE_TRAP_BAD_LAYOUTS,
    DODONGO_BAD_LAYOUTS,
    GLEEOK4_EXTRA_BAD,
    GLEEOK_BAD_LAYOUTS,
    GOHMA_BAD_LAYOUTS,
    LANMOLA_BAD_LAYOUTS,
    RUPEE_STASH_BAD_LAYOUTS,
)
from ..shapes.world import BOSS_CODES, D_BOMB, D_SHUTTER, D_WALL, GRID_COLS, set_side, side_of
from .monster_lists import (
    MonsterShuffleResult,
    RoomLists,
    _byte,
    _has_monster_bit,
    _low_six,
)

# --- PS-MONRD ------------------------------------------------------------------

REDEAL_BUDGET = 10_000
# PS-MONRD-01: whole monster bytes left out of the re-deal.
REDEAL_LEFT_OUT = frozenset({0x00, Enemy.HUNGRY_GORIYA, 0xC0})

# PS-MONRD-02's swap rules (layouts are the layout byte's low six bits).
ZELDA_BAD_LAYOUTS = frozenset({RoomType.CIRCLE_WALL, RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.VERTICAL_ROWS,
                               RoomType.SINGLE_SIX_BLOCK_ROOM, RoomType.NARROW_STAIR_ROOM,
                               RoomType.SPIRAL_STAIR_ROOM})
GANON_BAD_LAYOUTS = frozenset({RoomType.SPIKE_TRAP_ROOM, RoomType.FOUR_TALL_ROOM, RoomType.GLEEOK_ROOM,
                               RoomType.GOHMA_ROOM, RoomType.THREE_ROWS, RoomType.REVERSE_C,
                               RoomType.CIRCLE_WALL, RoomType.DOUBLE_BLOCK, RoomType.LAVA_MOAT,
                               RoomType.MAZE_ROOM, RoomType.GRID_ROOM, RoomType.VERTICAL_CHUTE_ROOM,
                               RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.VERTICAL_ROWS, RoomType.ZIGZAG_ROOM,
                               RoomType.T_ROOM, RoomType.DIAMOND_STAIR_ROOM, RoomType.NARROW_STAIR_ROOM,
                               RoomType.SPIRAL_STAIR_ROOM, RoomType.DOUBLE_SIX_BLOCK_ROOM,
                               RoomType.SINGLE_SIX_BLOCK_ROOM, RoomType.FIVE_PAIR_ROOM,
                               RoomType.TURNSTILE_ROOM, RoomType.SINGLE_BLOCK_ROOM,
                               RoomType.TWO_FIREBALL_ROOM, RoomType.FOUR_FIREBALL_ROOM, RoomType.ZELDA_ROOM,
                               RoomType.TRIFORCE_ROOM})
GLEEOK_BYTES = frozenset({0x02, 0x03, 0x04, 0x05})    # one to four heads
FOUR_HEAD_LIST = 0x05
TRAP_BYTES = frozenset({0x09, 0x0A})
GOHMA_BYTES = frozenset({0x33, 0x34})
DODONGO_BYTES = frozenset({0x31, 0x32})

# PS-MONRD-03: Ganon's new room.
GANON_ITEM = ItemInfo.from_item_byte(GANON_ITEM_BYTE)
GANON_SECRET = SecretInfo(RoomAction.LAST_BOSS, ItemPosition.POSITION_A)   # trigger byte $03
GANON_KEPT_DOORS = frozenset({D_WALL, D_BOMB})
BOSS_SOUND_NEAR = 1              # item byte bit $20: boss-sound index bit 0
RAW_NEIGHBOUR_STEPS = (-GRID_COLS, GRID_COLS, -1, 1)


def _is_zelda(value: int) -> bool:
    return value == ZELDA_LIST


def _is_ganon(value: int) -> bool:
    return value == GANON_LIST


def _is_gleeok(value: int) -> bool:
    return _has_monster_bit(value) and _byte(value) in GLEEOK_BYTES


def _is_redeal_trap(value: int) -> bool:
    """Quirk: 9 and 10 are whole-byte tests here (count bits clear), unlike
    PS-MONLV-04's low-six-bits test."""
    return _has_monster_bit(value) and (_byte(value) in TRAP_BYTES
                                or _low_six(value) in TRAP_LISTS - TRAP_BYTES)


@dataclass(frozen=True)
class _Room:
    """A taking-part room as the swap rules read it."""
    place: RoomPlace
    layout: int                  # layout byte's low six bits
    has_push_block: bool         # layout byte's bit 6
    is_cellar_exit: bool


def is_swap_allowed(value_a: int, value_b: int, room_a: _Room, room_b: _Room) -> bool:
    """PS-MONRD-02: may value_a (in room_a) and value_b (in room_b) exchange?
    Quirk (the rule shape): if EITHER value is X, BOTH rooms' layouts must
    be safe for X."""
    rooms = (room_a, room_b)

    def are_both_clear(bad_layouts: frozenset[int]) -> bool:
        return all(room.layout not in bad_layouts for room in rooms)

    if _is_zelda(value_a) or _is_zelda(value_b):
        if not are_both_clear(ZELDA_BAD_LAYOUTS) or any(room.has_push_block for room in rooms):
            return False
        # Zelda may not arrive in a cellar exit (her own room included when
        # the draw picks her own position).
        if (_is_zelda(value_a) and room_b.is_cellar_exit) or (_is_zelda(value_b) and room_a.is_cellar_exit):
            return False
    if (_is_ganon(value_a) or _is_ganon(value_b)) and not are_both_clear(GANON_BAD_LAYOUTS):
        return False
    if (_byte(value_a) in LANMOLA_VALUES or _byte(value_b) in LANMOLA_VALUES) \
            and not are_both_clear(LANMOLA_BAD_LAYOUTS):
        return False
    if (_byte(value_a) == RUPEE_VALUE or _byte(value_b) == RUPEE_VALUE) \
            and not are_both_clear(RUPEE_STASH_BAD_LAYOUTS):
        return False
    if _is_gleeok(value_a) or _is_gleeok(value_b):
        # Each room against the value arriving in it (QUESTIONS #58.2).
        for room, arriving in ((room_a, value_b), (room_b, value_a)):
            if room.layout in GLEEOK_BAD_LAYOUTS or room.has_push_block:
                return False
            if _low_six(arriving) == FOUR_HEAD_LIST and room.layout in GLEEOK4_EXTRA_BAD:
                return False
    if (_is_redeal_trap(value_a) or _is_redeal_trap(value_b)) and not are_both_clear(BLADE_TRAP_BAD_LAYOUTS):
        return False
    for monster_bytes, bad_layouts in ((GOHMA_BYTES, GOHMA_BAD_LAYOUTS), (DODONGO_BYTES, DODONGO_BAD_LAYOUTS)):
        if (any(not _has_monster_bit(value) and _byte(value) in monster_bytes for value in (value_a, value_b))
                and not are_both_clear(bad_layouts)):
            return False
    return True


def _cellar_exits(level: Level) -> set[int]:
    """Both exit rooms of each staircase in the level's
    `LevelInfo_CellarRoomIdArray` (those with a room in the level)."""
    exits: set[int] = set()
    for stair in level.staircase_rooms:
        rooms = ([stair.return_dest] if stair.room_type == RoomType.ITEM_STAIRCASE
                 else [stair.left_exit, stair.right_exit])
        exits.update(room for room in rooms if room is not None)
    return exits


def _monsters(value: int) -> EnemyInfo:
    """The monsters a nine-bit monster value writes. A boss's count index
    ships as 0 (SH-BOSS-07), whatever count bits its value carries."""
    monsters = EnemyInfo.from_monster_value(value)
    return EnemyInfo(monsters.enemy) if monsters.enemy in BOSS_CODES else monsters


def _write_ganon_room(block: LevelBlock, room_number: int, copy_to: int | None,
                      taking_part: set[int]) -> None:
    """PS-MONRD-03's Ganon writes, in order: the room's item byte to the
    last walked $28 room, then $8E and trigger 3, shutters on every side
    but walls and bombable walls, and the boss sound on taking-part
    byte-neighbours (raw index: left/right look across a row end)."""
    room = block.room(room_number)
    if copy_to is not None:
        block.room(copy_to).item_info = room.item_info
    room.item_info = GANON_ITEM
    room.secret_info = GANON_SECRET
    for side in Side:
        if side_of(room, side) not in GANON_KEPT_DOORS:
            set_side(room, side, D_SHUTTER)
    for step in RAW_NEIGHBOUR_STEPS:
        if room_number + step in taking_part:
            beside = block.room(room_number + step)
            beside.boss_sound = BossSound(beside.boss_sound | BOSS_SOUND_NEAR)


def redeal_level(blocks: list[LevelBlock], levels: list[Level], lists: RoomLists, level_num: int,
                 state: MonsterShuffleResult, rng: IntRng) -> None:
    """PS-MONRD-01..03 for one level: a Fisher-Yates walk over the taking-
    part rooms with the swap rules (a rejected draw redraws the same
    position; 10,000 draws per level, then the generation restarts), then
    the write-back."""
    staged_level = next(candidate for candidate in levels if candidate.level_num == level_num)
    block = staged_level.block
    places = [place for place in lists.rooms[level_num] if _byte(lists.values[place]) not in REDEAL_LEFT_OUT]
    exits = _cellar_exits(staged_level)
    rooms = [_Room(place, block.room(place.room_number).room_type, block.room(place.room_number).movable_block,
                   place.room_number in exits)
             for place in places]
    values = [lists.values[place] for place in places]
    count = len(rooms)
    draws = 0
    last_ganon_layout: int | None = None
    for position in range(count):
        while True:
            draws += 1
            if draws > REDEAL_BUDGET:
                raise GenerationFailure(f"level {level_num}: monster re-deal ran out of draws")
            # the $28 test is made at every draw, for the position being filled
            if block.room(rooms[position].place.room_number).layout_code == RoomType.GANON_ROOM:
                last_ganon_layout = rooms[position].place.room_number
            other = position + rng.below(count - position)
            if is_swap_allowed(values[position], values[other], rooms[position], rooms[other]):
                values[position], values[other] = values[other], values[position]
                break
    state.redeal_draws += draws
    # write-back: every boss-sound clear first, then every monster write
    for room in rooms:
        dealt_room = block.room(room.place.room_number)
        if dealt_room.boss_sound != BossSound.NONE:
            dealt_room.boss_sound = BossSound.NONE
    taking_part = {room.place.room_number for room in rooms}
    for room, value in zip(rooms, values, strict=True):
        block.room(room.place.room_number).enemy_info = _monsters(value)
        if _is_ganon(value):
            _write_ganon_room(block, room.place.room_number, last_ganon_layout, taking_part)


def shuffle_dungeon_monsters(blocks: list[LevelBlock], levels: list[Level], lists: RoomLists,
                             state: MonsterShuffleResult, rng: IntRng) -> None:
    """PS-MONRD: every level, 1 to 9. The re-deal moves Zelda and Ganon;
    the passes after it find them by content."""
    for level_num in sorted(lists.rooms):
        redeal_level(blocks, levels, lists, level_num, state, rng)
