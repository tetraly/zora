"""Item Counter in an Archipelago game's ROM, in the emulator (2.0.2; owner decision 2026-11-21), on PRG0 and PRG1:
every area shows its total, and taking a location that holds another player's item counts, as the client's check
does. The ROM is a multiworld player's (every other location another player's item; the PRG1 one rebuilt from the
recipe, as Archipelago's patch and the page's .apzora step build it). tests/test_item_counter_emulator.py plays
ZORA mode's counter."""
from functools import cache

import pytest

from tests.emulator import OBJ_X, OBJ_Y
from tests.needs import needs_base_rom
from tests.test_archipelago_item_counter import built, multiworld_assignment
from tests.test_item_counter_emulator import (
    PICKUP_FRAMES,
    ROOM_ITEM_SLOT,
    areas,
    enter,
    set_place,
    settle,
    shown,
)
from zora import archipelago
from zora.rom import inventory
from zora.rom.base_rom import PRG1_ROM_PATH, remember_repo_base_rom

pytestmark = [needs_base_rom, pytest.mark.slow]

CASE = "per-level items"
REVISIONS = ["PRG0", pytest.param("PRG1", marks=pytest.mark.skipif(not PRG1_ROM_PATH.exists(),
                                                                    reason="no PRG1 ROM beside the base"))]


@cache
def multiworld_rom(revision: str) -> bytes:
    result = built(CASE)
    assignment, received = multiworld_assignment(result)
    made = archipelago.recipe(result, assignment, received)
    rom = remember_repo_base_rom() if revision == "PRG0" else PRG1_ROM_PATH.read_bytes()
    return archipelago.rom_from_recipe(made, rom)


def foreign_rooms() -> dict[int, list[int]]:
    """Per level, the rooms whose location holds another player's item (floor items and cellars alike)."""
    result = built(CASE)
    assignment, _received = multiworld_assignment(result)
    rooms: dict[int, list[int]] = {}
    for place in result.state.places:
        if place.level and place.room_num is not None and assignment[place.name] == archipelago.FOREIGN:
            rooms.setdefault(place.level, []).append(place.room_num)
    return rooms


@pytest.mark.parametrize("revision", REVISIONS)
def test_every_area_shows_its_total_and_each_check_counts(revision: str) -> None:
    rom = multiworld_rom(revision)
    for level, (flags, places) in enumerate(areas(rom)):
        emu = enter(rom, level)
        assert shown(emu) == (0, len(places)), level
        for found, place in enumerate(places, start=1):
            set_place(emu, flags, place)
            assert shown(emu) == (found, len(places)), (level, hex(place))


@pytest.mark.parametrize("revision", REVISIONS)
def test_taking_another_players_item_counts(revision: str) -> None:
    """Link walks onto a floor item that is another player's: the room's item bit is set (the client's check)
    and the counter adds one."""
    rom = multiworld_rom(revision)
    table = areas(rom)
    for level, rooms in sorted(foreign_rooms().items()):
        flags, places = table[level]
        for room in rooms:
            assert room in places
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
    pytest.fail("no floor item of another player's that Link could take")
