"""Item places (zora/generate/places.py; Archipelago Phase 2 tests 4 and 5, docs/archipelago.md):
names are stable, unique and inside the superset; the same seed gives the same places in the
same order; and the places read back from the finished ZORA-mode ROM are the BUILD list."""
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from zora.generate.pipeline import GenerationPlan, extra_options, generate_world, plan
from zora.generate.places import PlaceKind, all_item_places, all_place_names, major_pool, read_item
from zora.model.game_world import GameWorld
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

SEEDS = (1, 2, 3)


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("vanilla ROM missing")
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
    assert len(names) == len(set(names)) == 9 * 128 * 2 + 5 + 5 * 3
    for expected in ("Level 3 Room 4B", "Level 3 Room 4B Cellar", "White Sword Cave", "Shop 2 Middle",
                     "Potion Shop Middle", "Armos", "Coast", "Magical Sword Cave", "Letter Cave"):
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
    assert all(read_item(world, place) in major_pool(extras) for place in places)
    kinds = [place.is_dungeon for place in places]
    assert kinds == sorted(kinds, reverse=True)
    again, _ = _world(base, case, seed)
    assert all_item_places(again, extras) == places


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
