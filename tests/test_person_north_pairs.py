"""A hint person's north side (docs/deviations.md "Hint persons below a life-or-money room").

The game never lets Link walk north past a person (aldonunez CheckPersonBlocking: no moving up
above Y $8E while a person, object types $4B-$52, is in the room), and a hint person never leaves,
so a door there can't be reached from the person's side. The late gate's deal pins the pair above
a person room to wall/wall (VA-REJ-03 step 3), but the spec leaves a level-9 person unpinned when
the room above is life-or-money: 4 of 999 random configurations (all with Add Money or Life
Rooms, B22) had an open door behind a level-9 hint person (2026-10-22). ZORA pins it; only the life-or-money person
($11), who leaves once paid, keeps the spec's exception."""
from functools import cache

import pytest

from tests.needs import needs_base_rom, needs_encoder
from zora.flags.codec import decode
from zora.flags.fields import ENCODE_LEVEL_DATA
from zora.generate.late_gate.deal import _internal_slots, _pinned_pairs
from zora.generate.late_gate.walk import level9_entry_room
from zora.generate.pipeline import build, plan
from zora.model.enums import Enemy, RoomAction, Side, WallType
from zora.model.game_world import GameWorld
from zora.model.levels import MERCHANT_LIST, Level
from zora.model.rooms import MONSTER_BIT_CODE, DoorPair, Room
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = needs_base_rom
# The scan's seeds whose level-9 hint person (room) sat below a life-or-money room with an open door
# between them, before the fix
SCAN_SEEDS = [
    ("oIbnPfPSJCQiQIzDd3L!8TmKREjbobSBVlZO!", "3.67QWS", 401148),
    ("oIbnPfPjdM8NRaITKUbKA3s6kuKDATbYiV3UT", "3.8IyFA", 401563),
    ("HMPMRZOpBQQDFMJT7VB6edXmafZawN", "3.2o7GB", 744088),
    ("oIbnPfPaymn2nGLIFAVSB4QMOSsYZ1DxltVxH", "3.30pGg", 400755),
]
# A string with Encode level data on is planned only with the private encoder; a release tree skips it
SCAN_CASES = [pytest.param(*case, marks=needs_encoder) if decode(case[0]).is_on(ENCODE_LEVEL_DATA) else case
              for case in SCAN_SEEDS]
MORE_BOMBS_LIST = 0x0F


@cache
def world(flag_string: str, zora: str, seed: int) -> GameWorld:
    return build(plan(flag_string, seed, zora), remember_repo_base_rom()).world


def level_9(game: GameWorld) -> Level:
    return next(level for level in game.levels if level.level_num == 9)


def is_hint_person(level: Level, room: Room) -> bool:
    return (room.is_person and room.monster_list not in (MERCHANT_LIST, MORE_BOMBS_LIST)
            and room.room_num != level9_entry_room(level))


@pytest.mark.parametrize(("flag_string", "zora", "seed"), SCAN_CASES)
def test_no_hint_person_has_a_door_behind_them(flag_string: str, zora: str, seed: int) -> None:
    for level in world(flag_string, zora, seed).levels:
        for room in level.rooms:
            if is_hint_person(level, room):
                assert room.walls[Side.NORTH] == WallType.SOLID_WALL, (level.level_num, hex(room.room_num))


@needs_encoder
@pytest.mark.parametrize("person_list", ["hint", "life-or-money"])
def test_the_deal_pins_a_level_9_person_below_a_life_or_money_room(person_list: str) -> None:
    """A level-9 hint person below a life-or-money room is pinned; the life-or-money person in that
    place keeps the spec's exception."""
    level = level_9(world(*SCAN_SEEDS[0]))
    pairs = _internal_slots(set(level.room_nums))
    person = next(room for room in sorted(level.rooms, key=lambda room: room.room_num)
                  if is_hint_person(level, room) and room.room_num - 16 in level.room_nums)
    above = level.block.room(person.room_num - 16)
    saved = (person.enemy_info, above.enemy_info, above.secret_info)
    pair = DoorPair(above.room_num, person.room_num, Side.SOUTH)
    try:
        above.room_action = RoomAction.MONEY_OR_LIFE
        if person_list == "life-or-money":
            person.enemy = Enemy(MERCHANT_LIST | MONSTER_BIT_CODE)
        assert (pair in _pinned_pairs(level, pairs)) is (person_list == "hint")
    finally:
        person.enemy_info, above.enemy_info, above.secret_info = saved
