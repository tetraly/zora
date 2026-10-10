"""Tuning tables copied from the behavior spec (docs: docs/spec/shapes-behavior.md "Tuning data").

All weights are integers (Rng.weighted contract).
"""
from ...model.enums import Item, RoomType

# --- T1 door weights (first quest) -----------------------------------------
# Order: open, wall, walk-through, walk-through-2, bombable, key, key-2, shutter
DOOR_KINDS = ("open", "wall", "walk1", "walk2", "bomb", "key1", "key2", "shutter")
T1_FIRST_QUEST: dict[int, list[int]] = {
    1: [18, 0, 0, 0, 4, 12, 0, 3],
    2: [25, 0, 0, 0, 10, 6, 0, 6],
    3: [23, 0, 0, 0, 4, 8, 0, 8],
    4: [23, 2, 0, 0, 8, 10, 0, 6],
    5: [21, 12, 0, 0, 10, 12, 0, 6],
    6: [25, 8, 0, 0, 6, 10, 0, 12],
    7: [30, 26, 0, 0, 20, 10, 0, 11],
    8: [21, 12, 0, 0, 12, 8, 0, 12],
    9: [41, 68, 0, 0, 38, 32, 0, 14],
}

# SPEC-GAP 2 (SH-DOOR-02): second-quest door weights are "in the source" and
# were not provided. second_quest_doors=True currently raises. The finished
# corpus holds no walk-through walls (0 in 1,000 ROMs; the earlier raw census
# read staircases' exit-room bytes as door fields), consistent with the
# Consternation preset keeping second-quest doors off.
T1_SECOND_QUEST: dict[int, list[int]] | None = None

# --- T2 stair-room layouts ---------------------------------------------------
T2_LAYOUTS = (0x5A, 0x1B, 0x62, 0x4A, 0x48, 0x1C, 0x41,
              0x46, 0x47, 0x4C, 0x4D, 0x51, 0x5C, 0x5F)
T2_FIRST_QUEST_WEIGHTS = [14, 6, 2, 4, 2, 2, 0, 0, 0, 0, 0, 0, 0, 0]
T2_SECOND_QUEST_WEIGHTS = [4, 9, 5, 7, 3, 3, 2, 2, 2, 1, 2, 4, 1, 6]

# --- T3 room item weights ----------------------------------------------------
# Order: bombs, nothing, five rupees, key
T3_ITEMS = ("bombs", "nothing", "rupees5", "key")
T3_WEIGHTS: dict[int, list[int]] = {
    1: [0, 1, 0, 6],
    2: [2, 4, 1, 4],
    3: [3, 2, 1, 5],
    4: [0, 8, 0, 4],
    5: [2, 3, 1, 7],
    6: [1, 8, 1, 5],
    7: [7, 11, 3, 4],
    8: [3, 8, 3, 6],
    9: [5, 29, 7, 4],
}

# --- SH-STAIR-02: stair budget per level (item cellars included) -------------
STAIR_BUDGET: dict[int, int] = {1: 1, 2: 0, 3: 1, 4: 1, 5: 2, 6: 2, 7: 2, 8: 3, 9: 8}

# --- SH-STAIR-03: item cellar contents (first quest) --------------------------
CELLAR_ITEMS: dict[int, list[int]] = {
    1: [0x0A],        # bow
    2: [],
    3: [0x0C],        # raft
    4: [0x0D],        # ladder
    5: [0x05],        # recorder
    6: [0x10],        # wand
    7: [0x07],        # red candle
    8: [0x11, 0x0B],  # book, magic key
    9: [0x09, 0x13],  # silver arrows, red ring
}

# ASNB (docs/design/asnb.md section 4): with Add L4 Sword = Level 2, level 2 gets one item cellar,
# holding one sword upgrade (item $01, the wooden sword's code: with Progressive Items, the next
# sword), and a stair budget of 1 for it.
LEVEL_2_SWORD_LEVEL = 2
LEVEL_2_SWORD_ITEM = 0x01


def stair_budget(level: int, level_2_sword_cellar: bool = False) -> int:
    """SH-STAIR-02's budget, with ASNB's level-2 cellar."""
    return STAIR_BUDGET[level] + (level_2_sword_cellar and level == LEVEL_2_SWORD_LEVEL)


def cellar_items(level: int, level_2_sword_cellar: bool = False) -> list[int]:
    """SH-STAIR-03's cellar contents, with ASNB's level-2 sword."""
    if level_2_sword_cellar and level == LEVEL_2_SWORD_LEVEL:
        return [LEVEL_2_SWORD_ITEM]
    return CELLAR_ITEMS.get(level, [])


# --- SH-ROOM-02/03: person rooms ----------------------------------------------
# U13 (2026-09-28): 1/1/1/1/2/2/1/2/3 for levels 1-9 (#44.4).
PERSON_ROOMS: dict[int, int] = {1: 1, 2: 1, 3: 1, 4: 1, 5: 2, 6: 2, 7: 1, 8: 2, 9: 3}
PERSON_LIST_DEFAULT = 0x4D            # old man (SH-ROOM-02)
L9_PERSON_LISTS = (0x4C, 0x4D, 0x4E)  # one each (SH-ROOM-02)
EXTRA_PERSON_5_7 = 0x4F               # bomb upgrader (SH-ROOM-03)

# --- SH-BOSS-01/02/03: boss pools, banks, counts -------------------------------
BOSS_POOL_A = (0x3D, 0x31, 0x32, 0x38, 0x39)   # aqua, dodongo x2, digdogger x2
BOSS_POOL_B = (0x33, 0x34, 0x3C, 0x43, 0x44, 0x45)  # gohma x2, manhandla, gleeok 2-4
BOSS_POOL_C = (0x47, 0x48)                     # patras
BOSS_COUNTS: dict[int, int] = {1: 1, 2: 1, 3: 1, 4: 2, 5: 2,
                               6: 2, 7: 5, 8: 6, 9: 5}
# SH-BOSS-01/02 by the vanilla grouping (QUESTIONS #57): levels 1, 2, 5, 7
# pool A, 3, 4, 6, 8 pool B, 9 pool C, each with the bank of its pool.
# SH-BOSS-01's text lists levels 1, 2, 3, 6, 8 for pool A, but its own Why
# says "the vanilla groupings", PS-BOSS-02's vanilla tiers are these, and
# the shapes-stage corpus holds only these tiers per level (300 ROMs).
LEVEL_BOSS_SET: dict[int, str] = {1: "A", 2: "A", 5: "A", 7: "A",
                                  3: "B", 4: "B", 6: "B", 8: "B", 9: "C"}
LEVEL_BOSS_POOL: dict[int, tuple[int, ...]] = {
    1: BOSS_POOL_A, 2: BOSS_POOL_A, 5: BOSS_POOL_A, 7: BOSS_POOL_A,
    3: BOSS_POOL_B, 4: BOSS_POOL_B, 6: BOSS_POOL_B, 8: BOSS_POOL_B, 9: BOSS_POOL_C,
}

# SH-ENEMY-01: enemy bank per level number (vanilla sprite bank groups).
LEVEL_ENEMY_BANK: dict[int, str] = {
    1: "A", 2: "A", 7: "A", 3: "B", 5: "B", 8: "B", 4: "C", 6: "C", 9: "C",
}

# SH-BOSS-05: layouts a boss fight must not use (masked layout ids).
GLEEOK_BAD_LAYOUTS = frozenset({RoomType.CIRCLE_WALL, RoomType.LAVA_MOAT, RoomType.VERTICAL_CHUTE_ROOM,
                                RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.T_ROOM, RoomType.CIRCLE_MOAT_ROOM,
                                RoomType.TWO_FIREBALL_ROOM, RoomType.FOUR_FIREBALL_ROOM})
GLEEOK4_EXTRA_BAD = frozenset({RoomType.VERTICAL_MOAT_ROOM, RoomType.POINTLESS_MOAT_ROOM, RoomType.CHEVY_ROOM,
                               RoomType.NSU, RoomType.HORIZONTAL_MOAT_ROOM, RoomType.DOUBLE_MOAT_ROOM})
GOHMA_BAD_LAYOUTS = frozenset({RoomType.LAVA_MOAT, RoomType.VERTICAL_CHUTE_ROOM,
                               RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.T_ROOM})
DODONGO_BAD_LAYOUTS = frozenset({RoomType.CIRCLE_WALL, RoomType.LAVA_MOAT, RoomType.VERTICAL_CHUTE_ROOM,
                                 RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.T_ROOM})

# SH-ENEMY-04: the barred layouts of Lanmolas, the rupee object and traps (the
# families themselves are defined on monster values in enemies.py).
LANMOLA_BAD_LAYOUTS = frozenset({RoomType.SPIKE_TRAP_ROOM, RoomType.AQUAMENTUS_ROOM, RoomType.CIRCLE_WALL,
                                 RoomType.LAVA_MOAT, RoomType.MAZE_ROOM, RoomType.HORIZONTAL_CHUTE_ROOM,
                                 RoomType.ZIGZAG_ROOM, RoomType.T_ROOM, RoomType.CHEVY_ROOM, RoomType.NSU,
                                 RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM,
                                 RoomType.TURNSTILE_ROOM, RoomType.ZELDA_ROOM, RoomType.TRIFORCE_ROOM,
                                 RoomType.LAYOUT_0x33})
RUPEE_STASH_BAD_LAYOUTS = frozenset({RoomType.CIRCLE_WALL, RoomType.LAVA_MOAT, RoomType.MAZE_ROOM,
                                     RoomType.VERTICAL_CHUTE_ROOM, RoomType.HORIZONTAL_CHUTE_ROOM,
                                     RoomType.VERTICAL_ROWS, RoomType.T_ROOM, RoomType.VERTICAL_MOAT_ROOM,
                                     RoomType.CIRCLE_MOAT_ROOM, RoomType.CHEVY_ROOM, RoomType.NSU,
                                     RoomType.HORIZONTAL_MOAT_ROOM, RoomType.DOUBLE_MOAT_ROOM,
                                     RoomType.DIAMOND_STAIR_ROOM, RoomType.SINGLE_SIX_BLOCK_ROOM,
                                     RoomType.TURNSTILE_ROOM})
BLADE_TRAP_BAD_LAYOUTS = frozenset({RoomType.THREE_ROWS, RoomType.REVERSE_C, RoomType.CIRCLE_WALL,
                                    RoomType.MAZE_ROOM, RoomType.HORIZONTAL_CHUTE_ROOM, RoomType.T_ROOM,
                                    RoomType.SPIRAL_STAIR_ROOM, RoomType.TRIFORCE_ROOM})

# SH-ENEMY-02: ids removed from pools: bosses (Gohma/Dodongo/Digdogger/
# Aquamentus/Manhandla/Gleeok/Patra), Ganon, Zelda, hungry goriya, people and
# projectile-ish ids. Moldorm (0x41) and lanmolas (0x3A/0x3B) STAY (ordinary
# room monsters per spec); rupee stash (0x35) stays (SH-ENEMY-04 treats it as
# a room enemy). SPEC-GAP 18: "projectiles" taken as falling rocks, whistle
# tornado, fairy, bubbles.
POOL_EXCLUSIONS = frozenset({
    0x31, 0x32, 0x33, 0x34, 0x36, 0x37, 0x38, 0x39, 0x3C, 0x3D, 0x3E,
    0x42, 0x43, 0x44, 0x45, 0x47, 0x48,
    0x4B, 0x4C, 0x4D, 0x4E, 0x4F, 0x50, 0x51, 0x52,
    0x1F, 0x20, 0x2E, 0x2F, 0x2B, 0x2C, 0x2D,
})

# SH-ROOM-01: triforce layout/item; SH-ROOM-06 special layouts.

# SH-ROOM-08: reserved layouts never drawn randomly (masked ids).
RESERVED_RANDOM_LAYOUTS = frozenset({RoomType.DIAMOND_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM,
                                     RoomType.NARROW_STAIR_ROOM, RoomType.SPIRAL_STAIR_ROOM,
                                     RoomType.GANON_ROOM, RoomType.ZELDA_ROOM, RoomType.TRIFORCE_ROOM,
                                     RoomType.ENTRANCE_ROOM})

MAP_MOVE_TRIGGER_PROB_NUM = 4
MAP_MOVE_TRIGGER_PROB_DEN = 5
# SH-ITEM-01: compass/map/boomerangs replace ordinary dropped items.
T3_REPLACEABLE = frozenset({Item.BOMBS, Item.FIVE_RUPEES, Item.KEY})
MAP_MOVE_TRIGGER_CODES = frozenset({Item.COMPASS, Item.MAP})

# RoomAction codes (zora.model.enums.RoomAction).

STAIR_EXIT_POSITION = 0x69   # packed 0xXY → X=6, Y=9 (SH-STAIR-04; SPEC-GAP 6)
