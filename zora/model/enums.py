"""The model's enumerations: sides and directions, room layouts and actions,
items, enemies, cave destinations and the other byte-valued names."""

from enum import Enum, IntEnum, auto


class UnderworldPersonInit(IntEnum):
    """Low byte of a level's InitUnderworldPerson_Full_JumpTable entry
    (bank 1, high byte $8A): which init routine the level's persons run.
    Vanilla: A in levels 1, 2, 5, 7; B in levels 3, 4, 6, 8. The hint pass
    (post-shapes-b25.md PS-HINT-06) calls B levels helpful, A unhelpful."""
    A = 0x23      # InitUnderworldPersonA: text selectors A, the bomb-upgrade offer
    B = 0x69      # InitUnderworldPersonB: text selectors B


VANILLA_PERSON_INITS = (UnderworldPersonInit.A, UnderworldPersonInit.A,
                        UnderworldPersonInit.B, UnderworldPersonInit.B,
                        UnderworldPersonInit.A, UnderworldPersonInit.B,
                        UnderworldPersonInit.A, UnderworldPersonInit.B)


ROOMS_PER_ROW = 16          # a level block's grid: room number = row * 16 + column


class Side(IntEnum):
    """A side of a room, in the order the generator walks them (N, E, S, W).
    The values index per-side tables; Direction holds each side's room-number
    step."""
    NORTH = 0
    EAST = 1
    SOUTH = 2
    WEST = 3

    @property
    def opposite(self) -> "Side":
        return _OPPOSITE_SIDES[self]

    @property
    def delta(self) -> int:
        """The room-number step to the neighbour on this side."""
        return _SIDE_DELTAS[self]

    @property
    def direction(self) -> "Direction":
        return Direction(_SIDE_DELTAS[self])

    @property
    def wall_attr(self) -> str:
        """WallSet's field for this side."""
        return _SIDE_WALL_ATTRS[self]


_OPPOSITE_SIDES = (Side.SOUTH, Side.WEST, Side.NORTH, Side.EAST)
_SIDE_DELTAS = (-ROOMS_PER_ROW, +1, +ROOMS_PER_ROW, -1)
_SIDE_WALL_ATTRS = ("north", "east", "south", "west")


class Direction(IntEnum):
    """A side as a room-number step (derived from Side), plus the staircase
    pseudo-direction of the traversal."""
    WEST  = _SIDE_DELTAS[Side.WEST]
    EAST  = _SIDE_DELTAS[Side.EAST]
    NORTH = _SIDE_DELTAS[Side.NORTH]
    SOUTH = _SIDE_DELTAS[Side.SOUTH]
    STAIRCASE = 0x20  # pseudo-direction used for staircase room traversal

    @property
    def side(self) -> Side:
        return _DIRECTION_SIDES[self]


_DIRECTION_SIDES = {Direction(delta): side for side, delta in zip(Side, _SIDE_DELTAS, strict=True)}


class OverworldDirection(IntEnum):
    """Direction byte values used in the Lost Hills and Dead Woods maze sequences.

    These are ROM bitmask values, distinct from the dungeon-traversal Direction
    enum which uses signed deltas.
    """
    UP_NORTH   = 0x08
    DOWN_SOUTH = 0x04
    RIGHT_EAST = 0x01
    LEFT_WEST  = 0x02


class WallType(IntEnum):
    OPEN_DOOR           = 0
    SOLID_WALL          = 1
    WALK_THROUGH_WALL_1 = 2
    WALK_THROUGH_WALL_2 = 3
    BOMB_HOLE           = 4
    LOCKED_DOOR_1       = 5
    LOCKED_DOOR_2       = 6
    SHUTTER_DOOR        = 7


class RoomType(IntEnum):
    """Byte D bits 5-0: the room layout, an index into aldonunez
    `RoomLayoutsUW` (which names none of them). Source of the names: the
    names commonly used in the Z1R community, approved by the owner
    (2026-10-04); docs/glossary/room-layouts.csv lists them.
    Layouts without a community name keep their code (LAYOUT_0xNN)."""
    PLAIN_ROOM             = 0x00
    SPIKE_TRAP_ROOM        = 0x01
    FOUR_SHORT_ROOM        = 0x02
    FOUR_TALL_ROOM         = 0x03
    AQUAMENTUS_ROOM        = 0x04
    GLEEOK_ROOM            = 0x05
    GOHMA_ROOM             = 0x06
    THREE_ROWS             = 0x07
    REVERSE_C              = 0x08
    CIRCLE_WALL            = 0x09
    DOUBLE_BLOCK           = 0x0A
    LAVA_MOAT              = 0x0B
    MAZE_ROOM              = 0x0C
    GRID_ROOM              = 0x0D
    VERTICAL_CHUTE_ROOM    = 0x0E
    HORIZONTAL_CHUTE_ROOM  = 0x0F
    VERTICAL_ROWS          = 0x10
    ZIGZAG_ROOM            = 0x11
    T_ROOM                 = 0x12
    VERTICAL_MOAT_ROOM     = 0x13
    CIRCLE_MOAT_ROOM       = 0x14
    POINTLESS_MOAT_ROOM    = 0x15
    CHEVY_ROOM             = 0x16
    NSU                    = 0x17
    HORIZONTAL_MOAT_ROOM   = 0x18
    DOUBLE_MOAT_ROOM       = 0x19
    DIAMOND_STAIR_ROOM     = 0x1A
    NARROW_STAIR_ROOM      = 0x1B
    SPIRAL_STAIR_ROOM      = 0x1C
    DOUBLE_SIX_BLOCK_ROOM  = 0x1D
    SINGLE_SIX_BLOCK_ROOM  = 0x1E
    FIVE_PAIR_ROOM         = 0x1F
    TURNSTILE_ROOM         = 0x20
    ENTRANCE_ROOM          = 0x21
    SINGLE_BLOCK_ROOM      = 0x22
    TWO_FIREBALL_ROOM      = 0x23
    FOUR_FIREBALL_ROOM     = 0x24
    DESERT_ROOM            = 0x25
    BLACK_ROOM             = 0x26
    ZELDA_ROOM             = 0x27
    GANON_ROOM            = 0x28
    TRIFORCE_ROOM          = 0x29
    # Layouts $2A-$3D are not used by vanilla first-quest rooms but appear in
    # randomized (shapes) ROMs. Names unknown (disassembly ships no layout
    # labels here); placeholders keep parsing lossless.
    LAYOUT_0x2A = 0x2A
    LAYOUT_0x2B = 0x2B
    LAYOUT_0x2C = 0x2C
    LAYOUT_0x2D = 0x2D
    LAYOUT_0x2E = 0x2E
    LAYOUT_0x2F = 0x2F
    LAYOUT_0x30 = 0x30
    LAYOUT_0x31 = 0x31
    LAYOUT_0x32 = 0x32
    LAYOUT_0x33 = 0x33
    LAYOUT_0x34 = 0x34
    LAYOUT_0x35 = 0x35
    LAYOUT_0x36 = 0x36
    LAYOUT_0x37 = 0x37
    LAYOUT_0x38 = 0x38
    LAYOUT_0x39 = 0x39
    LAYOUT_0x3A = 0x3A
    LAYOUT_0x3B = 0x3B
    LAYOUT_0x3C = 0x3C
    LAYOUT_0x3D = 0x3D
    TRANSPORT_STAIRCASE    = 0x3E
    ITEM_STAIRCASE         = 0x3F

    def has_open_staircase(self) -> bool:
        """Spiral, Narrow, and Diamond stair rooms always have an open staircase."""
        return self in (RoomType.SPIRAL_STAIR_ROOM, RoomType.NARROW_STAIR_ROOM, RoomType.DIAMOND_STAIR_ROOM)

    def can_have_push_block(self) -> bool:
        """Room types that can have a movable middle-row push block triggering a staircase."""
        return self in (
            RoomType.PLAIN_ROOM, RoomType.SPIKE_TRAP_ROOM, RoomType.FOUR_SHORT_ROOM,
            RoomType.FOUR_TALL_ROOM, RoomType.THREE_ROWS, RoomType.REVERSE_C,
            RoomType.CIRCLE_WALL, RoomType.DOUBLE_BLOCK, RoomType.MAZE_ROOM,
            RoomType.GRID_ROOM, RoomType.VERTICAL_ROWS, RoomType.ZIGZAG_ROOM,
            RoomType.DOUBLE_SIX_BLOCK_ROOM, RoomType.SINGLE_SIX_BLOCK_ROOM,
            RoomType.FIVE_PAIR_ROOM, RoomType.TURNSTILE_ROOM, RoomType.ENTRANCE_ROOM,
            RoomType.SINGLE_BLOCK_ROOM, RoomType.TWO_FIREBALL_ROOM, RoomType.FOUR_FIREBALL_ROOM,
            RoomType.DESERT_ROOM, RoomType.BLACK_ROOM,
        )


class Item(IntEnum):
    BOMBS           = 0x00
    WOOD_SWORD      = 0x01
    WHITE_SWORD     = 0x02
    MAGICAL_SWORD   = 0x03
    BAIT            = 0x04
    RECORDER        = 0x05
    BLUE_CANDLE     = 0x06
    RED_CANDLE      = 0x07
    WOOD_ARROWS     = 0x08
    SILVER_ARROWS   = 0x09
    BOW             = 0x0A
    MAGICAL_KEY     = 0x0B
    RAFT            = 0x0C
    LADDER          = 0x0D
    TRIFORCE_OF_POWER = 0x0E
    FIVE_RUPEES     = 0x0F
    WAND            = 0x10
    BOOK            = 0x11
    BLUE_RING       = 0x12
    RED_RING        = 0x13
    POWER_BRACELET  = 0x14
    LETTER          = 0x15
    COMPASS         = 0x16
    MAP             = 0x17
    # "No item" is a MODEL MEANING, not a byte: NOTHING's numeric value is an
    # internal placeholder and is never written to or read from the ROM.
    # The ROM byte that encodes it is a serialization setting —
    # game_config.DungeonNothingCode ($03 vanilla/Consternation, $0E with the
    # ZORA remap + its assembly patch).
    NOTHING         = 0x7F
    ITEM_0x18       = 0x18  # overworld rupee-family code; no known dungeon use
    KEY             = 0x19
    HEART_CONTAINER = 0x1A
    TRIFORCE        = 0x1B
    MAGICAL_SHIELD  = 0x1C
    WOOD_BOOMERANG  = 0x1D
    MAGICAL_BOOMERANG = 0x1E
    BLUE_POTION     = 0x1F
    RED_POTION      = 0x20
    ITEM_0x21       = 0x21  # unused in vanilla dungeon rooms; placeholder
    SINGLE_HEART    = 0x22
    FAIRY           = 0x23
    # $24-$3E: not defined by vanilla cave/item bytes; randomized ROMs use
    # extended item codes (identity unknown - likely progressive-item space).
    # Placeholders keep parsing lossless.
    ITEM_0x24 = 0x24
    ITEM_0x25 = 0x25
    ITEM_0x26 = 0x26
    ITEM_0x27 = 0x27
    ITEM_0x28 = 0x28
    ITEM_0x29 = 0x29
    ITEM_0x2A = 0x2A
    ITEM_0x2B = 0x2B
    ITEM_0x2C = 0x2C
    ITEM_0x2D = 0x2D
    ITEM_0x2E = 0x2E
    ITEM_0x2F = 0x2F
    ITEM_0x30 = 0x30
    ITEM_0x31 = 0x31
    ITEM_0x32 = 0x32
    ITEM_0x33 = 0x33
    ITEM_0x34 = 0x34
    ITEM_0x35 = 0x35
    ITEM_0x36 = 0x36
    ITEM_0x37 = 0x37
    ITEM_0x38 = 0x38
    ITEM_0x39 = 0x39
    ITEM_0x3A = 0x3A
    ITEM_0x3B = 0x3B
    ITEM_0x3C = 0x3C
    ITEM_0x3D = 0x3D
    ITEM_0x3E = 0x3E
    OVERWORLD_NO_ITEM = 0x3F
    # Virtual items — not ROM values, used only by the validator
    BEAST_DEFEATED_VIRTUAL_ITEM        = 0x40
    KIDNAPPED_RESCUED_VIRTUAL_ITEM     = 0x41
    LOST_HILLS_HINT_VIRTUAL_ITEM       = 0x42
    DEAD_WOODS_HINT_VIRTUAL_ITEM       = 0x43


class RoomAction(IntEnum):
    """Byte F bits 2-0: the secret trigger, an index into aldonunez
    `CheckSecretTrigger_JumpTable` (a 3-bit enum, not flags). Names are the
    aldonunez labels (CheckSecretTrigger<Name>)."""
    NONE          = 0   # nothing opens the shutters
    ALL_DEAD      = 1   # killing the enemies opens the shutters
    RINGLEADER    = 2   # killing the ringleader kills the enemies, opening the shutters
    LAST_BOSS     = 3   # the Triforce of Power opens the shutters; also hides the room item at load (CreateRoomObjects)
    BLOCK_DOOR    = 4   # pushing the block opens the shutters
    BLOCK_STAIRS  = 5   # pushing the block makes the stairway visible
    MONEY_OR_LIFE = 6   # defeating the person (the life-or-money choice) opens the shutters
    ALL_DEAD_ITEM = 7   # AllDead + item activation in CheckUnderworldSecrets


class BossSound(IntEnum):
    """Byte E bits 6-5: 2-bit index into aldonunez `BossSoundEffects`
    ($00,$10,$20,$40 → SampleRequest), played on loop by
    CheckBossSoundEffectUW while the level's LevelInfo_BossRoomId boss is
    undefeated. Both bits set is a third roar, not "both"."""
    NONE                           = 0
    ROAR_AQUAMENTUS_GLEEOK_GANON   = 1
    ROAR_DODONGO_GOHMA             = 2
    ROAR_DIGDOGGER_MANHANDLA_PATRA = 3

class ItemPosition(IntEnum):
    """2-bit index (0-3) into the level's item_position_table.

    Each entry in item_position_table is a packed 0xXY byte:
      high nibble = X tile coordinate
      low nibble  = Y tile coordinate

    The four positions are named A-D to stay faithful to the ROM structure.
    Semantic names belong in randomizer logic, not here.
    See Level.item_position_table for the coordinate values.
    """
    POSITION_A = 0
    POSITION_B = 1
    POSITION_C = 2
    POSITION_D = 3


class Enemy(IntEnum):
    NOTHING           = 0x00
    BLUE_LYNEL        = 0x01
    RED_LYNEL         = 0x02
    BLUE_MOBLIN       = 0x03
    RED_MOBLIN        = 0x04
    BLUE_GORIYA       = 0x05
    RED_GORIYA        = 0x06
    RED_OCTOROK_1     = 0x07
    RED_OCTOROK_2     = 0x08
    BLUE_OCTOROK_1    = 0x09
    BLUE_OCTOROK_2    = 0x0A
    RED_DARKNUT       = 0x0B
    BLUE_DARKNUT      = 0x0C
    BLUE_TEKTITE      = 0x0D
    RED_TEKTITE       = 0x0E
    BLUE_LEEVER       = 0x0F
    RED_LEEVER        = 0x10
    ZOLA              = 0x11
    VIRE              = 0x12
    ZOL               = 0x13
    GEL_1             = 0x14
    GEL_2             = 0x15
    POLS_VOICE        = 0x16
    LIKE_LIKE         = 0x17
    DIGDOGGER_SPAWN   = 0x18
    ENEMY_0x19        = 0x19
    PEAHAT            = 0x1A
    BLUE_KEESE        = 0x1B
    RED_KEESE         = 0x1C
    DARK_KEESE        = 0x1D
    ARMOS             = 0x1E
    FALLING_ROCKS     = 0x1F
    FALLING_ROCK      = 0x20
    GHINI_1           = 0x21
    GHINI_2           = 0x22
    RED_WIZZROBE      = 0x23
    BLUE_WIZZROBE     = 0x24
    ENEMY_0x25        = 0x25
    PATRA_SPAWN       = 0x26
    WALLMASTER        = 0x27
    ROPE              = 0x28
    ENEMY_0x29        = 0x29
    STALFOS           = 0x2A
    BUBBLE            = 0x2B
    BLUE_BUBBLE       = 0x2C
    RED_BUBBLE        = 0x2D
    WHISTLE_TORNADO   = 0x2E
    FAIRY             = 0x2F
    GIBDO             = 0x30
    TRIPLE_DODONGO    = 0x31
    SINGLE_DODONGO    = 0x32
    BLUE_GOHMA        = 0x33
    RED_GOHMA         = 0x34
    RUPEE_BOSS        = 0x35
    HUNGRY_GORIYA     = 0x36
    THE_KIDNAPPED     = 0x37
    TRIPLE_DIGDOGGER  = 0x38
    SINGLE_DIGDOGGER  = 0x39
    RED_LANMOLA       = 0x3A
    BLUE_LANMOLA      = 0x3B
    MANHANDLA         = 0x3C
    AQUAMENTUS        = 0x3D
    THE_BEAST         = 0x3E
    KILLABLE_FLAME    = 0x3F
    MIXED_FLAME       = 0x40
    MOLDORM           = 0x41
    GLEEOK_1          = 0x42
    GLEEOK_2          = 0x43
    GLEEOK_3          = 0x44
    GLEEOK_4          = 0x45
    FLYING_GLEEOK_HEAD = 0x46
    PATRA_2           = 0x47
    PATRA_1           = 0x48
    THREE_PAIRS_OF_TRAPS = 0x49
    CORNER_TRAPS      = 0x4A
    OLD_MAN           = 0x4B
    OLD_MAN_2         = 0x4C
    OLD_MAN_3         = 0x4D
    OLD_MAN_4         = 0x4E
    BOMB_UPGRADER     = 0x4F
    OLD_MAN_5         = 0x50
    MUGGER            = 0x51
    OLD_MAN_6         = 0x52
    # Object-template IDs $53-$61: the engine spawns these directly as repeated
    # objects (disasm Z_05 "repeated object" path); only $62+ are member lists.
    # Exact identities are overworld/NPC variants; placeholders for parsing.
    ENEMY_0x53 = 0x53
    ENEMY_0x54 = 0x54
    ENEMY_0x55 = 0x55
    ENEMY_0x56 = 0x56
    ENEMY_0x57 = 0x57
    ENEMY_0x58 = 0x58
    ENEMY_0x59 = 0x59
    ENEMY_0x5A = 0x5A
    ENEMY_0x5B = 0x5B
    ENEMY_0x5C = 0x5C
    ENEMY_0x5D = 0x5D
    ENEMY_0x5E = 0x5E
    ENEMY_0x5F = 0x5F
    ENEMY_0x60 = 0x60
    ENEMY_0x61 = 0x61
    MIXED_ENEMY_GROUP_1  = 0x62
    MIXED_ENEMY_GROUP_2  = 0x63
    MIXED_ENEMY_GROUP_3  = 0x64
    MIXED_ENEMY_GROUP_4  = 0x65
    MIXED_ENEMY_GROUP_5  = 0x66
    MIXED_ENEMY_GROUP_6  = 0x67
    MIXED_ENEMY_GROUP_7  = 0x68
    MIXED_ENEMY_GROUP_8  = 0x69
    MIXED_ENEMY_GROUP_9  = 0x6A
    MIXED_ENEMY_GROUP_10 = 0x6B
    MIXED_ENEMY_GROUP_11 = 0x6C
    MIXED_ENEMY_GROUP_12 = 0x6D
    MIXED_ENEMY_GROUP_13 = 0x6E
    MIXED_ENEMY_GROUP_14 = 0x6F
    MIXED_ENEMY_GROUP_15 = 0x70
    MIXED_ENEMY_GROUP_16 = 0x71
    MIXED_ENEMY_GROUP_17 = 0x72
    MIXED_ENEMY_GROUP_18 = 0x73
    MIXED_ENEMY_GROUP_19 = 0x74
    MIXED_ENEMY_GROUP_20 = 0x75
    MIXED_ENEMY_GROUP_21 = 0x76
    MIXED_ENEMY_GROUP_22 = 0x77
    MIXED_ENEMY_GROUP_23 = 0x78
    MIXED_ENEMY_GROUP_24 = 0x79
    MIXED_ENEMY_GROUP_25 = 0x7A
    MIXED_ENEMY_GROUP_26 = 0x7B
    MIXED_ENEMY_GROUP_27 = 0x7C
    MIXED_ENEMY_GROUP_28 = 0x7D
    MIXED_ENEMY_GROUP_29 = 0x7E
    MIXED_ENEMY_GROUP_30 = 0x7F

    @property
    def is_boss(self) -> bool:
        return self in (
    Enemy.TRIPLE_DODONGO, Enemy.SINGLE_DODONGO, Enemy.BLUE_GOHMA, Enemy.RED_GOHMA,
    Enemy.RUPEE_BOSS, Enemy.HUNGRY_GORIYA, Enemy.THE_KIDNAPPED,
    Enemy.TRIPLE_DIGDOGGER, Enemy.SINGLE_DIGDOGGER, Enemy.RED_LANMOLA,
    Enemy.BLUE_LANMOLA, Enemy.MANHANDLA, Enemy.AQUAMENTUS, Enemy.THE_BEAST,
    Enemy.MOLDORM, Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
    Enemy.PATRA_2, Enemy.PATRA_1,
        )

    def is_unkillable(self) -> bool:
        """Enemies that cannot be killed (Old Men, NPCs, etc.) — room is always passable."""
        return self in (
            Enemy.NOTHING, Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3,
            Enemy.OLD_MAN_4, Enemy.BOMB_UPGRADER, Enemy.OLD_MAN_5, Enemy.MUGGER,
            Enemy.OLD_MAN_6, Enemy.RUPEE_BOSS, Enemy.KILLABLE_FLAME, Enemy.MIXED_FLAME,
            Enemy.WHISTLE_TORNADO, Enemy.FAIRY,
        )

    def is_digdogger(self) -> bool:
        return self in (Enemy.TRIPLE_DIGDOGGER, Enemy.SINGLE_DIGDOGGER)

    def is_gohma(self) -> bool:
        return self in (Enemy.BLUE_GOHMA, Enemy.RED_GOHMA)

    def is_gleeok_or_patra(self) -> bool:
        return self in (Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4,
                        Enemy.PATRA_1, Enemy.PATRA_2)


# Boss enemy values (int) — used by is_boss to avoid forward-reference issues
_BOSS_ENEMY_VALUES: frozenset[int] = frozenset()


class Destination(IntEnum):
    NONE               = 0x00
    LEVEL_1            = 0x01
    LEVEL_2            = 0x02
    LEVEL_3            = 0x03
    LEVEL_4            = 0x04
    LEVEL_5            = 0x05
    LEVEL_6            = 0x06
    LEVEL_7            = 0x07
    LEVEL_8            = 0x08
    LEVEL_9            = 0x09
    # $0A-$0F are not used by vanilla overworld screens; randomized ROMs write
    # codes here (identity unknown). Placeholders keep parsing lossless.
    DEST_0x0A = 0x0A
    DEST_0x0B = 0x0B
    DEST_0x0C = 0x0C
    DEST_0x0D = 0x0D
    DEST_0x0E = 0x0E
    DEST_0x0F = 0x0F
    WOOD_SWORD_CAVE    = 0x10
    TAKE_ANY           = 0x11
    WHITE_SWORD_CAVE   = 0x12
    MAGICAL_SWORD_CAVE = 0x13
    ANY_ROAD           = 0x14
    LOST_HILLS_HINT    = 0x15
    MONEY_MAKING_GAME  = 0x16
    DOOR_REPAIR        = 0x17
    LETTER_CAVE        = 0x18
    DEAD_WOODS_HINT    = 0x19
    POTION_SHOP        = 0x1A
    HINT_SHOP_1        = 0x1B
    HINT_SHOP_2        = 0x1C
    SHOP_1             = 0x1D
    SHOP_2             = 0x1E
    SHOP_3             = 0x1F
    SHOP_4             = 0x20
    MEDIUM_SECRET      = 0x21
    LARGE_SECRET       = 0x22
    SMALL_SECRET       = 0x23
    ARMOS_ITEM         = 0x24
    COAST_ITEM         = 0x25
    # $26-$3F: beyond vanilla cave space; seen in randomized overworld data.
    # Placeholders keep parsing lossless.
    DEST_0x26 = 0x26
    DEST_0x27 = 0x27
    DEST_0x28 = 0x28
    DEST_0x29 = 0x29
    DEST_0x2A = 0x2A
    DEST_0x2B = 0x2B
    DEST_0x2C = 0x2C
    DEST_0x2D = 0x2D
    DEST_0x2E = 0x2E
    DEST_0x2F = 0x2F
    DEST_0x30 = 0x30
    DEST_0x31 = 0x31
    DEST_0x32 = 0x32
    DEST_0x33 = 0x33
    DEST_0x34 = 0x34
    DEST_0x35 = 0x35
    DEST_0x36 = 0x36
    DEST_0x37 = 0x37
    DEST_0x38 = 0x38
    DEST_0x39 = 0x39
    DEST_0x3A = 0x3A
    DEST_0x3B = 0x3B
    DEST_0x3C = 0x3C
    DEST_0x3D = 0x3D
    DEST_0x3E = 0x3E
    DEST_0x3F = 0x3F

    @property
    def is_level(self) -> bool:
        return 1 <= self.value <= 9

    @property
    def is_cave(self) -> bool:
        return self.value >= 0x10

    @property
    def level_num(self) -> int:
        assert self.is_level
        return self.value

    @property
    def cave_id(self) -> int:
        assert self.is_cave
        return self.value - 0x10


class EnemySpriteSet(Enum):
    A  = auto()  # vanilla: overworld, levels 1, 2, 7  (enemy_set_a)
    B  = auto()  # vanilla: levels 3, 5, 8             (enemy_set_b)
    C  = auto()  # vanilla: levels 4, 6, 9             (enemy_set_c)
    OW = auto()  # overworld-specific set               (ow_sprites)


class BossSpriteSet(Enum):
    A = auto()  # vanilla: levels 1, 2, 5, 7
    B = auto()  # vanilla: levels 3, 4, 6, 8
    C = auto()  # vanilla: level 9 only


class QuestVisibility(Enum):
    BOTH_QUESTS    = auto()
    FIRST_QUEST    = auto()
    SECOND_QUEST   = auto()
    # ROM code 0b11: not in vanilla; the cave pass writes it on the armos
    # screen (OW-CAVE-05 step 4). IsQuestSecretMismatch reads it one byte past
    # SecretQuestNumbers, a value that matches neither quest (QUESTIONS #14).
    NEITHER_QUEST  = auto()


class SecretSize(Enum):
    SMALL  = auto()
    MEDIUM = auto()
    LARGE  = auto()


class ShopType(Enum):
    SHOP_A = auto()  # SHOP_1
    SHOP_B = auto()  # SHOP_2
    SHOP_C = auto()  # SHOP_3
    SHOP_D = auto()  # SHOP_4
    SHOP_E = auto()  # POTION_SHOP


class HintVariant(Enum):
    LOST_HILLS = auto()
    DEAD_WOODS = auto()


class TollOption(Enum):
    """What a life-or-money merchant asks the player to leave (PS-MERCH-02);
    the value is the word in the toll text."""
    LIFE = "LIFE"
    MAX_BOMBS = "MAX BOMBS"
    KEYS = "KEYS"
    MONEY = "MONEY"
