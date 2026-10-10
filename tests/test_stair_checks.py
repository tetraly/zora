"""The finished-ROM staircase checks (SH-STAIR-02, -03, -09) count a level's own staircases: a
cell another level of the block also lists, and whose staircase leads into that level, is that
level's (zora_measure.checks.own_staircases; the final corpus lists cell $02 in both level 9's
and level 7's or 8's stairway list in 4 of 1,000 ROMs)."""
import pytest

from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora_measure.checks import check_cellar_counts, check_stair_budget, check_transport_same_level, own_staircases
from zora.model.enums import RoomType
from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="PRG0 base ROM not found")

STAIR_CHECKS = (check_cellar_counts, check_stair_budget, check_transport_same_level)


@pytest.mark.parametrize("staircase_type", [RoomType.TRANSPORT_STAIRCASE, RoomType.ITEM_STAIRCASE])
def test_a_cell_listed_by_two_levels_counts_for_its_own_level(staircase_type: RoomType) -> None:
    world = parse_rom(generate_rom(MVP_BASELINE_LEVEL_ENCODING_OFF, 1, verify_base_rom().read_bytes()).rom)
    assert all(check(world).passed for check in STAIR_CHECKS)
    level_9 = next(level for level in world.levels if level.level_num == 9)
    other = next(level for level in world.levels if level.block is level_9.block and level is not level_9
                 and any(s.room_type == staircase_type for s in level.staircase_rooms))
    shared = next(s for s in other.staircase_rooms if s.room_type == staircase_type)
    own_before = own_staircases(level_9)

    level_9.staircase_nums = sorted([*level_9.staircase_nums, shared.room_num])

    assert shared in level_9.staircase_rooms
    assert own_staircases(level_9) == own_before
    assert shared in own_staircases(other)
    assert all(check(world).passed for check in STAIR_CHECKS)
