"""Archipelago items piece 7 in the emulator (docs/design/archipelago-items.md section 8), on PRG0 and PRG1: a
single-player ROM from generate_rom with both level-item switches On under Item Shuffle Full, played with no
client. A level item the swaps moved into another level's room, and one in a cave or shop ware, each set exactly
their own level's bit; a piece refills the hearts and the level goes on; the digit beside an item is the number its
level's status bar shows. The patch itself is piece 6's, checked on Archipelago ROMs by
tests/test_level_items_emulator.py."""
from functools import cache

import pytest

from tests.emulator import Mode
from tests.needs import needs_base_rom
from tests.test_assignment_emulator import HEART_VALUES, Console
from tests.test_cave_takes_emulator import _base
from tests.test_level_items_emulator import (
    DIGIT_FRAMES,
    GAME_MODE,
    SETTLE_FRAMES,
    WORLD_IS_FILLING_HEARTS,
    expected_bit,
    inventory_bytes,
    shown_digits,
    take,
)
from tests.test_solo_level_items import BOTH_ON, z1r
from zora.flags.fields import ItemShuffleScope
from zora.generate import pipeline
from zora.generate.places import Place, PlaceKind
from zora.generate.solo_assignment import level_items_moved, solo_assignment
from zora.model.enums import Item, RoomAction
from zora.model.level_items import LevelItemKind, level_of
from zora.rom.base_rom import as_player_rom, using_player_rom

FLAGS = z1r(ItemShuffleScope.FULL)
SEEDS = range(1, 21)
SHOWN_LATER = (RoomAction.LAST_BOSS, RoomAction.ALL_DEAD_ITEM)
PIECE_LEVEL_ABSENT = 9


def floor_place(built: pipeline.Built, place: Place) -> bool:
    """A room place whose item stands on the floor at once, not in a boss's room."""
    if place.kind != PlaceKind.ROOM:
        return False
    assert place.level is not None and place.room_num is not None
    room = next(level for level in built.world.levels if level.level_num == place.level).block.room(place.room_num)
    return room.room_action not in SHOWN_LATER and not room.enemy.is_boss


@cache
def seed_rom(revision: str) -> tuple[bytes, pipeline.Built, dict[str, tuple[Place, Item]]]:
    """The first seed whose swaps put a piece on another level's room floor and a level item in a cave or ware
    with an entrance: its single-player ROM, BUILD and those places (`away piece`, `ware`)."""
    base = _base(revision)
    for seed in SEEDS:
        with using_player_rom(as_player_rom(base)):
            built = pipeline.build(pipeline.plan(FLAGS, seed, BOTH_ON), base)
        assignment = solo_assignment(built)
        new = level_items_moved(built)
        chosen: dict[str, tuple[Place, Item]] = {}
        for place in built.places:
            item = assignment[place.name]
            if not isinstance(item, Item) or item not in new:
                continue
            kind_level = level_of(item)
            assert kind_level is not None
            kind, level = kind_level
            if (place.is_dungeon and kind is LevelItemKind.TRIFORCE and level != place.level
                    and floor_place(built, place)):
                chosen.setdefault("away piece", (place, item))
            elif not place.is_dungeon and place.screens and place.kind in (PlaceKind.SHOP_WARE, PlaceKind.CAVE):
                chosen.setdefault("ware", (place, item))
        if len(chosen) == 2:
            rom = pipeline.generate_rom(FLAGS, seed, base, zora_flag_string=BOTH_ON).rom
            return rom, built, chosen
    raise AssertionError("no seed with both kinds of place")


def shown_number(built: pipeline.Built, item: Item) -> int:
    found = level_of(item)
    assert found is not None
    return next(level.rom_level_num for level in built.world.levels if level.level_num == found[1])


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("which", ["away piece", "ware"])
def test_a_moved_level_item_sets_exactly_its_bit(revision: str, which: str) -> None:
    image, _built, chosen = seed_rom(revision)
    place, item = chosen[which]
    console = Console(image)
    before = inventory_bytes(console)
    kind = "room floor" if place.is_dungeon else "cave" if place.kind is PlaceKind.CAVE else "shop ware"
    take(console, place, kind)
    console.emu.run(SETTLE_FRAMES)
    after = inventory_bytes(console)
    address, mask = expected_bit(item)
    what = (revision, which, item.name, place.name)
    assert {a: after[a] for a in after if after[a] != before.get(a)} == {address: before[address] | mask}, what
    assert not console.emu.nes.has_crashed, what


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_piece_in_another_level_refills_and_the_level_goes_on(revision: str) -> None:
    image, _built, chosen = seed_rom(revision)
    place, _item = chosen["away piece"]
    assert place.level is not None and place.room_num is not None
    console = Console(image)
    console.enter_room(place.level, place.room_num)
    console.clear_monsters()
    console.emu[HEART_VALUES] = console.emu[HEART_VALUES] & 0xF0          # one heart left
    console.take_room_item()
    assert console.emu[WORLD_IS_FILLING_HEARTS] != 0
    console.emu.run_until(lambda: console.emu[WORLD_IS_FILLING_HEARTS] == 0, limit=600)
    assert console.emu[HEART_VALUES] & 0x0F == console.emu[HEART_VALUES] >> 4    # full
    assert console.emu.mode == Mode.PLAY and console.emu[GAME_MODE] != 0x12


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_the_digit_is_the_pieces_own_level(revision: str) -> None:
    """The moved piece shows its own level's number (as the status bar shows it), not the room's level."""
    image, built, chosen = seed_rom(revision)
    place, item = chosen["away piece"]
    assert place.level is not None and place.room_num is not None
    console = Console(image)
    console.enter_room(place.level, place.room_num)
    console.emu.run(DIGIT_FRAMES)
    assert shown_digits(console, image) == [shown_number(built, item)]
