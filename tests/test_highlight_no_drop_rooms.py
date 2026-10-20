"""Highlight No-Drop Rooms (ZORA flag highlight_no_drop_rooms; owner decision, 2026-10-18; the
research doc "Highlight No-Drop Rooms: Research and Implementation Plan"): every dungeon room whose
layout has blocks and whose inner palette selector is 2 or 3 takes 3 when it can never hold an
item and 2 otherwise (zora/generate/steps/highlight_no_drop_rooms.py).

The doc's acceptance checks, without its accent and dark-fade color writes (owner decision 2):
  - only room table B bits 0-1 change (and the seed's code, a hash of the ROM), against the same
    plan with the flag resolved off (a ZORA flag moves the whole seed, so the flag-off ROM keeps
    the flag string and turns only the resolved flag off);
  - no item in a marked room, on ZORA's own output for the MVP baseline and the 1st Quest, 2nd
    Quest, Mixed Quest, Mixed + Shapes and Random dungeon sources, and the rule itself on the
    crossed corpora of those flag strings (slow);
  - every block room follows the rule; every other room keeps its selector;
  - the marks per seed near the doc's figures (slow);
  - Allow Universal Drops In Shapes (B91) on: the ROM equals the flag-off ROM.
The 2nd Quest pairs are rebuilt here from PRG0's 2nd Quest item rooms."""
from collections.abc import Iterator
from dataclasses import dataclass, replace
from functools import cache
from pathlib import Path

import pytest

from tests.needs import needs_base_rom, needs_corpus
from tests.seed_rotation import SEEDS_PER_SWEEP, chunk_id, chunks, sweep_seeds
from tests.test_coop_reserved import z1r_with
from zora.flags import zora_flags
from zora.flags.fields import DungeonLayoutSource, ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import GenerationPlan, build, finish, plan
from zora.generate.shapes.t5_positions import T5_BASE
from zora.generate.steps.highlight_no_drop_rooms import (
    MARKED_PALETTE,
    SECOND_QUEST_PAIRS,
    allowed_positions,
    is_exception,
    is_no_drop_room,
    takes_part,
)
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.rooms import Room
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.code_patches import SEED_CODE_ADDRESS, SEED_CODE_LENGTH
from zora.rom.layout import (
    LEVEL_1_6_DATA_ADDRESS,
    LEVEL_1_6_DATA_ADDRESS_Q2,
    LEVEL_7_9_DATA_ADDRESS,
    LEVEL_7_9_DATA_ADDRESS_Q2,
)
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora_measure.corpora import corpus

pytestmark = needs_base_rom

ON = zora_flags.encode(zora_flags.ZoraFlags(highlight_no_drop_rooms=ThreeState.ON))
ROOMS_PER_TABLE = 0x80
TABLE_B = 1                                  # LevelBlockAttrsB: the second of the six tables
INNER_PALETTE_BITS = 0x03
TABLE_B_OFFSETS = frozenset(start + TABLE_B * ROOMS_PER_TABLE + room
                            for start in (LEVEL_1_6_DATA_ADDRESS, LEVEL_7_9_DATA_ADDRESS,
                                          LEVEL_1_6_DATA_ADDRESS_Q2, LEVEL_7_9_DATA_ADDRESS_Q2)
                            for room in range(ROOMS_PER_TABLE))
SEED_CODE_OFFSETS = frozenset(range(SEED_CODE_ADDRESS, SEED_CODE_ADDRESS + SEED_CODE_LENGTH))
SOURCES = {"MVP baseline": MVP_BASELINE_LEVEL_ENCODING_OFF,
           **{name: z1r_with(options={"C02": source}) for name, source in (
               ("1st Quest", DungeonLayoutSource.FIRST_QUEST), ("2nd Quest", DungeonLayoutSource.SECOND_QUEST),
               ("Mixed Quest", DungeonLayoutSource.MIXED), ("Mixed + Shapes", DungeonLayoutSource.MIXED_WITH_SHAPES),
               ("Random", DungeonLayoutSource.RANDOM))}}
REMOVE_MOST_OPEN_STAIRS = z1r_with(toggles={"B30": ThreeState.ON})
UNIVERSAL_DROPS = z1r_with(toggles={"B91": ThreeState.ON})
QUICK_SEEDS = range(1, 4)


@cache
def base() -> bytes:
    return remember_repo_base_rom()


def plans(flag_string: str, seed: int) -> tuple[GenerationPlan, GenerationPlan]:
    """The flag on, and the same plan (the same seed and stream) with it resolved off."""
    on = plan(flag_string, seed, ON)
    return on, replace(on, zora_resolved=replace(on.zora_resolved, highlight_no_drop_rooms=ThreeState.OFF))


@cache
def roms(flag_string: str, seed: int) -> tuple[bytes, bytes]:
    on, off = plans(flag_string, seed)
    return finish(build(on, base()), base()), finish(build(off, base()), base())


@dataclass
class Audit:
    """One world's rooms against the rule."""
    marked: int = 0                  # rooms the rule marks (the exceptions aside), shown or not
    shown: int = 0                   # of them, rooms whose selector changes (blocks, on 2 or 3)
    holding: list[str] | None = None  # rule-marked rooms holding an item

    def __post_init__(self) -> None:
        self.holding = self.holding or []


def level_rooms(world: GameWorld) -> Iterator[tuple[int, Room, bool]]:
    """Each level's rooms, with whether the rule calls it a no-drop room (before the exceptions)."""
    allowed = allowed_positions(any(level.is_second_quest for level in world.levels))
    for level in world.levels:
        for room in level.rooms:
            yield level.level_num, room, is_no_drop_room(level, room, allowed)


def audit(world: GameWorld, open_stairs_removed: bool) -> Audit:
    result = Audit()
    for level_num, room, no_drop in level_rooms(world):
        if not no_drop or is_exception(room, open_stairs_removed):
            continue
        result.marked += 1
        result.shown += takes_part(room)
        if room.item != Item.NOTHING:
            assert result.holding is not None
            result.holding.append(f"level {level_num} room ${room.room_num:02X}: {room.item.name}")
    return result


def test_the_second_quest_pairs_are_prg0s_second_quest_item_rooms() -> None:
    """Every PRG0 2nd Quest item room as (screen type, position value), less the T5 base list."""
    world = parse_rom(base())
    pairs: dict[int, set[int]] = {}
    for level in world.levels_2q:
        for room in level.rooms:
            position = level.item_position_table[room.item_position]
            if room.item != Item.NOTHING and position not in T5_BASE.get(room.layout_code, ()):
                pairs.setdefault(room.layout_code, set()).add(position)
    assert pairs == {screen_type: set(positions) for screen_type, positions in SECOND_QUEST_PAIRS.items()}


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("source", ["MVP baseline", "2nd Quest"])
def test_only_the_inner_palette_bits_change(source: str, seed: int) -> None:
    on, off = roms(SOURCES[source], seed)
    changed = [offset for offset, (a, b) in enumerate(zip(on, off, strict=True)) if a != b]
    assert changed, "no room changed"
    assert set(changed) <= TABLE_B_OFFSETS | SEED_CODE_OFFSETS
    assert all((on[offset] ^ off[offset]) & ~INNER_PALETTE_BITS == 0
               for offset in changed if offset in TABLE_B_OFFSETS)


def check_rooms(on: bytes, off: bytes, open_stairs_removed: bool) -> Audit:
    """Every block room on 2 or 3 follows the rule; every other room keeps its selector; no item
    in a marked room."""
    world_on, world_off = parse_rom(on), parse_rom(off)
    before = {(level.level_num, room.room_num): room.palette_1 for level in world_off.levels for room in level.rooms}
    for level_num, room, no_drop in level_rooms(world_on):
        was = before[level_num, room.room_num]
        if takes_part(replace(room, palette_1=was)):
            marked = no_drop and not is_exception(room, open_stairs_removed)
            assert (room.palette_1 == MARKED_PALETTE) == marked, (level_num, hex(room.room_num))
            assert not marked or room.item == Item.NOTHING, (level_num, hex(room.room_num), room.item)
        else:
            assert room.palette_1 == was, (level_num, hex(room.room_num))
    return audit(world_on, open_stairs_removed)


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("source", SOURCES)
def test_every_block_room_follows_the_rule(source: str, seed: int) -> None:
    result = check_rooms(*roms(SOURCES[source], seed), open_stairs_removed=False)
    assert result.shown and not result.holding


@pytest.mark.parametrize("seed", QUICK_SEEDS)
def test_remove_most_open_stairs_keeps_its_three_screen_types(seed: int) -> None:
    result = check_rooms(*roms(REMOVE_MOST_OPEN_STAIRS, seed), open_stairs_removed=True)
    assert result.shown and not result.holding


@pytest.mark.parametrize("seed", QUICK_SEEDS)
def test_universal_drops_on_means_no_change(seed: int) -> None:
    on, off = roms(UNIVERSAL_DROPS, seed)
    assert on == off


# --- slow: many seeds, and the rule on the crossed corpora ---------------------------------------

# The sweep's range; each run checks a rotated block of 20 of it (tests/seed_rotation.py), as chunks.
SWEEP_SEEDS = range(1, 101)
# The doc's shown marks per seed (300 ROMs per corpus); ZORA's own figures over the whole range are
# 39.8, 26.2 and 40.6 (measured 2026-10-18, 300 seeds each).
SHOWN_PER_SEED = {"MVP baseline": 40.1, "1st Quest": 26.3, "2nd Quest": 40.5}
# A block of 20 seeds: about three standard deviations of its mean (the per-seed spread is about 5)
TOLERANCE = 3.5


@pytest.mark.slow
@pytest.mark.parametrize("chunk", chunks(sweep_seeds(SWEEP_SEEDS), SEEDS_PER_SWEEP), ids=chunk_id)
@pytest.mark.parametrize("source", SOURCES)
def test_no_item_in_a_marked_room_over_many_seeds(source: str, chunk: range) -> None:
    shown = 0
    for seed in chunk:
        result = check_rooms(*roms(SOURCES[source], seed), open_stairs_removed=False)
        assert not result.holding, (seed, result.holding)
        shown += result.shown
        roms.cache_clear()
    if source in SHOWN_PER_SEED:
        assert abs(shown / len(chunk) - SHOWN_PER_SEED[source]) <= TOLERANCE, shown / len(chunk)


CORPORA = {"clean": False, "c02-quest1": False, "c02-quest2": False, "c02-mixed": False,
           "c02-mixshapes": False, "c02-random": False, "b30": True}
CORPUS_ROMS = 200


def corpus_roms(name: str) -> list[Path]:
    return sorted(corpus(name).glob("*.nes"))[:CORPUS_ROMS]


@pytest.mark.slow
@pytest.mark.parametrize("name", [pytest.param(name, marks=needs_corpus(corpus(name))) for name in CORPORA])
def test_the_rule_holds_on_the_crossed_corpora(name: str) -> None:
    """The corpora are option-off ROMs: no room the rule marks holds an item there either."""
    base()
    for path in corpus_roms(name):
        result = audit(parse_rom(load_rom(path)), CORPORA[name])
        assert not result.holding, (path.name, result.holding)

