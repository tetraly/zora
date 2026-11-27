"""Archipelago items piece 6 (docs/design/archipelago-items.md): with Add Triforces to the Item Pool and Add
Maps/Compasses to the Item Pool, each level's piece, map and compass is a place and a pool item named by the
number the status bar shows ("Level 3 Map"); the pieces are items, not events, in the logic; FINISH writes each
level's own code, refuses a piece in a shop's side ware, and its sanity check collects the pieces as items; the
client gives each item's bit by its data level. The emulator side is tests/test_level_items_emulator.py."""
import json
from dataclasses import replace
from functools import cache
from pathlib import Path

import pytest

from tests.archipelago_cases import FLAG_CASES
from tests.needs import needs_base_rom
from zora import archipelago
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.zora_flags import LevelItemShuffle
from zora.generate.finish import AssignmentRefused
from zora.generate.logic import ItemTerm
from zora.model.enums import Item
from zora.model.level_items import ALL_LEVEL_ITEM_NAMES, LevelItemKind, level_item
from zora.rom import inventory
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora_export.leveled_log import is_level_own
from zora_export.seed_document import seed_document
from zora_export.spoiler_log import MAJOR_ITEMS, spoiler_log

SECOND_QUEST = "second quest dungeons"       # data levels 2/3, 4/5, 7/8 show each other's numbers
LEVEL_9_ENTRY = "Level 9 Entry"


@cache
def result(case: str = "baseline", seed: int = 1) -> archipelago.BuildResult:
    flags, zora_string = FLAG_CASES[case]
    zora = replace(zora_flags.decode(zora_string) if zora_string else zora_flags.ZoraFlags(),
                   triforce_shuffle=LevelItemShuffle.ANYWHERE, map_compass_shuffle=LevelItemShuffle.ANYWHERE)
    return archipelago.build_from_strings(flags, zora_flags.encode(zora), seed, remember_repo_base_rom())


def own(built: archipelago.BuildResult) -> dict[str, str | archipelago.Foreign]:
    return {place.name: name for place, name in zip(built.places, built.pool, strict=True)}


@needs_base_rom
def test_every_level_item_is_a_place_named_by_its_shown_number() -> None:
    built = result(SECOND_QUEST)
    shown = archipelago.level_numbers(built)
    assert sorted(shown.values()) == list(range(1, 10)) and shown != {level: level for level in shown}
    level_names = [name for name in built.pool if name in ALL_LEVEL_ITEM_NAMES]
    assert sorted(level_names) == sorted(ALL_LEVEL_ITEM_NAMES)
    for place, name in zip(built.places, built.pool, strict=True):
        if name in ALL_LEVEL_ITEM_NAMES:
            assert place.name.startswith(name.split()[0] + " " + name.split()[1] + " "), (place.name, name)
    assert built.triforces == ()


@needs_base_rom
def test_level_9_asks_for_the_pieces_as_items() -> None:
    built = result()
    terms = {term for clause in built.logic.events[LEVEL_9_ENTRY] for term in clause}
    assert terms == {ItemTerm(level_item(LevelItemKind.TRIFORCE, level)) for level in range(1, 9)}
    assert not any(name.endswith("Triforce") for name in built.logic.events)
    assert {level_item(LevelItemKind.TRIFORCE, level) for level in range(1, 9)} <= built.logic.progression


@needs_base_rom
@pytest.mark.parametrize("case", ["baseline", SECOND_QUEST])
def test_finish_writes_each_levels_own_code(case: str) -> None:
    built = result(case)
    world = parse_rom(archipelago.finish(built, own(built)))
    by_level = {level.level_num: level for level in world.levels}
    for data_level, level in by_level.items():
        held = {room.item for room in level.rooms} | {stair.item for stair in level.block.staircases
                                                      if stair.return_dest in level.room_nums}
        for kind in LevelItemKind:
            if data_level == 9 and kind is LevelItemKind.TRIFORCE:
                continue
            others = {level_item(kind, other) for other in range(1, 10 if kind is not LevelItemKind.TRIFORCE else 9)
                      if other != data_level}
            assert not held & others, (case, data_level, kind)


@needs_base_rom
def test_a_moved_piece_is_still_collected() -> None:
    """Level 1's piece and a level 2 major item trade places: FINISH accepts it (the sanity check collects the
    piece as an item) and level 1's piece code sits in level 2's room."""
    built = result()
    assignment = own(built)
    names = archipelago.level_numbers(built)
    piece = f"Level {names[1]} Triforce"
    piece_place = next(place for place, name in assignment.items() if name == piece)
    other = next(place.name for place, name in zip(built.places, built.pool, strict=True)
                 if place.name.startswith(f"Level {names[2]} ") and name not in ALL_LEVEL_ITEM_NAMES)
    assignment[piece_place], assignment[other] = assignment[other], piece
    world = parse_rom(archipelago.finish(built, assignment))
    level_2 = next(level for level in world.levels if level.level_num == 2)
    assert level_item(LevelItemKind.TRIFORCE, 1) in {room.item for room in level_2.rooms} | {
        stair.item for stair in level_2.block.staircases}


@needs_base_rom
def test_a_piece_in_a_side_ware_is_refused() -> None:
    flags, zora_string = FLAG_CASES["every owner flag on"]
    zora = replace(zora_flags.decode(zora_string), triforce_shuffle=LevelItemShuffle.ANYWHERE)
    built = archipelago.build_from_strings(flags, zora_flags.encode(zora), 1, remember_repo_base_rom())
    side = next((place for place in built.places if place.kind == "shop ware" and "Middle" not in place.name), None)
    if side is None:
        pytest.skip("this case joins no side ware")
    assert any(name.endswith("Triforce") for name in side.forbids)
    assignment = own(built)
    piece = next(place for place, name in assignment.items() if str(name).endswith("Triforce"))
    assignment[piece], assignment[side.name] = assignment[side.name], assignment[piece]
    with pytest.raises(AssignmentRefused):
        archipelago.finish(built, assignment)


def test_the_client_gives_the_data_levels_bit() -> None:
    """Shown 3 is data level 2 in a second-quest pair: its map sets bit 1 of InvMap; level 9's compass its own
    byte."""
    ram = {inventory.ITEMS + offset: 0 for offset in range(0x28)}
    numbers = {1: 1, 2: 3, 3: 2, 4: 5, 5: 4, 6: 6, 7: 8, 8: 7, 9: 9}
    assert archipelago.receive("Level 3 Map", ram, level_numbers=numbers) == {inventory.ITEMS + 0x11: 0x02}
    assert archipelago.receive("Level 9 Compass", ram, level_numbers=numbers) == {inventory.ITEMS + 0x12: 0x01}
    assert archipelago.receive("Level 7 Triforce", ram) == {inventory.ITEMS + 0x1A: 0x40}
    assert all(archipelago.receivable(name) for name in ALL_LEVEL_ITEM_NAMES)


@needs_base_rom
def test_names_turn_back_into_the_seeds_codes() -> None:
    built = result(SECOND_QUEST)
    world = built.state.world
    assert archipelago.item_named("Level 3 Map", world) == level_item(LevelItemKind.MAP, 2)
    assert archipelago.item_named("Level 9 Map", world) == Item.MAP
    with pytest.raises(archipelago.UnknownItem):
        archipelago.item_named("Level 3 Map")


SCHEMA = Path(__file__).resolve().parent.parent / "docs" / "seed-format" / "seed-format.schema.json"


@needs_base_rom
def test_the_seed_document_names_each_levels_items_by_its_shown_number() -> None:
    """Format 1.2: a second-quest seed's document validates, each level's floor and stairway items include its
    own piece, map and compass by the number its status bar shows (the plain names are never written), and
    the spoiler log lists the pieces as major items."""
    jsonschema = pytest.importorskip("jsonschema")
    built = result(SECOND_QUEST)
    document = seed_document(archipelago.finish(built, own(built)), built.state.plan)
    jsonschema.Draft202012Validator(json.loads(SCHEMA.read_text())).validate(document)
    for level in document["levels"]:
        shown = level["shownNumber"]
        held = {room["item"]["name"] for room in level["rooms"] if room["item"]} | {
            room["staircase"]["item"] for room in level["rooms"]
            if room["staircase"] and room["staircase"]["kind"] == "item"}
        own_items = {f"Level {shown} {kind.value}" for kind in LevelItemKind
                     if shown != 9 or kind is not LevelItemKind.TRIFORCE}
        assert own_items <= held and not held & {"Triforce", "Map", "Compass"}, (shown, held)
    assert {f"Level {level} Triforce" for level in range(1, 9)} <= MAJOR_ITEMS
    assert all(f"Level {level} Triforce" in spoiler_log(document) for level in range(1, 9))


def test_only_a_levels_own_piece_is_its_own() -> None:
    assert is_level_own("Level 3 Triforce", {"shownNumber": 3})
    assert not is_level_own("Level 4 Triforce", {"shownNumber": 3})
    assert is_level_own("Triforce", {"shownNumber": 3})


@needs_base_rom
@pytest.mark.parametrize("case", ["baseline", SECOND_QUEST])
def test_maps_and_compasses_alone_finish(case: str) -> None:
    """Add Maps/Compasses to the Item Pool without Add Triforces: the pieces stay events, but FINISH writes
    each as its level's own code, and the sanity walk finds each level's Triforce room by that code."""
    flags, zora_string = FLAG_CASES[case]
    zora = replace(zora_flags.decode(zora_string) if zora_string else zora_flags.ZoraFlags(),
                   map_compass_shuffle=LevelItemShuffle.ANYWHERE)
    built = archipelago.build_from_strings(flags, zora_flags.encode(zora), 1, remember_repo_base_rom())
    assert built.triforces
    world = parse_rom(archipelago.finish(built, own(built)))
    for level in world.levels:
        if level.level_num != 9:
            assert level_item(LevelItemKind.TRIFORCE, level.level_num) in {room.item for room in level.rooms} | {
                stair.item for stair in level.block.staircases}
