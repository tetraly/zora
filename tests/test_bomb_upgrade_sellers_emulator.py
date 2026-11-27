"""Archipelago items piece 8 in the emulator (docs/design/archipelago-items.md), on PRG0 and PRG1: in seller mode
a bomb upgrader's room byte holds his place's item. He shows it where the game shows his rupee; standing there
without the rupees takes nothing (the room item object stays off); paying gives the item, not the bombs, and sets
the room's item-taken bit, so he is gone on re-entry. A Bomb Upgrade ($37), from him or from any other place,
raises MaxBombs by the seed's count and fills the bombs. With seller mode off he sells bombs as the game does."""
from dataclasses import replace
from functools import cache

import pytest

from tests.emulator import OBJ_STATE, OBJ_TYPE, OBJ_X, OBJ_Y, ROOM_ID, ROOM_ITEM_SLOT
from tests.needs import needs_base_rom
from tests.test_assignment import identity
from tests.test_assignment_emulator import ENTER_ROOM_MODE, INV_RUPEES, MONSTER_SLOTS, TAKEN, Console
from tests.test_level_items_emulator import _finished
from zora.generate.pipeline import finish_world, written_world
from zora.generate.places import Place, PlaceKind, write_item
from zora.model.enums import Enemy, Item
from zora.rom import inventory
from zora.rom.base_rom import as_player_rom, using_player_rom
from zora.rom.serialize.rom_file import serialize_to_rom

MAX_BOMBS = 0x67C
INV_BOMBS = 0x658
UPGRADER = 0x4F
PAY_X, PAY_Y = 0x78, 0x98               # where the "more bombs" man's rupee lies: Link pays standing there
VANILLA_UPGRADE_LEVELS = (5, 7)
SETTLE_FRAMES = 60
STAND_FRAMES = 120
RAFT_SLOT = 0x09


def sellers(revision: str) -> list[Place]:
    """CASE's two bomb upgraders that sell: a $4F person in one of the two bomb levels."""
    _, built = _finished(revision)
    levels = built.world.bomb_upgrade_levels or VANILLA_UPGRADE_LEVELS
    found = [Place(PlaceKind.ROOM, f"seller {room.room_num:02X}", level=level.level_num, room_num=room.room_num)
             for level in built.world.levels if level.level_num in levels
             for room in level.rooms if room.enemy == Enemy.BOMB_UPGRADER]
    assert len(found) == 2, found
    return found


@cache
def rom(revision: str, items: tuple[tuple[Place, Item], ...], on: bool = True) -> tuple[bytes, int]:
    """CASE's Archipelago ROM with each item written into its place, seller mode `on`; and the seed's count."""
    base, built = _finished(revision)
    with using_player_rom(as_player_rom(base)):
        world, finished = finish_world(built, identity(built))
    for place, item in items:
        write_item(world, place, item)
    config = replace(finished.config, archipelago_rom=True, seed_number=None, bomb_upgrade_sellers=on)
    return serialize_to_rom(written_world(world, config), base, config=config), world.overworld.bomb_upgrade.count


def upgrader_present(console: Console) -> bool:
    return any(console.emu[OBJ_TYPE + slot] == UPGRADER for slot in MONSTER_SLOTS)


def enter(console: Console, place: Place, rupees: int) -> None:
    assert place.level is not None and place.room_num is not None
    console.enter_room(place.level, place.room_num)
    console.emu[INV_RUPEES] = rupees
    console.emu.run(SETTLE_FRAMES)


def stand_on_the_rupee(console: Console) -> None:
    console.emu[OBJ_X], console.emu[OBJ_Y] = PAY_X, PAY_Y
    console.emu.run(STAND_FRAMES)


def reenter(console: Console, place: Place) -> None:
    assert place.room_num is not None
    console.emu[ROOM_ID] = place.room_num
    console._mode(ENTER_ROOM_MODE)
    console._wait()
    console.emu.run(SETTLE_FRAMES)


def taken_bit(console: Console, place: Place) -> bool:
    assert place.level is not None and place.room_num is not None
    return bool(console.emu[inventory.room_flags(place.level) + place.room_num] & inventory.ITEM_TAKEN)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_a_seller_gives_his_places_item_once_and_only_for_his_price(revision: str) -> None:
    place = sellers(revision)[0]
    image, _count = rom(revision, ((place, Item.RAFT),))
    console = Console(image)
    enter(console, place, rupees=0)
    assert upgrader_present(console)
    assert console.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN            # the room item object stays off
    stand_on_the_rupee(console)
    assert console.inventory(Item.RAFT) == 0 and not taken_bit(console, place)   # no rupees: nothing taken
    max_bombs = console.emu[MAX_BOMBS]
    console.emu[INV_RUPEES] = 0xFF
    console.emu[OBJ_X] = PAY_X - 0x10
    console.emu.run(10)
    stand_on_the_rupee(console)
    assert console.inventory(Item.RAFT) == 1
    assert console.emu[MAX_BOMBS] == max_bombs
    assert taken_bit(console, place)
    reenter(console, place)
    assert not upgrader_present(console)
    assert console.emu[OBJ_STATE + ROOM_ITEM_SLOT] == TAKEN
    assert not console.emu.nes.has_crashed


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
@pytest.mark.parametrize("where", ["seller", "room floor"])
def test_a_bomb_upgrade_raises_max_bombs_by_the_seeds_count(revision: str, where: str) -> None:
    """From the other seller's room, or lying on a room floor (from tests/test_assignment_emulator's own)."""
    if where == "seller":
        place = sellers(revision)[1]
    else:
        from tests.test_level_items_emulator import rom as level_rom
        place = level_rom(revision, Item.MAP_5)[1]["room floor"]
    image, count = rom(revision, ((place, Item.BOMB_UPGRADE),))
    console = Console(image)
    enter(console, place, rupees=0xFF)
    before = console.emu[MAX_BOMBS]
    if where == "seller":
        stand_on_the_rupee(console)
    else:
        console.clear_monsters()
        console.take_room_item()
    assert console.emu[MAX_BOMBS] == before + count
    assert console.emu[INV_BOMBS] == before + count
    assert taken_bit(console, place)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_without_seller_mode_he_sells_bombs(revision: str) -> None:
    place = sellers(revision)[0]
    image, count = rom(revision, (), on=False)
    console = Console(image)
    enter(console, place, rupees=0xFF)
    before = console.emu[MAX_BOMBS]
    stand_on_the_rupee(console)
    assert console.emu[MAX_BOMBS] == before + count
    assert taken_bit(console, place)


@needs_base_rom
@pytest.mark.parametrize("revision", ["prg0", "prg1"])
def test_archipelagos_raft_at_a_seller_is_bought(revision: str) -> None:
    """End to end: Bomb Upgrades in the Item Pool on, the raft placed with a seller by the assignment
    (archipelago.finish on the player's ROM): paying gives the raft, and the raft's own place holds a Bomb
    Upgrade."""
    from tests.archipelago_cases import FLAG_CASES
    from tests.test_bomb_upgrade_sellers import BOMB_UPGRADE, own, sellers, zora_string
    from tests.test_cave_takes_emulator import _base
    from zora import archipelago
    built = archipelago.build_from_strings(FLAG_CASES["baseline"][0], zora_string("baseline"), 1, _base(revision))
    assignment = own(built)
    seller = sellers(built)[0]
    raft = next(place for place, name in assignment.items() if name == "Raft")
    assignment[seller], assignment[raft] = "Raft", BOMB_UPGRADE
    console = Console(archipelago.finish(built, assignment))
    place = next(place for place in built.state.places if place.name == seller)
    enter(console, place, rupees=0xFF)
    assert upgrader_present(console)
    stand_on_the_rupee(console)
    assert console.inventory(Item.RAFT) == 1 and taken_bit(console, place)
