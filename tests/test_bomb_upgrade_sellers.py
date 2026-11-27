"""Archipelago items piece 8 (docs/design/archipelago-items.md): with Bomb Upgrades in the Item Pool each selling
bomb upgrader's room is a place, "Level N Room XX Bomb Upgrade", holding a Bomb Upgrade (code $37); FINISH writes
the assigned item into his room byte and turns the ROM's seller mode on; the client gives a Bomb Upgrade by the
seed's count; a single-player ROM refuses the flag. The emulator side is
tests/test_bomb_upgrade_sellers_emulator.py."""
from dataclasses import replace
from functools import cache

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags import zora_flags
from zora.generate import pipeline
from zora.generate.places import LATER_CAVE_NAMES, SELLER_SUFFIX, all_place_names, seller_rooms
from zora.model.enums import Item
from zora.rom import inventory, level_items
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import BOMB_COUNT_OFFSET
from zora.rom.parse.rom_file import parse_rom

BOMB_UPGRADE = "Bomb Upgrade"
SELLERS = 2


def zora_string(case: str) -> str:
    _flags, zora = FLAG_CASES[case]
    return zora_flags.encode(replace(zora_flags.decode(zora) if zora else zora_flags.ZoraFlags(),
                                     bomb_upgrades_in_pool=True))


@cache
def result(case: str = "baseline", seed: int = 1) -> archipelago.BuildResult:
    return archipelago.build_from_strings(FLAG_CASES[case][0], zora_string(case), seed, remember_repo_base_rom())


def own(built: archipelago.BuildResult) -> dict[str, str | archipelago.Foreign]:
    return {place.name: name for place, name in zip(built.places, built.pool, strict=True)}


def sellers(built: archipelago.BuildResult) -> list[str]:
    return [place.name for place in built.places if place.name.endswith(SELLER_SUFFIX)]


@needs_base_rom
@pytest.mark.parametrize("case", ["baseline", "bomb upgraders not shuffled"])
def test_each_seller_is_a_place_holding_a_bomb_upgrade(case: str) -> None:
    built = result(case)
    names = sellers(built)
    assert len(names) == SELLERS == len(seller_rooms(built.state.world))
    assert [own(built)[name] for name in names] == [BOMB_UPGRADE] * SELLERS
    assert set(names) <= set(built.logic.places)
    for name in names:
        words = name.split()                                  # Level 5 Room 43 Bomb Upgrade
        assert any(level.rom_level_num == int(words[1]) for level in built.state.world.levels)


@needs_base_rom
def test_without_the_flag_no_seller_is_a_place() -> None:
    flags, zora = FLAG_CASES["baseline"]
    built = archipelago.build_from_strings(flags, zora, 1, remember_repo_base_rom())
    assert not sellers(built) and BOMB_UPGRADE not in built.pool


@needs_base_rom
def test_finish_writes_the_sellers_item_and_turns_seller_mode_on() -> None:
    built = result()
    assignment = own(built)
    first, second = sellers(built)
    raft = next(place for place, name in assignment.items() if name == "Raft")
    assignment[first], assignment[raft] = "Raft", BOMB_UPGRADE
    rom = archipelago.finish(built, assignment)
    world = parse_rom(rom)
    held = {(level.level_num, room.room_num): room.item for level in world.levels for room in level.rooms}
    place = {place.name: (place.level, place.room_num) for place in built.state.places}
    assert held.get(place[first]) == Item.RAFT                                         # type: ignore[arg-type]
    assert held.get(place[second]) == Item.BOMB_UPGRADE                                # type: ignore[arg-type]
    assert rom[level_items.SELLER_MODE] == level_items.SELLER_ON
    assert rom[level_items.BOMB_UPGRADE_COUNT] == rom[BOMB_COUNT_OFFSET] == world.overworld.bomb_upgrade.count


@needs_base_rom
def test_seller_mode_stays_off_without_the_flag() -> None:
    flags, zora = FLAG_CASES["baseline"]
    built = archipelago.build_from_strings(flags, zora, 1, remember_repo_base_rom())
    rom = archipelago.finish(built, own(built))
    assert rom[level_items.SELLER_MODE] != level_items.SELLER_ON
    assert rom[level_items.BOMB_UPGRADE_COUNT] == rom[BOMB_COUNT_OFFSET]


@needs_base_rom
def test_a_single_player_rom_refuses_the_flag() -> None:
    with pytest.raises(pipeline.FlagsRefused, match="Multiworld games only"):
        pipeline.generate_rom(FLAG_CASES["baseline"][0], 1, remember_repo_base_rom(),
                              zora_flag_string=zora_string("baseline"))


def test_the_client_gives_a_bomb_upgrade_by_the_seeds_count() -> None:
    ram = {inventory.MAX_BOMBS: 12, inventory.ITEMS + inventory.BOMB_SLOT: 3}
    rules = inventory.GiveRules(bomb_upgrade_count=6)
    assert archipelago.receive(BOMB_UPGRADE, ram, rules) == {inventory.MAX_BOMBS: 18,
                                                             inventory.ITEMS + inventory.BOMB_SLOT: 18}
    assert archipelago.receivable(BOMB_UPGRADE)


@needs_base_rom
def test_the_client_tables_carry_the_count() -> None:
    built = result()
    tables = archipelago.client_tables_from_json(archipelago.client_tables_to_json(built))
    assert tables.rules.bomb_upgrade_count == built.state.world.overworld.bomb_upgrade.count
    old = archipelago.client_tables_to_json(built)
    del old["rules"]["bombUpgradeCount"]
    assert archipelago.client_tables_from_json(old).rules.bomb_upgrade_count == inventory.VANILLA_BOMB_UPGRADE_COUNT


def test_the_sellers_names_come_after_every_earlier_location() -> None:
    names = all_place_names()
    first = names.index(f"Level 1 Room 00 {SELLER_SUFFIX}")
    assert names[first - 1] == list(LATER_CAVE_NAMES.values())[-1]
    assert len(names) - first == 9 * 128 and len(set(names)) == len(names)


def test_a_hint_names_a_bomb_upgrade() -> None:
    """A Bomb Upgrade an assignment puts in a cave a hint names (the White Sword Cave's) has a hint name: the logic
    scan found FINISH crashing there (2026-11-21)."""
    from zora.generate.steps.hint_text import item_name
    assert item_name(Item.BOMB_UPGRADE) == "BOMB UPGRADE"


def test_the_tracker_hints_name_the_sellers_as_places() -> None:
    """The flags spec's tracker hints carry the switch (docs/flags-api.md "Tracker hints"): with it on, the two
    selling bomb upgraders are places named as the generator names them, and the Bomb Upgrade an item."""
    from zora.generate.places import seller_name
    from zora_export.tracker_hints import Status, flag_digits, modifier, status
    rule = modifier(zora_flags.BOMB_UPGRADES_FIELD)
    assert rule["locations"]["count"] == SELLERS and rule["items"] == [BOMB_UPGRADE]
    pattern = rule["locations"]["name"].replace("N", "5").replace("XX", "43")
    assert pattern == seller_name(5, 0x43)
    flags, _zora = FLAG_CASES["baseline"]
    assert status(rule, flag_digits(flags, zora_string("baseline"))) is Status.APPLIES
    assert status(rule, flag_digits(flags, "")) is Status.OFF
