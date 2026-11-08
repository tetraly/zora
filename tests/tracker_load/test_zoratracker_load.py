"""ZoraTracker loads ZORA's tracker files and holds what the seed document says (opt-in; README.md here).

Each file is loaded by the pinned ZoraTracker's --load/--dump switch (harness.py): the real load path, on this
machine, headless (no window). The tracker's own re-save is then compared with the file (nothing
refused, dropped or turned into "unmarked") and with the seed document (rooms, edges, stairway pairs, entrance,
item cellars, item boxes, level markers), at each spoiler level, with Z1R flags only and with ZORA flags.
"""
import copy
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora_export.tracker_file import tracker_file

from . import compare, harness, samples

pytestmark = [needs_base_rom, pytest.mark.skipif(harness.available() is not None, reason=harness.available() or "")]

CASES = [(family, level, seed) for family in samples.FAMILIES for level in samples.LEVELS for seed in samples.SEEDS]


def run(tmp_path: Path, save: dict[str, Any]) -> dict[str, Any]:
    path = tmp_path / "save.json"
    path.write_text(json.dumps(save))
    return harness.run_dump(path, tmp_path / "dump.json")


@pytest.mark.parametrize(("family", "level", "seed"), CASES, ids=[f"{f}-L{n}-seed{s}" for f, n, s in CASES])
def test_the_tracker_holds_what_the_file_and_the_seed_document_say(tmp_path: Path, family: str, level: int,
                                                                   seed: int) -> None:
    document = samples.document(family, level, seed)
    written = json.loads(json.dumps(tracker_file(document)))
    dump = run(tmp_path, written)
    problems = compare.kept(written, dump) + compare.facts(document, dump)
    assert not problems, f"{family} level {level} seed {seed}:\n" + "\n".join(problems[:40])


# The harness must see a problem when there is one: a file made wrong on purpose is loaded, and the comparison has
# to report it. (Without these, a harness that compared nothing would pass.)

def tampered(change: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    document = samples.document("zora", 3, 1)
    written = json.loads(json.dumps(tracker_file(document)))
    bad = copy.deepcopy(written)
    change(bad)
    return written, bad


def first_cell(save: dict[str, Any], level: int, kind: str) -> tuple[int, int]:
    rows = save["DungeonMaps"][level]["RoomStates"]
    return next((r, c) for r in range(8) for c in range(8) if rows[r][c]["RoomType"] == f"RoomType_{kind}")


def test_an_unknown_room_name_is_reported(tmp_path: Path) -> None:
    def change(save: dict[str, Any]) -> None:
        row, column = first_cell(save, 0, "NonDescript")
        save["DungeonMaps"][0]["RoomStates"][row][column]["RoomType"] = "RoomType_NoSuchRoom"
    _, bad = tampered(change)
    problems = compare.kept(bad, run(tmp_path, bad))
    assert any("RoomType" in p and "Unmarked" in p for p in problems), problems


@pytest.mark.skipif(os.environ.get("ZORA_TRACKER_LOAD_LOUD") != "1",
                    reason="the tracker sounds its system alert beep for this; set ZORA_TRACKER_LOAD_LOUD=1 to run it")
def test_a_third_use_of_a_stairway_number_is_refused(tmp_path: Path) -> None:
    def change(save: dict[str, Any]) -> None:
        first = next(n for n in range(9) if any(c["RoomType"] == "RoomType_Transport1"
                                               for row in save["DungeonMaps"][n]["RoomStates"] for c in row))
        row, column = first_cell(save, first, "NonDescript")
        save["DungeonMaps"][first]["RoomStates"][row][column]["RoomType"] = "RoomType_Transport1"
    _, bad = tampered(change)
    problems = compare.kept(bad, run(tmp_path, bad))
    assert any("RoomType" in p for p in problems), problems


def test_an_item_id_the_tracker_does_not_have_is_reported(tmp_path: Path) -> None:
    def change(save: dict[str, Any]) -> None:
        save["Items"]["Dungeons"][0]["Boxes"][0]["CellCurrent"] = 99
    _, bad = tampered(change)
    dump = run(tmp_path, bad)
    assert compare.kept(bad, dump), "an id of 99 was kept without a word"


def test_a_file_the_tracker_cannot_read_is_reported(tmp_path: Path) -> None:
    def change(save: dict[str, Any]) -> None:
        save["Overworld"]["Map"] = save["Overworld"]["Map"][:-3]
    _, bad = tampered(change)
    dump = run(tmp_path, bad)
    assert compare.kept(bad, dump)


def test_a_wrong_edge_is_reported_against_the_seed_document(tmp_path: Path) -> None:
    """The file says something the seed document does not: the tracker keeps it faithfully (so kept() is quiet), and
    only the comparison with the document can see it."""
    document = samples.document("zora", 3, 1)
    wrong = json.loads(json.dumps(tracker_file(document)))
    cell = wrong["DungeonMaps"][0]["HorizontalDoors"]
    row, column = next((r, c) for r in range(8) for c in range(7) if cell[r][c] == 1)
    cell[row][column] = 2
    dump = run(tmp_path, wrong)
    assert not compare.kept(wrong, dump)
    assert any("edge" in line for line in compare.facts(document, dump))
