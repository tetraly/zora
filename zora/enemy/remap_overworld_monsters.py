"""Shuffle overworld enemy placements among screens.

Redistributes which enemy types appear on which overworld screens by
performing a constrained Fisher-Yates shuffle. Certain enemies are
excluded from specific screens to prevent gameplay issues:

- Blue Moblins cannot be placed on screens requiring the Power Bracelet
  (they would block access before the player has the bracelet).
- Peahats cannot be placed on screens 63 or 85 (raft landing and
  a narrow passage where Peahats' movement pattern causes problems).
- Leevers cannot be placed on screen 7 (a beach screen where their
  sand-spawning behavior conflicts with the terrain).

Screens with no enemies, Ghini screens, and Fairy screens are excluded
from the shuffle entirely (their placements are fixed).

Ported from RemapOverworldMonsters.cs.
"""

from __future__ import annotations

from zora.data_model import (
    Enemy,
    EnemySpec,
    EntranceType,
    GameWorld,
    Screen,
    SCREEN_ENTRANCE_TYPES,
)
from zora.rng import Rng


_MAX_SHUFFLE_ATTEMPTS = 1000

_BAD_FOR_PEAHAT_SCREENS: frozenset[int] = frozenset({63, 85})

_BAD_FOR_LEEVER_SCREEN = 7

_LEEVER_MIXED_GROUPS: frozenset[Enemy] = frozenset({
    Enemy.MIXED_ENEMY_GROUP_5,
    Enemy.MIXED_ENEMY_GROUP_6,
})


def _needs_bracelet(screen_num: int) -> bool:
    entrance = SCREEN_ENTRANCE_TYPES.get(screen_num)
    return entrance in (EntranceType.POWER_BRACELET, EntranceType.POWER_BRACELET_AND_BOMB)


def _has_enemy(spec: EnemySpec, target: Enemy) -> bool:
    """Check if an enemy spec (direct or mixed group) contains the target."""
    if not spec.is_group:
        return spec.enemy == target
    if spec.group_members is not None:
        return target in spec.group_members
    return False


def _is_blue_moblin(spec: EnemySpec) -> bool:
    return _has_enemy(spec, Enemy.BLUE_MOBLIN)


def _is_peahat(spec: EnemySpec) -> bool:
    return _has_enemy(spec, Enemy.PEAHAT)


def _is_leever(spec: EnemySpec) -> bool:
    """Check if the enemy spec contains a Leever.

    The original checks enemy == RED_LEEVER for non-groups, and for
    groups checks two specific mixed group codes (0x26 and 0x27, which
    become MIXED_ENEMY_GROUP_5 and _6) rather than doing a ROM lookup.
    We check group_members for any Leever variant to be safe.
    """
    if not spec.is_group:
        return spec.enemy in (Enemy.RED_LEEVER, Enemy.BLUE_LEEVER)
    if spec.group_members is not None:
        return (Enemy.RED_LEEVER in spec.group_members
                or Enemy.BLUE_LEEVER in spec.group_members)
    return spec.enemy in _LEEVER_MIXED_GROUPS


def _is_excluded(screen: Screen) -> bool:
    """Screens excluded from the shuffle: no enemy, Ghini, or Fairy."""
    enemy = screen.enemy_spec.enemy
    if enemy == Enemy.NOTHING:
        return True
    if not screen.enemy_spec.is_group:
        if enemy == Enemy.GHINI_1:
            return True
        if enemy == Enemy.FAIRY:
            return True
    return False


def _violates_constraints(
    spec: EnemySpec,
    dest_screen_num: int,
) -> bool:
    """Check if placing this enemy spec on the given screen violates any constraint."""
    if _is_blue_moblin(spec) and _needs_bracelet(dest_screen_num):
        return True
    if _is_peahat(spec) and dest_screen_num in _BAD_FOR_PEAHAT_SCREENS:
        return True
    if _is_leever(spec) and dest_screen_num == _BAD_FOR_LEEVER_SCREEN:
        return True
    return False


def remap_overworld_monsters(world: GameWorld, rng: Rng) -> None:
    """Shuffle overworld enemy assignments among eligible screens.

    Performs a Fisher-Yates shuffle on the (enemy_spec, enemy_quantity)
    pairs of eligible overworld screens, with constraint-based retry
    on each swap step.
    """
    screens = world.overworld.screens

    candidates: list[int] = []
    for i, screen in enumerate(screens):
        if not _is_excluded(screen):
            candidates.append(i)

    specs: list[EnemySpec] = [screens[i].enemy_spec for i in candidates]
    quantities: list[int] = [screens[i].enemy_quantity for i in candidates]

    count = len(candidates)
    for i in range(count):
        remaining = count - i

        placed = False
        for _attempt in range(_MAX_SHUFFLE_ATTEMPTS):
            j = i + int(rng.random() * remaining)

            if _violates_constraints(specs[i], screens[candidates[j]].screen_num):
                continue
            if _violates_constraints(specs[j], screens[candidates[i]].screen_num):
                continue

            specs[i], specs[j] = specs[j], specs[i]
            quantities[i], quantities[j] = quantities[j], quantities[i]
            placed = True
            break

        if not placed:
            pass

    for idx, screen_idx in enumerate(candidates):
        screens[screen_idx].enemy_spec = specs[idx]
        screens[screen_idx].enemy_quantity = quantities[idx]
