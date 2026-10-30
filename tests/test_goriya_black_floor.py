"""The hungry Goriya's room always has a person room's look, inner palette 0 and lit (SH-DOOR-01, SH-ROOM-04;
ruling 2026-10-29): when the start room's move (B26, PS-START-02) swaps the start room with the Goriya's room,
the inner palettes change rooms with the contents (docs/deviations.md). As the spec has it, the Goriya took the
old start room's palette: 12 of 200 Goriya rooms over 100 2nd Quest seeds on c780331, seeds 2 and 14 here."""
import pytest

from tests.needs import needs_base_rom
from tests.test_coop_reserved import z1r_with
from zora.flags.fields import ThreeState
from zora.generate.pipeline import build, plan
from zora.generate.steps.swap_start_rooms import _exchange_contents
from zora.model.enums import Enemy
from zora.model.rooms import EnemyInfo, Room
from zora.rom.base_rom import remember_repo_base_rom

PERSON_INNER_PALETTE = 0
SECOND_QUEST_START_MOVES = z1r_with(toggles={"B26": ThreeState.ON}, options={"C02": 1})
START_ROOM_PALETTE = 3


def test_the_swap_carries_the_goriyas_palette() -> None:
    goriya, start = Room.blank(0x20, palette_1=PERSON_INNER_PALETTE), Room.blank(0x30, palette_1=START_ROOM_PALETTE)
    goriya.enemy_info = EnemyInfo(Enemy.HUNGRY_GORIYA)
    _exchange_contents(start, goriya)
    assert start.enemy == Enemy.HUNGRY_GORIYA and start.palette_1 == PERSON_INNER_PALETTE
    assert goriya.palette_1 == START_ROOM_PALETTE


def test_other_rooms_keep_their_palettes_as_the_spec_has_it() -> None:
    first, second = Room.blank(0x20, palette_1=2), Room.blank(0x30, palette_1=START_ROOM_PALETTE)
    _exchange_contents(first, second)
    assert (first.palette_1, second.palette_1) == (2, START_ROOM_PALETTE)


@needs_base_rom
@pytest.mark.parametrize("seed", [2, 14])
def test_a_moved_goriya_keeps_its_black_floor(seed: int) -> None:
    world = build(plan(SECOND_QUEST_START_MOVES, seed), remember_repo_base_rom()).world
    goriyas = [(level.level_num, room) for level in world.levels for room in level.rooms
               if room.enemy == Enemy.HUNGRY_GORIYA]
    assert goriyas
    assert [(level_num, f"${room.room_num:02X}", room.palette_1, room.is_dark) for level_num, room in goriyas
            if room.palette_1 != PERSON_INNER_PALETTE or room.is_dark] == []
