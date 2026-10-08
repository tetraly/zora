"""The spoiler log (FP-SPOIL-01, owner rules 2026-10-06): a finished seed as plain text, at most
80 columns, ZORA's own layout (the owner adjusts it; docs/spoiler-log-sample.txt).

It is written from the seed document (seed_document.py) and nothing else, so the log and the
"View in Visualizer" hand-off cannot disagree, and both describe the finished ROM. Making it or
not changes no ROM byte and no random draw: the document reads the ROM after it is made, and
the "?" values from their own stream. The ROM itself holds no placement text.
"""
from __future__ import annotations

import textwrap
from typing import Any

from zora.version import player_version

WIDTH = 80
RULE = "=" * WIDTH
# The items a player plans a route around; the rest (keys, bombs, rupees, maps, compasses,
# potions and the like) are left out of the item lists, though the shops list every ware.
MAJOR_ITEMS = frozenset({
    "Wood Sword", "White Sword", "Magical Sword", "Recorder", "Blue Candle", "Red Candle", "Wooden Arrow",
    "Silver Arrow", "Bow", "Magical Key", "Raft", "Ladder", "Wand", "Book", "Blue Ring", "Red Ring",
    "Power Bracelet", "Letter", "Boomerang", "Magical Boomerang", "Heart Container", "Triforce",
    "Triforce of Power",
})
# When a room's item appears (the document's ZORA extra `appears`).
APPEARS = {"floor": "on the floor", "foes": "drops when the room's foes are beaten",
           "ganon": "appears when Ganon is beaten", "never": "never appears (trigger 3 without Ganon)"}
UPGRADE_LINES = {
    "Wood Sword": "Sword", "White Sword": "Sword", "Magical Sword": "Sword", "Blue Candle": "Candle",
    "Red Candle": "Candle", "Wooden Arrow": "Arrow", "Silver Arrow": "Arrow", "Blue Ring": "Ring",
    "Red Ring": "Ring", "Boomerang": "Boomerang", "Magical Boomerang": "Boomerang",
}


def spoiler_file_name(document: dict[str, Any]) -> str:
    seed = document.get("seed", {}).get("number", "unknown")
    return f"zora-{document['producer']['version']}-seed-{seed}-spoiler.txt"


def heading(title: str) -> list[str]:
    return ["", RULE, title, RULE]


def wrapped(text: str, indent: str = "", first: str | None = None) -> list[str]:
    return textwrap.wrap(text, WIDTH, initial_indent=indent if first is None else first,
                         subsequent_indent=indent, break_long_words=True) or [first or indent]


def item_label(name: str, progressive: bool) -> str:
    """An item as the player gets it: with Progressive Items, a line item is the line's next
    upgrade (the ROM holds a concrete item; the game gives the next level the player lacks)."""
    if progressive and name in UPGRADE_LINES:
        return f"{UPGRADE_LINES[name]} Upgrade ({name})"
    return name


def header(document: dict[str, Any]) -> list[str]:
    seed = document.get("seed", {})
    lines = [f"ZORA {player_version(document['producer']['version'])} spoiler log", RULE,
             f"Seed: {seed.get('number', '')}"]
    lines += wrapped(seed.get("flags", ""), " " * 7, "Flags: ")
    lines.append(f"ZORA flags: {seed.get('zoraFlags') or '(none)'}")
    lines += wrapped(", ".join(seed.get("code", [])), " " * 11, "Seed code: ")
    if document.get("progressiveItems"):
        lines += wrapped("Progressive Items is on: a sword, candle, arrow, ring or boomerang gives the next "
                         "level of its line that you lack. Items are listed as the ROM holds them, with "
                         "their line.")
    return lines


def flag_breakdown(document: dict[str, Any]) -> list[str]:
    lines = heading("Flags: each setting as chosen, and as this seed resolved it")
    for setting in document.get("settings", []):
        chosen, resolved = setting["chosen"], setting["resolved"]
        value = chosen if chosen == resolved else f"{chosen} -> {resolved}"
        label = f"{setting.get('id', ''):5} {setting['name']}"
        if len(label) + len(value) + 2 <= WIDTH:
            lines.append(f"{label} {'.' * (WIDTH - len(label) - len(value) - 2)} {value}")
        else:
            lines += wrapped(label)
            lines += wrapped(value, " " * 8)
    return lines


def room_label(room: dict[str, Any]) -> str:
    return f"room {room['number']:02X} (column {room['column']}, row {room['row']})"


L4_SWORD_LABEL = "Level-4 sword (progressive sword)"


def major_items(document: dict[str, Any]) -> list[str]:
    progressive = bool(document.get("progressiveItems"))
    l4 = document.get("zoraExtras", {}).get("l4Sword")
    lines = heading("Major items by place")
    for level in document["levels"]:
        found = []
        for room in level["rooms"]:
            item = room["item"]
            if l4 and (level["number"], room["number"]) == (l4["level"], l4["room"]):
                found.append(f"{room_label(room)}: {L4_SWORD_LABEL}, on the floor")
            elif item and item["name"] in MAJOR_ITEMS:
                how = APPEARS.get(item.get("appears", ""), "drops when the room's foes are beaten"
                                  if item["drop"] else "on the floor")
                found.append(f"{room_label(room)}: {item_label(item['name'], progressive)}, {how}")
            stair = room["staircase"]
            if stair and stair["kind"] == "item" and stair["item"] in MAJOR_ITEMS:
                found.append(f"{room_label(room)}, down the stairs: {item_label(stair['item'], progressive)}")
        lines.append(f"Level {level['number']}")
        lines += [line for entry in found for line in wrapped(entry, " " * 6, "    ")] or ["    (none)"]
    overworld = document["overworld"]
    lines.append("Overworld")
    for place in ("armos", "coast"):
        name = overworld[place]
        shown = item_label(name, progressive) if name else "(nothing)"
        lines.append(f"    {'Armos statue' if place == 'armos' else 'Coast'}: {shown}")
    for cave in document["caves"]:
        for ware in cave["wares"]:
            if ware["item"] in MAJOR_ITEMS:
                price = f" for {ware['price']} rupees" if "price" in ware else ""
                lines += wrapped(f"{cave['name']}: {item_label(ware['item'], progressive)}{price}", " " * 6, "    ")
    return lines


def caves(document: dict[str, Any]) -> list[str]:
    progressive = bool(document.get("progressiveItems"))
    lines = heading("Caves and shops: every ware, in the order the cave shows it")
    for cave in document["caves"]:
        wares = []
        for ware in cave["wares"]:
            text = item_label(ware["item"], progressive)
            if "price" in ware:
                text += f" ({ware['price']} rupees{', sold once' if ware.get('sellsOnce') else ''})"
            wares.append(text)
        lines += wrapped("; ".join(wares) or "(nothing)", " " * 4, f"{cave['name']}: ")
    return lines


def hints(document: dict[str, Any]) -> list[str]:
    lines = heading("Texts: the game's texts in its order, with who says them")
    for slot, hint in enumerate(document["hints"]):
        lines += wrapped(hint["text"] or "(empty)", " " * 5, f"{slot:2}.  ")
        if "speaker" in hint:
            lines += wrapped(f"said by {hint['speaker']}", " " * 7, " " * 5)
    return lines


def mazes_and_gates(document: dict[str, Any]) -> list[str]:
    """The owner's 2.0 flags' overworld results (the document's ZORA extra `zoraExtras`)."""
    extras = document.get("zoraExtras", {})
    if not extras:
        return []
    lines = heading("Mazes and overworld gates")
    for maze in extras.get("mazes", []):
        lines += wrapped(f"{maze['name']}: {', '.join(maze['sequence'])}; sold by {maze['hintShop']}, "
                         f"hint {maze['hint']}, for 1 rupee", " " * 6, " " * 4)
    for gate in extras.get("gates", []):
        screens = " ".join(f"${screen:02X}" for screen in gate["screens"])
        lines += wrapped(f"Needs {gate['needs']}: screens {screens}", " " * 6, " " * 4)
    return lines


def requirements(document: dict[str, Any]) -> list[str]:
    needed = document.get("requirements", {})
    lines = heading("Requirements")
    for key, text in (("whiteSwordHearts", "White sword cave: hearts needed"),
                      ("magicalSwordHearts", "Magical sword cave: hearts needed"),
                      ("level9Triforces", "Level 9: triforce pieces needed"),
                      ("doorRepairCost", "Door repair charge (rupees)")):
        if key in needed:
            lines.append(f"{text}: {needed[key]}")
    return lines


def spoiler_log(document: dict[str, Any]) -> str:
    """The log's text, every line at most WIDTH columns, ending in a newline."""
    lines = [*header(document), *flag_breakdown(document), *major_items(document), *caves(document),
             *mazes_and_gates(document), *hints(document), *requirements(document)]
    assert all(len(line) <= WIDTH for line in lines)
    return "\n".join(lines) + "\n"
