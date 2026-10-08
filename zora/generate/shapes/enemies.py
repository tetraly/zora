"""Enemy placement (SH-ENEMY-01..07).

Pools come from the vanilla GameWorld handed to the flow: every monster
value used in the vanilla levels of the level's bank group (SH-ENEMY-01),
minus the exclusions of SH-ENEMY-02.

A pool entry is a whole monster value (post-shapes-b2.md PS-MONLV-02): the
monster byte, count index included, plus $100 for the monster bit. The
shapes-stage corpus shows these values are drawn, not a group
and a separate count: every ordinary value it holds is a vanilla value of
the level's group, count bits included, drawn about evenly over the
distinct values (QUESTIONS #58.1).
"""
from zora.generate.rng import Rng
from zora.generate.shapes.options import ShapeOptions
from zora.generate.shapes.tables import (
    BLADE_TRAP_BAD_LAYOUTS,
    LANMOLA_BAD_LAYOUTS,
    LEVEL_ENEMY_BANK,
    POOL_EXCLUSIONS,
    RUPEE_STASH_BAD_LAYOUTS,
)
from zora.generate.shapes.world import SetWorld
from zora.model.enums import RoomType
from zora.model.levels import Level
from zora.model.rooms import MONSTER_BIT_CODE, MONSTER_LIST_BITS, MONSTER_VALUE_BIT

GROUP_BY_BANK = {"A": (1, 2, 7), "B": (3, 5, 8), "C": (4, 6, 9)}

# The three barred families as monster values (PS-MONLV-04's definitions; the
# shapes-stage corpus has none of them on a barred layout, QUESTIONS #58.1):
# Lanmolas and the rupee object by whole value, traps by the monster bit and
# the low six bits.
LANMOLA_VALUES = frozenset({0x3A, 0x3B})
RUPEE_VALUE = 0x35
TRAP_LISTS = frozenset({0x09, 0x0A, 0x2D, 0x2E, 0x36, 0x37})


def is_trap(value: int) -> bool:
    return bool(value & MONSTER_VALUE_BIT) and value & MONSTER_LIST_BITS in TRAP_LISTS


def monster_barred(value: int, layout: int) -> bool:
    """SH-ENEMY-04 / PS-MONLV-04: is this monster value barred from the
    layout (the layout byte's low six bits)? Quirk: the Lanmola and rupee
    tests are whole-value, so a count-indexed one would skip its ban; the
    trap test masks the low six bits."""
    if value in LANMOLA_VALUES:
        return layout in LANMOLA_BAD_LAYOUTS
    if value == RUPEE_VALUE:
        return layout in RUPEE_STASH_BAD_LAYOUTS
    if is_trap(value):
        return layout in BLADE_TRAP_BAD_LAYOUTS
    return False


def _group_code(value: int) -> int:
    """The value as POOL_EXCLUSIONS names groups: list id plus $40 for the
    monster bit, count index dropped."""
    return (value & MONSTER_LIST_BITS) | (MONSTER_BIT_CODE if value & MONSTER_VALUE_BIT else 0)


class EnemyPools:
    def __init__(self) -> None:
        self.pools: dict[str, list[int]] = {"A": [], "B": [], "C": []}


def harvest_pools(levels_lists: list[list[Level]], opts: ShapeOptions) -> EnemyPools:
    """levels_lists: one list of vanilla Levels per quest to include.

    SH-ENEMY-01: the pool of a bank = every distinct monster value used in
    the vanilla levels of its group, first quest and (with the "second
    quest monsters" option) second quest; SH-ENEMY-02's exclusions apply
    to the group, whatever the count index. Rooms without a monster add
    nothing: the shapes-stage corpus has no empty room outside SH-ENEMY-03's
    exempt ones (0 of 52,906 level rooms, 300 ROMs), and with that the
    first-quest pools equal the corpus's values exactly (QUESTIONS #58.1).
    """
    pools = EnemyPools()
    for levels in levels_lists:
        by_num = {level.level_num: level for level in levels}
        for bank, nums in GROUP_BY_BANK.items():
            for num in nums:
                level = by_num.get(num)
                if level is None:
                    continue
                for room in level.rooms:
                    value = room.monster_value
                    if (value & MONSTER_LIST_BITS == 0         # no monster
                            or _group_code(value) in POOL_EXCLUSIONS
                            or value in pools.pools[bank]):
                        continue
                    pools.pools[bank].append(value)
    for pool in pools.pools.values():
        pool.sort()
    return pools


def place_enemies(world: SetWorld, rng: Rng, opts: ShapeOptions,
                  pools: EnemyPools) -> None:
    """SH-ENEMY-03/04: one value per room without a monster, drawn evenly
    from the level's pool and redrawn while its layout bars it."""
    for blob in range(world.blob_count):
        level = world.levels[blob]
        pool = pools.pools[LEVEL_ENEMY_BANK[level]]
        if not pool:
            continue
        entrance = world.entrance.get(level)
        for cell in sorted(world.cells_by_blob[blob]):
            plan = world.plans[cell]
            if plan.enemy is not None or cell == entrance:
                continue
            if plan.layout in (RoomType.TRIFORCE_ROOM, RoomType.TURNSTILE_ROOM):   # SH-ENEMY-03
                continue
            value = pool[rng.below(len(pool))]
            for _ in range(100):
                if not monster_barred(value, plan.layout_id):
                    break
                value = pool[rng.below(len(pool))]
            plan.set_monster_value(value)
