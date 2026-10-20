"""Add Bridges to the River (B87; features-behavior.md FP-BRIDGE-01) and Add Lost Woods Shortcut
(B88; FP-WOODS-01), the 2026-10-19 export: their bytes in generated ROMs against PRG0, every other
layout and column byte left as PRG0's, both under every Overworld Quest, "?" a coin per seed, and
nothing written while they are off. The walk they open is tests/test_overworld_gates.py's; Link
walking them, tests/test_overworld_crossings_emulator.py."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.support import Support, support
from zora.generate.pipeline import generate_rom, plan
from zora.rom import overworld_crossings as crossings
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom

# FP-BRIDGE-01's and FP-WOODS-01's Check strings: CP-5 with B87 on, "?", B88 on, "?", and both on
# under Overworld Quest 1st Quest, 2nd Quest and Mixed (C01 = 0, 1, 2)
BRIDGES_ON = "34!kkZyiAJjxQSBaFEcCTIEXxbHR5PkaoqHUJ3A"
BRIDGES_RANDOM = "69!UU8wPKUm3mijjT9gboRHmrC5cMM5AZmQUJ3A"
SHORTCUT_ON = "9E!EDiu6UfoB7zGsh4l08aL0knundIQlKiZUJ3A"
SHORTCUT_RANDOM = "ITzSRQnCzBuXBluJLqyD90UjRbLKR7SVcW!UJ3A"
BOTH_ON = ("CJzyyHroeqqIUEp0u!pPTjOFeOiyuEmL5eiUJ3A", "CJzyyHroeqqIUEp0u!pPTjOFeOiyuEmL5eiUJ3B",
           "CJzyyHroeqqIUEp0u!pPTjOFeOiyuEmL5eiUJ3C")
SEEDS = (1, 2)
RANDOM_SEEDS = range(1, 13)
# The overworld's layouts (RoomLayoutsOW) and column data (the column heaps), as FP-BRIDGE-01's Check
LAYOUTS = range(0x15428, 0x15BB8)
COLUMNS = range(0x15BE8, 0x15FA0)
BRIDGE_BYTES = {crossings.ROOM_17_RIVER_ROWS: crossings.ROOM_17_BRIDGE,
                crossings.ROOM_27_RIVER_COLUMN: crossings.BRIDGE_COLUMN}
SHORTCUT_BYTES = {crossings.ROOM_51_WEST_EDGE: crossings.OPEN_TREES_COLUMN}


@cache
def rom(flag_string: str, seed: int) -> bytes:
    return generate_rom(flag_string, seed, remember_repo_base_rom()).rom


def changed_overworld_bytes(data: bytes) -> dict[int, int]:
    """The layout and column bytes that differ from PRG0's."""
    base = remember_repo_base_rom()
    return {offset: data[offset] for offset in (*LAYOUTS, *COLUMNS) if data[offset] != base[offset]}


def test_the_offsets_are_the_specs() -> None:
    assert (crossings.ROOM_17_RIVER_ROWS, crossings.ROOM_27_RIVER_COLUMN, crossings.ROOM_51_WEST_EDGE) == (
        0x15E9D, 0x1568E, 0x158F8)
    base = remember_repo_base_rom()
    assert (base[0x15E9D], base[0x1568E], base[0x158F8]) == (0x45, 0x13, 0x15)


@pytest.mark.parametrize("field_id", ["B87", "B88"])
def test_on_and_random_are_supported(field_id: str) -> None:
    cp5 = decode(MVP_BASELINE_LEVEL_ENCODING_OFF)
    for state in ThreeState:
        assert support(cp5.updated(toggles={field_id: state}))[field_id] is Support.SUPPORTED


@pytest.mark.parametrize("seed", SEEDS)
def test_off_writes_nothing(seed: int) -> None:
    assert changed_overworld_bytes(rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed)) == {}


@pytest.mark.parametrize("seed", SEEDS)
def test_the_bridges_write_their_two_bytes(seed: int) -> None:
    assert changed_overworld_bytes(rom(BRIDGES_ON, seed)) == BRIDGE_BYTES


@pytest.mark.parametrize("seed", SEEDS)
def test_the_shortcut_writes_its_byte(seed: int) -> None:
    assert changed_overworld_bytes(rom(SHORTCUT_ON, seed)) == SHORTCUT_BYTES


@pytest.mark.parametrize("flag_string", BOTH_ON)
def test_both_under_every_overworld_quest(flag_string: str) -> None:
    assert changed_overworld_bytes(rom(flag_string, SEEDS[0])) == {**BRIDGE_BYTES, **SHORTCUT_BYTES}


@pytest.mark.parametrize(("flag_string", "field_id", "written"), [(BRIDGES_RANDOM, "B87", BRIDGE_BYTES),
                                                                  (SHORTCUT_RANDOM, "B88", SHORTCUT_BYTES)])
def test_random_is_a_coin_per_seed(flag_string: str, field_id: str, written: dict[int, int]) -> None:
    """Each seed's ROM has the bytes exactly when its coin came up on, and both sides come up."""
    outcomes = set()
    for seed in RANDOM_SEEDS:
        on = plan(flag_string, seed).settings.toggle(field_id) is ThreeState.ON
        assert changed_overworld_bytes(rom(flag_string, seed)) == (written if on else {})
        outcomes.add(on)
    assert outcomes == {True, False}
