"""Highlight No-Drop Rooms (ZORA flag highlight_no_drop_rooms; owner decision, 2026-10-18; reworked
2026-10-24): every dungeon room on inner palette 2 or 3 takes 3 when it can never hold an item
and 2 otherwise, and color 1 (block faces, water, statues, stairs) is red ($16) in each level's
palette 3, in the palette and in the dark-room fade
(zora/generate/steps/highlight_no_drop_rooms.py).

The acceptance checks:
  - against the same plan with the flag resolved off (a ZORA flag moves the whole seed, so the
    flag-off ROM keeps the flag string and turns only the resolved flag off), only the inner
    palette selector of rooms on 2 or 3 and color 1 of palette 3 (palette and fade) change
    (and the seed's code, a hash of the ROM);
  - no item in a marked room, on ZORA's own output for the MVP baseline and the 1st Quest, 2nd
    Quest, Mixed Quest, Mixed + Shapes and Random dungeon sources, and the rule itself on the
    crossed corpora of those flag strings (slow);
  - every room on 2 or 3 follows the rule (water rooms and entrance rooms too); every other room
    keeps its selector; no room outside a level's palettes 2 and 3 looks marked;
  - the marks per seed near the doc's figures (slow);
  - Allow Universal Drops In Shapes (B91) on: the ROM equals the flag-off ROM.
The 2nd Quest pairs are rebuilt here from PRG0's 2nd Quest item rooms."""
from collections import Counter
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
    ACCENT_SLOT,
    BLACK,
    FADE_GROUP_STARTS,
    FADE_STEP_SIZE,
    FADE_STEPS_PER_GROUP,
    MARKED_PALETTE,
    NO_DROP_COLOR,
    PALETTE_SIZE,
    SECOND_QUEST_PAIRS,
    UNMARKED_PALETTE,
    allowed_positions,
    darker,
    is_exception,
    is_no_drop_room,
    takes_part,
)
from zora.model.enums import Item
from zora.model.game_world import GameWorld
from zora.model.rooms import LAYOUT_ID_MASK, Room
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


def mark_offsets() -> tuple[list[int], list[int]]:
    """Where the no-drop color goes: color 1 of palette 3 in a level's palette bytes, and in each
    fade step of its two fade groups."""
    palette = [MARKED_PALETTE * PALETTE_SIZE + ACCENT_SLOT]
    fade = [(start + step) * FADE_STEP_SIZE + PALETTE_SIZE + ACCENT_SLOT
            for start in FADE_GROUP_STARTS for step in range(FADE_STEPS_PER_GROUP)]
    return palette, fade


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("source", ["MVP baseline", "2nd Quest"])
def test_only_the_selectors_and_the_marks_colors_change(source: str, seed: int) -> None:
    on, off = roms(SOURCES[source], seed)
    changed = [offset for offset, (a, b) in enumerate(zip(on, off, strict=True)) if a != b]
    assert changed, "no room changed"
    assert all((on[offset] ^ off[offset]) & ~INNER_PALETTE_BITS == 0
               for offset in changed if offset in TABLE_B_OFFSETS)
    # everything else that differs is a level's palette bytes: parsed, only the marks' color bytes differ
    world_on, world_off = parse_rom(on), parse_rom(off)
    palette_offsets, fade_offsets = mark_offsets()
    for level_on, level_off in zip(world_on.levels, world_off.levels, strict=True):
        palette_on, fade_on = level_on.color_sets
        palette_off, fade_off = level_off.color_sets
        differing = {i for i, (a, b) in enumerate(zip(palette_on, palette_off, strict=True)) if a != b}
        assert differing <= set(palette_offsets)
        assert {i for i, (a, b) in enumerate(zip(fade_on, fade_off, strict=True)) if a != b} <= set(fade_offsets)
        for room_on, room_off in zip(level_on.rooms, level_off.rooms, strict=True):
            assert replace(room_on, palette_1=room_off.palette_1) == room_off
    unexplained = set(changed) - TABLE_B_OFFSETS - SEED_CODE_OFFSETS
    assert len(unexplained) <= len(world_on.levels) * (len(palette_offsets) + len(fade_offsets))


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("source", ["MVP baseline", "1st Quest", "2nd Quest"])
def test_every_levels_palette_3_carries_the_no_drop_color(source: str, seed: int) -> None:
    """The red as palette 3's color 1, in the palette and in every step of both fade groups (each
    one brightness row darker, black at the bottom); palette 2, which a room that can drop keeps,
    and the rest of palette 3 are as the level has them."""
    on, off = roms(SOURCES[source], seed)
    for level_on, level_off in zip(parse_rom(on).levels, parse_rom(off).levels, strict=True):
        palette, fade = level_on.color_sets
        palette_before, fade_before = level_off.color_sets
        start = MARKED_PALETTE * PALETTE_SIZE
        assert palette[start + ACCENT_SLOT] == NO_DROP_COLOR
        assert palette[:start] == palette_before[:start], "an earlier palette changed (palette 2 is the level's own)"
        assert palette[start:start + ACCENT_SLOT] == palette_before[start:start + ACCENT_SLOT]
        assert palette[start + ACCENT_SLOT + 1:] == palette_before[start + ACCENT_SLOT + 1:]
        _, fade_offsets = mark_offsets()
        for number, offset in enumerate(fade_offsets):
            assert fade[offset] == darker(NO_DROP_COLOR, number % FADE_STEPS_PER_GROUP)
        assert fade[fade_offsets[FADE_STEPS_PER_GROUP - 1]] == BLACK
        changed = {i for i, (a, b) in enumerate(zip(fade, fade_before, strict=True)) if a != b}
        assert changed <= set(fade_offsets)


def check_rooms(on: bytes, off: bytes, open_stairs_removed: bool) -> Audit:
    """Every room on 2 or 3 follows the rule, whatever its layout (a vanilla moat on palette 3 too);
    every other room keeps its selector; no item in a marked room."""
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
def test_every_room_on_palette_2_or_3_follows_the_rule(source: str, seed: int) -> None:
    result = check_rooms(*roms(SOURCES[source], seed), open_stairs_removed=False)
    assert result.shown and not result.holding


WATER_LAYOUTS = frozenset({0x0B, *range(0x12, 0x1A)})      # the layouts that draw water (the doc's section 5)


@pytest.mark.parametrize("seed", QUICK_SEEDS)
@pytest.mark.parametrize("source", ["MVP baseline", "1st Quest", "2nd Quest"])
def test_water_rooms_are_red_only_when_they_cannot_drop(source: str, seed: int) -> None:
    """A water room on palette 3 shows the red, on palette 2 the level's block-face color: it takes
    3 exactly when the rule marks it, and the flag-off ROM's vanilla moats (palette 3) lose their
    water color when they can drop."""
    on, off = roms(SOURCES[source], seed)
    world_on, world_off = parse_rom(on), parse_rom(off)
    before = {(level.level_num, room.room_num): room.palette_1 for level in world_off.levels for room in level.rooms}
    seen = Counter[bool]()
    for level_num, room, no_drop in level_rooms(world_on):
        if room.layout_code & LAYOUT_ID_MASK in WATER_LAYOUTS and before[level_num, room.room_num] in (2, 3):
            seen[no_drop] += 1
            assert room.palette_1 == (MARKED_PALETTE if no_drop else UNMARKED_PALETTE), (level_num, room.room_num)
    assert sum(seen.values()), "no water room on palette 2 or 3"


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
# The marks shown per seed, every room on palette 2 or 3 now (measured 2026-10-24, 24 seeds each;
# the doc's block-room figures were 40.1, 26.3 and 40.5).
SHOWN_PER_SEED = {"MVP baseline": 50.6, "1st Quest": 35.8, "2nd Quest": 51.0}
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

