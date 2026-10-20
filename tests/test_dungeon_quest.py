"""Dungeon Quest (C02; shapes-behavior.md SH-SRC-01 to SH-SRC-10, post-shapes-b9.md PS-VAN-01 to
PS-VAN-07): the set sources, the vanilla sets' fixed lists, and finished ROMs of 1st Quest
(C02 = 0), 2nd Quest (C02 = 1), Mixed Quest (C02 = 2), Mixed + Shapes (C02 = 4), Random No Shapes
(C02 = 5) and Random (C02 = 6). The Checks over 1,000 seeds: `python3 scripts/compare_corpus.py
--set c02-quest1` (or c02-quest2, c02-mixed, c02-mixshapes, c02-random-noshapes, c02-random), and
the CP-5 set against each value's corpus. tests/test_dungeon_quest_values.py tests the new values'
flags and draws without the ROM."""
from collections import Counter
from functools import cache

import pytest

from zora.flags.codec import decode, encode
from zora.flags.fields import DUNGEON_LAYOUT_SOURCE, ENCODE_LEVEL_DATA, DungeonLayoutSource, ThreeState
from zora.generate.pipeline import generate_rom, plan
from zora.generate.rng import Rng
from zora.generate.steps.dungeon_quest import (
    MIXED_HEADS,
    MIXED_TAILS,
    SetSource,
    SetSources,
    draw_attempt_set_sources,
    draw_seed_set_sources,
    vanilla_room_list,
)
from zora.generate.steps.shuffle_items import PAIRED_LEVELS, _RoomPosition, heart_rooms
from zora.model.game_world import GameWorld
from zora.rom import level_encoding
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom
from zora.rom.game_config import GameConfig
from zora.rom.parse.rom_file import parse_rom
from zora_measure.checkpoints.dungeon_quest import (
    FIRST_QUEST_DUNGEONS_FLAGS,
    MIXED_DUNGEONS_FLAGS,
    MIXED_WITH_SHAPES_FLAGS,
    RANDOM_DUNGEONS_FLAGS,
    RANDOM_NO_SHAPES_FLAGS,
    SECOND_QUEST_DUNGEONS_FLAGS,
    item_invariants,
    level_2_bank,
    level_3_guard,
    level_9_rooms,
    monster_branches,
    second_quest_people,
    set_sources,
    start_rooms,
)

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

# PS-VAN-02's Check: the room counts of the 18 lists, first-quest levels 1-9 then second-quest
LIST_SIZES = {SetSource.FIRST_QUEST: (16, 17, 17, 19, 20, 23, 30, 23, 53),
              SetSource.SECOND_QUEST: (14, 11, 20, 18, 27, 21, 34, 25, 44)}


@cache
def _base() -> bytes:
    return remember_repo_base_rom()


@cache
def _prg0() -> GameWorld:
    return parse_rom(_base())


@cache
def _finished(flags: str, seed: int) -> GameWorld:
    config = plan(flags, seed).config
    rom = generate_rom(flags, seed, _base()).rom
    return parse_rom(rom, GameConfig(dungeon_nothing_code=config.dungeon_nothing_code, hint_mode=config.hint_mode))


@pytest.mark.parametrize("source", [SetSource.FIRST_QUEST, SetSource.SECOND_QUEST])
def test_the_vanilla_room_lists(source: SetSource) -> None:
    levels = _prg0().levels if source is SetSource.FIRST_QUEST else _prg0().levels_2q
    assert tuple(len(vanilla_room_list(level, source)) for level in levels) == LIST_SIZES[source]


def test_the_two_listed_last_orders() -> None:
    """PS-VAN-02's quirk: first-quest level 7 ends 11, 58; level 9 ends 49, 33, 53."""
    levels = _prg0().levels
    assert vanilla_room_list(levels[6], SetSource.FIRST_QUEST)[-2:] == [11, 58]
    assert vanilla_room_list(levels[8], SetSource.FIRST_QUEST)[-3:] == [49, 33, 53]


def test_mixed_with_shapes_draws_two_different_sources() -> None:
    """SH-SRC-01: the six ordered pairs, never the same source twice."""
    rng = Rng(7)
    pairs: Counter[SetSources | None] = Counter(
        draw_seed_set_sources(DungeonLayoutSource.MIXED_WITH_SHAPES, rng) for _ in range(600))
    assert len(pairs) == 6 and all(pair is not None and pair[0] is not pair[1] for pair in pairs)


def test_mixed_quest_draws_its_coin_per_attempt() -> None:
    """SH-SRC-09: no source per seed; a coin on every attempt."""
    assert draw_seed_set_sources(DungeonLayoutSource.MIXED, Rng(1)) is None
    rng = Rng(3)
    assert {draw_attempt_set_sources(None, rng) for _ in range(40)} == {MIXED_HEADS, MIXED_TAILS}


@pytest.mark.skipif(not level_encoding.is_available(), reason="needs the encoder")
def test_level_encoding_plans_with_second_quest_dungeons() -> None:
    """Encode level data with second-quest dungeons is no longer refused (owner decision,
    2026-10-12): the encoding folds a second-quest set's block first (tests/test_level_encoding_fold.py)."""
    settings = decode(SECOND_QUEST_DUNGEONS_FLAGS).updated(toggles={ENCODE_LEVEL_DATA.id: ThreeState.ON})
    assert plan(encode(settings), 1).config.level_encoding is not None
    first_quest = decode(FIRST_QUEST_DUNGEONS_FLAGS)
    assert first_quest.option(DUNGEON_LAYOUT_SOURCE) == DungeonLayoutSource.FIRST_QUEST


@pytest.mark.parametrize("seed", [1, 2])
def test_first_quest_dungeons(seed: int) -> None:
    gw = _finished(FIRST_QUEST_DUNGEONS_FLAGS, seed)
    assert set_sources(gw) == (SetSource.FIRST_QUEST, SetSource.FIRST_QUEST)
    assert not any(monster_branches(gw).values())
    assert all(level_3_guard(gw).values())                 # PS-ROOM-16
    assert gw.bomb_upgrade_levels is not None              # SH-SRC-08: the move ran
    assert all(item_invariants(gw).values()) and all(level_9_rooms(gw).values())
    assert start_rooms(gw) == (9, 9)


@pytest.mark.parametrize("seed", [1, 2])
def test_second_quest_dungeons(seed: int) -> None:
    gw = _finished(SECOND_QUEST_DUNGEONS_FLAGS, seed)
    assert set_sources(gw) == (SetSource.SECOND_QUEST, SetSource.SECOND_QUEST)
    assert all(monster_branches(gw).values())              # SH-SRC-05: $D0
    assert gw.bomb_upgrade_levels is None                  # SH-SRC-08: PRG0's code
    assert level_2_bank(gw)["bank = level 7's there"]       # PS-VAN-04
    assert second_quest_people(gw) == (8, 8)               # PS-VAN-07
    assert all(item_invariants(gw).values()) and all(level_9_rooms(gw).values())
    assert start_rooms(gw) == (9, 9)


@pytest.mark.parametrize("seed", range(1, 7))
def test_mixed_with_shapes_dungeons(seed: int) -> None:
    """SH-SRC-01 to SH-SRC-06 (C02 = 4): two different sources (so at most one set shapes); the monster
    branches take the second-quest path exactly when a set is second quest; the hungry-goriya and
    bomb-upgrade moves are off; the item and level-9 invariants hold."""
    gw = _finished(MIXED_WITH_SHAPES_FLAGS, seed)
    sources = set_sources(gw)
    assert sources[0] is not sources[1]
    assert all(monster_branches(gw).values()) == (SetSource.SECOND_QUEST in sources)
    assert not any(monster_branches(gw).values()) == (SetSource.SECOND_QUEST not in sources)
    assert gw.bomb_upgrade_levels is None                  # SH-SRC-06 item 1 (FL-DEP-02 item 4)
    assert all(item_invariants(gw).values()) and all(level_9_rooms(gw).values())


@pytest.mark.parametrize("seed", range(1, 7))
def test_mixed_quest_dungeons(seed: int) -> None:
    """SH-SRC-09 (C02 = 2): one set second quest and the other first quest, by the attempt's coin;
    the monster branches keep $F0 (the quirk); a second-quest levels 1-6 gives level 2 level 7's
    bank (PS-VAN-04); the hungry-goriya and bomb-upgrade moves are off (FL-DEP-02 rule 4); the item
    and level-9 invariants hold (PS-VAN-03, PS-VAN-01)."""
    gw = _finished(MIXED_DUNGEONS_FLAGS, seed)
    assert set_sources(gw) in (MIXED_HEADS, MIXED_TAILS)
    assert not monster_branches(gw)["$D0"]  # one set is always second quest; the bytes stay $F0
    assert gw.bomb_upgrade_levels is None
    assert level_2_bank(gw)["bank = level 7's there"] == (set_sources(gw) == MIXED_HEADS)
    assert all(item_invariants(gw).values()) and all(level_9_rooms(gw).values())
    assert start_rooms(gw) == (9, 9)


# SH-SRC-10: the set sources each drawn value allows (SH-SRC-07's table)
ALLOWED_SOURCES = {
    DungeonLayoutSource.FIRST_QUEST: {(SetSource.FIRST_QUEST, SetSource.FIRST_QUEST)},
    DungeonLayoutSource.SECOND_QUEST: {(SetSource.SECOND_QUEST, SetSource.SECOND_QUEST)},
    DungeonLayoutSource.MIXED: {MIXED_HEADS, MIXED_TAILS},
    DungeonLayoutSource.GENERATED_SHAPES: {(SetSource.SHAPES, SetSource.SHAPES)},
    DungeonLayoutSource.MIXED_WITH_SHAPES: {(first, second) for first in SetSource for second in SetSource
                                            if first is not second},
}


@pytest.mark.parametrize("flags", [RANDOM_NO_SHAPES_FLAGS, RANDOM_DUNGEONS_FLAGS])
@pytest.mark.parametrize("seed", range(1, 5))
def test_random_dungeon_quests_build_their_drawn_value(flags: str, seed: int) -> None:
    """SH-SRC-10 (C02 = 5 and 6): the seed builds the value it drew, with that value's sources and
    monster branches (SH-SRC-05, SH-SRC-09), and the item and level-9 invariants hold."""
    drawn = plan(flags, seed).alternatives.dungeon_quest
    gw = _finished(flags, seed)
    sources = set_sources(gw)
    assert sources in ALLOWED_SOURCES[drawn]
    second_quest_path = drawn is not DungeonLayoutSource.MIXED and SetSource.SECOND_QUEST in sources
    assert gw.monsters_take_second_quest_path is second_quest_path
    assert all(item_invariants(gw).values()) and all(level_9_rooms(gw).values())


def test_ps_item_08_records_a_second_quest_heart_room_as_its_paired_level() -> None:
    """PS-ITEM-08: the heart scan records a second-quest-style block's heart room of level 2, 4
    or 7 as level 3, 5 or 8 and the other way round; the first quest's keep their own level, and
    every room keeps its owner."""
    world = _prg0()
    for levels, paired in ((world.levels, False), (world.levels_2q, True)):
        hearts = [place for place in heart_rooms(levels, []) if isinstance(place, _RoomPosition)]
        assert len(hearts) == 8
        for place in hearts:
            own = place.level.level_num
            assert place.level.block.owner_of(place.room.room_num) is place.level
            assert place.level_num == (PAIRED_LEVELS.get(own, own) if paired else own)
        assert paired == any(place.level_num != place.level.level_num for place in hearts)
