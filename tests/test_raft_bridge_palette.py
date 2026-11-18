"""Extra Raft Blocks' bridge in brown (CustomShield's report on 2.0.1): the dock the flag's layout edit draws
across screen $44 (west of the first quest's level 4 at $45, south of $34) is drawn in the screen's inner
palette. With the flag on, finished ROMs give $44 inner palette 3 (brown) instead of PRG0's 2 (green), whatever
the cave shuffle moved there; with it off, $44 keeps what generation gave it."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.pipeline import generate_rom
from zora.generate.steps.overworld_gates import BROWN_INNER_PALETTE, RAFT_BRIDGE_SCREEN
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom
SEEDS = (1, 2, 3)
GREEN_INNER_PALETTE = 2


@cache
def inner_palette(seed: int, raft_blocks: ThreeState) -> int:
    zora = zora_flags.encode(ZoraFlags(extra_raft_blocks=raft_blocks))
    rom = generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, remember_repo_base_rom(), zora_flag_string=zora).rom
    return parse_rom(rom).overworld.screens[RAFT_BRIDGE_SCREEN].inner_palette


def test_the_bridge_screen_is_the_one_west_of_level_4() -> None:
    assert (RAFT_BRIDGE_SCREEN, BROWN_INNER_PALETTE) == (0x44, 3)
    assert parse_rom(remember_repo_base_rom()).overworld.screens[RAFT_BRIDGE_SCREEN].inner_palette \
        == GREEN_INNER_PALETTE


@pytest.mark.parametrize("seed", SEEDS)
def test_the_bridge_is_brown_with_extra_raft_blocks(seed: int) -> None:
    assert inner_palette(seed, ThreeState.ON) == BROWN_INNER_PALETTE
