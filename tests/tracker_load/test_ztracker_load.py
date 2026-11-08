"""ZTracker (the original) against ZORA's tracker files: the data-level check (opt-in; README.md here).

What runs: ZTracker's own model and save classes, on .NET 10 (ztracker_harness.py), applying the file's overworld tiles
and item boxes the way its loader does. What is read from its source text: the names its loader knows. What does not run
on a Mac: its window, its dungeon room import, its dialogs (the owner's manual pass, MANUAL-CHECKLIST.md, covers those).

Item ids 15 and up are expected differences, not failures (owner's instruction); the test names what ZTracker does with
them. ids 0 to 14 must come back exactly.
"""
import json
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora_export.tracker_file import tracker_file

from . import samples
from . import ztracker_harness as zt

pytestmark = [needs_base_rom, pytest.mark.skipif(zt.available() is not None, reason=zt.available() or "")]

CASES = [(family, level, seed) for family in samples.FAMILIES for level in samples.LEVELS for seed in samples.SEEDS]
ZTRACKER_LAST_SHARED_ID = 14       # ids 0 to 14 mean the same item in both trackers
ZTRACKER_LAST_ITEM_ID = 23         # its item table has 24 entries (0 to 23); a higher id is refused


def run(tmp_path: Path, save: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "save.json"
    path.write_text(json.dumps(save))
    return zt.run_probe(path)


def file_names(save: dict[str, Any]) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {"RoomType": set(), "MonsterDetail": set(), "FloorDropDetail": set()}
    for dungeon_map in save["DungeonMaps"]:
        for row in dungeon_map["RoomStates"]:
            for state in row:
                if state is not None:
                    for kind, seen in found.items():
                        seen.add(state[kind])
    return found


def problems(save: dict[str, Any], probe: dict[str, Any]) -> list[str]:
    out: list[str] = []
    if probe["error"] is not None:
        return [f"ZTracker's loader would fail: {probe['error']}"]
    out += [f"overworld tile column {t['column']} row {t['row']}: file {t['requested']}, ZTracker holds {t['got']}"
            for t in probe["tilesNotKept"]]
    for box in probe["boxes"]:
        if 0 <= box["requested"] <= ZTRACKER_LAST_SHARED_ID and (not box["accepted"] or box["got"] != box["requested"]):
            out.append(f"{box['name']}: file {box['requested']}, ZTracker holds {box['got']}")
    known = zt.names()
    for kind, wanted in file_names(save).items():
        out += [f"{name}: ZTracker does not know this name and would load it as unmarked"
                for name in sorted(wanted - known[kind])]
    return out


@pytest.mark.parametrize(("family", "level", "seed"), CASES, ids=[f"{f}-L{n}-seed{s}" for f, n, s in CASES])
def test_ztracker_holds_the_shared_part_of_the_file(tmp_path: Path, family: str, level: int, seed: int) -> None:
    save = json.loads(json.dumps(tracker_file(samples.document(family, level, seed))))
    found = problems(save, run(tmp_path, save))
    assert not found, f"{family} level {level} seed {seed}:\n" + "\n".join(found)


def test_what_ztracker_does_with_ids_15_and_up(tmp_path: Path) -> None:
    """A characterization, not a requirement: the committed ZTracker 1.3.1 has 15 item ids (0 to 14) and refuses any
    other: the box stays empty and nothing is said (its loader counts the failure and ignores it). If this fails,
    ZTracker's item table grew (a working tree of ZTracker has been seen with nine more, 15 to 23, which would be
    read as other items than ZoraTracker's): update docs/reports/tracker-load-tests.md and pin.py."""
    save = json.loads(json.dumps(tracker_file(samples.document("z1r", 3, 1))))
    save["Items"]["Dungeons"][0]["Boxes"][0]["CellCurrent"] = 16
    save["Items"]["Dungeons"][0]["Boxes"][1]["CellCurrent"] = 27
    probe = run(tmp_path, save)
    boxes = {box["name"]: box for box in probe["boxes"]}
    for name in ("Level1Box1", "Level1Box2", "WoodSwordBox", "MagicalSwordBox", "LetterBox"):
        assert not boxes[name]["accepted"] and boxes[name]["got"] == -1, name
        assert boxes[name]["why"] == "Cell.Set out of range"


def test_the_probe_sees_a_problem_when_there_is_one(tmp_path: Path) -> None:
    save = json.loads(json.dumps(tracker_file(samples.document("zora", 3, 1))))
    save["DungeonMaps"][0]["RoomStates"][0][0]["RoomType"] = "RoomType_PrincessRoom_NoSuch"
    save["Items"]["Dungeons"][2]["Boxes"][0]["CellCurrent"] = 3
    save["Overworld"]["Map"] = save["Overworld"]["Map"][:-3]
    assert problems(save, run(tmp_path, save))      # the short map is a load failure
    save["Overworld"]["Map"] += [-1, -1, 0]
    found = problems(save, run(tmp_path, save))
    assert any("does not know this name" in line for line in found), found
