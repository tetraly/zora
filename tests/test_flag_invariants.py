"""Flag-combination invariants: properties every generated ROM must have
under ANY option values, checked over a sampled set of combinations (not
the full cross product) and 3 fixed seeds each.

Combinations: the Consternation preset (ZORA's defaults; there is no
separate preset object), each implemented option at its non-default value
on top of the preset, and an all-pairs set over the implemented options.
Blocked options (shapes.options.BLOCKED_OPTIONS, game_config.BLOCKED_CONFIG)
cannot be set away from their defaults: construction raises
NotImplementedError naming what each waits on. They are left out of the
combinations and tested for that error instead.

The combination and default-equivalence suites are marked `slow` and are
skipped by the default run; run them with `python3 -m pytest -m slow -n auto`.
One preset seed runs by default as a smoke test.
"""
import os
import re
from collections import Counter
from collections.abc import Iterator
from dataclasses import dataclass, fields, replace
from functools import cache
from itertools import combinations, product
from pathlib import Path
from typing import Any

import pytest

from zora.rom.base_rom import BASE_ROM_PATH, verify_base_rom
from zora_measure.checkpoints.summaries import POOL_ITEMS
from zora_measure.checks import Check, CheckResult, finished_rom_checks
from zora.model.enums import Destination, Enemy, Item
from zora.model.overworld import ItemCave, Shop
from zora.model.game_world import GameWorld
from zora.rom.game_config import BLOCKED_CONFIG, DungeonNothingCode, GameConfig, HintMode
from zora.rom.parse.rom_file import load_rom, parse_rom
from zora.rom.serialize.rom_file import serialize_to_rom
from zora.generate.rng import Rng
from zora.rom.layout import ines_header
from zora.flags.fields import CaveShuffle, DungeonLayoutSource, HitPointChange, ItemShuffleScope, WoodenSwordState
from zora.flags.zora_flags import OopsAllBosses, OopsAllEnemies
from zora.generate.alternative_values import AlternativeValues
from zora.generate.extra_options import ExtraOptions
from zora.generate.flag_steps import FlagSteps
from zora.generate.generation_pass import generate_shapes
from zora.generate.shapes.options import BLOCKED_OPTIONS, ShapeOptions
from zora_measure.statistics import special_cave_items

SEEDS = (101, 202, 303)

# PS-ITEM-02: nine heart containers take part in every finished ROM
# (dungeon tables + the three special-cave slots), with or without B1.
HEART_CONTAINERS_PER_ROM = 9
TRIFORCE_LEVELS = range(1, 9)


@dataclass(frozen=True)
class Flags:
    """One option combination: the shape options, the post-shapes switch
    and the serialization config. Defaults are the Consternation preset."""
    shapes: ShapeOptions = ShapeOptions()
    post_shapes: bool = True
    steps: FlagSteps = FlagSteps()       # the flag-switched steps (FL-OFF)
    extras: ExtraOptions = ExtraOptions()  # the ZORA extras (docs/zora-extras.md)
    alternatives: AlternativeValues = AlternativeValues()   # the alternative values (FL-ALT)
    # The hint style every flag string produces (zora.generate.pipeline.HINT_STYLE_MODES):
    # GameConfig's own default writes the composed texts into the vanilla
    # bank, which the hint pool's wording can overflow.
    config: GameConfig = GameConfig(hint_mode=HintMode.CONSTERNATION)

    def label(self) -> str:
        changed = [f"{name}={getattr(value, 'name', value)}"
                   for name, value in _non_defaults(self)]
        changed += [f"{name}=off" for name in TURN_OFF_STEPS if not option_value(self, name)]
        return ",".join(changed) or "preset"


PRESET = Flags()

# Implemented options and their non-default values. Each entry sets one
# option on a Flags value.
IMPLEMENTED: dict[str, tuple[Any, ...]] = {
    "sort_shapes": (True, False),
    "second_quest_rooms": (True, False),
    "second_quest_monsters": (False, True),
    "universal_drops": (False, True),
    "start_room_swap": (False, True),             # B26: SH-GRID-02, SH-ENT-01 and PS-START
    "post_shapes": (True, False),
    "dungeon_nothing_code": (DungeonNothingCode.VANILLA, DungeonNothingCode.ZORA_REMAP),
    "features_b10": (False, True),
    "randomize_magical_sword": (False, True),
    "randomize_letter": (False, True),
    "progressive_items": (False, True),
    "shop_items_in_pool": (False, True),
    "starting_hearts": (3, 4, 1, 5, 16),                       # FL-ALT-02, FL-ALT-07
    "white_sword_hearts": (range(4, 7), range(5, 7), range(4, 6), range(6, 7), range(4, 5)),   # FL-ALT-05
    "generate_community_hint_text": (False, True),
    "show_every_helpful_hint": (False, True),
    "important_items_in_level_9": (False, True),
    "remove_most_open_stairs": (False, True),        # B30: PS-OSTAIR
    "book_to_understand_npcs": (False, True),     # B48: HT-BOOK-01 (GameConfig) and HT-BOOK-02
    # C06: full (the baseline), within each dungeon (PS-ITW), Item Only (PS-ITEM-09), None (PS-ITEM-10)
    "item_shuffle": (ItemShuffleScope.FULL, ItemShuffleScope.WITHIN_EACH_DUNGEON,
                     ItemShuffleScope.DUNGEON_ITEMS_ONLY, ItemShuffleScope.NONE),
    "mix_overworld_quest": (False, True),
    "full_start_shuffle": (False, True),
    "start_on_wood_sword_screen": (False, True),
    "mix_overworld_quest_second_variant": (False, True),
    "second_quest_overworld": (False, True),
    "force_overworld_block": (False, True),
    "wood_sword_cave_behind_blocks": (False, True),
    "dungeon_quest": (DungeonLayoutSource.GENERATED_SHAPES, DungeonLayoutSource.FIRST_QUEST,
                      DungeonLayoutSource.SECOND_QUEST, DungeonLayoutSource.MIXED,
                      DungeonLayoutSource.MIXED_WITH_SHAPES),
    # FP-START-02: none, or a set that widens B03's cave screens (FP-START-04) and fills other slots
    "start_items": ((), (Item.BOMBS, Item.RECORDER, Item.RAFT, Item.POWER_BRACELET, Item.LETTER),
                    # the d8cf117 export's: the better of each pair, the Ladder (OW-CAVE-07) and the Book
                    (Item.MAGICAL_SWORD, Item.SILVER_ARROWS, Item.BOW, Item.RED_CANDLE, Item.WAND, Item.BOOK,
                     Item.RED_RING, Item.LADDER, Item.MAGICAL_KEY, Item.MAGICAL_SHIELD)),
    # Oops All Enemies and Oops All Bosses (docs/design/oops-all.md)
    "oops_all_enemies": tuple(OopsAllEnemies),
    "oops_all_bosses": tuple(OopsAllBosses),
    # The ZORA 1.0 flags (docs/zora-extras.md section 13)
    "allow_triforces_in_stairways": (False, True),
    "shuffle_wood_sword": (False, True),
    # Expanded Dungeon Locations (docs/zora-extras.md section 15): a 1st Quest overworld only, with
    # Dungeons Only or All Caves (producible)
    "expanded_dungeon_locations": (False, True),
    # Highlight No-Drop Rooms (docs/zora-extras.md section 16): inert with B91 on
    "highlight_no_drop_rooms": (False, True),
    # C05, OW-CAVE-09: the walk's parts
    "cave_shuffle": (CaveShuffle.ALL_CAVES, CaveShuffle.VANILLA, CaveShuffle.DUNGEON_DOORS_ONLY,
                     CaveShuffle.NON_DUNGEON_CAVES_ONLY),
    # The November tournament's settings (2026-10-17 export): C09 and C10's walks and zero
    # (PS-HP-01, PS-HP-02, PS-HP-04, PS-HP-05), B41 (PS-HP-06), B52 and B53 (FP-BEAM-01, FP-OHKO-01)
    "enemy_hit_points": (HitPointChange.UP_TO_2, HitPointChange.UP_TO_4, HitPointChange.ALL_ZERO),
    "boss_hit_points": (HitPointChange.UP_TO_2, HitPointChange.UP_TO_4, HitPointChange.ALL_ZERO),
    "ganon_hit_points_zero": (False, True),
    "permanent_sword_beam": (False, True),
    "one_hit_knock_out": (False, True),
    # Add Bridges to the River (B87, FP-BRIDGE-01) and Add Lost Woods Shortcut (B88, FP-WOODS-01)
    "river_bridges": (False, True),
    "lost_woods_shortcut": (False, True),
    "start_triforce_pieces": (0, 0b00100001, 0xFF),                             # FL-ALT-06
    # PS-ITEM-12: the Book at the Armos slot, a heart container in the white-sword cave, Non-Heart
    "armos_pin": (0, 1, 16),
    "white_sword_pin": (0, 4, 16),
    "level_9_pins": ((0, 0), (16, 16), (7, 2)),
    # FP-WOOD-01 to FP-WOOD-04: the four wooden-sword states
    "wooden_sword_state": tuple(state for state in WoodenSwordState if state is not WoodenSwordState.RANDOM),
}
# FL-OFF-07's turn-off values: each flag-switched step off on the preset (with
# the feature switch on, as every flag string has it), and all of them off.
# Not in IMPLEMENTED: all-pairs walks the whole cross product.
TURN_OFF_STEPS = (*(f.name for f in fields(FlagSteps)), "book_is_an_atlas")
SHAPE_FIELDS = {f.name for f in fields(ShapeOptions)}
EXTRA_FIELDS = {f.name for f in fields(ExtraOptions)}
ALTERNATIVE_FIELDS = {f.name for f in fields(AlternativeValues)}
# The ZORA extras' caves: an item the extras move there is still placed once.
EXTRA_CAVES = (Destination.MAGICAL_SWORD_CAVE, Destination.LETTER_CAVE, Destination.WOOD_SWORD_CAVE)
CONFIG_FIELDS = {f.name for f in fields(GameConfig)}
STEP_FIELDS = {f.name for f in fields(FlagSteps)}


def with_option(flags: Flags, name: str, value: Any) -> Flags:
    if name in SHAPE_FIELDS:
        return replace(flags, shapes=replace(flags.shapes, **{name: value}))
    if name in STEP_FIELDS:
        return replace(flags, steps=replace(flags.steps, **{name: value}))
    if name in EXTRA_FIELDS:
        return replace(flags, extras=replace(flags.extras, **{name: value}))
    if name in ALTERNATIVE_FIELDS:
        # A value with a generation side and a ROM side (B48) sets both
        config = replace(flags.config, **{name: value}) if name in CONFIG_FIELDS else flags.config
        return replace(flags, alternatives=replace(flags.alternatives, **{name: value}), config=config)
    if name in CONFIG_FIELDS:
        return replace(flags, config=replace(flags.config, **{name: value}))
    return replace(flags, **{name: value})


def option_value(flags: Flags, name: str) -> Any:
    if name in SHAPE_FIELDS:
        return getattr(flags.shapes, name)
    if name in STEP_FIELDS:
        return getattr(flags.steps, name)
    if name in EXTRA_FIELDS:
        return getattr(flags.extras, name)
    if name in ALTERNATIVE_FIELDS:
        return getattr(flags.alternatives, name)
    if name in CONFIG_FIELDS:
        return getattr(flags.config, name)
    return getattr(flags, name)


def _non_defaults(flags: Flags) -> Iterator[tuple[str, Any]]:
    for name in IMPLEMENTED:
        value = option_value(flags, name)
        if value != option_value(PRESET, name):
            yield name, value


def one_at_a_time() -> list[Flags]:
    """Each implemented option at each non-default value, on the preset."""
    return [with_option(PRESET, name, value)
            for name, values in IMPLEMENTED.items()
            for value in values if value != option_value(PRESET, name)]


def all_pairs() -> list[Flags]:
    """A greedy all-pairs covering set: every value pair of every two implemented options appears
    in at least one combination.

    Each combination starts from the first pair not yet covered (options in IMPLEMENTED order,
    values in their listed order) and gives every other option the value that covers the most
    uncovered pairs with the options already set, ties keeping the first. It never builds the
    cross product, which doubles with each switch (2^20 at 20 options). Deterministic."""
    names = list(IMPLEMENTED)
    order = {name: index for index, name in enumerate(names)}
    uncovered = {((a, ia), (b, ib))
                 for a, b in combinations(names, 2)
                 for ia in range(len(IMPLEMENTED[a])) for ib in range(len(IMPLEMENTED[b]))}

    def first_pair() -> tuple[tuple[str, int], tuple[str, int]]:
        return min(uncovered, key=lambda pair: (order[pair[0][0]], order[pair[1][0]], pair[0][1], pair[1][1]))

    chosen: list[Flags] = []
    while uncovered:
        (a, ia), (b, ib) = first_pair()
        candidate = {a: ia, b: ib}
        for name in names:
            if name in candidate:
                continue
            gains = [sum(((other, index), (name, value)) in uncovered if order[other] < order[name]
                         else ((name, value), (other, index)) in uncovered
                         for other, index in candidate.items())
                     for value in range(len(IMPLEMENTED[name]))]
            candidate[name] = gains.index(max(gains))
        uncovered -= {((x, candidate[x]), (y, candidate[y])) for x, y in combinations(names, 2)}
        flags = PRESET
        for name in names:
            flags = with_option(flags, name, IMPLEMENTED[name][candidate[name]])
        chosen.append(flags)
    return chosen


def turned_off() -> list[Flags]:
    """Each flag-switched step off, then all of them (FL-OFF-01: they combine freely)."""
    featured = with_option(PRESET, "features_b10", True)
    every_off = featured
    out = []
    for name in TURN_OFF_STEPS:
        out.append(with_option(featured, name, False))
        every_off = with_option(every_off, name, False)
    return [*out, every_off]


def producible(flags: Flags) -> bool:
    """Not every combination is one a flag string makes: every Dungeon Quest value runs the
    post-shapes passes (PS-VAN-01), and Mixed + Shapes without them would leave a shapes set's
    shape-stage items beside a vanilla set's own (two wands, say), as Mixed Quest would leave one
    quest's levels 1-6 beside the other's levels 7-9 (PS-VAN-03: the wand twice and no Book). 1st
    and 2nd Quest without them keep their quest's items, so they stay as a test of the vanilla
    sets alone.

    Nor does a flag string make shaped dungeons with the start-room swap (B26) but without the
    post-shapes passes: the swap is half done. The shape stage draws entrances off the bottom
    row (SH-GRID-02, SH-ENT-01) with the south side open onto another level, and only PS-START,
    a post-shapes pass, moves each start room to the level's edge. The shape-stage test modes
    (metrics, compare_corpus, output_hash) run without the swap. Vanilla sets place no shaped
    entrances, so the swap changes nothing there and those combinations stay.

    Nor does a flag string make Expanded Dungeon Locations with a Mixed overworld quest or a Cave
    Shuffle but Dungeons Only or All Caves (refused, zora_flags.expanded_dungeon_locations_conflicts)."""
    if flags.extras.expanded_dungeon_locations and (
            flags.alternatives.mix_overworld_quest or flags.alternatives.mix_overworld_quest_second_variant
            or flags.alternatives.cave_shuffle not in (CaveShuffle.DUNGEON_DOORS_ONLY, CaveShuffle.ALL_CAVES)):
        return False
    if flags.post_shapes:
        return True
    if flags.alternatives.dungeon_quest in (DungeonLayoutSource.MIXED, DungeonLayoutSource.MIXED_WITH_SHAPES):
        return False
    return not (flags.shapes.start_room_swap
                and flags.alternatives.dungeon_quest is DungeonLayoutSource.GENERATED_SHAPES)


def sampled_combinations() -> list[Flags]:
    """Preset, one-at-a-time, all-pairs and the turn-offs, without duplicates, the ones a flag
    string can make (producible)."""
    out: list[Flags] = []
    for flags in [PRESET, *one_at_a_time(), *all_pairs(), *turned_off()]:
        if flags not in out and producible(flags):
            out.append(flags)
    return out


# --- generation ----------------------------------------------------------------------

def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("needs the base ROM")
    # The PRG0 hash guard: refuses any other input ROM.
    verify_base_rom(cand)
    return load_rom(cand)


@cache
def vanilla_rom() -> bytes:
    return _vanilla_rom()


def serialization_config(flags: Flags) -> GameConfig:
    """The config a ROM is written and read with: Randomize Magical Sword brings its "no item"
    remap, as generate.plan sets it, whatever the combination's own nothing code; the start-room
    swap brings the B10 patches; the
    progressive items' flags choose their patches (PI-CODE-01)."""
    config = replace(flags.config, progressive_items=flags.extras.progressive_items,
                     shop_items_in_pool=flags.extras.shop_items_in_pool)
    if flags.shapes.start_room_swap:
        # B26's arrival codes and exit rooms (PS-START-03) are B10 data, which every flag string has
        config = replace(config, features_b10=True)
    if flags.extras.randomize_magical_sword:
        return replace(config, dungeon_nothing_code=DungeonNothingCode.ZORA_REMAP)
    return config


def generate(flags: Flags, seed: int) -> bytes:
    rom = vanilla_rom()
    world = parse_rom(rom)
    generate_shapes(world, Rng(seed), flags.shapes, post_shapes=flags.post_shapes,
                    feature_data=flags.config.features_b10, seed=seed, steps=flags.steps, extras=flags.extras,
                    alternatives=flags.alternatives)
    return serialize_to_rom(world, rom, config=serialization_config(flags))


@cache
def generate_cached(flags: Flags, seed: int) -> bytes:
    return generate(flags, seed)


# --- invariants ----------------------------------------------------------------------

def level_checks(flags: Flags) -> tuple[Check, ...]:
    """The zora_measure.checks checks a finished ROM must pass under these flags
    (sorted numbering only with sort_shapes; the rules B1 moves only
    without B1; the shape stage's rules only for shaped dungeons)."""
    return finished_rom_checks(sort_shapes=flags.shapes.sort_shapes, post_shapes=flags.post_shapes,
                               shaped=flags.alternatives.dungeon_quest is DungeonLayoutSource.GENERATED_SHAPES,
                               start_rooms_moved=flags.shapes.start_room_swap)


def run_level_checks(world: GameWorld, flags: Flags) -> list[CheckResult]:
    """Like checks.run_checks: a check that raises is reported as failed,
    so one broken level does not hide the other invariants."""
    results = []
    for check in level_checks(flags):
        try:
            results.append(check(world))
        except Exception as exc:
            results.append(CheckResult("EXC:" + check.__name__, False, repr(exc)[:120]))
    return results


def levels_do_not_overlap(world: GameWorld) -> list[str]:
    problems = []
    for block_index, block in enumerate(world.level_blocks):
        owners = Counter(room_num for level in block.levels for room_num in level.room_nums)
        problems += [f"block {block_index}: room {room_num:02X} owned {count} times"
                     for room_num, count in owners.items() if count > 1]
    return problems




def item_problems(world: GameWorld, flags: Flags) -> list[str]:
    """Item integrity from PS-ITEM-01/02 and SH-ROOM-01."""
    dungeon = [room.item for block in world.level_blocks for room in block.rooms]
    dungeon += [stair.item for block in world.level_blocks for stair in block.staircases
                if stair.item is not None]
    extra_caves = [world.overworld.get_cave(destination, ItemCave) for destination in EXTRA_CAVES]
    # Shop Items in the Item Pool may put a pool item in a shop ware (SI-JOIN-01).
    shop_wares = [ware.item for cave in world.overworld.caves if isinstance(cave, Shop) for ware in cave.items]
    everywhere = Counter(dungeon + special_cave_items(world) + [cave.item for cave in extra_caves if cave]
                         + shop_wares)
    problems = [f"{item.name} placed {everywhere[item]} times"
                for item in POOL_ITEMS if everywhere[item] != 1]
    hearts = everywhere[Item.HEART_CONTAINER]
    if hearts != HEART_CONTAINERS_PER_ROM:
        problems.append(f"{hearts} heart containers")
    for level in world.levels:
        triforces = sum(room.item == Item.TRIFORCE for room in level.rooms)
        triforces += sum(stair.item == Item.TRIFORCE for stair in level.staircase_rooms)
        expected = 1 if level.level_num in TRIFORCE_LEVELS else 0
        if triforces != expected:
            problems.append(f"level {level.level_num}: {triforces} triforces")
    # PS-GRUM-02: B1 replaces the grumble room with exactly one hungry goriya, in the levels 7-9
    # set. PS-VAN-02: a vanilla set keeps its quest's own: first-quest level 7's room $28,
    # second-quest level 7's room $2F, and with second-quest levels 1-6 also level 2's room $25
    # (measured: 60 seeds of Mixed + Shapes, every source pair).
    if flags.post_shapes:
        goriyas = sum(room.enemy == Enemy.HUNGRY_GORIYA
                      for block in world.level_blocks for room in block.rooms)
        expected = 1 + (world.levels[0].block is world.blocks_2q[0])
        if goriyas != expected:
            problems.append(f"{goriyas} hungry goriya rooms")
    return problems


def invariant_failures(flags: Flags, seed: int) -> list[str]:
    """Every invariant that breaks for this combination and seed."""
    rom = vanilla_rom()
    try:
        out = generate_cached(flags, seed)
    except Exception as exc:  # generation must finish within its retry budget
        return [f"generation: {exc!r}"]
    failures = []
    if len(out) != len(rom):
        failures.append(f"size {len(out)} != {len(rom)}")
    if ines_header(out) != ines_header(rom):
        failures.append("iNES header changed")
    config = serialization_config(flags)
    world = parse_rom(out, config=config)
    if serialize_to_rom(world, out, config=config) != out:
        failures.append("round trip not byte-identical")
    failures += [f"{r.check_id}: {r.message}" for r in run_level_checks(world, flags)
                 if not r.passed]
    overlaps = levels_do_not_overlap(world)
    if overlaps:
        failures.append(f"{len(overlaps)} overlapping rooms, first: {overlaps[0]}")
    failures += item_problems(world, flags)
    if generate(flags, seed) != out:
        failures.append("not deterministic")
    return failures


# --- tests ---------------------------------------------------------------------------

def test_sampling_covers_every_pair() -> None:
    combos = all_pairs()
    for a, b in combinations(IMPLEMENTED, 2):
        for va, vb in product(IMPLEMENTED[a], IMPLEMENTED[b]):
            assert any(option_value(f, a) == va and option_value(f, b) == vb
                       for f in combos), (a, va, b, vb)


def test_preset_invariants_smoke() -> None:
    assert invariant_failures(PRESET, SEEDS[0]) == []


@pytest.mark.slow
@pytest.mark.parametrize("flags", sampled_combinations(), ids=Flags.label)
@pytest.mark.parametrize("seed", SEEDS)
def test_invariants(flags: Flags, seed: int) -> None:
    assert invariant_failures(flags, seed) == []


# A non-default value for each blocked option.
BLOCKED_VALUES: dict[str, Any] = {
    "second_quest_doors": True,
    "seed_placement": "adjacent", "relocate_hint_text": True, "relocate_boss_sprites": True,
}


def test_every_blocked_option_has_a_value() -> None:
    assert set(BLOCKED_VALUES) == set(BLOCKED_OPTIONS) | set(BLOCKED_CONFIG)


@pytest.mark.parametrize("name", sorted(BLOCKED_VALUES))
def test_blocked_option_raises(name: str) -> None:
    waits_on = {**BLOCKED_OPTIONS, **BLOCKED_CONFIG}[name]
    options = ShapeOptions if name in SHAPE_FIELDS else GameConfig
    with pytest.raises(NotImplementedError, match=f"^{name}: waits on {re.escape(waits_on)}$"):
        options(**{name: BLOCKED_VALUES[name]})


# The config "unset" stands for: GameConfig's defaults, but the generated hint texts written as
# generated seeds write them (GameConfig's own vanilla bank cannot hold ZORA's wording; Flags.config
# above does the same).
UNSET_CONFIG = GameConfig(hint_mode=HintMode.CONSTERNATION)
# Every option ZORA accepts, implemented or not, with its default.
DEFAULTS: dict[str, Any] = {
    **{f.name: getattr(ShapeOptions(), f.name) for f in fields(ShapeOptions)},
    **{f.name: getattr(UNSET_CONFIG, f.name) for f in fields(GameConfig)},
    "post_shapes": True,
}


def generate_explicit(name: str, value: Any, seed: int) -> bytes:
    """Generate with one option passed explicitly (the others unset)."""
    rom = vanilla_rom()
    world = parse_rom(rom)
    shapes = ShapeOptions(**{name: value}) if name in SHAPE_FIELDS else ShapeOptions()
    if name == "post_shapes":
        generate_shapes(world, Rng(seed), shapes, post_shapes=value)
    else:
        generate_shapes(world, Rng(seed), shapes)
    if name in CONFIG_FIELDS:
        return serialize_to_rom(world, rom, config=replace(UNSET_CONFIG, **{name: value}))
    return serialize_to_rom(world, rom, config=UNSET_CONFIG)


@cache
def generate_unset(seed: int) -> bytes:
    """Every option left unset: no ShapeOptions arguments, no post_shapes, no config."""
    rom = vanilla_rom()
    world = parse_rom(rom)
    generate_shapes(world, Rng(seed), ShapeOptions())
    return serialize_to_rom(world, rom, config=UNSET_CONFIG)


@pytest.mark.slow
@pytest.mark.parametrize("name", sorted(DEFAULTS))
@pytest.mark.parametrize("seed", SEEDS)
def test_default_equals_unset(name: str, seed: int) -> None:
    assert generate_explicit(name, DEFAULTS[name], seed) == generate_unset(seed)
