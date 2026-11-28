"""Show Item Pickups (ZORA flag show_item_pickups; asm/flags2/item-line/) in the emulator. The status bar's top row
(PPU $2022, 28 tiles) is read from the nametable.

  - Taking a floor item writes "GOT <item>" there, centered; about 6 seconds later the row is blank again.
  - A code in the latch shows its text; bombs, keys, maps and compasses for about 3 seconds; the quiet items, codes
    past the table and $FF (no item) show nothing.
  - With Item Counter on too, both rows show."""
from functools import cache

import pytest

from tests.emulator import CUR_LEVEL, GAME_MODE, GAME_SUBMODE, OBJ_X, OBJ_Y, ROOM_ID, Emulator, Mode
from tests.needs import needs_base_rom
from tests.test_item_line import ON
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.model.enums import Item
from zora.rom import item_line
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.item_counter import CHEST_TILE
from zora.rom.text_encoding import CHAR_TO_BYTE

pytestmark = [needs_base_rom, pytest.mark.slow]

ROW = 0x2022
ROW_ATTRIBUTES = 0x23C0
ROW_TILES = 28
COUNTER = 0x208B
LATCH = 0xF0
TIMER = 0xF1
IS_UPDATING_MODE = 0x11
ENTER_ROOM_MODE = 0x04
HEART_VALUES = 0x66F
THREE_HEARTS = 0x22
LINK_INVINCIBILITY_TIMER = 0x4F0
INVINCIBLE = 0xFF
ROOM_ITEM_SLOT = 0x13
SETTLE_FRAMES = 30
SHOW_FRAMES = 4
GONE_FRAMES = 2 * 180 + 10
SHORT_FRAMES = 2 * 90
NO_ITEM = 0xFF
PICKUP_FRAMES = 120
SEED = 3
BLANK = bytes([CHAR_TO_BYTE[" "]]) * ROW_TILES
BOTH = zora_flags.encode(zora_flags.ZoraFlags(show_item_pickups=ThreeState.ON, item_counter=ThreeState.ON))


@cache
def line_rom(zora: str = ON) -> bytes:
    return generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, SEED, remember_repo_base_rom(), zora_flag_string=zora).rom


def row_for(text: str) -> bytes:
    left = (ROW_TILES - len(text)) // 2
    return (" " * left + text).ljust(ROW_TILES).encode("ascii").translate(
        bytes(CHAR_TO_BYTE.get(chr(c), 0) for c in range(256)))


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
        emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = Mode.LOAD_LEVEL, 0, 0
        emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    if room is not None:
        emu[ROOM_ID] = room
        emu[GAME_MODE], emu[GAME_SUBMODE], emu[IS_UPDATING_MODE] = ENTER_ROOM_MODE, 0, 0
        emu.run_until(lambda: emu.mode == Mode.PLAY and emu[IS_UPDATING_MODE] == 1, limit=900)
    settle(emu)
    return emu


def test_the_row_starts_blank_and_the_bytes_start_clear() -> None:
    emu = enter(line_rom(), 0)
    assert emu.nametable(ROW, ROW_TILES) == BLANK
    assert emu[LATCH] == NO_ITEM and emu[TIMER] == 0


@pytest.mark.parametrize("zora", [ON, BOTH], ids=["alone", "with-item-counter"])
def test_a_latched_item_shows_then_goes(zora: str) -> None:
    emu = enter(line_rom(zora), 1)
    counter = emu.nametable(COUNTER, 1)
    attributes = emu.nametable(ROW_ATTRIBUTES, 8)
    emu[LATCH] = Item.RAFT
    settle(emu, SHOW_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == row_for("GOT RAFT")
    assert emu[LATCH] == NO_ITEM
    # The row's quadrants are palette 0 (white); the quadrants below keep theirs (the life meter's red).
    assert emu.nametable(ROW_ATTRIBUTES, 8) == bytes(byte & 0xF0 for byte in attributes)
    settle(emu, GONE_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == BLANK
    if zora == BOTH:
        assert counter[0] == CHEST_TILE and emu.nametable(COUNTER, 1)[0] == CHEST_TILE


@pytest.mark.parametrize("code", [Item.BOMBS, Item.KEY, Item.MAP, Item.COMPASS])
def test_short_items_show_for_half_the_time(code: Item) -> None:
    emu = enter(line_rom(), 1)
    emu[LATCH] = code
    settle(emu, SHOW_FRAMES)
    shown = row_for(item_line.item_texts()[code])
    assert emu.nametable(ROW, ROW_TILES) == shown
    settle(emu, SHORT_FRAMES - 20)
    assert emu.nametable(ROW, ROW_TILES) == shown
    settle(emu, 30)
    assert emu.nametable(ROW, ROW_TILES) == BLANK


PAUSED = 0xE0


def test_the_line_waits_while_paused() -> None:
    emu = enter(line_rom(), 1)
    emu[LATCH] = Item.RAFT
    settle(emu, SHOW_FRAMES)
    emu[PAUSED] = 1
    settle(emu, GONE_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == row_for("GOT RAFT")
    emu[PAUSED] = 0
    settle(emu, GONE_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == BLANK


def test_the_line_waits_while_the_item_screen_is_down() -> None:
    """MenuState, not Paused, is set then (Select's swap leaves Start the only pause)."""
    emu = enter(line_rom(), 0)              # the overworld: emulator.open_item_screen waits for its MenuState
    emu[LATCH] = Item.RAFT
    settle(emu, SHOW_FRAMES)
    timer = emu[TIMER]
    emu.open_item_screen()
    settle(emu, GONE_FRAMES)
    assert emu[TIMER] == timer
    emu.close_item_screen()
    settle(emu, GONE_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == BLANK


@pytest.mark.parametrize("code", [Item.FIVE_RUPEES, item_line.ITEM_CODES, NO_ITEM])
def test_quiet_codes_show_nothing(code: int) -> None:
    emu = enter(line_rom(), 1)
    emu[LATCH] = code
    settle(emu, SHOW_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == BLANK


def test_taking_a_floor_item_shows_it() -> None:
    """A level room whose item lies on the floor: Link walks onto it."""
    rom = line_rom()
    texts = item_line.item_texts()
    for level in range(1, 10):
        for room in range(0x80):
            emu = enter(rom, level, room)
            taken = None
            for _ in range(PICKUP_FRAMES):
                emu[OBJ_X], emu[OBJ_Y] = emu[OBJ_X + ROOM_ITEM_SLOT], emu[OBJ_Y + ROOM_ITEM_SLOT]
                settle(emu, 1)
                if emu[LATCH] != NO_ITEM:
                    taken = emu[LATCH]
                if emu[TIMER]:
                    break
            if taken in texts and emu[TIMER]:
                settle(emu, SHOW_FRAMES)            # the NMI copies the record a frame after it is written
                assert emu.nametable(ROW, ROW_TILES) == row_for(texts[taken])
                return
    pytest.fail("no floor item with a line was taken")


ITEM_TYPE_TO_LIFT = 0x505


@pytest.mark.parametrize("music", [False, True], ids=["original music", "Music: Random"])
def test_a_cave_ware_lifts_as_before_and_shows(music: bool) -> None:
    """TakeItem's lift setup is rewritten: Link still lifts the ware, and the row names it."""
    from tests.test_bait_in_pool import CAVE_ITEM_IDS, ITEM_INACTIVE, Console
    from tests.test_cave_takes_emulator import _music_assets
    from zora.model.enums import Destination
    from zora.rom.parse.rom_file import parse_rom
    base = remember_repo_base_rom()
    rom = line_rom()
    screen = next(screen.screen_num for screen in parse_rom(rom).overworld.screens
                  if screen.destination == Destination.WOOD_SWORD_CAVE)
    if music:
        from zora.rom.music.randomize import randomize_music
        rom = randomize_music(rom, base, _music_assets(), SEED).rom
    console = Console(rom)
    console.enter_cave(screen)
    position = next(position for position in range(3) if console.emu[CAVE_ITEM_IDS + position] != ITEM_INACTIVE)
    console.emu[CAVE_ITEM_IDS + position] = Item.BLUE_RING
    console.take_ware(position)
    for _ in range(GONE_FRAMES):
        console.emu.run(1)
        if console.emu.nametable(ROW, ROW_TILES) == row_for("GOT BLUE RING"):
            break
    else:
        pytest.fail("the row never named the ware")
    assert not console.emu.nes.has_crashed
    assert console.emu[ITEM_TYPE_TO_LIFT] == Item.BLUE_RING


PER_LEVEL = zora_flags.encode(zora_flags.ZoraFlags(
    show_item_pickups=ThreeState.ON, triforce_shuffle=zora_flags.LevelItemShuffle.ANYWHERE,
    map_compass_shuffle=zora_flags.LevelItemShuffle.ANYWHERE))
LEVEL_SHOWN = 0x19D80                   # bank 6 $9D70: each data level's status-bar number (zora/rom/level_items.py)


@pytest.mark.parametrize(("code", "kind", "level"), [
    (0x24, "COMPASS", 1), (0x2B, "COMPASS", 8), (0x2C, "MAP", 1), (0x33, "MAP", 8), (0x38, "TRIFORCE", 1),
    (0x3B, "TRIFORCE", 4), (0x3E, "TRIFORCE", 7),
    (Item.COMPASS, "COMPASS", 9), (Item.MAP, "MAP", 9), (Item.TRIFORCE, "TRIFORCE", 8)])
def test_a_level_item_names_its_level(code: int, kind: str, level: int) -> None:
    """Per-level mode: a level's own piece, map or compass says which level's it is, by the number shown."""
    rom = line_rom(PER_LEVEL)
    emu = enter(rom, 1)
    emu[LATCH] = code
    settle(emu, SHOW_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == row_for(f"GOT LEVEL {rom[LEVEL_SHOWN + level - 1]} {kind}")
    assert emu[LATCH] == NO_ITEM


@pytest.mark.parametrize("code", [0x34, 0x37, 0x3F])
def test_codes_between_and_past_the_level_items_show_nothing(code: int) -> None:
    emu = enter(line_rom(PER_LEVEL), 1)
    emu[LATCH] = code
    settle(emu, SHOW_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == BLANK


def test_the_generic_triforce_has_no_level_outside_per_level_mode() -> None:
    emu = enter(line_rom(), 1)
    emu[LATCH] = Item.TRIFORCE
    settle(emu, SHOW_FRAMES)
    assert emu.nametable(ROW, ROW_TILES) == row_for("GOT TRIFORCE")


def test_a_level_map_keeps_the_short_time() -> None:
    emu = enter(line_rom(PER_LEVEL), 1)
    emu[LATCH] = 0x2C
    settle(emu, SHOW_FRAMES + SHORT_FRAMES + 10)
    assert emu.nametable(ROW, ROW_TILES) == BLANK
