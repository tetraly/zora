"""Archipelago items piece 4 in the emulator (docs/design/archipelago-items.md section 8), on PRG0 and
PRG1. The test code $24 (the level 1 compass: the far routines' one row in piece 4) is written into one
place of each kind (tests/test_ap_items.py's every_kind). At each, it is drawn as the Compass is (the
sprites equal a control ROM's with the Compass in the same places, frame for frame), lifted in a cave
the same way, taken once, and sets InvCompass bit 0. The bank-4 item object (UpdateItem: the Armos item
and monster drops) draws and takes it too and the game goes on in bank 4, and every cave kind still
takes a plain item (the stubs leave bank 1 mapped)."""
from functools import cache

import pytest

from tests.emulator import (
    CUR_LEVEL,
    FRAME_COUNTER,
    ITEMS,
    OBJ_STATE,
    OBJ_TYPE,
    OBJ_X,
    OBJ_Y,
    ROOM_ID,
    ROOM_ITEM_SLOT,
    Mode,
)
from tests.needs import needs_base_rom
from tests.test_ap_items import TEST_CODE, every_kind
from tests.test_assignment_emulator import (
    CAVE_ITEM_IDS,
    CAVE_MODE,
    CAVE_WARE_XS,
    CAVE_WARE_Y,
    ENTER_ROOM_MODE,
    LEAVE_CAVE_MODE,
    TAKE_WARE_FRAMES,
    TAKEN,
    UNDERGROUND_EXIT_TYPE,
    Console,
)
from tests.test_bait_in_pool import ITEM_INACTIVE
from tests.test_bait_in_pool import Console as CaveConsole
from tests.test_cave_takes_emulator import CAVES, SETTLE_FRAMES, _base
from tests.test_progressive_emulator import INV_LETTER, LETTER_DELIVERED
from zora.generate.places import Place, PlaceKind
from zora.model.enums import Item
from zora.rom.parse.rom_file import parse_rom

CONTROL = Item.COMPASS
INV_COMPASS = ITEMS + 0x10
LEVEL_1_COMPASS = 0x01
ROOM_ITEM_ID = 0xAB                     # RoomItemId
COAST_SCREEN = 0x5F
ITEM_OBJECT = 0x60                      # UpdateObject_JumpTable's UpdateItem
OBJ_UNINITIALIZED = 0x492
OBJ_METASTATE = 0x405
ITEM_OBJ_ITEM_ID = 0xAC                 # Item_ObjItemId (shares ObjState's bytes)
ITEM_OBJ_LIFETIME = 0x3A8               # Item_ObjItemLifetime: under $F0 it can be taken
TAKEABLE_LIFETIME = 0x80
SPAWN_SLOT = 1
SPAWN_X, SPAWN_Y = 0x40, 0x8D
SHOWN_FRAMES = 4
LIFT_FRAMES = 20                        # into the $80-frame lift
TAKE_FRAMES = 60
PLAIN_WARE = Item.BLUE_RING
SPRITE_SIZE = 4
INV_RING = 0x0B
HIDDEN_Y = 0xEF
DIGIT_TILES = (0x55, 0x57, 0x59)            # ap-items' digit pairs' sprite tiles


@cache
def consoles(revision: str) -> tuple[Console, Console, dict[str, Place]]:
    base = _base(revision)
    rom, places, _ = every_kind(base, TEST_CODE)
    control, _, _ = every_kind(base, CONTROL)
    return Console(rom), Console(control), places


def both(revision: str) -> tuple[Console, Console, dict[str, Place]]:
    test, control, places = consoles(revision)
    for console in (test, control):
        console.emu.load(console.start)
    return test, control, places


def visible_sprites(console: Console) -> list[bytes]:
    """The OAM records on screen (a hidden record, Y $EF and up, may keep a stale tile)."""
    oam = console.emu.sprites()
    return [oam[at:at + SPRITE_SIZE] for at in range(0, len(oam), SPRITE_SIZE) if oam[at] < HIDDEN_Y]


def same_sprites(test: Console, control: Console, what: object, items: int = 1) -> None:
    """The test code is drawn as the Compass, plus its level's digit (piece 6): one more 8x16 sprite on a
    digit pair's tile."""
    shown = visible_sprites(test)
    digits = [record for record in shown if record[1] in DIGIT_TILES]
    # the digit takes a sprite record, so the cycling puts the rest in other records: compare them as a set
    assert sorted(record for record in shown if record[1] not in DIGIT_TILES) == sorted(visible_sprites(control)), what
    assert len(digits) == items, what                          # one per test-code item shown


def assert_taken_once(test: Console, what: object) -> None:
    assert test.emu[INV_COMPASS] == LEVEL_1_COMPASS, what
    test.emu.run(TAKE_FRAMES)
    assert test.emu[INV_COMPASS] == LEVEL_1_COMPASS, what
    assert not test.emu.nes.has_crashed, what


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("kind", ["room floor", "room drop", "cellar"])
def test_a_room_item(revision: str, kind: str) -> None:
    test, control, places = both(revision)
    place = places[kind]
    assert place.level is not None and place.room_num is not None
    for console in (test, control):
        console.enter_room(place.level, place.room_num)
        if kind == "room drop":
            console.clear_monsters()
    what = (revision, kind, place.name)
    assert test.emu[ROOM_ITEM_ID] == TEST_CODE.value, what
    same_sprites(test, control, what)
    assert test.emu[INV_COMPASS] == 0, what
    test.take_room_item()
    assert_taken_once(test, what)
    # Taken once: entering the room again shows no item.
    test.emu[ROOM_ID] = place.room_num
    test._mode(ENTER_ROOM_MODE)
    test._wait()
    test.emu.run(SHOWN_FRAMES)
    assert test.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN, what
    assert test.emu[INV_COMPASS] == LEVEL_1_COMPASS, what


def take_ware_and_lift(console: Console, position: int) -> None:
    """Walk onto the ware and run until it is taken, then LIFT_FRAMES into the lift."""
    console.emu[OBJ_X] = CAVE_WARE_XS[position]
    console.emu[OBJ_Y] = CAVE_WARE_Y
    console.emu.run_until(lambda: console.emu[CAVE_ITEM_IDS + position] == TAKEN, limit=TAKE_WARE_FRAMES)
    console.emu.run(LIFT_FRAMES)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("kind", ["cave", "shop ware"])
def test_a_cave_ware_is_lifted(revision: str, kind: str) -> None:
    test, control, places = both(revision)
    place = places[kind]
    position = 1 if place.kind == PlaceKind.CAVE else place.position or 0
    what = (revision, kind, place.name)
    for console in (test, control):
        console.enter_cave(place.screens[0])
    assert test.emu[CAVE_ITEM_IDS + position] & 0x3F == TEST_CODE.value, what
    same_sprites(test, control, what)
    for console in (test, control):
        take_ware_and_lift(console, position)
    same_sprites(test, control, what)            # lifted over Link's head as the Compass is
    assert_taken_once(test, what)
    assert test.emu.mode == CAVE_MODE, what


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_coast_item(revision: str) -> None:
    test, control, _ = both(revision)
    for console in (test, control):
        console.emu[ROOM_ID] = COAST_SCREEN
        console.emu[CUR_LEVEL] = 0
        console.emu[UNDERGROUND_EXIT_TYPE] = 1
        console._mode(LEAVE_CAVE_MODE)
        console._wait()
        console.emu.run(SHOWN_FRAMES)
    assert test.emu[ROOM_ITEM_ID] == TEST_CODE.value
    assert test.emu[OBJ_STATE + ROOM_ITEM_SLOT] != TAKEN
    same_sprites(test, control, revision)
    test.take_room_item()
    assert_taken_once(test, revision)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_bank_4_item_object(revision: str) -> None:
    """An item object (the Armos item's and the drops' kind) holding the test code, in a level room
    with its monsters gone: drawn as the Compass, taken by Link, and the item object's update goes on
    in bank 4 (the wrappers map it again after a far draw or take)."""
    test, control, places = both(revision)
    place = places["room floor"]
    assert place.level is not None and place.room_num is not None
    for console, item in ((test, TEST_CODE), (control, CONTROL)):
        console.enter_room(place.level, place.room_num)
        console.clear_monsters()
        emu = console.emu
        emu[OBJ_TYPE + SPAWN_SLOT] = ITEM_OBJECT
        emu[OBJ_UNINITIALIZED + SPAWN_SLOT] = 0
        emu[OBJ_METASTATE + SPAWN_SLOT] = 0
        emu[ITEM_OBJ_ITEM_ID + SPAWN_SLOT] = item.value
        emu[ITEM_OBJ_LIFETIME + SPAWN_SLOT] = TAKEABLE_LIFETIME
        emu[OBJ_X + SPAWN_SLOT], emu[OBJ_Y + SPAWN_SLOT] = SPAWN_X, SPAWN_Y
        emu.run(SHOWN_FRAMES)
    same_sprites(test, control, revision, items=2)          # the room's own item and the object
    assert test.emu[INV_COMPASS] == 0
    test.emu[OBJ_X], test.emu[OBJ_Y] = SPAWN_X, SPAWN_Y
    test.emu.run_until(lambda: test.emu[OBJ_TYPE + SPAWN_SLOT] == 0, limit=TAKE_FRAMES)
    assert_taken_once(test, revision)
    before = test.emu[FRAME_COUNTER]
    test.emu.run(SETTLE_FRAMES)
    assert test.emu.mode == Mode.PLAY and test.emu[FRAME_COUNTER] != before


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_every_cave_kind_takes_a_plain_item(revision: str) -> None:
    """tests/test_cave_takes_emulator.py's take, in each cave kind, on this patch's ROM."""
    rom, _, _ = every_kind(_base(revision), TEST_CODE)
    screens = {destination: next(screen.screen_num for screen in parse_rom(rom).overworld.screens
                                 if screen.destination == destination) for destination in CAVES}
    for destination in CAVES:
        console = CaveConsole(rom)
        console.emu[INV_LETTER] = LETTER_DELIVERED           # the potion shop opens
        console.enter_cave(screens[destination])
        position = next(position for position in range(3)
                        if console.emu[CAVE_ITEM_IDS + position] != ITEM_INACTIVE)
        console.emu[CAVE_ITEM_IDS + position] = PLAIN_WARE
        console.take_ware(position)
        before = console.emu[FRAME_COUNTER]
        console.emu.run(SETTLE_FRAMES)
        case = (revision, destination.name)
        assert not console.emu.nes.has_crashed, case
        assert console.emu[FRAME_COUNTER] != before, case
        assert console.emu.mode == CAVE_MODE, case
        assert console.emu[ITEMS + INV_RING] == 1, case
