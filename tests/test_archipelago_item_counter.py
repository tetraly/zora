"""Item Counter in an Archipelago game (2.0.2; owner decision 2026-11-21): a beta value in Archipelago mode, and the
game's ROM gets the counter's table (pipeline.finish), the same table ZORA mode builds from the built places.

What counts (2026-11-21; places, not items, from 2026-11-26): every location of the player's game but Shuffle Minor
Dungeon Drops' (B17) minor places, as in ZORA mode, whatever the assignment put there, another player's item too:
taking one is still a check; and, unless Triforce Shuffle is Anywhere (the pieces then being locations), each
level's Triforce spot. So the table's places are exactly the client's pickup checks (archipelago.pickup_checks) of
those locations, plus the spots' item bits, each read back as the address and bit the patch tests, and the totals
follow the options and the dungeon layout alone, never the assignment. The table is derived from the built
places, which a recipe rebuilds (BUILD from the recipe's flags and seed), so no recipe format change: Archipelago's
patch and the page's .apzora step make the same bytes. tests/test_archipelago_item_counter_emulator.py plays it."""
from functools import cache
from typing import Any

import pytest

from zora import archipelago
from zora.generate.places import triforce_spot_rooms
from zora.model.level_items import ALL_LEVEL_ITEM_NAMES
from zora.rom import inventory
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.item_counter import AREAS, BLOCK_HEADER, TABLE, TABLE_SIZE, WARE_PLACE, WARE_POSITION_SHIFT

SEED = 4
ON = {"item_counter": "on"}
WARE_POSITION_MASK = 0x03
WARE_SHOP_MASK = 0x07
# Each case: Archipelago options with the counter on; the per-level items (pieces 6 and 7), Bomb Upgrades in the
# Item Pool (piece 8), B17's minor places (never counted), the shop wares, Mirror Overworld (screens flipped)
CASES: dict[str, dict[str, str]] = {
    "defaults": ON,
    "per-level items": {**ON, "triforce_shuffle": "anywhere", "map_compass_shuffle": "anywhere"},
    "bomb upgrades": {**ON, "bomb_upgrades_in_pool": "on"},
    "minor drops": {**ON, "shuffle_minor_dungeon_drops": "on"},
    "shop wares": {**ON, "shop_items_in_pool": "on", "shuffle_blue_potion": "on", "randomize_letter": "on"},
    "mirrored": {**ON, "mirror_overworld": "on"},
}


@pytest.fixture(scope="module")
def base() -> bytes:
    if not BASE_ROM_PATH.exists():
        pytest.skip("needs the base ROM")
    return remember_repo_base_rom()


@cache
def built(case: str) -> archipelago.BuildResult:
    return archipelago.build_from_strings(*archipelago.flag_strings(CASES[case]), SEED, remember_repo_base_rom())


def multiworld_assignment(result: archipelago.BuildResult, every: int = 2) -> tuple[dict[str, Any], list[str]]:
    """The build's own items (its pool's names, place by place), every EVERY-th location but a level's map,
    compass or triforce holding another player's item instead, and this player's items they held received from
    other worlds (so FINISH's sanity check still passes)."""
    assignment: dict[str, Any] = {}
    received = []
    for number, (place, name) in enumerate(zip(result.places, result.pool, strict=True)):
        if number % every == 0 and name not in ALL_LEVEL_ITEM_NAMES and not isinstance(name, archipelago.Foreign):
            assignment[place.name] = archipelago.FOREIGN
            received.append(name)
        else:
            assignment[place.name] = name
    return assignment, received


def counted_checks(rom: bytes) -> list[set[tuple[int, int]]]:
    """Per area, the (address, bit) each counted place's byte stands for, as asm/flags2/item-counter reads it."""
    table = rom[TABLE:TABLE + TABLE_SIZE]
    areas = []
    for area in range(AREAS):
        start = table[area]
        flags = table[start] | table[start + 1] << 8
        checks = set()
        for place in table[start + BLOCK_HEADER:start + BLOCK_HEADER + table[start + 2]]:
            if place & WARE_PLACE:
                checks.add((inventory.SHOP_BOUGHT_FLAGS + (place >> WARE_POSITION_SHIFT & WARE_POSITION_MASK),
                            1 << (place & WARE_SHOP_MASK)))
            else:
                checks.add((flags + place, inventory.ITEM_TAKEN))
        assert len(checks) == table[start + 2], area          # no place twice
        areas.append(checks)
    return areas


def expected_checks(result: archipelago.BuildResult, pieces_in_pool: bool) -> list[set[tuple[int, int]]]:
    """Per area (the overworld, levels 1-9), the client's pickup checks of the locations that count, and unless
    the pieces are pool items (Triforce Shuffle: Anywhere) each level's Triforce spot's item bit."""
    checks = archipelago.pickup_checks(result)
    areas: list[set[tuple[int, int]]] = [set() for _ in range(AREAS)]
    for place in result.state.places:
        if not place.minor:
            check = checks[place.name]
            areas[place.level or 0].add((check.address, check.mask))
    if not pieces_in_pool:
        for level, room in triforce_spot_rooms(result.state.world).items():
            areas[level].add((inventory.room_flags(level) + room, inventory.ITEM_TAKEN))
    return areas


@pytest.mark.parametrize("case", CASES)
def test_the_table_counts_every_location_but_minor_places(base: bytes, case: str) -> None:
    result = built(case)
    assignment, received = multiworld_assignment(result)
    rom = archipelago.finish(result, assignment, received)
    pieces_in_pool = CASES[case].get("triforce_shuffle") == "anywhere"
    assert counted_checks(rom) == expected_checks(result, pieces_in_pool)
    # every location that holds another player's item is counted (but a minor place)
    foreign = {place.name for place in result.state.places if assignment[place.name] == archipelago.FOREIGN}
    checks = archipelago.pickup_checks(result)
    counted = set().union(*counted_checks(rom))
    assert foreign and all((checks[name].address, checks[name].mask) in counted for name in foreign
                           if not next(place for place in result.state.places if place.name == name).minor)
    # the totals never depend on the assignment
    other, other_received = multiworld_assignment(result, every=3)
    other_rom = archipelago.finish(result, other, other_received)
    assert other_rom[TABLE:TABLE + TABLE_SIZE] == rom[TABLE:TABLE + TABLE_SIZE]


def test_the_cases_cover_what_they_name(base: bytes) -> None:
    def places(case: str) -> list[Any]:
        return list(built(case).state.places)
    names = {case: {place.name for place in places(case)} for case in CASES}
    assert any(name.endswith("Bomb Upgrade") for name in names["bomb upgrades"])
    # at least levels 1-8's own triforce, map and compass are locations
    assert len([name for name in built("per-level items").pool if name in ALL_LEVEL_ITEM_NAMES]) >= 8 * 3
    assert any(place.minor for place in places("minor drops"))
    assert any(place.is_shop for place in places("shop wares"))
    # per-level items count in their own level, Bomb Upgrade sellers in theirs
    per_level = counted_checks(archipelago.finish(built("per-level items"), *multiworld_assignment(
        built("per-level items"))))
    assert all(len(per_level[level]) >= 3 for level in range(1, AREAS))


def test_a_recipe_rebuilds_the_same_bytes(base: bytes) -> None:
    """Archipelago's patch and the page's .apzora step rebuild the ROM, the table included, from the recipe."""
    result = built("per-level items")
    assignment, received = multiworld_assignment(result)
    ap_name = b"ZORA1_12345678901234567"
    rom = archipelago.finish(result, assignment, received, ap_name=ap_name)
    recipe = archipelago.recipe(result, assignment, received, None, ap_name)
    assert archipelago.rom_from_recipe(recipe, base) == rom
    assert any(rom[TABLE:TABLE + TABLE_SIZE])


def test_item_counter_is_offered() -> None:
    """A beta value from 2026-11-21 until its logic scan passed (2026-11-26)."""
    spec = next(spec for spec in archipelago.option_fields() if spec.key == "item_counter")
    assert spec.default == 0 and spec.beta == () and spec.scanned_values == (0, 1, 2)
    assert "item_counter" not in archipelago.NOT_OFFERED
    assert archipelago.beta_in_use(ON) == []
