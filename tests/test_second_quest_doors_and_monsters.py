"""Add 2nd Quest Doors (B21; shapes-behavior.md SH-DOOR-02 with T1b) and Add 2nd Quest Monsters (B37;
SH-ENEMY-05, post-shapes-b2.md PS-MONLV-02), on the spec's own Check strings:

  - T1b is the spec's table, and a level's weights under B21 are its T1 row plus its T1b row;
  - B21 brings in walk-through walls: more door sides of that type than CP-5's, and every seed
    generates; "?" resolves both ways;
  - B37 sets the three quest-branch bytes to the second-quest path whenever the shape stage places
    enemies or B36 runs, whatever C02 is, and not with neither (CP-5 with B36 off and C02 = 0);
  - with B37 on, the finished rooms hold monsters only PRG0's second-quest room lists hold."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, finish, plan
from zora.generate.shapes.doors import _weights_for_level
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.tables import T1_FIRST_QUEST, T1_SECOND_QUEST
from zora.generate.steps.dungeon_quest import SetSource, vanilla_room_list
from zora.model.enums import Enemy, WallType
from zora.model.game_world import GameWorld
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

CP5 = MVP_BASELINE_LEVEL_ENCODING_OFF
B21_ON, B21_POSSIBLE = "8hq4BeR1Jw9T80n8IkIFeKw77HUJ3A", "8hq4BeR1KJVo6rGDc0KgpGrBLQUJ3A"
B37_ON, B37_POSSIBLE = "8hq4ChzlgcbuvW2iTrDWRrGsViUJ3A", "8hq4DlXV2hPggqnMyEBDQIXh7HUJ3A"
B37_WITHOUT_B36 = "8hq4CLoBDv!zfP89ejEHnMrGIrUJ3A"
B37_WITHOUT_B36_FIRST_QUEST = "8hq4CLoBDv!zfP89ejEHnMrGIrUJ2n"     # neither pass: no change
B37_FIRST_QUEST = "8hq4ChzlgcbuvW2iTrDWRrGsViUJ2n"                 # C02 = 0, B36 on
B37_MIXED_QUEST = "8hq4ChzlgcbuvW2iTrDWRrGsViUJ32"                 # C02 = 2, B36 on
FIRST_QUEST_B37_OFF = "8hq4BeR1JXo89BJ2!TFpTP02u8UJ2n"
WALK_THROUGH = (WallType.WALK_THROUGH_WALL_1, WallType.WALK_THROUGH_WALL_2)


@cache
def world(flag_string: str, seed: int) -> GameWorld:
    base = remember_repo_base_rom()
    return parse_rom(finish(build(plan(flag_string, seed), base), base))


def test_t1b_is_the_spec_s_table() -> None:
    assert T1_SECOND_QUEST[1] == [15, 4, 0, 0, 6, 4, 0, 4] and T1_SECOND_QUEST[9] == [55, 23, 16, 0, 18, 10, 0, 21]
    assert _weights_for_level(1, ShapeOptions(second_quest_doors=True)) == [33, 4, 0, 0, 10, 16, 0, 7]
    for level in range(1, 10):
        assert _weights_for_level(level, ShapeOptions()) == T1_FIRST_QUEST[level]


def walk_through_sides(shipped: GameWorld) -> int:
    return sum(getattr(room.walls, side) in WALK_THROUGH for block in shipped.blocks[:2] for room in block.rooms
               for side in ("north", "east", "south", "west"))


@needs_base_rom
def test_second_quest_doors_bring_in_walk_through_walls() -> None:
    seeds = (1, 2, 3)
    assert sum(walk_through_sides(world(B21_ON, seed)) for seed in seeds) > sum(
        walk_through_sides(world(CP5, seed)) for seed in seeds)


@pytest.mark.parametrize("flag_string, field_id", [(B21_POSSIBLE, "B21"), (B37_POSSIBLE, "B37")])
def test_random_comes_up_both_ways(flag_string: str, field_id: str) -> None:
    assert {plan(flag_string, seed).settings.is_on(field_id) for seed in range(16)} == {True, False}


@needs_base_rom
@pytest.mark.parametrize("flag_string, second_quest_path", [
    (B37_ON, True), (B37_WITHOUT_B36, True), (B37_FIRST_QUEST, True), (B37_MIXED_QUEST, True),
    (B37_WITHOUT_B36_FIRST_QUEST, False), (FIRST_QUEST_B37_OFF, False), (CP5, False)])
def test_the_quest_branches(flag_string: str, second_quest_path: bool) -> None:
    assert world(flag_string, 1).monsters_take_second_quest_path is second_quest_path


def second_quest_only_kinds() -> frozenset[Enemy]:
    """Monster kinds (count bits aside) in PRG0's second-quest room lists and in none of the
    first-quest ones."""
    base = parse_rom(remember_repo_base_rom())
    def kinds(levels: list, source: SetSource) -> set[Enemy]:
        return {level.block.room(room).enemy for level in levels for room in vanilla_room_list(level, source)}
    return frozenset(kinds(base.levels_2q, SetSource.SECOND_QUEST) - kinds(base.levels, SetSource.FIRST_QUEST)
                     - {Enemy.HUNGRY_GORIYA})


@needs_base_rom
@pytest.mark.parametrize("seed", (1, 2))
def test_second_quest_monsters_appear(seed: int) -> None:
    only = second_quest_only_kinds()
    shipped = world(B37_ON, seed)
    rooms = [level.block.room(number) for level in shipped.levels for number in level.room_nums]
    assert sum(room.enemy in only for room in rooms) >= 5
    cp5 = world(CP5, seed)
    assert not any(cp5_room.enemy in only for level in cp5.levels
                   for cp5_room in (level.block.room(number) for number in level.room_nums))
