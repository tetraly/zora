"""The maze hints never loop (owner request, 2026-10-15; docs/deviations.md): with both mazes randomized,
the cave walk keeps each hint shop off its own maze, but it can leave the Lost Hills' shop (Hint Shop
1) past the Dead Woods while the Dead Woods' shop (Hint Shop 2) is past the Lost Hills, so neither path
can ever be learned. The acceptance check's E1 target holds every randomized maze's hint, so such a
world is rejected (acceptance_check.AcceptanceCheck.collects_everything)."""
from copy import deepcopy
from functools import cache

import pytest

from zora.flags import zora_flags
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.flags.zora_flags import ZoraFlags
from zora.generate.acceptance_check import LEVEL9_ENTRY, AcceptanceCheck
from zora.generate.pipeline import Built, build, extra_options, plan
from zora.generate.steps import overworld_gates as gates
from zora.generate.steps.cave_entries import DUNGEONS, CaveShuffle, Entry
from zora.model.enums import Destination, Item
from zora.rom.base_rom import BASE_ROM_PATH, remember_repo_base_rom

pytestmark = pytest.mark.skipif(not BASE_ROM_PATH.exists(), reason="needs the base ROM")

MAZES = zora_flags.encode(ZoraFlags(randomize_lost_hills=ThreeState.ON, randomize_dead_woods=ThreeState.ON))
SEEDS = range(1, 21)
# Codes a moved hint shop may trade places with: a cave no tracked place or level entry depends on
HARMLESS = frozenset({Destination.DOOR_REPAIR, Destination.MEDIUM_SECRET, Destination.LARGE_SECRET,
                      Destination.SMALL_SECRET, Destination.MONEY_MAKING_GAME, Destination.HINT_SHOP_1,
                      Destination.HINT_SHOP_2})


@cache
def built(seed: int) -> Built:
    return build(plan(MVP_BASELINE_LEVEL_ENCODING_OFF, seed, MAZES), remember_repo_base_rom())


def checker(seed: int, caves: CaveShuffle) -> AcceptanceCheck:
    world = built(seed)
    assert world.result.item_shuffle_result is not None
    return AcceptanceCheck(world.world.levels, world.result.item_shuffle_result, world.world.overworld,
                           caves, extra_options(world.plan).logic_rules)


def move_shop(entries: list[Entry], shop: Destination, gated: frozenset[int]) -> bool:
    """Put the shop on a gated screen by exchanging codes with a harmless cave there (or leave it
    there); False when no gated screen holds one."""
    home = next(entry for entry in entries if entry.code == shop)
    if home.screen in gated:
        return True
    partner = next((entry for entry in entries if entry.screen in gated and entry.code in HARMLESS
                    and entry.code not in DUNGEONS), None)
    if partner is None:
        return False
    home.code, partner.code = partner.code, home.code
    return True


def looping_caves(seed: int) -> CaveShuffle | None:
    """The seed's caves with Hint Shop 1 past the Dead Woods and Hint Shop 2 past the Lost Hills."""
    caves = deepcopy(built(seed).result.overworld)
    assert caves is not None
    if not (move_shop(caves.entries, gates.LOST_HILLS_HINT_SHOP, gates.DEAD_WOODS_GATED)
            and move_shop(caves.entries, gates.DEAD_WOODS_HINT_SHOP, gates.LOST_HILLS_GATED)):
        return None
    return caves


def tracked_target(check: AcceptanceCheck) -> set[int]:
    """VA-REJ-07's own target: the wooden sword, level-9 entry and every tracked item type."""
    return {Item.WOOD_SWORD, LEVEL9_ENTRY} | {place.item for place in check.item_shuffle_result.tracked}


@cache
def looping_seed() -> int:
    """The first seed whose looping caves still let the closure collect every tracked item, so the
    loop is the only thing E1 can reject."""
    for seed in SEEDS:
        caves = looping_caves(seed)
        if caves is not None and tracked_target(check := checker(seed, caves)) <= check.closure()[0]:
            return seed
    raise AssertionError(f"no seed in {SEEDS} gives a loop with everything tracked still collected")


def test_the_seeds_own_caves_are_accepted() -> None:
    world = built(looping_seed())
    assert world.result.overworld is not None
    check = checker(looping_seed(), world.result.overworld)
    assert check.collects_everything()
    held = check.closure()[0]
    assert gates.LOST_HILLS_HINT in held and gates.DEAD_WOODS_HINT in held


def test_a_hint_loop_is_rejected() -> None:
    """Both shops past each other's maze: neither hint is ever held, everything tracked still is,
    and E1 rejects the world (without the hints in its target it would accept it)."""
    seed = looping_seed()
    caves = looping_caves(seed)
    assert caves is not None
    doors = {entry.code: entry.screen for entry in caves.entries}
    assert doors[gates.LOST_HILLS_HINT_SHOP] in gates.DEAD_WOODS_GATED
    assert doors[gates.DEAD_WOODS_HINT_SHOP] in gates.LOST_HILLS_GATED
    check = checker(seed, caves)
    held = check.closure()[0]
    assert gates.LOST_HILLS_HINT not in held and gates.DEAD_WOODS_HINT not in held
    assert tracked_target(check) <= held
    assert not check.collects_everything()


def test_one_shop_past_the_other_maze_is_no_loop() -> None:
    """Hint Shop 2 past the Lost Hills alone (Hint Shop 1 outside both mazes) is no loop: both hints
    are learned and E1 accepts."""
    seed = looping_seed()
    caves = deepcopy(built(seed).result.overworld)
    assert caves is not None
    lost_hills_shop = next(entry for entry in caves.entries if entry.code == gates.LOST_HILLS_HINT_SHOP)
    if lost_hills_shop.screen in gates.DEAD_WOODS_GATED:
        outside = next(entry for entry in caves.entries if entry.code in HARMLESS - {gates.DEAD_WOODS_HINT_SHOP}
                       and entry.screen not in gates.DEAD_WOODS_GATED | gates.LOST_HILLS_GATED
                       | gates.DEAD_WOODS_WEST)
        lost_hills_shop.code, outside.code = outside.code, lost_hills_shop.code
    assert move_shop(caves.entries, gates.DEAD_WOODS_HINT_SHOP, gates.LOST_HILLS_GATED)
    check = checker(seed, caves)
    held = check.closure()[0]
    assert gates.LOST_HILLS_HINT in held and gates.DEAD_WOODS_HINT in held
    assert check.collects_everything()
