"""Item Counter (ZORA flag item_counter; asm/flags2/item-counter/) in the emulator. A new game is put on the overworld
or in a level by the level-load and enter-room modes; the status bar row under the rupees (PPU $208B) is read from
the nametable.

  - Each area shows the chest, 0, the slash and its table total; a total over 9 shows as the font's A-F.
  - Taking a counted floor item adds one; so do the bits a counted cellar, cave screen and once-only ware set.
  - Bits of places that do not count change nothing (a room or screen not listed, a re-buyable ware).
  - Under Item Only a level's heart containers count only as many as the deal placed there.
  - Neither tile shows anywhere else: no overworld screen or level room draws $50 or $51."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, ROOM_ID, Button, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_item_counter import ON, with_scope
from zora.flags import zora_flags
from zora.flags.fields import ItemShuffleScope, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
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


@cache
def counter_rom(scope: ItemShuffleScope = ItemShuffleScope.FULL, zora: str = ON) -> bytes:
    return generate_rom(with_scope(scope), SEED, remember_repo_base_rom(), zora_flag_string=zora).rom


def areas(rom: bytes) -> list[tuple[int, list[int], list[int], int]]:
    """The table as the patch reads it: each area's flags address, unique places, group and cap."""
    table = rom[TABLE:TABLE + TABLE_SIZE]
    out = []
    for area in range(AREAS):
        start = table[area]
        unique, group, cap = table[start + 2], table[start + 3], table[start + 4]
        places = list(table[start + BLOCK_HEADER:start + BLOCK_HEADER + unique + group])
        out.append((table[start] | table[start + 1] << 8, places[:unique], places[unique:], cap))
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


def test_every_area_shows_its_total() -> None:
    rom = counter_rom()
    for level, (_flags, unique, _group, cap) in enumerate(areas(rom)):
        assert shown(enter(rom, level)) == (0, len(unique) + cap), level


def test_taking_a_counted_floor_item_counts() -> None:
    """A counted room whose item lies on the floor: Link walks onto it."""
    rom = counter_rom()
    for level, (flags, unique, _group, _cap) in enumerate(areas(rom)):
        for room in unique if level else ():
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
    for level, (flags, unique, _group, _cap) in enumerate(areas(rom)):
        emu = enter(rom, level)
        for found, place in enumerate(unique, start=1):
            set_place(emu, flags, place)
            assert shown(emu) == (found, len(unique)), (level, hex(place))
        others = [number for number in range(0x80) if number not in unique][:4]
        for place in others:
            set_place(emu, flags, place)
        assert shown(emu) == (len(unique), len(unique))


def test_wares_count_and_totals_over_9_show_in_hex() -> None:
    zora = zora_flags.encode(zora_flags.ZoraFlags(item_counter=ThreeState.ON, shop_items_in_pool=True,
                                                  shuffle_blue_potion=ThreeState.ON,
                                                  shuffle_wood_sword=ThreeState.ON, randomize_letter=True))
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom(), zora_flag_string=zora).rom
    flags, unique, _group, _cap = areas(rom)[0]
    assert len(unique) > 9 and any(place & WARE_PLACE for place in unique)
    emu = enter(rom, 0)
    assert shown(emu) == (0, len(unique))
    emu[inventory.SHOP_BOUGHT_FLAGS + REBUYABLE_WARE[1]] |= 1 << REBUYABLE_WARE[0]
    settle(emu, UPDATE_FRAMES)
    assert shown(emu) == (0, len(unique))
    wares = [place for place in unique if place & WARE_PLACE]
    for found, place in enumerate(wares, start=1):
        set_place(emu, flags, place)
        assert shown(emu) == (found, len(unique))


def test_item_only_counts_only_the_dealt_hearts() -> None:
    rom = counter_rom(ItemShuffleScope.DUNGEON_ITEMS_ONLY)
    grouped = [(level, area) for level, area in enumerate(areas(rom)) if area[2]]
    assert grouped, "no level holds the coast's heart beside a boss's"
    level, (flags, unique, group, cap) = grouped[0]
    emu = enter(rom, level)
    assert shown(emu) == (0, len(unique) + cap)
    for place in group:
        set_place(emu, flags, place)
        assert shown(emu) == (cap, len(unique) + cap)


def test_neither_tile_shows_elsewhere() -> None:
    rom = counter_rom()

    def assert_clean(emu: Emulator, where: str) -> None:
        for base in NAMETABLES:
            for index, tile in enumerate(emu.nametable(base, NAMETABLE_SIZE)):
                if tile in (CHEST_TILE, SLASH_TILE):
                    assert base + index in (COUNTER, COUNTER + 2), (where, hex(base + index))

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
