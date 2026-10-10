"""The seed document (zora_export/seed_document.py) and the spoiler log built from it
(zora_export/spoiler_log.py): the visualizer's schema, the "no ROM change" rule (FP-SPOIL-01),
the refusal for encoded seeds, the log's layout, and a cross-check against the z1r-visualizer's
own reading of the same ROMs (skipped without ../z1r-visualizer)."""
import json
from functools import cache
from pathlib import Path
from typing import Any

import pytest

from tests import visualizer_crosscheck
from zora_web.api import seed_report
from zora_export.seed_document import EncodedSeedRefused, seed_document, seed_document_for
from zora_export.spoiler_log import MAJOR_ITEMS, WIDTH, spoiler_file_name, spoiler_log
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE, MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom, plan
from zora.model import room_grid
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.player_settings import PlayerSettings
from zora.version import player_version

jsonschema = pytest.importorskip("jsonschema")
pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

REPO = Path(__file__).resolve().parent.parent
SCHEMA = json.loads((REPO / "docs" / "seed-format" / "seed-format.schema.json").read_text())
WITHOUT_EXTRA_CANDLES = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles={"B09": ThreeState.OFF}))
# Some "?" fields, so the settings show resolved values.
QUESTIONS = encode(decode(WITHOUT_EXTRA_CANDLES).updated(
    toggles=dict.fromkeys(("B27", "B31", "B42"), ThreeState.POSSIBLE)))
# The flag combinations: the ZORA extras, Progressive Items and Shop Items in the Item Pool.
CONFIGS = [
    (MVP_BASELINE_LEVEL_ENCODING_OFF, ""), (MVP_BASELINE_LEVEL_ENCODING_OFF, "1.D"),
    (MVP_BASELINE_LEVEL_ENCODING_OFF, "1.2"), (MVP_BASELINE_LEVEL_ENCODING_OFF, "1.F"),
    (WITHOUT_EXTRA_CANDLES, "2.O"), (MVP_BASELINE_LEVEL_ENCODING_OFF, "2.m"),
    (WITHOUT_EXTRA_CANDLES, "2.19"), (QUESTIONS, "2.1B"),
]


@cache
def base() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def finished(flags: str, seed: int, zora: str) -> bytes:
    return generate_rom(flags, seed, base(), zora_flag_string=zora).rom


def document(flags: str, seed: int, zora: str) -> dict[str, Any]:
    return seed_document_for(finished(flags, seed, zora), flags, seed, zora)


# --- the schema --------------------------------------------------------------------------------

@pytest.mark.parametrize(("flags", "zora"), CONFIGS)
def test_every_document_validates_against_the_schema(flags: str, zora: str) -> None:
    validator = jsonschema.Draft202012Validator(SCHEMA)
    for seed in (1, 2):
        problems = [error.message for error in validator.iter_errors(document(flags, seed, zora))]
        assert not problems, problems[:5]


def test_the_copied_schema_names_its_source() -> None:
    assert "z1r-visualizer" in SCHEMA["$comment"] and "commit" in SCHEMA["$comment"]


# --- FP-SPOIL-01: no ROM change, no random draw -------------------------------------------------

@pytest.mark.parametrize(("flags", "zora"), [CONFIGS[0], CONFIGS[-1]])
def test_making_the_report_changes_no_rom(flags: str, zora: str) -> None:
    """Generate, make the report, generate again: the same ROM, and the same plan (the "?"
    values come from their own stream, which the report reads again without drawing from the
    generation's)."""
    first = generate_rom(flags, 3, base(), zora_flag_string=zora).rom
    before = plan(flags, 3, zora)
    report = seed_report(first, flags, 3, zora)
    again = generate_rom(flags, 3, base(), zora_flag_string=zora).rom
    assert again == first and plan(flags, 3, zora) == before
    assert json.loads(report["json"])["seed"]["number"] == "3"


def test_the_player_settings_do_not_change_the_document() -> None:
    plain = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, base()).rom
    dressed = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 4, base(),
                           PlayerSettings(tunic_colours=(0x21, 0x22, 0x23), heart_colour=0x24)).rom
    assert plain != dressed
    assert seed_document_for(plain, MVP_BASELINE_LEVEL_ENCODING_OFF, 4) == \
        seed_document_for(dressed, MVP_BASELINE_LEVEL_ENCODING_OFF, 4)


def test_an_encoded_seed_gets_no_document_and_no_log() -> None:
    from zora.rom import level_encoding
    if not level_encoding.is_available():
        # Without the private module an encoded seed is refused before any ROM exists.
        with pytest.raises(level_encoding.LevelEncodingUnavailable):
            plan(MVP_BASELINE, 1)
        return
    chosen = plan(MVP_BASELINE, 1)
    assert chosen.encode_level_data
    with pytest.raises(EncodedSeedRefused):
        seed_document(b"", chosen)
    rom = generate_rom(MVP_BASELINE, 1, base()).rom
    with pytest.raises(EncodedSeedRefused):
        seed_report(rom, MVP_BASELINE, 1)


# --- what the document says ----------------------------------------------------------------------

def test_the_document_names_the_seed_and_its_settings() -> None:
    doc = document(QUESTIONS, 1, "2.1B")
    assert doc["producer"]["name"] == "ZORA" and doc["progressiveItems"]
    assert doc["seed"] == {"number": "1", "flags": QUESTIONS, "zoraFlags": "2.1B", "code": doc["seed"]["code"]}
    assert len(doc["seed"]["code"]) == 4
    settings = {setting["id"]: setting for setting in doc["settings"] if setting["id"] != "ZORA"}
    for field_id in ("B27", "B31", "B42"):
        assert settings[field_id]["chosen"] == "?" and settings[field_id]["resolved"] in ("On", "Off")
    assert settings["B82"]["chosen"] == "Off"
    zora = {setting["name"]: setting["chosen"] for setting in doc["settings"] if setting["id"] == "ZORA"}
    assert zora["Progressive Items"] == "on" and zora["Randomize Letter"] == "on"


def test_one_time_wares_follow_the_flags() -> None:
    def once(doc: dict[str, Any]) -> list[bool]:
        return [ware["sellsOnce"] for cave in doc["caves"] if cave["kind"] in ("shop", "potion-shop")
                for ware in cave["wares"]]
    assert not any(once(document(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, "")))
    assert any(once(document(WITHOUT_EXTRA_CANDLES, 1, "2.O")))


def test_the_map_column_is_the_minimap_bitmap_middle() -> None:
    """SH-MAP-01: the level sits centred in its 16-column map bitmap (pad = (16 - width) // 2),
    and the map shows the bitmap's middle eight columns, so the level's leftmost room is in
    column pad - 3, and the columns keep the grid's order and spacing."""
    for level in document(MVP_BASELINE_LEVEL_ENCODING_OFF, 2, "")["levels"]:
        grid = {room["number"]: room_grid.column(room["number"]) for room in level["rooms"]}
        width = max(grid.values()) - min(grid.values()) + 1
        shown = {room["number"]: room["column"] for room in level["rooms"]}
        assert min(shown.values()) == (16 - width) // 2 - 3
        assert all(shown[number] - grid[number] == shown[min(grid)] - grid[min(grid)] for number in grid)


def test_bomb_upgraders_sell_only_in_their_two_levels() -> None:
    """PS-BOMB-03: only the two patched levels' persons take the selling path; a $0F person
    elsewhere (a helpful hint room, PS-HINT-05) only talks."""
    from zora.rom.parse.rom_file import parse_rom
    for seed in range(1, 9):
        doc = document(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, "")
        selling = parse_rom(finished(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, "")).bomb_upgrade_levels
        assert selling is not None
        for level in doc["levels"]:
            for room in level["rooms"]:
                name = (room["enemies"] or {}).get("name", "")
                if name.startswith("Bomb Upgrader"):
                    assert (name == "Bomb Upgrader") == (level["number"] in selling), (seed, level["number"])


def test_every_text_has_a_known_speaker_or_none() -> None:
    doc = document(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, "")
    speakers = [hint["speaker"] for hint in doc["hints"] if "speaker" in hint]
    assert any(speaker.startswith("Level ") for speaker in speakers)
    assert any("Hint Shop" in speaker for speaker in speakers)


# --- the spoiler log -------------------------------------------------------------------------------

@pytest.mark.parametrize(("flags", "zora"), CONFIGS)
def test_the_log_fits_80_columns_and_lists_what_the_document_holds(flags: str, zora: str) -> None:
    doc = document(flags, 1, zora)
    log = spoiler_log(doc)
    assert all(len(line) <= WIDTH for line in log.splitlines())
    assert log.startswith(f"ZORA {player_version(doc['producer']['version'])} spoiler log\n")   # "2.0 beta 2"
    words = " ".join(log.split())          # wrapping may break a line anywhere between words
    assert f"Seed: {doc['seed']['number']}" in log and doc["seed"]["flags"] in log
    for cave in doc["caves"]:
        assert f"{cave['name']}: " in words
        for ware in cave["wares"]:
            if "price" in ware:
                assert f"{ware['price']} rupees" in words
    for level in doc["levels"]:
        for room in level["rooms"]:
            if room["item"] and room["item"]["name"] in MAJOR_ITEMS:
                assert f"room {room['number']:02X} (column {room['column']}, row {room['row']})" in words
    for setting in doc["settings"]:
        assert " ".join(setting["name"].split())[:40] in words
    assert spoiler_file_name(doc) == f"zora-{doc['producer']['version']}-seed-1-spoiler.txt"


def test_the_sample_log_is_current() -> None:
    """docs/spoiler-log-sample.txt is the log of its seed, as the owner reviews it."""
    sample = (REPO / "docs" / "spoiler-log-sample.txt").read_text()
    assert sample == spoiler_log(document(QUESTIONS, 12345, "2.1B"))


# --- the cross-check against the visualizer (dev only) ---------------------------------------------

# The two differences the cross-check finds, both on the visualizer's side:
# - level 9's trigger-3 ("last boss") rooms: the engine hides their item at load
#   (aldonunez CreateRoomObjects) and only Ganon's death brings it out; the visualizer shows
#   it on the floor;
# - texts longer than 64 bytes: the visualizer reads at most 64.
def visualizer_side(difference: str) -> bool:
    if " item: " in difference and "'drop': True" in difference and "'drop': False" in difference:
        return True
    return " text " in difference and difference.split("ZORA ")[1].startswith(
        difference.split("visualizer ")[1].rstrip("'"))


@pytest.mark.slow
@pytest.mark.skipif(not visualizer_crosscheck.CLI.exists(), reason="../z1r-visualizer is not checked out")
@pytest.mark.parametrize(("flags", "zora"), CONFIGS)
def test_the_visualizer_reads_the_same_seed(flags: str, zora: str, tmp_path: Path) -> None:
    """Seven seeds per combination (56 in all): ZORA's document and the visualizer's own
    reading of the same ROM agree on everything both read from the ROM."""
    comparison = visualizer_crosscheck.Comparison()
    for seed in range(1, 8):
        rom_path = tmp_path / f"seed-{seed}.nes"
        rom_path.write_bytes(finished(flags, seed, zora))
        comparison.compare(f"{zora or '-'} seed {seed}", document(flags, seed, zora),
                           visualizer_crosscheck.visualizer_document(rom_path))
    unexplained = [difference for difference in comparison.differences if not visualizer_side(difference)]
    assert not unexplained, unexplained[:10]
    assert not comparison.name_problems()
