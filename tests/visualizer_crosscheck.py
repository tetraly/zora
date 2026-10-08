"""Cross-check of ZORA's seed document against the z1r-visualizer's, for the same finished ROM
(tests/test_seed_document.py). The visualizer's document comes from its own command line,
run as a subprocess (`cli.py --seed`); none of its code is imported.

Compared: what both read from the ROM. Not compared: names each side chooses for itself
(room layouts, enemies, cave and screen names, level colours, transport staircase numbers);
for those the check is that each side's names map one to one onto the other's, so the two
sides at least tell the same things apart. ZORA's extras (settings, speakers, sellsOnce) the
visualizer cannot read, so they are not compared."""
from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

VISUALIZER = Path(__file__).resolve().parent.parent.parent / "z1r-visualizer"
CLI = VISUALIZER / "cli.py"


def visualizer_document(rom_path: Path) -> dict[str, Any]:
    run = subprocess.run([sys.executable, str(CLI), "--files", str(rom_path), "--seed"],
                         capture_output=True, text=True, check=True, timeout=120)
    document: dict[str, Any] = json.loads(run.stdout)
    return document


class Names:
    """Checks that two sides' names for the same things map one to one."""

    def __init__(self, what: str) -> None:
        self.what = what
        self.ours: dict[str, set[str]] = defaultdict(set)
        self.theirs: dict[str, set[str]] = defaultdict(set)

    def add(self, ours: str, theirs: str) -> None:
        self.ours[ours].add(theirs)
        self.theirs[theirs].add(ours)

    def problems(self) -> list[str]:
        out = [f"{self.what}: ZORA's {name!r} is the visualizer's {sorted(seen)}"
               for name, seen in self.ours.items() if len(seen) > 1]
        out += [f"{self.what}: the visualizer's {name!r} is ZORA's {sorted(seen)}"
                for name, seen in self.theirs.items() if len(seen) > 1]
        return out


class Comparison:
    def __init__(self) -> None:
        self.differences: list[str] = []
        self.layouts = Names("room type")
        self.enemies = Names("enemy")
        self.places = Names("cave")

    def differ(self, where: str, ours: Any, theirs: Any) -> None:
        self.differences.append(f"{where}: ZORA {ours!r}, visualizer {theirs!r}")

    def compare(self, label: str, ours: dict[str, Any], theirs: dict[str, Any]) -> None:
        for key in ("progressiveItems", "requirements"):
            if ours.get(key) != theirs.get(key):
                self.differ(f"{label} {key}", ours.get(key), theirs.get(key))
        self._levels(label, ours["levels"], theirs["levels"])
        self._overworld(label, ours["overworld"], theirs["overworld"])
        self._caves(label, ours["caves"], theirs["caves"])
        # spacing is each side's own (where two lines join); the words are compared
        ours_texts = [" ".join(hint["text"].split()) for hint in ours["hints"]]
        theirs_texts = [" ".join(hint["text"].split()) for hint in theirs["hints"]]
        for slot, (mine, other) in enumerate(zip(ours_texts, theirs_texts, strict=False)):
            if mine != other:
                self.differ(f"{label} text {slot}", mine, other)
        if len(ours_texts) != len(theirs_texts):
            self.differ(f"{label} text count", len(ours_texts), len(theirs_texts))

    def _levels(self, label: str, ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> None:
        theirs_by_number = {level["number"]: level for level in theirs}
        for level in ours:
            other = theirs_by_number.get(level["number"])
            where = f"{label} level {level['number']}"
            if other is None:
                self.differ(where, "present", "missing")
                continue
            rooms = {room["number"]: room for room in other["rooms"]}
            if set(rooms) != {room["number"] for room in level["rooms"]}:
                self.differ(f"{where} rooms", sorted(room["number"] for room in level["rooms"]), sorted(rooms))
            for room in level["rooms"]:
                if room["number"] in rooms:
                    self._room(f"{where} room {room['number']:02X}", room, rooms[room["number"]])

    def _room(self, where: str, ours: dict[str, Any], theirs: dict[str, Any]) -> None:
        for key in ("column", "row", "doors"):
            if ours[key] != theirs[key]:
                self.differ(f"{where} {key}", ours[key], theirs[key])
        # the format's two item fields (ZORA's `appears` is an extra the visualizer has not)
        item, other_item = (None if found is None else {"name": found["name"], "drop": found["drop"]}
                            for found in (ours["item"], theirs["item"]))
        if item != other_item:
            self.differ(f"{where} item", item, other_item)
        self.layouts.add(ours["type"], theirs["type"])
        mine, other = ours["enemies"], theirs["enemies"]
        if (mine is None) != (other is None):
            self.differ(f"{where} enemies", mine, other)
        elif mine is not None and other is not None:
            self.enemies.add(mine["name"], other["name"])
            if mine.get("count") != other.get("count"):
                self.differ(f"{where} enemy count", mine, other)
        stair, other_stair = ours["staircase"], theirs["staircase"]
        if stair is None or other_stair is None or stair["kind"] != other_stair["kind"]:
            if stair != other_stair:
                self.differ(f"{where} staircase", stair, other_stair)
        elif stair["kind"] == "item" and stair["item"] != other_stair["item"]:
            self.differ(f"{where} cellar item", stair["item"], other_stair["item"])
        elif stair["kind"] == "transport" and stair["to"] != other_stair["to"]:
            self.differ(f"{where} transport to", stair["to"], other_stair["to"])

    def _overworld(self, label: str, ours: dict[str, Any], theirs: dict[str, Any]) -> None:
        for key in ("armos", "coast"):
            if ours[key] != theirs[key]:
                self.differ(f"{label} {key}", ours[key], theirs[key])
        mine = {screen["number"]: screen for screen in ours["screens"]}
        other = {screen["number"]: screen for screen in theirs["screens"]}
        if set(mine) != set(other):
            self.differ(f"{label} cave screens", sorted(set(mine) - set(other)), sorted(set(other) - set(mine)))
        for number in set(mine) & set(other):
            for key in ("column", "row"):
                if mine[number][key] != other[number][key]:
                    self.differ(f"{label} screen {number} {key}", mine[number][key], other[number][key])
            self.places.add(mine[number]["cave"]["name"], other[number]["cave"]["name"])

    def _caves(self, label: str, ours: list[dict[str, Any]], theirs: list[dict[str, Any]]) -> None:
        other = {cave["name"]: cave for cave in theirs}
        if {cave["name"] for cave in ours} != set(other):
            self.differ(f"{label} caves", sorted(cave["name"] for cave in ours), sorted(other))
        for cave in ours:
            if cave["name"] not in other:
                continue
            theirs_cave = other[cave["name"]]
            wares = [(ware["item"], ware.get("price")) for ware in cave["wares"]]
            theirs_wares = [(ware["item"], ware.get("price")) for ware in theirs_cave["wares"]]
            if cave["kind"] != theirs_cave["kind"] or wares != theirs_wares:
                self.differ(f"{label} {cave['name']}", (cave["kind"], wares), (theirs_cave["kind"], theirs_wares))

    def name_problems(self) -> list[str]:
        return [*self.layouts.problems(), *self.enemies.problems(), *self.places.problems()]
