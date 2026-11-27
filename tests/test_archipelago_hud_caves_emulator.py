"""The client's HUD lines and received items in caves and cellars, in the emulator (2026-11-23; TheGobOne reported the
HUD often missing in caves).

In a cave a line used to wait for the frames the status-bar text took in the tile buffer: never on an empty buffer,
the Item Counter's record or a typed character of cave text, so it waited up to two seconds while the text typed.
zora.archipelago.hud_plans now writes into an empty buffer in caves too, and in caves and cellars after the game's
own short record (the typed character, the counter's record), which the NMI then sends with it. On a multiworld ROM
(Shop Items in the Item Pool), Item Counter on and off:

- every cave kind and an item cellar: from the frame the mode's update runs, every boundary whose frame finished
  takes a line, which lands whole: CHR RAM as without it, the nametables differing only in the HUD row, which holds
  the line (the cave text still types);
- right after a ware is taken (a "SENT ..." line), the next boundary takes it;
- a received item given in a cellar (zora.archipelago.may_receive, since 2026-11-23), every kind: the status bar
  then as if the item had been held before the cellar, the arrival sound played, Link still takes the cellar's own
  item and climbs out to the room it returns to.
"""
from collections.abc import Callable, Iterator, Sequence
from functools import cache

import pytest

from tests.emulator import OBJ_X, OBJ_Y, Button, Emulator
from tests.test_archipelago_item_counter import multiworld_assignment
from tests.test_bait_in_pool import CAVE_ITEM_IDS, CAVE_MODE, ITEM_INACTIVE, LEAVE_CAVE_MODE, Console
from tests.test_cellar_items import CELLAR_SOURCE_ROOM, RIGHT_LADDER_X
from zora import archipelago
from zora.model.enums import Destination, RoomType
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = [pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM"), pytest.mark.slow]

SEED = 8
LINE = "SENT BOW TO ANOTHER PLAYER"
ROOM_ID, CUR_LEVEL, UNDERGROUND_EXIT_TYPE = 0x0EB, 0x010, 0x05A
LOAD_LEVEL_MODE = 0x02
HEART_VALUES = inventory.ITEMS + inventory.HEART_VALUES_SLOT
EVERY_HEART = 0xFF
STATUS_CATCH_UP = 3                      # the status-bar text is queued every second frame
STAY_FRAMES = 240                        # the cave's text types in the first two seconds or so
HUD_START = archipelago.HUD_ROW - 0x2000
HUD_ROW = range(HUD_START, HUD_START + archipelago.HUD_WIDTH)
STATUS_BAR = range(0x40, 0x100)          # the status bar's rows below the HUD row, the minimap among them
LEFT_LADDER_X, FLOOR_Y = 0x30, 0xBD
CAVE_KINDS = (Destination.WOOD_SWORD_CAVE, Destination.TAKE_ANY, Destination.WHITE_SWORD_CAVE,
              Destination.MAGICAL_SWORD_CAVE, Destination.ANY_ROAD, Destination.LOST_HILLS_HINT,
              Destination.MONEY_MAKING_GAME, Destination.DOOR_REPAIR, Destination.LETTER_CAVE,
              Destination.DEAD_WOODS_HINT, Destination.POTION_SHOP, Destination.HINT_SHOP_1, Destination.SHOP_1,
              Destination.MEDIUM_SECRET)
AFTER_TAKE_FRAMES = 6                    # the take's own frames (the item's sound, the wares' redraw)
WARE_CAVES = (Destination.TAKE_ANY, Destination.WHITE_SWORD_CAVE, Destination.SHOP_1)
CELLAR_ITEMS = ("Heart Container", "White Sword", "Blue Ring", "Red Candle", "Raft", "Bow", "Bombs", "5 Rupees",
                "Key", "Red Potion", "Shield")
TABLES = archipelago.ClientTables({}, inventory.GiveRules())


@cache
def built(counter: bool) -> archipelago.BuildResult:
    values = {"item_counter": "on" if counter else "off", "shop_items_in_pool": "on"}
    return archipelago.build_from_strings(*archipelago.flag_strings(values), SEED, remember_repo_base_rom())


@cache
def rom(counter: bool) -> bytes:
    result = built(counter)
    assignment, received = multiworld_assignment(result)
    return archipelago.rom_from_recipe(archipelago.recipe(result, assignment, received), remember_repo_base_rom())


def buffer(emu: Emulator) -> list[int]:
    return [emu[inventory.DYN_TILE_BUF + index] for index in range(inventory.DYN_TILE_BUF_SIZE)]


def holds(emu: Emulator, guards: Sequence[archipelago.HudBytes]) -> bool:
    return all(emu[address + offset] == value for address, data in guards for offset, value in enumerate(data))


def plan(emu: Emulator) -> tuple[archipelago.HudBytes, ...] | None:
    """hud_write's choice at this boundary: the writes of the first plan whose guards hold, or None."""
    plans = archipelago.hud_plans(LINE, emu[inventory.CUR_PPU_CONTROL], emu[inventory.GAME_MODE], buffer(emu))
    return next((writes for writes, guards in plans if holds(emu, guards)), None)


def screen(emu: Emulator, frames: int = 1) -> tuple[bytes, bytes]:
    state = emu.save()
    emu.run(frames)
    seen = emu.pattern_tables(), emu.ciram()
    emu.load(state)
    return seen


def lands_whole(emu: Emulator, writes: Sequence[archipelago.HudBytes]) -> bool:
    """From this boundary, with the writes against without them: the next frame shows the line in the HUD row and
    leaves CHR RAM alone, and STATUS_CATCH_UP frames on nothing but the HUD row differs. (A line that took the
    status-bar text's place delays that text's next copy by the two frames it is queued again in: a rupee count
    that changed then shows a frame late, as in play.)"""
    state = emu.save()
    tiles, _nametables = screen(emu)
    _tiles, later = screen(emu, STATUS_CATCH_UP)
    for address, data in writes:
        for offset, value in enumerate(data):
            emu[address + offset] = value
    written_tiles, written = screen(emu)
    _written_tiles, written_later = screen(emu, STATUS_CATCH_UP)
    emu.load(state)
    changed = {index for index, (a, b) in enumerate(zip(written_later, later, strict=True)) if a != b}
    row = list(written[HUD_ROW.start:HUD_ROW.stop])
    return written_tiles == tiles and changed <= set(HUD_ROW) and row == list(archipelago.hud_record(LINE)[3:-1])


def cave_screen(counter: bool, destination: Destination) -> int:
    world = parse_rom(rom(counter))
    return next(screen.screen_num for screen in world.overworld.screens if screen.destination == destination)


def enter_cave(counter: bool, destination: Destination) -> Console:
    """Out on the cave's screen, then in; returned as the cave's update starts."""
    console = Console(rom(counter))
    emu = console.emu
    emu[HEART_VALUES] = EVERY_HEART                    # the sword caves hand their swords over
    emu[ROOM_ID], emu[CUR_LEVEL], emu[UNDERGROUND_EXIT_TYPE] = cave_screen(counter, destination), 0, 1
    console._mode(LEAVE_CAVE_MODE)
    emu.run(10)
    console._mode(CAVE_MODE, CAVE_MODE)
    return console


def item_cellar(counter: bool) -> tuple[int, int, int]:
    """(level, cellar room, the room it returns to) of the first level with an item cellar."""
    for level in parse_rom(rom(counter)).levels:
        for stair in level.block.staircases:
            if stair.room_type == RoomType.ITEM_STAIRCASE and stair.return_dest in level.room_nums:
                assert stair.return_dest is not None
                return level.level_num, stair.room_num, stair.return_dest
    raise AssertionError("no item cellar")


def enter_cellar(counter: bool, before: Callable[[Emulator], None] | None = None) -> Console:
    """Down the level's item cellar's stairs (as its staircase does); returned as the cellar's update starts.
    `before` runs on the room the stairs are in."""
    level, room, source = item_cellar(counter)
    console = Console(rom(counter))
    emu = console.emu
    emu[CUR_LEVEL] = level
    console._mode(LOAD_LEVEL_MODE)
    emu.run(40)
    if before is not None:
        before(emu)
    emu[CELLAR_SOURCE_ROOM], emu[ROOM_ID] = source, room
    console._mode(inventory.CELLAR_MODE, inventory.CELLAR_MODE)
    return console


def boundaries(emu: Emulator, frames: int) -> Iterator[Emulator]:
    for _ in range(frames):
        yield emu
        emu.run(1)


def assert_every_finished_frame_takes_the_line(emu: Emulator) -> None:
    missed = []
    for frame, at in enumerate(boundaries(emu, STAY_FRAMES)):
        if not inventory.frame_finished({inventory.CUR_PPU_CONTROL: at[inventory.CUR_PPU_CONTROL]}):
            continue                                    # a frame that lags: the next one takes it
        writes = plan(at)
        if writes is None:
            missed.append(frame)
        else:
            assert lands_whole(at, writes), frame
    assert not missed, missed


@pytest.mark.parametrize("counter", [False, True], ids=["counter off", "counter on"])
@pytest.mark.parametrize("destination", CAVE_KINDS, ids=lambda destination: destination.name)
def test_every_cave_frame_takes_a_line_whole(destination: Destination, counter: bool) -> None:
    assert_every_finished_frame_takes_the_line(enter_cave(counter, destination).emu)


@pytest.mark.parametrize("counter", [False, True], ids=["counter off", "counter on"])
def test_every_cellar_frame_takes_a_line_whole(counter: bool) -> None:
    assert_every_finished_frame_takes_the_line(enter_cellar(counter).emu)


@pytest.mark.parametrize("destination", WARE_CAVES, ids=lambda destination: destination.name)
def test_a_line_right_after_a_ware_is_taken(destination: Destination) -> None:
    console = enter_cave(True, destination)
    emu = console.emu
    emu.run(60)
    wares = [emu[CAVE_ITEM_IDS + position] for position in range(3)]
    console.take_ware(1 if wares[1] != ITEM_INACTIVE else wares.index(next(w for w in wares if w != ITEM_INACTIVE)))
    for _frame in range(AFTER_TAKE_FRAMES):
        writes = plan(emu)
        if writes is not None:
            assert lands_whole(emu, writes)
            return
        emu.run(1)
    raise AssertionError(f"no line within {AFTER_TAKE_FRAMES} frames of the take")


def decide(emu: Emulator, name: str) -> archipelago.Decision:
    ram = {address: emu[address] for address in TABLES.addresses()}
    server = archipelago.ServerView((archipelago.ReceivedItem(name),))
    return archipelago.client_step(ram, ram, server, TABLES, archipelago.NO_MEMORY)


def write(emu: Emulator, writes: Sequence[tuple[int, int]]) -> None:
    for address, value in writes:
        emu[address] = value


def cellar_check(counter: bool) -> archipelago.RamCheck:
    level, room, _source = item_cellar(counter)
    result = built(counter)
    place = next(place for place in result.state.places if place.level == level and place.room_num == room)
    return archipelago.pickup_checks(result)[place.name]


def take_and_climb_out(emu: Emulator, check: archipelago.RamCheck) -> bool:
    """Walk the cellar (test_cellar_items' route) until its item is taken, then back to the left ladder and up it.
    Whether the item was taken."""
    def taken() -> bool:
        return check.is_set({check.address: emu[check.address]})

    def walk(button: Button, done: Callable[[], bool], limit: int = 300) -> None:
        for _ in range(limit):
            if done() or emu.mode != inventory.CELLAR_MODE:
                return
            emu.run(1, button)

    walk(Button.DOWN, taken, 120)
    walk(Button.RIGHT, lambda: taken() or emu[OBJ_X] >= RIGHT_LADDER_X)
    walk(Button.UP, taken, 120)
    walk(Button.RIGHT, taken, 80)
    walk(Button.LEFT, taken, 200)
    took = taken()
    walk(Button.RIGHT, lambda: emu[OBJ_X] >= RIGHT_LADDER_X)
    walk(Button.DOWN, lambda: emu[OBJ_Y] >= FLOOR_Y, 200)
    walk(Button.LEFT, lambda: emu[OBJ_X] <= LEFT_LADDER_X)
    walk(Button.UP, lambda: False, 200)
    emu.run_until(lambda: emu.mode == inventory.PLAY_MODE, limit=600)
    return took


@pytest.mark.parametrize("name", CELLAR_ITEMS)
def test_a_received_item_is_given_in_a_cellar(name: str) -> None:
    emu = enter_cellar(True).emu
    emu.run(30)
    decision = decide(emu, name)
    assert decision.gives == name
    assert all(emu[address] == value for address, value in decision.guards)
    write(emu, decision.writes)
    emu.run(60)
    bar = bytes(emu.ciram()[index] for index in STATUS_BAR)
    assert emu[inventory.TUNE1_REQUEST] == 0                         # the arrival sound was played
    given = [(address, value) for address, value in decision.writes
             if address not in (archipelago.RECEIVED_COUNT, inventory.TUNE1_REQUEST)]
    held = enter_cellar(True, before=lambda before: write(before, given)).emu
    held.run(90)
    assert bar == bytes(held.ciram()[index] for index in STATUS_BAR)  # as if held from before the cellar
    _level, _room, source = item_cellar(True)
    assert take_and_climb_out(emu, cellar_check(True))
    assert (emu.mode, emu[ROOM_ID], emu.nes.has_crashed) == (inventory.PLAY_MODE, source, False)
    assert emu[archipelago.RECEIVED_COUNT] == 1
