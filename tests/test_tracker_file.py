"""The ZoraTracker save file (zora_export/tracker_file.py; docs/reports/tracker-file-format.md sections 2, 3 and
10.7): a written file is loaded back and checked against the format's required fields, sizes, box counts and
name lists (section 4: what the tracker cannot load), and each spoiler level fills exactly its own parts."""
import json
from functools import cache
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.flags.zora_flags import encode as encode_zora
from zora.generate.pipeline import generate_rom
from zora.model.item_names import ITEM_NAMES
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom
from zora.rom.start_items import items_in_table, start_table
from zora.version import ZORA_VERSION
from zora_export.seed_document import seed_document_for
from zora_export.spoiler_log import has_pegasus_boots, spoiler_log
from zora_export.tracker_file import (
    ITEM_IDS,
    START_ITEM_FIELDS,
    ZTRACKER_WARNING,
    ExportProblem,
    Writer,
    starter_file,
    tracker_file,
    ztracker_misses,
    ztracker_note,
)

BASELINE = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
LEVELS = {1: (ThreeState.ON, False), 2: (ThreeState.OFF, True), 3: (ThreeState.ON, True)}
SEEDS = (1, 2, 3)
# The format's name lists (section 2.8, from ZoraTracker's CDungeonRoomState.cs)
ROOM_TYPES = {f"RoomType_{name}" for name in (
    "Unmarked NonDescript MaybePushBlock ItemBasement StaircaseToUnknown Transport1 Transport2 Transport3 "
    "Transport4 Transport5 Transport6 Transport7 Transport8 Chevy DoubleMoat TopMoat RightMoat CircleMoat Tee "
    "LavaMoat VChute HChute Turnstile OldManHint BombUpgrade LifeOrMoney HungryGoriyaMeatBlock StartEnterFromE "
    "StartEnterFromW StartEnterFromN StartEnterFromS OffTheMap Gannon Zelda PrincessRoom").split()}
MONSTERS = {f"MonsterDetail_{name}" for name in (
    "Unmarked Gleeok Bow Digdogger BlueBubble RedBubble Dodongo Patra BlueWizzrobe BlueDarknut Manhandla Vire Zol "
    "PolsVoice RedTektite RedGoriya Rope Stalfos Wallmaster Gel Keese Likelike Gibdo RedLynel BlueMoblin "
    "Aquamentus BlueLanmola Moldorm RupeeBoss Traps Other Other2").split()}
DROPS = {f"FloorDropDetail_{name}" for name in
         "Unmarked Triforce Heart OtherKeyItem BombPack Key FiveRupee Map Compass".split()}
NEVER_WRITTEN = {"RoomType_Unmarked", "RoomType_MaybePushBlock", "RoomType_StaircaseToUnknown",
                 "RoomType_PrincessRoom", "MonsterDetail_Other", "MonsterDetail_Other2"}
TOP_LEVEL = ("Version", "SaveFormatVersion", "TimeInSeconds", "Overworld", "Items", "PlayerProgressAndTakeAnyHearts",
             "StartingItemsAndExtras", "Blockers", "Hints", "Notes", "DungeonMaps", "Seed", "Flags")


@cache
def document(level: int, seed: int) -> dict[str, Any]:
    b51, detailed = LEVELS[level]
    flags = encode(BASELINE.updated(toggles={PRINT_QUEST_INFO.id: b51}))
    zora = encode_zora(ZoraFlags(detailed_spoiler_log=detailed))
    rom = generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return seed_document_for(rom, flags, seed, zora)


def loaded(level: int, seed: int) -> dict[str, Any]:
    """The file as written to disk and read back."""
    return dict(json.loads(json.dumps(tracker_file(document(level, seed)))))


def boxes_expected(shown: int, second_quest: bool, hidden: bool) -> int:
    if hidden:
        return 2 if shown == 9 else 3
    return 3 if shown in (8, 4 if second_quest else 1) else 2


def check_format(save: dict[str, Any]) -> None:
    """Section 4's required parts, with the sizes and values the loader insists on."""
    for key in TOP_LEVEL:
        assert key in save, key
    # Kept at ZoraTracker 2.2.0, with its format number (owner rulings, 2026-11-06)
    assert save["Version"] == "2.2.0" and save["SaveFormatVersion"] == 1
    overworld = save["Overworld"]
    assert overworld["Quest"] in range(5)
    assert len(overworld["Map"]) == 384 and all(isinstance(value, int) for value in overworld["Map"])
    items = save["Items"]
    for name in ("HiddenDungeonNumbers", "SecondQuestDungeons"):
        assert isinstance(items[name], bool)
    all_boxes = [items[name] for name in ("WhiteSwordBox", "LadderBox", "ArmosBox", "MagicalSwordBox", "LetterBox",
                                          "WoodSwordBox", "Level2StairBox")]
    assert len(items["Dungeons"]) == 9
    for index, dungeon in enumerate(items["Dungeons"]):
        assert len(dungeon["Boxes"]) == boxes_expected(index + 1, items["SecondQuestDungeons"],
                                                       items["HiddenDungeonNumbers"])
        all_boxes += [*dungeon["Boxes"], dungeon["ExtraBox"]]
    for entry in all_boxes:
        assert entry["PlayerHas"] in (0, 1, 2) and -1 <= entry["CellCurrent"] <= 29
    ids = [entry["CellCurrent"] for entry in all_boxes if entry["CellCurrent"] >= 0]
    for item_id in set(ids):                     # the tracker skips a box over its id's limit
        assert ids.count(item_id) <= (9 if item_id in (14, 29) else 1), item_id
    assert len(save["PlayerProgressAndTakeAnyHearts"]["TakeAnyHearts"]) == 4
    assert len(save["StartingItemsAndExtras"]["HDNStartingTriforcePieces"]) == 8
    assert len(save["Blockers"]) == 8 and all(len(slots) == 3 and all(len(slot["AppliesTo"]) == 6 for slot in slots)
                                              for slots in save["Blockers"])
    hints = save["Hints"]["LocationHints"]
    assert len(hints) == 11 and all(0 <= zone <= 10 for zone in hints)
    assert len(save["DungeonMaps"]) == 9
    for dungeon_map in save["DungeonMaps"]:
        assert [len(row) for row in dungeon_map["HorizontalDoors"]] == [7] * 8
        assert [len(row) for row in dungeon_map["VerticalDoors"]] == [8] * 7
        doors = [door for rows in ("HorizontalDoors", "VerticalDoors") for row in dungeon_map[rows] for door in row]
        assert all(door in (1, 2, 3, 4) for door in doors)        # 10.7 rule 3: no edge left unknown
        assert [len(row) for row in dungeon_map["RoomStates"]] == [8] * 8
        for row in dungeon_map["RoomStates"]:
            for state in row:
                assert state is not None                          # 10.7 rule 1: no cell left null
                assert state["RoomType"] in ROOM_TYPES - NEVER_WRITTEN
                assert state["MonsterDetail"] in MONSTERS - NEVER_WRITTEN
                assert state["FloorDropDetail"] in DROPS
                assert state["IsCompleted"] is False and state["FloorDropShouldAppearBright"] is True


def states(save: dict[str, Any]) -> list[dict[str, Any]]:
    return [state for dungeon_map in save["DungeonMaps"] for row in dungeon_map["RoomStates"] for state in row]


@needs_base_rom
@pytest.mark.parametrize("level", LEVELS)
@pytest.mark.parametrize("seed", SEEDS)
def test_a_written_file_loads_against_the_formats_required_fields(level: int, seed: int) -> None:
    check_format(loaded(level, seed))


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_each_level_fills_its_own_parts(seed: int) -> None:
    basic, medium, full = (states(loaded(level, seed)) for level in (1, 2, 3))
    kinds = [{state["RoomType"].removeprefix("RoomType_") for state in level} for level in (basic, medium, full)]
    assert kinds[0] <= {"OffTheMap", "NonDescript", *(f"StartEnterFrom{side}" for side in "NSEW"),
                        *(f"Transport{number}" for number in range(1, 9))}
    assert "ItemBasement" in kinds[1] and "ItemBasement" not in kinds[0]
    assert {"Gannon", "Zelda"} <= kinds[2]
    assert all(state["FloorDropDetail"] == "FloorDropDetail_Unmarked" for state in basic)
    assert {state["FloorDropDetail"] for state in medium} <= {
        "FloorDropDetail_Unmarked", "FloorDropDetail_Heart", "FloorDropDetail_Triforce", "FloorDropDetail_OtherKeyItem"}
    assert "FloorDropDetail_Key" in {state["FloorDropDetail"] for state in full}
    assert all(state["MonsterDetail"] == "MonsterDetail_Unmarked" for state in basic + medium)
    assert {state["MonsterDetail"] for state in full} - {"MonsterDetail_Unmarked"}
    edges = ("HorizontalDoors", "VerticalDoors")
    doors = [{door for dungeon_map in loaded(level, seed)["DungeonMaps"] for rows in edges
              for row in dungeon_map[rows] for door in row} for level in (1, 3)]
    assert doors[0] <= {1, 2} and doors[1] <= {1, 2, 3, 4} and {3, 4} & doors[1]


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_the_overworld_and_the_boxes_match_the_log(seed: int) -> None:
    doc = document(1, seed)
    save = loaded(1, seed)
    tiles = save["Overworld"]["Map"]
    start = doc["spoiler"]["startScreen"]
    assert (save["Overworld"]["StartIconY"], save["Overworld"]["StartIconX"]) == divmod(start, 16)
    for screen in doc["overworld"]["screens"]:
        cave = screen["cave"]
        if "shownName" in cave:
            assert tiles[3 * screen["number"]] == int(cave["shownName"].removeprefix("Level ")) - 1
    boxed = sum(entry["CellCurrent"] >= 0 for dungeon in save["Items"]["Dungeons"] for entry in dungeon["Boxes"])
    assert boxed > 0
    items = save["Items"]
    every_box = [items[name] for name in ("WhiteSwordBox", "LadderBox", "ArmosBox", "MagicalSwordBox", "LetterBox",
                                          "WoodSwordBox", "Level2StairBox")]
    every_box += [entry for dungeon in items["Dungeons"] for entry in (*dungeon["Boxes"], dungeon["ExtraBox"])]
    dropped = sum(entry["CellCurrent"] > 14 for entry in every_box)
    assert ztracker_misses(save)[0] == dropped and ztracker_note(save).endswith(ZTRACKER_WARNING)
    assert ("ZTracker won't show" in ztracker_note(save)) == bool(dropped)


@needs_base_rom
def test_the_ztracker_note_names_each_place_ztracker_misses() -> None:
    """Prompt 660 ruling 2: the note says what ZTracker won't show, from the boxes holding an item numbered 15 or
    up, and none of that when every box holds one of ZTracker's items (0 to 14) or nothing; the version warning
    sentence always ends it (owner ruling, 2026-11-06)."""
    save = loaded(1, 1)
    items = save["Items"]
    every_box = [items[name] for name in ("WhiteSwordBox", "LadderBox", "ArmosBox", "MagicalSwordBox", "LetterBox",
                                          "WoodSwordBox", "Level2StairBox")]
    every_box += [entry for dungeon in items["Dungeons"] for entry in (*dungeon["Boxes"], dungeon["ExtraBox"])]
    for entry in every_box:
        entry["CellCurrent"] = min(entry["CellCurrent"], 14)
    assert ztracker_note(save) == ('ZTracker shows a version warning when it opens this file; click "Attempt Load" '
                                   "and the file opens.")
    items["WoodSwordBox"]["CellCurrent"], items["MagicalSwordBox"]["CellCurrent"] = 19, 20
    assert ztracker_note(save) == ("ZTracker won't show the items in the Wood Sword and Magical Sword caves; "
                                   f"open this file in ZoraTracker to see everything. {ZTRACKER_WARNING}")
    items["MagicalSwordBox"]["CellCurrent"] = 13
    items["LadderBox"]["CellCurrent"] = 22
    items["Dungeons"][2]["Boxes"][0]["CellCurrent"] = 23
    items["Dungeons"][8]["Boxes"][1]["CellCurrent"] = 21
    assert ztracker_note(save) == ("ZTracker won't show the items in the Wood Sword cave, at the coast and in "
                                   "levels 3 and 9; open this file in ZoraTracker to see everything. "
                                   f"{ZTRACKER_WARNING}")
    for name in ("WoodSwordBox", "LadderBox"):
        items[name]["CellCurrent"] = -1
    items["Dungeons"][8]["Boxes"][1]["CellCurrent"] = -1
    assert ztracker_note(save).startswith("ZTracker won't show the item in level 3;")


@needs_base_rom
def test_the_exporter_refuses_what_the_format_cannot_hold() -> None:
    """10.7's asserts: at most eight transport pairs, every room on the 8 by 8 map, and an entrance room that is
    never a stairway (the entrance arrow would hide it)."""
    doc = json.loads(json.dumps(document(1, 1)))
    level = doc["levels"][0]
    entrance = next(entry for entry in doc["spoiler"]["levels"] if entry["number"] == level["number"])
    room = next(room for room in level["rooms"] if room["number"] == entrance["entranceRoom"])
    room["staircase"] = {"kind": "item", "item": "Bow"}
    with pytest.raises(ExportProblem, match="entrance room"):
        Writer(doc).write()
    doc = json.loads(json.dumps(document(1, 1)))
    stair = next(room for level in doc["levels"] for room in level["rooms"]
                 if room["staircase"] and room["staircase"]["kind"] == "transport")
    stair["staircase"]["number"] = 9
    with pytest.raises(ExportProblem, match="transport pairs"):
        Writer(doc).write()
    doc = json.loads(json.dumps(document(1, 1)))
    doc["levels"][0]["rooms"][0]["column"] = 9
    with pytest.raises(ExportProblem, match="off the 8 by 8 map"):
        Writer(doc).write()


@cache
def boots_document(boots: ThreeState, seed: int) -> dict[str, Any]:
    zora = encode_zora(ZoraFlags(detailed_spoiler_log=True, pegasus_boots=boots))
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return seed_document_for(rom, MVP_BASELINE_LEVEL_ENCODING_OFF, seed, zora)


@needs_base_rom
@pytest.mark.parametrize("boots", [ThreeState.OFF, ThreeState.ON, ThreeState.POSSIBLE])
def test_pegasus_boots_is_the_seeds_boots_replace_boomerangs(boots: ThreeState) -> None:
    """The full file writes BootsReplaceBoomerangs as the seed resolved Pegasus Boots, 0 or 1 (the spoiler knows
    it, Random included), and boxes the boots as the boomerangs, never listing them as missing."""
    for seed in SEEDS:
        doc = boots_document(boots, seed)
        save = json.loads(json.dumps(tracker_file(doc)))
        check_format(save)
        resolved = has_pegasus_boots(doc)
        assert resolved is {ThreeState.OFF: False, ThreeState.ON: True}.get(boots, resolved)
        assert save["Overworld"]["BootsReplaceBoomerangs"] == int(resolved)
        assert "no tracker item" not in save["Notes"]
        writer = Writer(doc)
        for level, dungeon in zip(sorted(doc["levels"], key=lambda level: level["shownNumber"]),
                                  save["Items"]["Dungeons"], strict=True):
            expected = [ITEM_IDS[name] for name in writer.level_items(level)[:len(dungeon["Boxes"])]]
            assert [entry["CellCurrent"] for entry in dungeon["Boxes"]][:len(expected)] == expected
    assert (ITEM_IDS["Pegasus Boots"], ITEM_IDS["Magical Boots"]) == (ITEM_IDS["Boomerang"],
                                                                      ITEM_IDS["Magical Boomerang"])


@needs_base_rom
def test_the_full_file_names_zoras_version_and_a_start_magical_sword() -> None:
    """The full file writes ZoraVersion (ZORA_VERSION, never the flag string's prefix) and ZoraFlags as the starter
    file does, and a start Magical Sword in both blocks the tracker reads it from."""
    flags = encode(BASELINE.updated(options={"C17": 0}, toggles={"B70": ThreeState.ON}))   # no limit
    zora = encode_zora(ZoraFlags(detailed_spoiler_log=True, pegasus_boots=ThreeState.ON))
    rom = generate_rom(flags, 1, remember_repo_base_rom(), zora_flag_string=zora).rom
    save = json.loads(json.dumps(tracker_file(seed_document_for(rom, flags, 1, zora))))
    check_format(save)
    assert save["ZoraVersion"] == ZORA_VERSION and save["ZoraFlags"] == zora
    assert save["StartingItemsAndExtras"]["PlayerHasMagicalSword"] is True
    assert save["PlayerProgressAndTakeAnyHearts"]["PlayerHasMagicalSword"] is True
    plain = loaded(1, 1)
    assert plain["ZoraVersion"] == ZORA_VERSION and plain["ZoraFlags"] == document(1, 1)["seed"]["zoraFlags"]
    assert not plain["StartingItemsAndExtras"]["PlayerHasMagicalSword"]


# Max Start Items at most 2 (C17 = 3) over Raft and Bow On, and Magical Sword, Magical Key and Bombs Random
DRAWN_START_TOGGLES = {"B57": ThreeState.ON, "B58": ThreeState.ON, "B70": ThreeState.POSSIBLE,
                       "B62": ThreeState.POSSIBLE, "B59": ThreeState.POSSIBLE}
LIMIT_TWO = 3


@needs_base_rom
@pytest.mark.parametrize("seed", (1, 3, 4))
def test_the_full_file_sets_the_start_items_the_seed_drew(seed: int) -> None:
    """The start items after the Random fields and the Max Start Items draw: the document's spoiler block and the
    log list them, they are the items the ROM's starting table holds, and the full file sets exactly those, each
    wherever ZoraTracker reads it (the Magical Sword in both blocks). The starter file keeps to the flags."""
    flags = encode(BASELINE.updated(options={"C17": LIMIT_TWO}, toggles=DRAWN_START_TOGGLES))
    zora = encode_zora(ZoraFlags(detailed_spoiler_log=True))
    rom = generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    doc = seed_document_for(rom, flags, seed, zora)
    drawn = doc["spoiler"]["startItems"]
    by_name = {name: item for item, name in ITEM_NAMES.items()}
    assert len(drawn) == 2
    assert parse_rom(rom).start_items == items_in_table(start_table([by_name[name] for name in drawn], 3, 3))
    assert f"Start items: {', '.join(drawn)}" in spoiler_log(doc)
    save = json.loads(json.dumps(tracker_file(doc)))
    found = {(block, name) for block in ("StartingItemsAndExtras", "PlayerProgressAndTakeAnyHearts")
             for name, value in save[block].items() if value is True}
    assert found == {place for name in drawn for place in START_ITEM_FIELDS[name]}
    starter = starter_file(flags, zora, seed)
    assert not any(value is True for block in ("StartingItemsAndExtras", "PlayerProgressAndTakeAnyHearts")
                   for value in starter[block].values())          # the limit may drop any of them
