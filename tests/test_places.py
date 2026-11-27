"""Item places (zora/generate/places.py; Archipelago Phase 2 tests 4 and 5, docs/archipelago.md):
names are stable, unique and inside the superset; the same seed gives the same places in the
same order; and the places read back from the finished ZORA-mode ROM are the BUILD list."""
import re
from dataclasses import replace
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from zora.generate.item_counter import counter_table
from zora.generate.pipeline import GenerationPlan, extra_options, generate_world, plan
from zora.generate.places import PlaceKind, all_item_places, all_place_names, item_pool, major_pool, read_item
from zora.generate.steps.shuffle_items import MINOR_ITEMS
from zora.model.enums import Destination, Item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

SEEDS = (1, 2, 3)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def _superset() -> frozenset[str]:
    return frozenset(all_place_names())


def _world(base: bytes, case: str, seed: int) -> tuple[GameWorld, GenerationPlan]:
    flag_string, zora_flag_string = FLAG_CASES[case]
    chosen = plan(flag_string, seed, zora_flag_string)
    world, _ = generate_world(chosen, base)
    return world, chosen


def test_the_superset_is_unique_and_covers_every_kind() -> None:
    names = all_place_names()
    # the wood sword cave, then the bomb upgrade sellers (piece 8), last
    assert len(names) == len(set(names)) == 9 * 128 * 2 + 5 + 5 * 3 + 1 + 9 * 128
    for expected in ("Level 3 Room 4B Floor", "Level 3 Room 4B Stairway", "White Sword Cave", "Shop 2 Middle",
                     "Potion Shop Middle", "Armos", "Coast", "Magical Sword Cave", "Letter Cave",
                     "Wood Sword Cave"):
        assert expected in names


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_names_are_stable_unique_and_in_the_superset(base: bytes, case: str, seed: int) -> None:
    world, chosen = _world(base, case, seed)
    extras = extra_options(chosen)
    places = all_item_places(world, extras)
    names = [place.name for place in places]
    assert len(names) == len(set(names))
    assert set(names) <= _superset()
    # every place holds a pool item, and the dungeon places come first, in block and room order
    assert all(read_item(world, place) in item_pool(extras) for place in places)
    kinds = [place.is_dungeon for place in places]
    assert kinds == sorted(kinds, reverse=True)
    again, _ = _world(base, case, seed)
    assert all_item_places(again, extras) == places


DUNGEON_NAME = re.compile(r"Level (\d) Room ([0-9A-F]{2}) (Floor|Stairway)")


@pytest.mark.parametrize("seed", SEEDS)
def test_dungeon_names_take_the_shown_level_number(base: bytes, seed: int) -> None:
    """Owner decision (2026-10-18): a dungeon place is named by the level number the status bar
    shows, so in a second-quest-dungeon seed, where paired levels show each other's numbers, the
    name points to the level the player sees; the place keeps its data level for the logic and
    its pickup flag. A room's own item is its Floor item, an item cellar's its room's Stairway."""
    world, chosen = _world(base, "second quest dungeons", seed)
    shown = {level.level_num: level.rom_level_num for level in world.levels}
    assert any(data != number for data, number in shown.items())
    places = [place for place in all_item_places(world, extra_options(chosen)) if place.is_dungeon]
    assert {place.kind for place in places} == {PlaceKind.ROOM, PlaceKind.CELLAR}
    for place in places:
        match = DUNGEON_NAME.fullmatch(place.name)
        assert match is not None, place.name
        assert place.level is not None
        assert int(match[1]) == shown[place.level]
        room = place.stair_room if place.kind is PlaceKind.CELLAR else place.room_num
        assert int(match[2], 16) == room
        assert match[3] == ("Stairway" if place.kind is PlaceKind.CELLAR else "Floor")


@pytest.mark.parametrize("seed", SEEDS)
@pytest.mark.parametrize("case", list(FLAG_CASES))
def test_places_survive_a_round_trip_through_the_rom(base: bytes, case: str, seed: int) -> None:
    world, chosen = _world(base, case, seed)
    extras = extra_options(chosen)
    places = all_item_places(world, extras)
    config = chosen.config
    rom = serialize_to_rom(world, base, config=config)
    reading = GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode)
    parsed = parse_rom(rom, reading)
    assert all_item_places(parsed, extras) == places
    assert [read_item(parsed, place) for place in places] == [read_item(world, place) for place in places]


def test_every_kind_appears(base: bytes) -> None:
    world, chosen = _world(base, "every ZORA flag on", 1)
    assert {place.kind for place in all_item_places(world, extra_options(chosen))} == set(PlaceKind)


MINOR_CASE = "minor dungeon drops"


@pytest.mark.parametrize("seed", SEEDS)
def test_minor_drops_are_places_the_item_counter_leaves_out(base: bytes, seed: int) -> None:
    """Shuffle Minor Dungeon Drops (B17; docs/design/archipelago-items.md piece 3): every level room
    and item cellar holding bombs, five rupees or a key is a place, marked minor; the other places
    are those of the major pool alone, so the Item Counter's table is what it was; and the
    white-sword cave forbids keys, as B17's deal does."""
    world, chosen = _world(base, MINOR_CASE, seed)
    extras = extra_options(chosen)
    assert extras.minor_dungeon_drops
    places = all_item_places(world, extras)
    minor = [place for place in places if place.minor]
    assert minor and all(place.is_dungeon and read_item(world, place) in MINOR_ITEMS for place in minor)
    assert not any(place.minor for place in places if read_item(world, place) in major_pool(extras))
    without = all_item_places(world, replace(extras, minor_dungeon_drops=False))
    assert [place.name for place in places if not place.minor] == [place.name for place in without]
    assert counter_table([place for place in places if not place.minor]) == counter_table(without)
    white_sword = next(place for place in places if place.destination == Destination.WHITE_SWORD_CAVE)
    assert white_sword.forbids == {Item.KEY}
