"""The boss shuffle's export of 2026-10-28 (post-shapes-b2.md), on the spec's Check strings:

  - PS-BOSS-07, Add Extra Bosses (B79): more bosses in levels 1 to 8 than CP-5's 20, none in level 9,
    none with a boss sound; no effect with Shuffle Bosses (B34) off.
  - PS-BOSS-06: under 2nd Quest dungeons (C02 = 1) the second-quest levels' bosses are redrawn, with
    Shuffle Dungeon Monsters, Shuffle Monsters Between Levels and Shuffle Boss Groups off (B32, B36,
    B40) so only the boss shuffle changes them; with B34 off they keep PRG0's.
  - PS-BOSS-05's MAY (owner ruling 2026-10-27): with B40 off, a second-quest level 1 or 2 keeps no boss
    beaten by the item at either end of its planted records."""
from functools import cache

import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import DungeonLayoutSource, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import build, generate_rom, plan
from zora.generate.steps.shuffle_bosses import BOSS_TIERS, ITEM_BEATS_BOSS_LEVELS, bosses_beaten_by_planted_items
from zora.model.enums import BossSound
from zora.model.levels import LEVEL_9, Level
from zora.model.rooms import Room
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.parse.rom_file import parse_rom

pytestmark = needs_base_rom

BOSS_CODES = frozenset(code for tier in BOSS_TIERS for code in tier)
MONSTER_BIT_CODE = 0x40
CP5_BOSSES_IN_LEVELS_1_TO_8 = 20
LEVEL_9_BOSSES = 5
SEEDS = (1, 2, 3)
ONLY_THE_BOSS_SHUFFLE = {"B32": ThreeState.OFF, "B36": ThreeState.OFF, "B40": ThreeState.OFF}


def boss_code(room: Room) -> int:
    return room.enemy & (MONSTER_BIT_CODE - 1) | (MONSTER_BIT_CODE if room.has_monster_bit else 0)


def bosses(level: Level) -> list[Room]:
    return [room for room in level.block.rooms if room.room_num in level.room_nums and boss_code(room) in BOSS_CODES]


@cache
def levels(toggles: tuple[tuple[str, ThreeState], ...], seed: int, second_quest: bool = False) -> list[Level]:
    options = {"C02": DungeonLayoutSource.SECOND_QUEST} if second_quest else {}
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles=dict(toggles), options=options))
    return parse_rom(generate_rom(flags, seed, remember_repo_base_rom()).rom).levels


@pytest.mark.parametrize("seed", SEEDS)
def test_extra_bosses_join_levels_1_to_8_silently(seed: int) -> None:
    rom_levels = levels((("B79", ThreeState.ON),), seed)
    ordinary = [room for level in rom_levels if level.level_num != LEVEL_9 for room in bosses(level)]
    assert len(ordinary) > CP5_BOSSES_IN_LEVELS_1_TO_8
    assert all(room.boss_sound == BossSound(0) for room in ordinary)
    assert len(bosses(next(level for level in rom_levels if level.level_num == LEVEL_9))) == LEVEL_9_BOSSES


def test_without_the_boss_shuffle_extra_bosses_do_nothing() -> None:
    rom_levels = levels((("B79", ThreeState.ON), ("B34", ThreeState.OFF)), 1)
    assert sum(len(bosses(level)) for level in rom_levels if level.level_num != LEVEL_9) == CP5_BOSSES_IN_LEVELS_1_TO_8


def boss_codes_by_level(rom_levels: list[Level]) -> dict[int, list[int]]:
    return {level.level_num: sorted(boss_code(room) for room in bosses(level)) for level in rom_levels}


def test_second_quest_levels_get_their_redrawn_bosses() -> None:
    prg0 = boss_codes_by_level(parse_rom(remember_repo_base_rom()).levels_2q)
    kept = boss_codes_by_level(levels((*ONLY_THE_BOSS_SHUFFLE.items(), ("B34", ThreeState.OFF)), 1, True))
    assert kept == prg0
    for seed in SEEDS:
        redrawn = boss_codes_by_level(levels(tuple(ONLY_THE_BOSS_SHUFFLE.items()), seed, True))
        assert redrawn[LEVEL_9] == prg0[LEVEL_9]
        assert sum(redrawn[level] != prg0[level] for level in range(1, LEVEL_9)) >= LEVEL_9 - 3


@pytest.mark.parametrize("seed", SEEDS)
def test_the_item_rule_holds_on_second_quest_levels_1_and_2(seed: int) -> None:
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(
        toggles=ONLY_THE_BOSS_SHUFFLE, options={"C02": DungeonLayoutSource.SECOND_QUEST}))
    built = build(plan(flags, seed), remember_repo_base_rom())
    assert built.result.item_shuffle_result is not None
    barred = bosses_beaten_by_planted_items(built.result.item_shuffle_result.tracked)
    for level in built.world.levels:
        if level.level_num in ITEM_BEATS_BOSS_LEVELS:
            assert level.is_second_quest
            assert not {boss_code(room) for room in bosses(level)} & barred[level.level_num]
