"""The alternative values (flags-behavior.md FL-ALT-02 to FL-ALT-04; owner ruling 2026-10-05:
supported after the MVP): each entry's Check on a few seeds, the functions that produce the
values, and their data layer. The 200-seed batches: `python3 scripts/qa_sweep.py alternatives
--seeds 200`. The spec's Checks are byte-level, so this file reads finished ROMs' bytes
(tests/test_data_boundary.py lists it with the data layer's tests)."""
from functools import cache

import pytest

# The spec tables are left out of releases (release/allowlist.txt): this file skips there.
spec = pytest.importorskip("tests.flags_spec_fixture", reason="the spec tables are not in this tree")
from zora.flags.codec import decode, encode
from zora.flags.fields import HINT_STYLE, STARTING_HEARTS, WHITE_SWORD_LOWEST
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import ALTERNATIVE_OPTIONS
from zora.generate.pipeline import extra_options, generate_rom, plan
from zora.generate.rng import ScriptedRng
from zora.generate.steps.change_sword_hearts import change_sword_hearts, change_sword_hearts_from_five_hearts
from zora.measure.alternative_values import (
    HELPFUL_TEXT_SLOTS,
    community_hints,
    starting_hearts_4,
    white_sword_hearts,
)
from zora.model.enums import Destination
from zora.model.game_world import GameWorld
from zora.model.overworld import ItemCave
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.game_config import GameConfig
from zora.rom.layout import NEW_FILE_HEART_VALUES_OPERAND_ADDRESS, SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS
from zora.rom.parse.rom_file import parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

SEEDS = (1, 2)
CP5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)


def _flags(**options: int) -> str:
    return encode(CP5.updated(options=options))


CONTROL = MVP_BASELINE_LEVEL_ENCODING_OFF
FOUR_HEARTS = _flags(C16=3)
FROM_FIVE = _flags(C20=1)
COMMUNITY = _flags(C03=2)
ALL_THREE = _flags(C16=3, C20=1, C03=2)
# The ZORA extras' string: Randomize Magical Sword (heart cap 12) and Randomize Letter.
EXTRAS = "1.F"


@cache
def _base() -> bytes:
    return verify_base_rom().read_bytes()


@cache
def finished(flag_string: str, seed: int, zora: str = "") -> tuple[GameWorld, bytes]:
    """A finished ROM, parsed; parsing and re-serializing it gives the same bytes."""
    rom = generate_rom(flag_string, seed, _base(), zora_flag_string=zora).rom
    config = plan(flag_string, seed, zora).config
    reading = GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode)
    world = parse_rom(rom, reading)
    assert serialize_to_rom(world, rom, reading) == rom
    return world, rom


def test_the_spec_names_the_three_values() -> None:
    """FL-ALT-01: "C16 = 3, C20 = 1 and C03 = 2", the values the support matrix produces."""
    assert spec.ALTERNATIVE_VALUES == "C16 = 3, C20 = 1 and C03 = 2"
    assert ALTERNATIVE_OPTIONS == {STARTING_HEARTS.id: {3}, WHITE_SWORD_LOWEST.id: {1}, HINT_STYLE.id: {2}}


# ---------------------------------------------------------------------------
# FL-ALT-02: starting hearts 4
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zora", ["", EXTRAS])
@pytest.mark.parametrize("flag_string", [FOUR_HEARTS, ALL_THREE])
@pytest.mark.parametrize("seed", SEEDS)
def test_fl_alt_02_check(flag_string: str, seed: int, zora: str) -> None:
    """HeartValues $32, every other starting value FP-START-01's (the second-quest switch's
    too), the Continue operand $02, and a life toll still asking $30."""
    figures = starting_hearts_4(*finished(flag_string, seed, zora))
    assert figures["new file $32, the rest FP-START-01's"] and figures["second-quest switch the same"]
    assert figures["continue $02"]
    assert figures["life toll asks $30"] == figures["life toll"]


@pytest.mark.parametrize("seed", SEEDS)
def test_fl_alt_02_control(seed: int) -> None:
    figures = starting_hearts_4(*finished(CONTROL, seed))
    assert figures["new file FP-START-01's ($22)"] and not figures["new file $32, the rest FP-START-01's"]


@pytest.mark.parametrize("seed", SEEDS)
def test_fl_alt_02_adds_no_draw(seed: int) -> None:
    """No draw is added or removed: the ROM is the control's but for the two HeartValues
    operands and the seed code, which hashes the ROM (FP-HASH-01)."""
    _, control = finished(CONTROL, seed)
    _, four = finished(FOUR_HEARTS, seed)
    differ = {offset for offset, (a, b) in enumerate(zip(control, four, strict=True)) if a != b}
    seed_code = set(range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH))
    assert differ - seed_code == {NEW_FILE_HEART_VALUES_OPERAND_ADDRESS, SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS}


def test_fl_alt_02_heart_values_data_layer() -> None:
    """The model's new-file hearts: PRG0's three and three write nothing; four and three write $32
    into both starting-state routines, and parse back."""
    base = _base()
    world = parse_rom(base)
    assert (world.new_file_heart_containers, world.new_file_full_hearts) == (3, 3)
    assert serialize_to_rom(world, base) == base
    world.new_file_heart_containers = 4
    rom = serialize_to_rom(world, base)
    assert rom[NEW_FILE_HEART_VALUES_OPERAND_ADDRESS] == rom[SECOND_QUEST_HEART_VALUES_OPERAND_ADDRESS] == 0x32
    parsed = parse_rom(rom)
    assert (parsed.new_file_heart_containers, parsed.new_file_full_hearts) == (4, 3)


# ---------------------------------------------------------------------------
# FL-ALT-03: white-sword hearts from 5
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zora", ["", EXTRAS])
@pytest.mark.parametrize("flag_string", [FROM_FIVE, ALL_THREE])
@pytest.mark.parametrize("seed", SEEDS)
def test_fl_alt_03_check(flag_string: str, seed: int, zora: str) -> None:
    """The white-sword cave asks for 5 or 6 hearts; the magical-sword cave 10 to 14 (12 at most
    under the ZORA cap)."""
    figures = white_sword_hearts(finished(flag_string, seed, zora)[0])
    asked = [name for name, value in figures.items() if value]
    white, magical = sorted(asked, key=lambda name: name.startswith("magical"))
    assert white in ("white 5", "white 6")
    assert int(magical.split()[1]) in (range(10, 13) if zora else range(10, 15))


def test_fl_alt_03_keeps_the_draws() -> None:
    """The same draws in the same order: one draw for the white sword, from its two counts, then
    one for the magical sword, unchanged. (Rng.below rejects out-of-range words, so where the
    stream stands afterwards may differ; the stream is not normative, FL-SEED-01.)"""
    for white_draw in range(2):
        for magical_draw in range(5):
            world = parse_rom(_base())
            change_sword_hearts_from_five_hearts(world.overworld, ScriptedRng([white_draw, magical_draw]))
            white = world.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
            magical = world.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
            assert white is not None and magical is not None
            assert (white.heart_requirement, magical.heart_requirement) == (5 + white_draw, 10 + magical_draw)
            change_sword_hearts(world.overworld, ScriptedRng([white_draw, magical_draw]))
            assert magical.heart_requirement == 10 + magical_draw


# ---------------------------------------------------------------------------
# FL-ALT-04: community hints
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("zora", ["", EXTRAS])
@pytest.mark.parametrize("flag_string", [COMMUNITY, ALL_THREE])
@pytest.mark.parametrize("seed", SEEDS)
def test_fl_alt_04_check(flag_string: str, seed: int, zora: str) -> None:
    """No helpful text in slots 3, 6, 7 and 35 to 37; PRG0's hint-shop offers and prices; the
    white-sword selector $66; the eleven exchanged pointers distinct. Slot 0 shows an owner
    quote (owner ruling, in place of FL-ALT-04's greeting)."""
    figures = community_hints(finished(flag_string, seed, zora)[0])
    assert all(figures.values()), [name for name, value in figures.items() if not value]


def test_fl_alt_04_control_keeps_the_helpful_texts_and_drawn_shops() -> None:
    """Under mixed hints the helpful texts show in about half of those slots and the hint shops
    are rewritten."""
    figures = [community_hints(finished(CONTROL, seed)[0]) for seed in range(1, 7)]
    assert not any(f["hint-shop offers PRG0's"] or f["hint-shop prices PRG0's"] for f in figures)
    assert not all(f[f"slot {slot} a pool text"] for f in figures for slot in HELPFUL_TEXT_SLOTS)
    assert all(f["slot 0 an owner quote"] for f in figures)


# ---------------------------------------------------------------------------
# With the ZORA extras
# ---------------------------------------------------------------------------

def test_the_magical_sword_check_counts_four_starting_hearts() -> None:
    """Owner requirement B's M is FL-DEP-03's C16 + 1: four with FL-ALT-02. The white-sword
    requirement the check reads is the cave's drawn one, 5 or 6 with FL-ALT-03."""
    assert extra_options(plan(ALL_THREE, 1, EXTRAS)).starting_heart_containers == 4
    assert extra_options(plan(CONTROL, 1, EXTRAS)).starting_heart_containers == 3
