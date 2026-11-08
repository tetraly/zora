"""The player's spoiler log at its information level (rulings of 2026-11-06; docs/design/spoiler-levels.md),
written from a seed document that carries the `spoiler` block (seed_document.spoiler_entry), so only a seed
made with a log level above None has one.

Basic holds exactly FP-SPOIL-01's seven kinds of information and no more: the seed number, level 9's entry
rule, the start screen, the item places (a level's by its quest, number and entrance screen, never the room),
the caves by screen, the shops with their prices and the money secrets' amounts, and a map of each level
(its rooms, the passages between them, two-way or one-way, the way out, and each transport staircase's two
rooms by one letter). Screens are named by row letter and column number, with the hex after.
"""
from __future__ import annotations

from typing import Any

from zora.version import player_version

from .room_names import layout_name
from .spoiler_log import (
    APPEARS,
    L4_SWORD_LABEL,
    MAJOR_ITEMS,
    RULE,
    WIDTH,
    heading,
    item_label,
    level_9_entrance,
    wrapped,
)

LEVEL_NAMES = {1: "Basic", 2: "Medium", 3: "Full"}
SCREEN_ROWS = "ABCDEFGH"
SCREEN_COLUMNS = 16
MAP_SIZE = 8
# The items whose room is the level's own (the triforce piece, and Ganon's Triforce of Power): FP-SPOIL-01 leaves
# the triforce pieces' rooms out, so Basic lists neither; Medium lists every major item with its room.
LEVEL_OWN_ITEMS = frozenset({"Triforce", "Triforce of Power"})
SIDES = ("north", "east", "south", "west")
OPPOSITE = {"north": "south", "south": "north", "east": "west", "west": "east"}
# The map's marks: a passage open both ways, open one way only (in the arrow's direction), the way out
TWO_WAY_ACROSS, TWO_WAY_DOWN = "-", "|"
ONE_WAY = {"east": ">", "west": "<", "south": "v", "north": "^"}
STAIR_LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
MAP_LEGEND = ("[ ] a room; - and | a passage open both ways; > < v ^ a passage open one way, the way the "
              "arrow points; the arrow off the map is the way out; rooms with the same letter are the two "
              "ends of one staircase.")


def screen_name(number: int) -> str:
    """An overworld screen by row letter and column number, with its hex: "D8 ($37)"."""
    row, column = divmod(number, SCREEN_COLUMNS)
    return f"{SCREEN_ROWS[row]}{column + 1} (${number:02X})"


def spoiler_level(document: dict[str, Any]) -> int:
    return int(document["spoiler"]["level"])


def level_facts(document: dict[str, Any]) -> dict[int, dict[str, Any]]:
    """The spoiler block's entry of each level, by data number."""
    return {entry["number"]: entry for entry in document["spoiler"]["levels"]}


def entrance_screens(document: dict[str, Any]) -> dict[int, int]:
    """Each level's door screen, by data number (the screens name a level door by its data number)."""
    doors = {}
    for screen in document["overworld"]["screens"]:
        name = screen["cave"]["name"]
        if name.startswith("Level "):
            doors[int(name.removeprefix("Level "))] = screen["number"]
    return doors


def header(document: dict[str, Any]) -> list[str]:
    level = spoiler_level(document)
    lines = [f"ZORA {player_version(document['producer']['version'])} spoiler log: {LEVEL_NAMES[level]}", RULE,
             f"Seed: {document['seed']['number']}"]
    if (entrance := level_9_entrance(document, with_setting=False)) is not None:
        lines += wrapped(entrance, " " * 4, "")
    lines.append(f"Start screen: {screen_name(document['spoiler']['startScreen'])}")
    if document.get("progressiveItems"):
        lines += wrapped("Progressive Items is on: an item of a line (sword, candle, arrow, ring, boomerang or "
                         "boots) is listed as the ROM holds it, with its line; the game gives the next level "
                         "of that line that you lack.")
    return lines


def level_item_places(document: dict[str, Any], level: dict[str, Any], facts: dict[str, Any],
                      door: int | None) -> list[str]:
    """One line per major item in the level, by quest, number and entrance screen; from Medium on, with
    whether it lies on the floor or down a stairway, and the room it is in."""
    progressive = bool(document.get("progressiveItems"))
    detailed = spoiler_level(document) >= 2
    l4 = document.get("zoraExtras", {}).get("l4Sword")
    where = f"quest {facts['quest']}, entrance {screen_name(door)}" if door is not None else f"quest {facts['quest']}"
    lines = []
    for room in sorted(level["rooms"], key=lambda room: (room["row"], room["column"])):
        found = []
        item = room["item"]
        if l4 and (level["number"], room["number"]) == (l4["level"], l4["room"]):
            found.append(("floor", L4_SWORD_LABEL))
        elif item and item["name"] in MAJOR_ITEMS and (detailed or item["name"] not in LEVEL_OWN_ITEMS):
            found.append(("floor", item_label(item["name"], progressive)))
        stair = room["staircase"]
        if stair and stair["kind"] == "item" and stair["item"] in MAJOR_ITEMS:
            found.append(("stairway", item_label(stair["item"], progressive)))
        for kind, name in found:
            text = f"Level {level['shownNumber']} ({where}): {name}"
            if detailed:
                text += (f", on the floor of the room in {room_place(room)}" if kind == "floor"
                         else f", down the stairway in the room in {room_place(room)}")
            lines += wrapped(text, " " * 6, "    ")
    return lines


def room_place(room: dict[str, Any]) -> str:
    return f"column {room['column']}, row {room['row']}"


def item_places(document: dict[str, Any]) -> list[str]:
    """FP-SPOIL-01 group 4: every place the generator put a major item, a level's without its room (Basic)."""
    lines = heading("Item places")
    facts = level_facts(document)
    doors = entrance_screens(document)
    for level in sorted(document["levels"], key=lambda level: level["shownNumber"]):
        lines += level_item_places(document, level, facts[level["number"]], doors.get(level["number"]))
    progressive = bool(document.get("progressiveItems"))
    overworld = document["overworld"]
    for place, name in (("Armos statue", overworld["armos"]), ("Coast", overworld["coast"])):
        lines.append(f"    {place}: {item_label(name, progressive) if name else '(nothing)'}")
    for cave in document["caves"]:
        for ware in cave["wares"]:
            if ware["item"] in MAJOR_ITEMS:
                lines += wrapped(f"{cave['name']}: {item_label(ware['item'], progressive)}", " " * 6, "    ")
    return lines


def cave_screens(document: dict[str, Any]) -> list[str]:
    """FP-SPOIL-01 group 5: each screen with an entrance and what it leads to (a level by its door code)."""
    lines = heading("Caves: each entrance by screen")
    for screen in sorted(document["overworld"]["screens"], key=lambda screen: screen["number"]):
        lines.append(f"    {screen_name(screen['number'])}: {screen['cave']['name']}")
    return lines


SHOP_KINDS = ("shop", "potion-shop")


def shops(document: dict[str, Any]) -> list[str]:
    """FP-SPOIL-01 group 6: the shops' wares and prices, the potion shop's prices, the money secrets."""
    progressive = bool(document.get("progressiveItems"))
    lines = heading("Shops and money secrets")
    for cave in document["caves"]:
        if cave["kind"] in SHOP_KINDS:
            wares = "; ".join(f"{item_label(ware['item'], progressive)} ({ware['price']} rupees)"
                              for ware in cave["wares"])
            lines += wrapped(wares or "(nothing)", " " * 6, f"    {cave['name']}: ")
    for name, amount in document["spoiler"]["secrets"].items():
        lines.append(f"    {name}: {amount} rupees")
    return lines


def passage(room: dict[str, Any], side: str) -> bool:
    return bool(room["doors"][side] != "solid")


def mark(first: dict[str, Any] | None, second: dict[str, Any] | None, side: str, both: str) -> str:
    """The mark between FIRST and its neighbor SECOND on FIRST's SIDE: both ways, one way, or none."""
    if first is None or second is None:
        return " "
    out, back = passage(first, side), passage(second, OPPOSITE[side])
    if out and back:
        return both
    if out:
        return ONE_WAY[side]
    return ONE_WAY[OPPOSITE[side]] if back else " "


def neighbors(first: int, second: int, side: str) -> bool:
    """Whether two room numbers are neighbors on the room sheet across FIRST's SIDE (east or south)."""
    if side == "east":
        return second == first + 1 and second % SCREEN_COLUMNS != 0
    return second == first + SCREEN_COLUMNS


def stair_letters(level: dict[str, Any]) -> dict[int, str]:
    """Each transport staircase's two rooms by one letter, in the level's staircase order."""
    return {room["number"]: STAIR_LETTERS[room["staircase"]["number"] - 1] for room in level["rooms"]
            if room["staircase"] and room["staircase"]["kind"] == "transport"}


def cell_mark(room: dict[str, Any] | None, letters: dict[int, str], cellars: bool) -> str:
    if room is None:
        return "   "
    if room["number"] in letters:
        return f"[{letters[room['number']]}]"
    if cellars and room["staircase"] and room["staircase"]["kind"] == "item":
        return "[*]"
    return "[ ]"


def level_map(document: dict[str, Any], level: dict[str, Any], facts: dict[str, Any]) -> list[str]:
    """FP-SPOIL-01 group 7: the level's rooms where its map shows them (8 by 8), the passages between
    neighbors, the way out and the staircase letters. From Medium on an item cellar's room shows *."""
    grid: dict[tuple[int, int], dict[str, Any]] = {}
    for room in level["rooms"]:
        assert 1 <= room["column"] <= MAP_SIZE and 1 <= room["row"] <= MAP_SIZE, (level["number"], room["number"])
        grid[room["column"], room["row"]] = room
    letters = stair_letters(level)
    assert len(set(letters.values())) * 2 == len(letters), level["number"]
    cellars = spoiler_level(document) >= 2
    entrance = next(room for room in level["rooms"] if room["number"] == facts["entranceRoom"])
    exit_side = facts["entranceSide"]

    def across(row: int, column: int) -> str:
        first, second = grid.get((column, row)), grid.get((column + 1, row))
        if first and second and not neighbors(first["number"], second["number"], "east"):
            return " "
        return mark(first, second, "east", TWO_WAY_ACROSS)

    def down(row: int, column: int) -> str:
        first, second = grid.get((column, row)), grid.get((column, row + 1))
        if first and second and not neighbors(first["number"], second["number"], "south"):
            return " "
        return mark(first, second, "south", TWO_WAY_DOWN)

    columns = "".join(f" {column}  " for column in range(1, MAP_SIZE + 1)).rstrip()
    lines = [f"Level {level['shownNumber']}", f"     {columns}"]
    if exit_side == "north":
        lines.append("    " + " " * (2 + 4 * (entrance["column"] - 1)) + "^")
    for row in range(1, MAP_SIZE + 1):
        cells = ["<" if exit_side == "west" and grid.get((1, row)) is entrance else " "]
        for column in range(1, MAP_SIZE + 1):
            room = grid.get((column, row))
            cells.append(cell_mark(room, letters, cellars))
            if column < MAP_SIZE:
                cells.append(across(row, column))
            elif exit_side == "east" and room is entrance:
                cells.append(">")
        lines.append((f"{row:>3} " + "".join(cells)).rstrip())
        below = [" "]
        for column in range(1, MAP_SIZE + 1):
            room = grid.get((column, row))
            if room is entrance and exit_side == "south":
                link = "v"
            elif row < MAP_SIZE:
                link = down(row, column)
            else:
                link = " "
            below.append(f" {link}  ")
        lines.append(("    " + "".join(below)).rstrip())
    while not lines[-1]:
        lines.pop()
    return lines


def level_maps(document: dict[str, Any]) -> list[str]:
    lines = heading("Level maps")
    lines += wrapped(MAP_LEGEND)
    facts = level_facts(document)
    for level in sorted(document["levels"], key=lambda level: level["shownNumber"]):
        lines += ["", *level_map(document, level, facts[level["number"]])]
    return lines


# Full: a side's door in words
DOOR_WORDS = {"open": "open", "solid": "wall", "locked": "locked door", "shutter": "shutter",
              "bombable": "bombable wall", "walk-through": "walk-through wall"}
FULL = 3


def room_heading(room: dict[str, Any], facts: dict[str, Any]) -> str:
    """A room by its place, its number in hex, and its layout by glossary name with the code after."""
    layout = facts["layout"]
    push = ", push block" if facts["pushBlock"] else ""
    return (f"Column {room['column']}, row {room['row']} (room ${room['number']:02X}): "
            f"{layout_name(layout)} (${layout:02X}){push}")


def room_details(room: dict[str, Any], rooms: dict[int, dict[str, Any]], letters: dict[int, str],
                 entrance: tuple[int, str], progressive: bool) -> list[str]:
    details = []
    if room["number"] == entrance[0]:
        details.append(f"Entrance: the way out is {entrance[1]}")
    if (enemies := room["enemies"]) is not None:
        count = f" ({enemies['count']})" if "count" in enemies else ""
        details.append(f"Monsters: {enemies['name']}{count}")
    if (item := room["item"]) is not None:
        when = APPEARS.get(item.get("appears", ""))
        details.append(f"Floor item: {item_label(item['name'], progressive)}{f' ({when})' if when else ''}")
    if (stair := room["staircase"]) is not None:
        if stair["kind"] == "item":
            details.append(f"Stairway down to an item cellar: {item_label(stair['item'] or '(nothing)', progressive)}")
        else:
            other = rooms[stair["to"]]
            details.append(f"Staircase {letters[room['number']]}, to {room_place(other)}")
    details.append("Doors: " + ", ".join(f"{side} {DOOR_WORDS[room['doors'][side]]}" for side in SIDES))
    return details


def level_rooms(document: dict[str, Any]) -> list[str]:
    """Full: each level's rooms, row by row, with layout, push block, monsters, floor item, stairway and the
    four sides' doors (the map gives the passages; this gives each side's kind)."""
    lines = heading("Level layouts: every room, row by row")
    progressive = bool(document.get("progressiveItems"))
    facts = level_facts(document)
    for level in sorted(document["levels"], key=lambda level: level["shownNumber"]):
        level_fact = facts[level["number"]]
        by_number = {room["number"]: room for room in level["rooms"]}
        room_facts = {room["number"]: room for room in level_fact["rooms"]}
        letters = stair_letters(level)
        entrance = (level_fact["entranceRoom"], level_fact["entranceSide"])
        lines += ["", f"Level {level['shownNumber']}"]
        for room in sorted(level["rooms"], key=lambda room: (room["row"], room["column"])):
            lines += wrapped(room_heading(room, room_facts[room["number"]]), " " * 8, "    ")
            for detail in room_details(room, by_number, letters, entrance, progressive):
                lines += wrapped(detail, " " * 10, " " * 8)
    return lines


def leveled_log(document: dict[str, Any]) -> str:
    """The log's text at the document's level, every line at most WIDTH columns, ending in a newline."""
    lines = [*header(document), *item_places(document), *cave_screens(document), *shops(document),
             *level_maps(document)]
    if spoiler_level(document) >= FULL:
        lines += level_rooms(document)
    assert all(len(line) <= WIDTH for line in lines)
    return "\n".join(lines) + "\n"
