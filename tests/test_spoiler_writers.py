"""The spoiler log's levels (rulings of 2026-11-06; docs/design/spoiler-levels.md; zora_export/leveled_log.py):
Basic holds exactly FP-SPOIL-01's seven kinds of information; Medium adds each major item's room and whether
it is on the floor or down a stairway; Full adds the levels' layouts. A seed at None keeps its document."""
import csv
import re
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import PRINT_QUEST_INFO, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.flags.zora_flags import encode as encode_zora
from zora.generate.pipeline import generate_rom
from zora.rom.base_rom import remember_repo_base_rom
from zora_export.leveled_log import LEVEL_OWN_ITEMS, screen_name
from zora_export.room_names import LAYOUT_NAMES
from zora_export.seed_document import seed_document_for
from zora_export.spoiler_log import MAJOR_ITEMS, WIDTH, spoiler_log

REPO = Path(__file__).resolve().parent.parent
BASELINE = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
SEEDS = (1, 2)
# Each level's strings: Print Quest Info (B51) and Detailed Spoiler Log
LEVELS = {0: (ThreeState.OFF, False), 1: (ThreeState.ON, False), 2: (ThreeState.OFF, True), 3: (ThreeState.ON, True)}


def strings(level: int) -> tuple[str, str]:
    b51, detailed = LEVELS[level]
    return (encode(BASELINE.updated(toggles={PRINT_QUEST_INFO.id: b51})),
            encode_zora(ZoraFlags(detailed_spoiler_log=detailed)))


@cache
def document(level: int, seed: int) -> dict[str, Any]:
    flags, zora = strings(level)
    rom = generate_rom(flags, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return seed_document_for(rom, flags, seed, zora)


def major_places(doc: dict[str, Any], with_own: bool) -> int:
    count = 0
    for level in doc["levels"]:
        for room in level["rooms"]:
            item = room["item"]
            count += bool(item and item["name"] in MAJOR_ITEMS and (with_own or item["name"] not in LEVEL_OWN_ITEMS))
            stair = room["staircase"]
            count += bool(stair and stair["kind"] == "item" and stair["item"] in MAJOR_ITEMS)
    return count


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_a_seed_at_none_has_no_spoiler_block(seed: int) -> None:
    """Documents at None are as before: no `spoiler` block, and spoiler_log gives the developer's log."""
    doc = document(0, seed)
    assert "spoiler" not in doc
    assert "Flags: each setting as chosen" in spoiler_log(doc)


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_basic_holds_fp_spoil_01_and_no_more(seed: int) -> None:
    doc = document(1, seed)
    log = spoiler_log(doc)
    lines = log.splitlines()
    assert lines[0].endswith("spoiler log: Basic") and f"Seed: {seed}" in lines
    assert all(len(line) <= WIDTH for line in lines)
    # group 2 and 3: level 9's rule, the start screen by row letter and column, with its hex
    assert any(line.startswith("Level 9: ") for line in lines)
    assert f"Start screen: {screen_name(doc['spoiler']['startScreen'])}" in lines
    # group 4: one line per major item place in a level, never its room, triforce pieces left out
    level_lines = [line for line in lines if re.match(r"    Level \d \(quest [12], entrance [A-H]\d+ \(\$", line)]
    assert len(level_lines) == major_places(doc, with_own=False)
    assert not any("column" in line or "Triforce" in line for line in level_lines)
    # group 5: every entrance screen
    for screen in doc["overworld"]["screens"]:
        assert f"    {screen_name(screen['number'])}: {screen['cave']['name']}" in lines
    # group 6: the shops' prices and the three money secrets
    assert sum(" rupees)" in line for line in lines if line.startswith("    Shop ")) == 4
    assert {line.split(":")[0].strip() for line in lines if line.endswith(" rupees") and "Secret" in line} == {
        "Small Secret", "Medium Secret", "Large Secret"}
    # group 7: each level's map, every room once
    for level in doc["levels"]:
        maps = log.split("Level maps", 1)[1]
        block = maps.split(f"\nLevel {level['shownNumber']}\n", 1)[1].split("\nLevel ", 1)[0]
        assert block.count("[") == len(level["rooms"])
    # what FP-SPOIL-01 leaves out: settings, texts, the seed code, rooms by number, enemies
    for absent in ("Flags:", "Texts:", "Seed code", "said by", "room ", "Requirements", "Notice"):
        assert absent not in log, absent


@needs_base_rom
def test_a_transport_staircase_shows_one_letter_twice() -> None:
    for seed in SEEDS:
        doc = document(1, seed)
        pairs = sum(1 for level in doc["levels"] for room in level["rooms"]
                    if room["staircase"] and room["staircase"]["kind"] == "transport") // 2
        maps = spoiler_log(doc).split("Level maps", 1)[1]
        assert sum(maps.count(f"[{letter}]") for letter in "ABCDEFGH") == 2 * pairs


GLOSSARY = REPO / "docs" / "glossary" / "room-layouts.csv"


# The glossary is not released (release/allowlist.txt): zora_export/room_names.py holds its own table.
@pytest.mark.skipif(not GLOSSARY.exists(), reason="needs docs/glossary/room-layouts.csv (not released)")
def test_the_layout_names_are_the_glossarys() -> None:
    with GLOSSARY.open() as file:
        rows = {int(row["code"].lstrip("$"), 16): row["community_name"]
                for row in csv.DictReader(file) if "-" not in row["code"]}
    assert rows == LAYOUT_NAMES


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_medium_gives_each_major_items_room(seed: int) -> None:
    """Medium: Basic, plus every major item (Heart Containers and triforce pieces too) with its room, on the
    floor or down a stairway; no layouts."""
    doc = document(2, seed)
    log = spoiler_log(doc)
    assert log.splitlines()[0].endswith("spoiler log: Medium")
    joined = " ".join(log.split())              # an item line wraps
    places = re.findall(r"Level \d \(quest [12], entrance [A-H]\d+ \(\$[0-9A-F]{2}\)\): [^,]+, "
                        r"(?:on the floor of|down the stairway in) the room in column \d, row \d", joined)
    assert len(places) == major_places(doc, with_own=True)
    assert "Triforce, on the floor" in joined
    assert "Level layouts" not in log


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_full_lists_every_room_with_its_layout_doors_and_monsters(seed: int) -> None:
    doc = document(3, seed)
    log = spoiler_log(doc)
    assert log.splitlines()[0].endswith("spoiler log: Full")
    layouts = log.split("Level layouts", 1)[1]
    facts = {level["number"]: {room["number"]: room for room in level["rooms"]} for level in doc["spoiler"]["levels"]}
    for level in doc["levels"]:
        for room in level["rooms"]:
            layout = facts[level["number"]][room["number"]]["layout"]
            heading = (f"Column {room['column']}, row {room['row']} (room ${room['number']:02X}): "
                       f"{LAYOUT_NAMES.get(layout, f'Layout ${layout:02X}')} (${layout:02X})")
            assert heading in " ".join(layouts.split()), heading
    assert layouts.count("Doors: north ") == sum(len(level["rooms"]) for level in doc["levels"])
    assert "Entrance: the way out is" in layouts
