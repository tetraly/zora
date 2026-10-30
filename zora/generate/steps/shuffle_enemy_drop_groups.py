"""Shuffle Enemy Drop Groups (B38; post-shapes-b8.md PS-EDROP-03): the monster types are re-dealt among
the game's four drop-class lists.

The game finds a killed monster's drop class by looking its object type up in four lists, in this
order: a no-drop list of seven types, class A of six, class B of nine and class C of nine; a type in
none of them is class D. This pass rewrites every slot but the no-drop list's first, in each
generation pass (a restarted pass rewrites them from scratch). The lists live in the world as the 31
types in that order (GameWorld.enemy_drop_classes); the serializer writes them.
"""
from __future__ import annotations

from collections.abc import Sequence

from ...model.enums import Enemy
from ..rng import IntRng
from .shuffle_enemy_groups import EnemyDeal

NO_DROP_SIZE, CLASS_A_SIZE, CLASS_B_SIZE, CLASS_C_SIZE = 7, 6, 9, 9
CLASS_A_START = NO_DROP_SIZE
CLASS_C_START = NO_DROP_SIZE + CLASS_A_SIZE + CLASS_B_SIZE
LIST_SLOTS = CLASS_C_START + CLASS_C_SIZE                 # 31
# The no-drop list's first slot keeps PRG0's type, $5D, which no pass writes
KEPT_NO_DROP_TYPE = 0x5D
DEALT_FROM_SLOT = 2                                      # the no-drop list's slots 2 to 6 and every class's
# Step 2's 38 types: PRG0's 29 listed types other than $5D and $1B, and $02, $05, $0C, $11, $18, $1A,
# $3A, $3B and $41. The first 29 of a uniform order fill the slots from DEALT_FROM_SLOT on; the other
# nine are in no list (class D).
DEALT_TYPES: tuple[int, ...] = (
    *range(Enemy.BLUE_LYNEL, Enemy.DIGDOGGER_SPAWN + 1), Enemy.PEAHAT, Enemy.RED_KEESE, Enemy.DARK_KEESE,
    *range(Enemy.GHINI_1, Enemy.BLUE_WIZZROBE + 1), Enemy.WALLMASTER, Enemy.ROPE, Enemy.STALFOS, Enemy.GIBDO,
    Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA, Enemy.MOLDORM,
)
# Step 3: the twelve Lynels, Moblins, Octoroks, Tektites and Leevers; three different ones go to class
# C's slots 0, 1 and 2
OVERWORLD_TYPES: tuple[int, ...] = (*range(Enemy.BLUE_LYNEL, Enemy.RED_MOBLIN + 1),
                                    *range(Enemy.RED_OCTOROK_1, Enemy.BLUE_OCTOROK_2 + 1),
                                    *range(Enemy.BLUE_TEKTITE, Enemy.RED_LEEVER + 1))
OVERWORLD_PICKS = 3
DUNGEON_GROUPS = (0, 1, 2)
# Step 4's groups with Shuffle Enemy Groups off (B42): PRG0's three dungeon enemy groups
PRG0_DUNGEON_GROUPS: tuple[tuple[int, ...], ...] = (
    (Enemy.BLUE_GORIYA, Enemy.RED_GORIYA, Enemy.WALLMASTER, Enemy.ROPE, Enemy.STALFOS),
    (Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT, Enemy.POLS_VOICE, Enemy.GIBDO),
    (Enemy.VIRE, Enemy.LIKE_LIKE, Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE),
)
# A drawn Vire or Zol is drawn again while the other monster's hit points (the nibble the pair shares
# in ObjectTypeToHpPairs) are above this
SHARED_HIT_POINTS_LIMIT = 4


def dungeon_groups(deal: EnemyDeal | None) -> tuple[tuple[int, ...], ...]:
    """Step 4's three groups: the ones the enemy group pass left (PS-EGRP-01, PS-EGRP-02's partners,
    PS-EGRP-07), or PRG0's with that pass off."""
    if deal is None:
        return PRG0_DUNGEON_GROUPS
    return tuple(tuple(int(enemy) for enemy in deal.members(group)) for group in DUNGEON_GROUPS)


def _bring_into_class_c(lists: list[int], slot: int, enemy_type: int) -> None:
    """Steps 3 and 4: a type already in a slot of the lists exchanges with class C's slot; any other
    is written there, and the type it replaces drops out of the lists (class D)."""
    target = CLASS_C_START + slot
    if enemy_type in lists:
        source = lists.index(enemy_type)
        lists[source], lists[target] = lists[target], lists[source]
    else:
        lists[target] = enemy_type


def _redrawn(enemy_type: int, vire_hit_points: int, zol_hit_points: int) -> bool:
    """Quirk (PS-EDROP-03): each of Vire and Zol reads the other's hit points, as PS-EGRP-01's
    coverage test does."""
    return ((enemy_type == Enemy.VIRE and zol_hit_points > SHARED_HIT_POINTS_LIMIT)
            or (enemy_type == Enemy.ZOL and vire_hit_points > SHARED_HIT_POINTS_LIMIT))


def shuffle_enemy_drop_groups(rng: IntRng, groups: Sequence[Sequence[int]], vire_hit_points: int,
                              zol_hit_points: int) -> tuple[int, ...]:
    """PS-EDROP-03 steps 1 to 4: the 31 list slots (no-drop, A, B, C) in order. Under Maximum Enemy
    Health (B45) neither Vire nor Zol is ever drawn: both nibbles are above the limit."""
    dealt = list(DEALT_TYPES)
    rng.shuffle(dealt)
    # Step 1: blue Keese never drops (step 2 never places it)
    lists = [KEPT_NO_DROP_TYPE, Enemy.BLUE_KEESE, *dealt[:LIST_SLOTS - DEALT_FROM_SLOT]]
    remaining = list(OVERWORLD_TYPES)
    for slot in range(OVERWORLD_PICKS):
        _bring_into_class_c(lists, slot, remaining.pop(rng.below(len(remaining))))
    for group in DUNGEON_GROUPS:
        members = groups[group]
        while True:
            enemy_type = members[rng.below(len(members))]
            if not _redrawn(enemy_type, vire_hit_points, zol_hit_points):
                break
        _bring_into_class_c(lists, OVERWORLD_PICKS + group, enemy_type)
    return tuple(int(enemy_type) for enemy_type in lists)
