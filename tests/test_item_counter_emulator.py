"""Item Counter (ZORA flag item_counter; asm/flags2/item-counter/) in the emulator. A new game is put on the overworld
or in a level by the level-load and enter-room modes; the status bar row under the rupees (PPU $208B) is read from
the nametable.

  - Each area shows the chest, 0, the slash and its table total; a total over 9 shows as the font's A-F.
  - Taking a counted floor item adds one; so do the bits a counted cellar, cave screen and once-only ware set.
  - Bits of places that do not count change nothing (a room or screen not listed, a re-buyable ware).
  - Under Item Only every heart container counts the moment it is taken, the bosses' too.
  - With Change Hidden OW Tiles and Pegasus Boots on, the counter shows the same, and the chest and slash show
    nowhere else: no overworld screen or level room draws $52 or $53."""
from collections.abc import Callable
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_item_counter import ON, built, with_scope
from zora.flags import codec, zora_flags
from zora.flags.fields import (
    CHANGE_HIDDEN_TILES,
    DUNGEON_LAYOUT_SOURCE,
    DungeonLayoutSource,
    ItemShuffleScope,
    ThreeState,
)
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.places import read_item
from zora.model.enums import Item
from zora.rom import inventory
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.item_counter import AREAS, BLOCK_HEADER, CHEST_TILE, SLASH_TILE, TABLE, TABLE_SIZE, WARE_PLACE
from zora.rom.parse.rom_file import parse_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
COUNTER = 0x208B
COUNTER_TILES = 4
HEART_VALUES = 0x66F
THREE_HEARTS = 0x22
LINK_INVINCIBILITY_TIMER = 0x4F0
INVINCIBLE = 0xFF
ROOM_ITEM_SLOT = 0x13
SETTLE_FRAMES = 30
UPDATE_FRAMES = 4
PICKUP_FRAMES = 120
NAMETABLES = (0x2000, 0x2800)
NAMETABLE_SIZE = 0x3C0
REBUYABLE_WARE = (0, 0)             # the potion shop's left ware: a blue potion sold again and again
SEED = 3
SCREEN_COLUMNS = 16
EAST_EDGE_X = 0xF0
WALK_Y = 0x8D
WALK_FRAMES = 400
MOST_SCREENS = 120


BESIDE = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON, pegasus_boots=ThreeState.ON))


@cache
def counter_rom(scope: ItemShuffleScope = ItemShuffleScope.FULL, zora: str = ON, hidden_tiles: bool = False) -> bytes:
    flags = with_scope(scope)
    if hidden_tiles:
        flags = codec.encode(codec.decode(flags).updated(toggles={CHANGE_HIDDEN_TILES: ThreeState.ON}))
    return generate_rom(flags, SEED, remember_repo_base_rom(), zora_flag_string=zora).rom


def beside_rom() -> bytes:
    """The counter with Change Hidden OW Tiles and Pegasus Boots on, the flags that draw tiles $50-$5F."""
    return counter_rom(zora=BESIDE, hidden_tiles=True)


def areas(rom: bytes) -> list[tuple[int, list[int]]]:
    """The table as the patch reads it: each area's flags address and places."""
    table = rom[TABLE:TABLE + TABLE_SIZE]
    out = []
    for area in range(AREAS):
        start = table[area]
        count = table[start + 2]
        out.append((table[start] | table[start + 1] << 8,
                    list(table[start + BLOCK_HEADER:start + BLOCK_HEADER + count])))
    return out


def start_mode(emu: Emulator, mode: int) -> None:
    emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = mode, 0, 0


def wait_for_play(emu: Emulator) -> None:
    emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)


def settle(emu: Emulator, frames: int = SETTLE_FRAMES) -> None:
    for _ in range(frames):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1)


def enter(rom: bytes, level: int, room: int | None = None) -> Emulator:
    emu = Emulator(rom)
    emu.new_game()
    emu[HEART_VALUES] = THREE_HEARTS
    if level:
        emu[CUR_LEVEL] = level
        start_mode(emu, Mode.LOAD_LEVEL)
        wait_for_play(emu)
    if room is not None:
        emu[ROOM_ID] = room
        start_mode(emu, ENTER_ROOM_MODE)
        wait_for_play(emu)
    settle(emu)
    return emu


def shown(emu: Emulator) -> tuple[int, int] | None:
    """(found, total) as the row shows them, or None when it is blank."""
    tiles = emu.nametable(COUNTER, COUNTER_TILES)
    if tiles[0] != CHEST_TILE:
        return None
    assert tiles[2] == SLASH_TILE
    return tiles[1], tiles[3]


def set_place(emu: Emulator, flags: int, place: int) -> None:
    """Set the bit the game sets when the place's item is taken."""
    if place & WARE_PLACE:
        emu[inventory.SHOP_BOUGHT_FLAGS + (place >> 3 & 3)] |= 1 << (place & 7)
    else:
        emu[flags + place] |= inventory.ITEM_TAKEN
    settle(emu, UPDATE_FRAMES)


@pytest.mark.parametrize("rom", [counter_rom, beside_rom], ids=["alone", "beside-hidden-tiles-and-boots"])
def test_every_area_shows_its_total(rom: Callable[[], bytes]) -> None:
    made = rom()
    for level, (_flags, places) in enumerate(areas(made)):
        assert shown(enter(made, level)) == (0, len(places)), level


def test_taking_a_counted_floor_item_counts() -> None:
    """A counted room whose item lies on the floor: Link walks onto it."""
    rom = counter_rom()
    for level, (flags, places) in enumerate(areas(rom)):
        for room in places if level else ():
            emu = enter(rom, level, room)
            before = shown(emu)
            assert before is not None
            found, total = before
            for _ in range(PICKUP_FRAMES):
                emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
                settle(emu, 1)
                if emu[flags + room] & inventory.ITEM_TAKEN:
                    break
            else:
                continue                    # an item behind foes, a boss or stairs
            settle(emu)
            assert shown(emu) == (found + 1, total)
            return
    pytest.fail("no counted floor item")


def test_each_counted_bit_counts_and_others_do_not() -> None:
    rom = counter_rom()
    for level, (flags, places) in enumerate(areas(rom)):
        emu = enter(rom, level)
        for found, place in enumerate(places, start=1):
            set_place(emu, flags, place)
            assert shown(emu) == (found, len(places)), (level, hex(place))
        others = [number for number in range(0x80) if number not in places][:4]
        for place in others:
            set_place(emu, flags, place)
        assert shown(emu) == (len(places), len(places))


def test_wares_count_and_totals_over_9_show_in_hex() -> None:
    zora = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON, shop_items_in_pool=True,
                                                  shuffle_blue_potion=ThreeState.ON,
                                                  shuffle_wood_sword=ThreeState.ON, randomize_letter=True))
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom(), zora_flag_string=zora).rom
    flags, places = areas(rom)[0]
    assert len(places) > 9 and any(place & WARE_PLACE for place in places)
    emu = enter(rom, 0)
    assert shown(emu) == (0, len(places))
    emu[inventory.SHOP_BOUGHT_FLAGS + REBUYABLE_WARE[1]] |= 1 << REBUYABLE_WARE[0]
    settle(emu, UPDATE_FRAMES)
    assert shown(emu) == (0, len(places))
    wares = [place for place in places if place & WARE_PLACE]
    for found, place in enumerate(wares, start=1):
        set_place(emu, flags, place)
        assert shown(emu) == (found, len(places))


def test_item_only_counts_each_heart_container_when_taken() -> None:
    """Under Item Only the bosses' heart containers count too, each the moment it is taken."""
    rom = counter_rom(ItemShuffleScope.DUNGEON_ITEMS_ONLY)
    made = built(ItemShuffleScope.DUNGEON_ITEMS_ONLY, SEED)
    for level, (flags, places) in enumerate(areas(rom)):
        hearts = [place.room_num for place in made.places if level and place.level == level
                  and place.room_num is not None and read_item(made.world, place) == Item.HEART_CONTAINER]
        assert all(room in places for room in hearts)
        if not hearts:
            continue
        emu = enter(rom, level)
        for found, place in enumerate(hearts, start=1):
            set_place(emu, flags, place)
            assert shown(emu) == (found, len(places)), (level, hex(place))
        return
    pytest.fail("no level holds a heart container")


def test_second_quest_dungeons_count_by_the_level_loaded() -> None:
    """With the second quest's dungeons the game shows levels 2-3, 4-5 and 7-8 swapped; the table follows CurLevel,
    so each level shows its own total and counts its own bits."""
    flags = codec.encode(codec.decode(with_scope(ItemShuffleScope.FULL)).updated(
        options={DUNGEON_LAYOUT_SOURCE.id: int(DungeonLayoutSource.SECOND_QUEST)}))
    rom = generate_rom(flags, SEED, remember_repo_base_rom(), zora_flag_string=ON).rom
    for level, (flags_address, places) in enumerate(areas(rom)):
        emu = enter(rom, level)
        assert shown(emu) == (0, len(places)), level
        for found, place in enumerate(places, start=1):
            set_place(emu, flags_address, place)
            assert shown(emu) == (found, len(places)), (level, hex(place))


def test_the_chest_shows_nowhere_else() -> None:
    rom = beside_rom()

    def assert_clean(emu: Emulator, where: str) -> None:
        for base in NAMETABLES:
            for index, tile in enumerate(emu.nametable(base, NAMETABLE_SIZE)):
                if tile in (CHEST_TILE, SLASH_TILE):
                    assert base + index == COUNTER + (tile == SLASH_TILE) * 2, (where, hex(base + index))

    # Each overworld screen, scrolled onto from its neighbour (the east one; the west one for the last column).
    emu = enter(rom, 0)
    reached = 0
    for screen in range(0x80):
        east_edge = screen % SCREEN_COLUMNS == SCREEN_COLUMNS - 1
        emu[ROOM_ID] = screen - 1 if east_edge else screen + 1
        emu[OBJ_X], emu[OBJ_Y] = (EAST_EDGE_X, WALK_Y) if east_edge else (0, WALK_Y)
        for _ in range(WALK_FRAMES):
            emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
            emu.run(1, Button.RIGHT if east_edge else Button.LEFT)
            if emu[ROOM_ID] == screen and emu.mode == Mode.PLAY:
                break
        settle(emu)
        if emu[ROOM_ID] == screen:
            reached += 1
            assert_clean(emu, f"screen {screen:02X}")
    assert reached >= MOST_SCREENS
    # Each level's rooms, entered as the harness enters a room.
    rooms = 0
    for level in parse_rom(rom).levels:
        emu = enter(rom, level.level_num)
        assert_clean(emu, f"level {level.level_num}")
        for room in level.room_nums:
            emu[ROOM_ID] = room
            start_mode(emu, ENTER_ROOM_MODE)
            wait_for_play(emu)
            settle(emu, 3)
            assert_clean(emu, f"level {level.level_num} room {room:02X}")
            rooms += 1
    assert rooms > MOST_SCREENS


# Into a level by its overworld entrance and out by its first room's south door (found in testing): the counter
# shows the overworld's count until the level is on screen, and the level's until the overworld is. Link steps into
# the entrance inside a play frame (HandleWarpOW sets CurLevel and the stairs mode, $10), whose status bar update
# then comes; the stairs mode draws none, so a counter written on that frame showed the level's count for the
# whole walk down the stairs. The counter writes on every other frame: both parities are walked.
STAIRS_MODE = 0x10
LEAVE_CAVE_MODE = 0x0A
UNDERGROUND_EXIT_TYPE = 0x5A
LEVEL_EXIT = 2
PPU_MASK = 0xFE
RENDERING = 0x18
WALK_OUT_FRAMES = 120               # Link walks down out of the entrance, as leaving the level put him
STEP_FRAMES = 8
TRANSITION_FRAMES = 700


def open_entrance(rom: bytes) -> tuple[int, int]:
    """(level, screen) of a level whose entrance needs nothing: no bomb, candle, raft or ladder."""
    from zora.model.overworld import EntranceType
    for screen in parse_rom(rom).overworld.screens:
        if screen.destination.name.startswith("LEVEL_") and screen.entrance_type is EntranceType.OPEN:
            return int(screen.destination.name.removeprefix("LEVEL_")), screen.screen_num
    raise AssertionError("no level with an open entrance")


def rendering(emu: Emulator) -> bool:
    return bool(emu[PPU_MASK] & RENDERING)


def rows_around_the_load(emu: Emulator, button: Button, area: int) -> tuple[list[tuple[int, int] | None],
                                                                            list[tuple[int, int] | None], set[int]]:
    """The row each drawn frame before the screen goes dark for the load, and after it is drawn again, until play
    in `area` shows a count; and the modes seen."""
    before: list[tuple[int, int] | None] = []
    after: list[tuple[int, int] | None] = []
    modes: set[int] = set()
    dark = False
    for _ in range(TRANSITION_FRAMES):
        emu[LINK_INVINCIBILITY_TIMER] = INVINCIBLE
        emu.run(1, button)
        modes.add(emu.mode)
        if not rendering(emu):
            dark = True
            continue
        (after if dark else before).append(shown(emu))
        if dark and emu.mode == Mode.PLAY and emu[CUR_LEVEL] == area and shown(emu) is not None:
            return before, after, modes
    raise AssertionError("the transition never ended")


@pytest.mark.parametrize("parity", [0, 1])
def test_the_counter_switches_area_once_the_new_one_is_on_screen(parity: int) -> None:
    rom = counter_rom()
    level, screen = open_entrance(rom)
    flags, places = areas(rom)[0]
    emu = Emulator(rom)
    emu.new_game()
    emu[HEART_VALUES] = THREE_HEARTS
    emu[ROOM_ID], emu[CUR_LEVEL], emu[UNDERGROUND_EXIT_TYPE] = screen, 0, LEVEL_EXIT
    start_mode(emu, LEAVE_CAVE_MODE)
    wait_for_play(emu)
    set_place(emu, flags, places[0])            # the overworld's count differs from the level's
    settle(emu, WALK_OUT_FRAMES + parity)
    emu.run(STEP_FRAMES, Button.DOWN)
    overworld = (1, len(places))
    level_count = (0, len(areas(rom)[level][1]))
    assert shown(emu) == overworld and level_count != overworld

    # In: the overworld's count while the overworld is drawn, the walk down the stairs too; the level's from the
    # first count drawn in it (the game's load leaves the row blank until play)
    before, after, modes = rows_around_the_load(emu, Button.UP, level)
    assert STAIRS_MODE in modes, "Link never went down the stairs"
    assert set(before) == {overworld}, before
    assert {row for row in after if row is not None} == {level_count}, after

    # Out by the first room's south door: the level's count while the level is drawn, then the overworld's
    settle(emu)
    before, after, _ = rows_around_the_load(emu, Button.DOWN, 0)
    assert set(before) == {level_count}, before
    assert {row for row in after if row is not None} == {overworld}, after
