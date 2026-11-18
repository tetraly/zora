"""The owner's level-9 rule (2026-11-16): level 9 holds a bomb dropper a player reaches without
bombs. Only the drop table's row with bombs counts (class C: change_enemy_hp.bomb_droppers); an
attempt without one is redrawn (generation_pass.check_level_9_bomb_droppers_step).

The seeds are pinned on the flags of the report that found it (Hint Type: Helpful, Item Shuffle
within each dungeon, Shuffle Level 9 Monsters on): 3268821545 is the report's, whose level 9 held
only Red Lynels (no bombs) and those behind two bomb walls; 41, 668 and 775 held no bomb dropper
at all before the rule."""
from __future__ import annotations

from functools import cache

import pytest

from tests.needs import needs_base_rom, needs_encoder
from zora.generate.pipeline import Built, build, plan
from zora.generate.steps.change_enemy_hp import (
    MixedLists,
    level_9_bomb_droppers_without_bombs,
)
from zora.rom.base_rom import remember_repo_base_rom

pytestmark = [needs_base_rom, needs_encoder]
FLAGS = "143oNtDD4PAvB!U8nSk4yS8L09lgT10vRVe7sx"
ZORA_FLAGS = "10.J2EkcYg"
SEEDS = (3268821545, 41, 668, 775)


@cache
def _built(seed: int) -> Built:
    return build(plan(FLAGS, seed, ZORA_FLAGS), remember_repo_base_rom())


@pytest.mark.parametrize("seed", SEEDS)
def test_level_9_has_a_bomb_dropper_reached_without_bombs(seed: int) -> None:
    built = _built(seed)
    world = built.world
    assert level_9_bomb_droppers_without_bombs(world.levels, MixedLists.of(world), world.enemy_drop_classes)
    # each of these seeds' first accepted layout had none: the rule redrew it at least once
    assert built.result.acceptance_rejections["level 9 bombs"] >= 1

