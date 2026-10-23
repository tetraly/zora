"""Do Not Segment Dungeons (ZORA flag do_not_segment_dungeons, version 10; owner, 2026-10-22; tetraly/zora#6
and #7; docs/reports/research-candles-and-segments.md section 2): a shapes level grows as one
piece, and the late gate walks its doors without its transport staircases, so doors alone join
every room. The 10 item cellars and the 10 base-budget transports stay, as shortcuts: every level
has exactly its base stair budget (level 9 eight). Vanilla sets keep their stairway-linked areas."""
from functools import cache
from types import SimpleNamespace

import pytest

from tests.needs import needs_base_rom
from zora.flags import zora_flags
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.generation_pass import unsegmented_levels
from zora.generate.late_gate.walk import STAIR_SIDE, build_graph, connectivity_walk
from zora.generate.pipeline import Built, build, plan
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.tables import stair_budget
from zora.generate.steps.dungeon_quest import ALL_SHAPES, SetSource
from zora.model.enums import RoomType
from zora.model.levels import Level
from zora.rom.base_rom import remember_repo_base_rom
from zora_measure.checks import level_pieces

pytestmark = needs_base_rom
UNSEGMENTED = zora_flags.encode(ZoraFlags(do_not_segment_dungeons=ThreeState.ON))
SEEDS = (1, 2, 3)
STAIR_SIDE_TRANSPORTS = 10           # per ROM: levels 5-8 one each and level 9 six


@cache
def built(seed: int, zora: str = UNSEGMENTED, flags: str = MVP_BASELINE_LEVEL_ENCODING_OFF) -> Built:
    return build(plan(flags, seed, zora), remember_repo_base_rom())


def transports(level: Level) -> int:
    return sum(stair.room_type == RoomType.TRANSPORT_STAIRCASE for stair in level.staircase_rooms)


@pytest.mark.parametrize("seed", SEEDS)
def test_every_shapes_level_is_one_piece_joined_by_doors(seed: int) -> None:
    world = built(seed).world
    for level in world.levels:
        assert len(level_pieces(level)) == 1, level.level_num
        assert connectivity_walk(level, transports=False).passed, level.level_num
        assert len(level.staircase_rooms) == stair_budget(level.level_num), level.level_num
    assert sum(transports(level) for level in world.levels) == STAIR_SIDE_TRANSPORTS


def test_off_some_level_needs_its_stairways() -> None:
    """The control: without the flag the same seeds have extra pieces and stair-only areas."""
    worlds = [built(seed, "").world for seed in SEEDS]
    assert any(len(level_pieces(level)) > 1 for world in worlds for level in world.levels)
    assert any(not connectivity_walk(level, transports=False).passed for world in worlds for level in world.levels)


def test_the_doors_only_walk_leaves_transports_out() -> None:
    """build_graph(transports=False) has no stair link from a transport staircase; item cellars stay."""
    level_9 = next(level for level in built(1).world.levels if level.level_num == 9)
    with_stairs, doors_only = build_graph(level_9), build_graph(level_9, transports=False)
    assert doors_only.cellar_links == with_stairs.cellar_links != []
    stair_links = [state for state in with_stairs.exit_states if state[1] == STAIR_SIDE]
    assert [state for state in doors_only.exit_states if state[1] == STAIR_SIDE] == [
        start for start, _end in doors_only.cellar_links]
    assert len(stair_links) > len(doors_only.cellar_links)


@pytest.mark.parametrize(("sources", "expected"), [
    (ALL_SHAPES, frozenset(range(1, 10))),
    ((SetSource.SHAPES, SetSource.FIRST_QUEST), frozenset(range(1, 7))),
    ((SetSource.SECOND_QUEST, SetSource.SHAPES), frozenset(range(7, 10))),
    ((SetSource.FIRST_QUEST, SetSource.SECOND_QUEST), frozenset()),
])
def test_only_shapes_sets_are_walked_doors_only(sources: tuple[SetSource, SetSource], expected: frozenset[int]) -> None:
    def context(on: bool) -> SimpleNamespace:
        return SimpleNamespace(set_sources=sources,
                               settings=SimpleNamespace(shape_options=ShapeOptions(do_not_segment_dungeons=on)))
    assert unsegmented_levels(context(True)) == expected  # type: ignore[arg-type]
    assert unsegmented_levels(context(False)) == frozenset()  # type: ignore[arg-type]


def test_a_vanilla_set_keeps_its_stairway_areas() -> None:
    """Dungeon Quest: 1st Quest (C02 = 0): the levels keep their rooms and stairways, and the
    stair-only areas the 1st Quest has (the gate still walks its transports)."""
    first_quest = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(options={"C02": 0}))
    with_flag, without = built(1, UNSEGMENTED, first_quest).world, built(1, "", first_quest).world
    assert [level.room_nums for level in with_flag.levels] == [level.room_nums for level in without.levels]
    assert list(map(transports, with_flag.levels)) == list(map(transports, without.levels))
    assert any(not connectivity_walk(level, transports=False).passed for level in with_flag.levels)
