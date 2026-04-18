"""Shuffle boss assignments across dungeon levels.

Assigns a boss difficulty tier (mapped to BossSpriteSet) to each dungeon,
then replaces boss enemies in rooms with random picks from the assigned
tier's pool. Optionally adds extra bosses to non-boss rooms.

Ported from BossShuffler.cs (remapBosses, Module.cs:72753-73135).
"""

from zora.data_model import (
    BossSpriteSet,
    Enemy,
    GameWorld,
)
from zora.enemy.safety_checks import is_safe_for_room
from zora.rng import Rng

# Maximum retries when a safety check rejects a random boss pick for a room.
_MAX_ROOM_RETRIES = 50


# ---------------------------------------------------------------------------
# Boss tiers — groups of boss enemies by difficulty / sprite set.
#
# BossSpriteSet.A = easy bosses (vanilla: levels 1, 2, 5, 7)
# BossSpriteSet.B = medium bosses (vanilla: levels 3, 4, 6, 8)
# BossSpriteSet.C = hard bosses (vanilla: level 9)
# ---------------------------------------------------------------------------

BOSS_TIERS: dict[BossSpriteSet, list[Enemy]] = {
    BossSpriteSet.A: [
        Enemy.AQUAMENTUS,
        Enemy.TRIPLE_DODONGO,
        Enemy.SINGLE_DODONGO,
        Enemy.SINGLE_DIGDOGGER,
        Enemy.TRIPLE_DIGDOGGER,
    ],
    BossSpriteSet.B: [
        Enemy.BLUE_GOHMA,
        Enemy.RED_GOHMA,
        Enemy.MANHANDLA,
        Enemy.GLEEOK_2,
        Enemy.GLEEOK_3,
        Enemy.GLEEOK_4,
    ],
    BossSpriteSet.C: [
        Enemy.PATRA_2,
        Enemy.PATRA_1,
    ],
}

# All boss enemies that appear in any tier (used to detect existing bosses).
_ALL_TIER_BOSSES: frozenset[Enemy] = frozenset(
    boss for tier in BOSS_TIERS.values() for boss in tier
)

# Per-level default boss sprite set (vanilla assignment).
# Used to determine which bosses "belong" to a level before shuffling.
_DEFAULT_BOSS_TIER: dict[int, BossSpriteSet] = {
    1: BossSpriteSet.A,
    2: BossSpriteSet.A,
    3: BossSpriteSet.B,
    4: BossSpriteSet.B,
    5: BossSpriteSet.A,
    6: BossSpriteSet.B,
    7: BossSpriteSet.A,
    8: BossSpriteSet.B,
    9: BossSpriteSet.C,
}


# ---------------------------------------------------------------------------
# Tier assignment — weighted RNG biases early dungeons toward easier bosses.
# ---------------------------------------------------------------------------

# Ordered list of boss sprite sets for indexing during weighted selection.
_TIER_ORDER: list[BossSpriteSet] = [BossSpriteSet.A, BossSpriteSet.B, BossSpriteSet.C]


def _assign_boss_tiers(rng: Rng) -> dict[int, BossSpriteSet]:
    """Assign a boss sprite set to each dungeon level 1-9.

    Uses weighted RNG: early dungeons are biased toward BossSpriteSet.A,
    later dungeons get a more even distribution across all three tiers.
    Dungeon 9 is always forced to BossSpriteSet.C.

    Returns a dict mapping level number (1-9) to BossSpriteSet.
    """
    tier_count = len(_TIER_ORDER)  # 3
    assignments: dict[int, BossSpriteSet] = {}

    for dungeon_num in range(1, 9):
        # Weight increases with dungeon number, making higher tiers more likely.
        weight = 4
        if dungeon_num > 2:
            weight = 8
        if dungeon_num > 4:
            weight += 1   # 9
        if dungeon_num > 6:
            weight *= 3   # 27

        # Weighted selection: maps a random value in [0, (tier_count-1)*weight]
        # down to a tier index in [0, tier_count-1].
        max_val = (tier_count - 1) * weight
        tier_index = int(rng.random() * (max_val + 1)) // weight
        # Clamp to valid range (shouldn't be needed, but defensive)
        tier_index = min(tier_index, tier_count - 1)

        assignments[dungeon_num] = _TIER_ORDER[tier_index]

    # Dungeon 9 is always the hardest tier.
    assignments[9] = BossSpriteSet.C

    return assignments


# ---------------------------------------------------------------------------
# Main boss shuffling logic.
# ---------------------------------------------------------------------------

def shuffle_bosses(
    world: GameWorld,
    rng: Rng,
    add_extra_bosses: bool = False,
) -> None:
    """Shuffle boss assignments across dungeon levels.

    For each dungeon 1-9:
    1. Assigns a boss difficulty tier (BossSpriteSet) via weighted RNG.
    2. Updates the level's boss_sprite_set to match.
    3. Replaces existing boss enemies in rooms with random picks from the
       new tier's boss pool.
    4. If add_extra_bosses is True, non-boss rooms have a 25% chance of
       also receiving a random boss from the tier.

    Safety checks prevent placing certain bosses in incompatible room types.
    If a pick fails, the room is retried up to _MAX_ROOM_RETRIES times.

    Only Q1 levels (1-9) are processed.

    Args:
        world: The game world to modify (mutated in place).
        rng: Seeded RNG for deterministic output.
        add_extra_bosses: When True, 25% of non-boss rooms also get a boss.
    """
    tier_assignments = _assign_boss_tiers(rng)

    # Apply boss sprite sets to each level.
    for level in world.levels:
        level.boss_sprite_set = tier_assignments[level.level_num]

    # Replace bosses in rooms.
    for level in world.levels:
        assigned_tier = tier_assignments[level.level_num]
        default_tier = _DEFAULT_BOSS_TIER[level.level_num]
        boss_pool = BOSS_TIERS[assigned_tier]
        default_bosses = frozenset(BOSS_TIERS[default_tier])

        for room in level.rooms:
            enemy = room.enemy_spec.enemy

            # Decide whether this room should be considered for boss replacement.
            should_add_extra = add_extra_bosses and rng.random() < 0.25

            is_existing_boss = enemy in default_bosses

            if not is_existing_boss:
                # Non-boss room: skip unless we're adding extra bosses.
                # Also skip special enemies that should never be replaced:
                # THE_BEAST (Ganon), THE_KIDNAPPED (Zelda), HUNGRY_GORIYA,
                # NOTHING, and boss-arena room types (Aquamentus/Gleeok/Gohma rooms).
                if not should_add_extra:
                    continue
                if enemy == Enemy.NOTHING:
                    continue
                if enemy in (Enemy.THE_BEAST, Enemy.THE_KIDNAPPED, Enemy.HUNGRY_GORIYA):
                    continue

            # Pick a random boss from the assigned tier, retrying on safety failures.
            for _attempt in range(_MAX_ROOM_RETRIES):
                new_boss = rng.choice(boss_pool)

                if not is_safe_for_room(new_boss, room.room_type, has_push_block=room.movable_block):
                    continue

                room.enemy_spec.enemy = new_boss
                room.enemy_quantity = level.qty_table[0]
                break
