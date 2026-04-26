"""Shuffle dungeon enemies between levels.

Redistributes non-boss, non-special enemies across dungeon levels by
collecting them into sprite-set-based pools and then reassigning them.
Ported from remapDungeonMonstersBetweenLevels (Module.cs:85423).
"""

from zora.data_model import (
    Enemy,
    EnemySpriteSet,
    GameWorld,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# Maximum retries when a safety check rejects a random enemy pick for a room.
_MAX_ROOM_RETRIES = 50

# Maximum retries when a level fails the bubble balance check.
_MAX_LEVEL_RETRIES = 20


# Maps each dungeon level to its vanilla enemy sprite set.
# This determines which pool a level's enemies are collected into.
LEVEL_SPRITE_SET: dict[int, EnemySpriteSet] = {
    1: EnemySpriteSet.A, 2: EnemySpriteSet.A, 7: EnemySpriteSet.A,
    3: EnemySpriteSet.B, 5: EnemySpriteSet.B, 8: EnemySpriteSet.B,
    4: EnemySpriteSet.C, 6: EnemySpriteSet.C, 9: EnemySpriteSet.C,
}


_EXCLUDED_FROM_ENEMY_SHUFFLING: frozenset[Enemy] = frozenset({
    Enemy.NOTHING,
    Enemy.MIXED_FLAME,          # projectile sub-entity
    Enemy.FLYING_GLEEOK_HEAD,   # sub-entity of Gleeok
    Enemy.OLD_MAN,
    Enemy.OLD_MAN_2,
    Enemy.OLD_MAN_3,
    Enemy.OLD_MAN_4,
    Enemy.OLD_MAN_5,
    Enemy.OLD_MAN_6,
    Enemy.BOMB_UPGRADER,
    Enemy.MUGGER,
    Enemy.HUNGRY_GORIYA,
    Enemy.THE_KIDNAPPED,
})


# Bosses (per Enemy.is_boss) whose sprites live in the enemy sprite sets, not
# the boss sprite sets. These must participate in between-level shuffling so
# they stay matched to their level's enemy_sprite_set; the blanket is_boss
# exclusion would otherwise strand them in a level whose sprite bank no longer
# contains their tile data.
#
# Empirically derived from a 50-seed reference corpus (flagset
# MSqT2vqlQRwbDXS41SNS518uL):
#   - RED_LANMOLA, BLUE_LANMOLA: live in enemy sprite set C (L9's set)
#   - MOLDORM: lives in enemy sprite set A (L2/L7's set)
#   - RUPEE_BOSS: not actually a boss (money-room old-man variant); its
#     is_boss=True classification in data_model is a misclassification we
#     work around here. Reference includes RUPEE_BOSS in all three pools.
#     TODO: cleaner fix is to correct Enemy.is_boss; deferred to avoid
#     wider ripple effects on other code that checks is_boss.
_BOSS_ENEMIES_IN_ENEMY_SPRITE_SETS: frozenset[Enemy] = frozenset({
    Enemy.RED_LANMOLA,
    Enemy.BLUE_LANMOLA,
    Enemy.MOLDORM,
    Enemy.RUPEE_BOSS,
})


def _is_excluded_from_enemy_shuffling(enemy: Enemy) -> bool:
    """Return True if this enemy should not participate in inter-level shuffling."""
    if enemy in _EXCLUDED_FROM_ENEMY_SHUFFLING:
        return True
    if enemy.is_boss and enemy not in _BOSS_ENEMIES_IN_ENEMY_SPRITE_SETS:
        return True
    return False

def _build_enemy_pools(world: GameWorld) -> dict[EnemySpriteSet, list[Enemy]]:
    """Collect unique enemies from each dungeon level into sprite-set-based pools.

    Each level maps to one of three enemy sprite sets (A, B, C) based on its
    vanilla assignment. Rooms containing excluded enemies (bosses, NOTHING)
    are skipped. The result is a dict mapping EnemySpriteSet -> sorted list of
    unique Enemy values found across all levels sharing that sprite set.

    Lists are sorted by enum value for deterministic ordering (reproducible seeds).

    Only Q1 (levels 1-9) is processed; Q2 is out of scope.
    """
    pools: dict[EnemySpriteSet, set[Enemy]] = {
        EnemySpriteSet.A: set(),
        EnemySpriteSet.B: set(),
        EnemySpriteSet.C: set(),
    }

    for level in world.levels:
        sprite_set = LEVEL_SPRITE_SET[level.level_num]
        for room in level.rooms:
            if room.enemy_spec.is_group:
                continue
            enemy = room.enemy_spec.enemy
            if _is_excluded_from_enemy_shuffling(enemy):
                continue
            pools[sprite_set].add(enemy)

    # NOTE: The original C# also collected overworld enemies into separate pools
    # (indices 3 and 7). However, the redistribution loop in Phase 9 computes
    # pool indices from tierArr, whose values are always 0-2 (sprite sets A/B/C).
    # No level ever draws from pool 3 or 7, regardless of includeLevel9 or
    # allowQ2Monsters settings. The overworld collection is dead code in the
    # original and is intentionally omitted here.

    sorted_pools: dict[EnemySpriteSet, list[Enemy]] = {}
    for sprite_set, enemies in pools.items():
        sorted_pools[sprite_set] = sorted(enemies)

    return sorted_pools


# The initial sprite set distribution used before shuffling.
# Indices 1-8 correspond to levels 1-8; index 9 is level 9; index 0 is unused.
# This is NOT the vanilla assignment — it's a starting point that gets shuffled.
# The distribution is weighted toward set A (6 of 10 slots).
_INITIAL_SPRITE_SETS = [
    EnemySpriteSet.A,  # [0] unused
    EnemySpriteSet.A,  # [1] level 1
    EnemySpriteSet.A,  # [2] level 2
    EnemySpriteSet.B,  # [3] level 3
    EnemySpriteSet.B,  # [4] level 4
    EnemySpriteSet.C,  # [5] level 5
    EnemySpriteSet.A,  # [6] level 6 — replaced with random A/B/C
    EnemySpriteSet.A,  # [7] level 7 — replaced with random A/B/C
    EnemySpriteSet.A,  # [8] level 8
    EnemySpriteSet.C,  # [9] level 9
]

_ALL_SPRITE_SETS = [EnemySpriteSet.A, EnemySpriteSet.B, EnemySpriteSet.C]


def _shuffle_sprite_set_assignments(
    rng: Rng,
    include_level_9: bool,
) -> dict[int, EnemySpriteSet]:
    """Shuffle which enemy sprite set each dungeon level uses.

    Builds an initial distribution of sprite sets across levels 1-9,
    randomizes two slots, then shuffles the assignments.
    Returns a dict mapping level number (1-9) to its new EnemySpriteSet.

    If include_level_9 is False, level 9 is excluded from the shuffle and
    forced to sprite set C.
    """
    assignments = list(_INITIAL_SPRITE_SETS)  # copy; indices 0-9

    # Randomize slots 6 and 7 to any of the three sprite sets
    assignments[6] = rng.choice(_ALL_SPRITE_SETS)
    assignments[7] = rng.choice(_ALL_SPRITE_SETS)

    # Shuffle the assignments for levels 1-8 (or 1-9 if level 9 is included)
    last = 9 if include_level_9 else 8
    to_shuffle = assignments[1:last + 1]
    rng.shuffle(to_shuffle)
    assignments[1:last + 1] = to_shuffle

    # Level 9 fixup: if excluded from shuffle, force sprite set C
    if not include_level_9:
        assignments[9] = EnemySpriteSet.C

    # TODO: Phase 8 — when QuestVariants[2] == 2 (level 2 uses its Q2 layout),
    # the original forces level 2 to share level 7's sprite set. Skipped until
    # quest variant support is added to the data model.

    # Build level_num -> sprite set mapping
    return {level_num: assignments[level_num] for level_num in range(1, 10)}


def _redistribute_enemies(
    world: GameWorld,
    rng: Rng,
    pools: dict[EnemySpriteSet, list[Enemy]],
    sprite_set_assignments: dict[int, EnemySpriteSet],
    include_level_9: bool,
) -> None:
    """Replace non-excluded enemies in each dungeon level with random picks from pools.

    For each level, determines which enemy pool to draw from based on the
    level's (shuffled) sprite set assignment, then iterates rooms and replaces
    eligible enemies with random selections from that pool.

    Safety checks ensure certain enemies only appear in compatible room types.
    If a pick fails a safety check, the room is retried with a new pick
    (up to _MAX_ROOM_RETRIES times).

    After processing all rooms in a level, checks bubble balance: if red
    bubbles are present but no blue bubbles, the entire level is retried
    (up to _MAX_LEVEL_RETRIES times). Red bubbles disable sword use, and
    blue bubbles restore it — a level with only red bubbles could softlock
    the player.
    """
    for level in world.levels:
        if not include_level_9 and level.level_num == 9:
            continue

        sprite_set = sprite_set_assignments[level.level_num]
        pool = pools[sprite_set]
        if not pool:
            continue

        for level_attempt in range(_MAX_LEVEL_RETRIES):
            has_red_bubble = False
            has_blue_bubble = False

            for room in level.rooms:
                if room.enemy_spec.is_group:
                    continue
                enemy = room.enemy_spec.enemy
                if _is_excluded_from_enemy_shuffling(enemy):
                    continue

                for room_attempt in range(_MAX_ROOM_RETRIES):
                    replacement = rng.choice(pool)

                    if not is_safe_for_room(replacement, room.room_type, has_push_block=room.movable_block):
                        continue

                    # Track bubble types for level-wide balance check
                    if replacement == Enemy.RED_BUBBLE:
                        has_red_bubble = True
                    if replacement == Enemy.BLUE_BUBBLE:
                        has_blue_bubble = True

                    room.enemy_spec.enemy = replacement
                    break  # room successfully assigned

            # Bubble balance: red bubbles without blue bubbles can softlock
            if not (has_red_bubble and not has_blue_bubble):
                break  # level is fine, move on

    # TODO: When allow_q2_monsters is enabled, the original patches three
    # 6502 branch instructions (BNE = 0xD0) at ROM addresses 0x1135D,
    # 0x1139D, and 0x112DC to make the engine load Q2 enemy tables in Q1.
    # This is a ROM code patch — belongs in the serialization layer.


def shuffle_monsters_between_levels(
    world: GameWorld,
    rng: Rng,
    include_level_9: bool = False,
) -> None:
    """Shuffle enemies between dungeon levels.

    Collects non-boss enemies from all dungeon rooms into pools grouped by
    enemy sprite set (A, B, C), shuffles which sprite set each level uses,
    then replaces each room's enemy with a random pick from its level's
    new pool. Mutates world.levels in place.

    Args:
        world: The game world to modify.
        rng: Seeded RNG for deterministic output.
        include_level_9: If True, level 9 participates in the sprite set
            shuffle. If False, level 9 keeps sprite set C and its enemies
            are not replaced.
    """
    pools = _build_enemy_pools(world)
    sprite_set_assignments = _shuffle_sprite_set_assignments(rng, include_level_9)

    # Apply the new sprite set assignments to each level
    for level in world.levels:
        level.enemy_sprite_set = sprite_set_assignments[level.level_num]

    _redistribute_enemies(world, rng, pools, sprite_set_assignments, include_level_9)
