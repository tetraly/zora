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
    "post_shapes": (True, False),
    "dungeon_nothing_code": (DungeonNothingCode.VANILLA, DungeonNothingCode.ZORA_REMAP),
    "features_b10": (False, True),
    "randomize_magical_sword": (False, True),
    "randomize_letter": (False, True),
    "progressive_items": (False, True),
    "shop_items_in_pool": (False, True),
    "start_with_four_hearts": (False, True),
    "change_sword_hearts_from_five_hearts": (False, True),
    "generate_community_hint_text": (False, True),
}
# FL-OFF-07's turn-off values: each flag-switched step off on the preset (with
# the feature switch on, as every flag string has it), and all of them off.
# Not in IMPLEMENTED: all-pairs walks the whole cross product.
TURN_OFF_STEPS = (*(f.name for f in fields(FlagSteps)), "book_is_an_atlas")
SHAPE_FIELDS = {f.name for f in fields(ShapeOptions)}
EXTRA_FIELDS = {f.name for f in fields(ExtraOptions)}
ALTERNATIVE_FIELDS = {f.name for f in fields(AlternativeValues)}
# The ZORA extras' caves: an item the extras move there is still placed once.
EXTRA_CAVES = (Destination.MAGICAL_SWORD_CAVE, Destination.LETTER_CAVE)
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
        return replace(flags, alternatives=replace(flags.alternatives, **{name: value}))
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
    """A greedy all-pairs covering set: every value pair of every two
    implemented options appears in at least one combination.

    Deterministic: candidates are tried in cross-product order and ties
    keep the first."""
    names = list(IMPLEMENTED)
    uncovered = {((a, va), (b, vb))
                 for a, b in combinations(names, 2)
                 for va in IMPLEMENTED[a] for vb in IMPLEMENTED[b]}
    candidates = [dict(zip(names, values))
                  for values in product(*(IMPLEMENTED[n] for n in names))]
    chosen: list[Flags] = []
    while uncovered:
        def covered(candidate: dict[str, Any]) -> set[Any]:
            return {pair for pair in uncovered
                    if all(candidate[n] == v for n, v in pair)}
        best = max(candidates, key=lambda c: len(covered(c)))
        uncovered -= covered(best)
        flags = PRESET
        for name, value in best.items():
            flags = with_option(flags, name, value)
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


def sampled_combinations() -> list[Flags]:
    """Preset, one-at-a-time, all-pairs and the turn-offs, without duplicates."""
    out: list[Flags] = []
    for flags in [PRESET, *one_at_a_time(), *all_pairs(), *turned_off()]:
        if flags not in out:
            out.append(flags)
    return out


# --- generation ----------------------------------------------------------------------

def _vanilla_rom() -> bytes:
    env = os.environ.get("ZORA_VANILLA_ROM")
    cand = Path(env) if env else BASE_ROM_PATH
    if not cand.exists():
        pytest.skip("vanilla ROM missing")
    # The PRG0 hash guard: refuses any other input ROM.
    verify_base_rom(cand)
    return load_rom(cand)


@cache
def vanilla_rom() -> bytes:
    return _vanilla_rom()


def serialization_config(flags: Flags) -> GameConfig:
    """The config a ROM is written and read with: Randomize Magical Sword brings its "no item"
    remap, as generate.plan sets it, whatever the combination's own nothing code; the
    progressive items' flags choose their patches (PI-CODE-01)."""
    config = replace(flags.config, progressive_items=flags.extras.progressive_items,
                     shop_items_in_pool=flags.extras.shop_items_in_pool)
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
    without B1)."""
    return finished_rom_checks(sort_shapes=flags.shapes.sort_shapes, post_shapes=flags.post_shapes)


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
    for block_index, block in enumerate(world.blocks):
        owners = Counter(room_num for level in block.levels for room_num in level.room_nums)
        problems += [f"block {block_index}: room {room_num:02X} owned {count} times"
                     for room_num, count in owners.items() if count > 1]
    return problems


def item_problems(world: GameWorld, flags: Flags) -> list[str]:
    """Item integrity from PS-ITEM-01/02 and SH-ROOM-01."""
    dungeon = [room.item for block in world.blocks for room in block.rooms]
    dungeon += [stair.item for block in world.blocks for stair in block.staircases
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
    # PS-GRUM-02: B1 replaces the grumble room with exactly one hungry goriya.
    if flags.post_shapes:
        goriyas = sum(room.enemy == Enemy.HUNGRY_GORIYA
                      for block in world.blocks for room in block.rooms)
        if goriyas != 1:
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
    "start_room_swap": True, "second_quest_doors": True, "mixed_quests": True,
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
