"""What the tracker holds after loading a ZORA file, against the seed document.

Two checks, each returning a list of differences (empty = none). Every difference is a finding.

kept(): the tracker's own save of its state (the dump) against the file that was loaded. Anything the tracker
  refused, left empty, or turned into "unmarked" shows here. ids above 14 are allowed to differ only for ZTracker.
facts(): the dump against the seed document, worked out here without the writer's code: which cells hold a room,
  each edge, the stairway pairs, the entrance arrow, the item cellars, each level's item boxes, the overworld's
  level markers.
"""
from collections import Counter
from typing import Any

from zora_export.leveled_log import FULL, LEVEL_OWN_ITEMS, spoiler_level
from zora_export.spoiler_log import L4_SWORD_LABEL, MAJOR_ITEMS
from zora_export.tracker_file import ITEM_IDS, MEDIUM

# Parts of a save the tracker rebuilds itself or does not read back; everything else must come back as it went in
IGNORED_TOP = {"Version", "SaveFormatVersion", "TimeInSeconds", "Blockers", "Timeline",
               "OverworldSpotsRemainingOverTime", "UserCustomChecklist", "DrawingLayerIcons", "DungeonTabSelected"}
# A field ZORA writes that the tracker's own save has no place for (its class has it; its writer does not)
NOT_SAVED = {"/StartingItemsAndExtras/PlayerHasMagicalSword: missing"}
ENTRANCE = {"north": "N", "south": "S", "east": "E", "west": "W"}
SIDES = (("east", "west"), ("south", "north"))
COLUMNS = 16


def differences(expected: Any, actual: Any, path: str = "") -> list[str]:
    if isinstance(expected, dict) and isinstance(actual, dict):
        out: list[str] = []
        for key, value in expected.items():
            out += differences(value, actual[key], f"{path}/{key}") if key in actual else [f"{path}/{key}: missing"]
        return out
    if isinstance(expected, list) and isinstance(actual, list) and len(expected) == len(actual):
        pairs = enumerate(zip(expected, actual, strict=True))
        return [d for n, (x, y) in pairs for d in differences(x, y, f"{path}[{n}]")]
    return [] if expected == actual else [f"{path}: file {str(expected)[:60]} -> tracker {str(actual)[:60]}"]


def kept(loaded: dict[str, Any], dump: dict[str, Any]) -> list[str]:
    if dump["error"] is not None:
        return [f"the tracker could not load the file: {dump['error']}"]
    out = ["the tracker could not set an item box (setProblems)"] if dump["setProblems"] else []
    if dump["warning"] is not None:
        out.append(f"the tracker warned: {dump['warning']}")
    save = dump["save"]
    meant = {k: v for k, v in loaded.items() if k not in IGNORED_TOP}
    out += [d for d in differences(meant, save) if d not in NOT_SAVED]
    return out


def level_item_ids(document: dict[str, Any], level: dict[str, Any]) -> list[int]:
    """The ids of the major items a level's boxes should hold, in room order (the document's own words)."""
    l4 = document.get("zoraExtras", {}).get("l4Sword")
    names = []
    for room in sorted(level["rooms"], key=lambda r: (r["row"], r["column"])):
        if l4 and (level["number"], room["number"]) == (l4["level"], l4["room"]):
            names.append(L4_SWORD_LABEL)
        elif room["item"] and room["item"]["name"] in MAJOR_ITEMS - LEVEL_OWN_ITEMS:
            names.append(room["item"]["name"])
        stair = room["staircase"]
        if stair and stair["kind"] == "item" and stair["item"] in MAJOR_ITEMS:
            names.append(stair["item"])
    return [ITEM_IDS[name] for name in names if name in ITEM_IDS]


def facts(document: dict[str, Any], dump: dict[str, Any]) -> list[str]:
    """The dump against the seed document. The spoiler level is the document's own."""
    out: list[str] = []
    save = dump["save"]
    spoiler = spoiler_level(document)
    entrances = {entry["number"]: entry for entry in document["spoiler"]["levels"]}
    for level in sorted(document["levels"], key=lambda level: level["shownNumber"]):
        shown = level["shownNumber"]
        place = f"level {shown}"
        dungeon_map = save["DungeonMaps"][shown - 1]
        types = [[cell["RoomType"].removeprefix("RoomType_") for cell in row] for row in dungeon_map["RoomStates"]]
        grid = {(room["column"] - 1, room["row"] - 1): room for room in level["rooms"]}
        # which cells hold a room
        for row in range(8):
            for column in range(8):
                has_room = (column, row) in grid
                if has_room == (types[row][column] == "OffTheMap"):
                    out.append(f"{place} cell column {column + 1} row {row + 1}: "
                               f"{'a room' if has_room else 'no room'} but the tracker has {types[row][column]}")
        # each edge (10.7 rule 3), from the rooms' door words
        def edge(first: Any, second: Any, side: str, back: str) -> int:
            if not first or not second:
                return 1
            doors = (first["doors"][side], second["doors"][back])
            if all(door == "solid" for door in doors):
                return 1
            if spoiler >= FULL:
                return 4 if "shutter" in doors else 3 if "locked" in doors else 2
            return 2
        for row in range(8):
            for column in range(7):
                first, second = grid.get((column, row)), grid.get((column + 1, row))
                joined = bool(first and second and second["number"] == first["number"] + 1)
                want = edge(first, second, "east", "west") if joined else 1
                got = dungeon_map["HorizontalDoors"][row][column]
                if got != want:
                    out.append(f"{place} edge east of column {column + 1} row {row + 1}: "
                               f"document {want}, tracker {got}")
        for row in range(7):
            for column in range(8):
                first, second = grid.get((column, row)), grid.get((column, row + 1))
                joined = bool(first and second and second["number"] == first["number"] + COLUMNS)
                want = edge(first, second, "south", "north") if joined else 1
                got = dungeon_map["VerticalDoors"][row][column]
                if got != want:
                    out.append(f"{place} edge south of column {column + 1} row {row + 1}: "
                               f"document {want}, tracker {got}")
        # stairway pairs: each number twice, at the document's two rooms
        pairs: dict[int, set[tuple[int, int]]] = {}
        for cell, room in grid.items():
            stair = room["staircase"]
            if stair and stair["kind"] == "transport":
                pairs.setdefault(stair["number"], set()).add(cell)
        want_pairs = sorted(sorted(cells) for cells in pairs.values())
        tracker_cells: dict[str, list[tuple[int, int]]] = {}
        for row in range(8):
            for column in range(8):
                if types[row][column].startswith("Transport"):
                    tracker_cells.setdefault(types[row][column], []).append((column, row))
        got_pairs = sorted(sorted(cells) for cells in tracker_cells.values())
        if any(len(cells) != 2 for cells in tracker_cells.values()):
            out.append(f"{place}: a stairway number is not used exactly twice: "
                       f"{ {k: len(v) for k, v in tracker_cells.items()} }")
        if got_pairs != want_pairs:
            out.append(f"{place} stairway pairs: document {want_pairs}, tracker {got_pairs}")
        # the entrance arrow
        facts_level = entrances[level["number"]]
        entrance_cell = next(cell for cell, room in grid.items() if room["number"] == facts_level["entranceRoom"])
        want_arrow = f"StartEnterFrom{ENTRANCE[facts_level['entranceSide']]}"
        arrows = [(c, r) for r in range(8) for c in range(8) if types[r][c].startswith("StartEnterFrom")]
        if arrows != [entrance_cell] or types[entrance_cell[1]][entrance_cell[0]] != want_arrow:
            out.append(f"{place} entrance: document {want_arrow} at {entrance_cell}, tracker arrows {arrows}")
        # item cellars (Medium and Full): every item-cellar stairway room that is not the entrance or a transport
        if spoiler >= MEDIUM:
            for cell, room in grid.items():
                stair = room["staircase"]
                if stair and stair["kind"] == "item" and cell != entrance_cell \
                        and types[cell[1]][cell[0]] != "ItemBasement":
                    out.append(f"{place} cell {cell}: an item cellar but the tracker has {types[cell[1]][cell[0]]}")
        # the level's item boxes
        want_ids = level_item_ids(document, level)
        boxes = save["Items"]["Dungeons"][shown - 1]["Boxes"]
        got_ids = sorted(box["CellCurrent"] for box in boxes if box["CellCurrent"] >= 0)
        if got_ids != sorted(want_ids[:len(boxes)]):
            out.append(f"{place} item boxes: document {sorted(want_ids[:len(boxes)])}, tracker {got_ids}")
    # level entrances on the overworld: each of the nine markers 0 to 8 once
    marks = Counter(save["Overworld"]["Map"][n] for n in range(0, 384, 3))
    out += [f"overworld: level marker {marker} is on {marks[marker]} tiles"
            for marker in range(9) if marks[marker] != 1]
    return out
