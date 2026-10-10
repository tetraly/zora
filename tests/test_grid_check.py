"""SH-GRID-01's finished-ROM check follows the spec: unowned cells are not bounded (a level
sealed off from the columns only it may grow into leaves a whole edge strip unowned, SH-GRID-16),
and the levels 7-9 grid keeps at least one (SH-GRID-08's spare cell)."""
import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora_measure.checks import check_grid_tiled
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

# A level sealed off from the columns only it may grow into leaves that whole edge strip unowned
# (seed 726 did so before the 2026-10-07 output change: 17 cells of the six-level grid). Such
# seeds are rare (none in seeds 0-1999 since), so the strip is made by hand: levels 1-6 give up
# grid columns 0-2.
SEALED_COLUMNS = range(3)
GRID_COLUMNS = 16


def test_a_sealed_strip_passes() -> None:
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, verify_base_rom().read_bytes()).rom)
    for level in world.blocks[0].levels:
        level.room_nums = [room for room in level.room_nums if room % GRID_COLUMNS not in SEALED_COLUMNS]
    result = check_grid_tiled(world)
    assert result.passed
    assert int(result.message.split()[0]) > len(SEALED_COLUMNS) * 6, result.message


def test_a_fully_owned_three_level_grid_fails() -> None:
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, verify_base_rom().read_bytes()).rom)
    block = world.blocks[1]
    stairs = {room_num for level in block.levels for room_num in level.staircase_nums}
    spare = [room_num for room_num in range(0x80) if block.owner_of(room_num) is None and room_num not in stairs]
    assert spare and check_grid_tiled(world).passed
    level_9 = next(level for level in block.levels if level.level_num == 9)
    level_9.room_nums = sorted([*level_9.room_nums, *spare])
    assert not check_grid_tiled(world).passed
