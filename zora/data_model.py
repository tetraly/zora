from dataclasses import dataclass, field
from enum import Enum, IntEnum, auto
from typing import ClassVar, TypeVar

T = TypeVar("T")


class Direction(IntEnum):
    WEST  = -0x01
    EAST  = +0x01
    NORTH = -0x10
    SOUTH = +0x10
    STAIRCASE = 0x20  # pseudo-direction used for staircase room traversal


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
    GANNON_ROOM            = 0x28
    TRIFORCE_ROOM          = 0x29
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
    NOTHING         = 0x18  # also the rupee code in the overworld; unused in dungeons → NOTHING sentinel
    KEY             = 0x19
    HEART_CONTAINER = 0x1A
    TRIFORCE        = 0x1B
    MAGICAL_SHIELD  = 0x1C
    WOOD_BOOMERANG  = 0x1D
    MAGICAL_BOOMERANG = 0x1E
    BLUE_POTION     = 0x1F
    RED_POTION      = 0x20
    SINGLE_HEART    = 0x22
    FAIRY           = 0x23
    OVERWORLD_NO_ITEM = 0x3F
    # Virtual items — not ROM values, used only by the validator
    BEAST_DEFEATED_VIRTUAL_ITEM        = 0x40
    KIDNAPPED_RESCUED_VIRTUAL_ITEM     = 0x41
    LOST_HILLS_HINT_VIRTUAL_ITEM       = 0x42
    DEAD_WOODS_HINT_VIRTUAL_ITEM       = 0x43


class RoomAction(IntEnum):
    NOTHING_OPENS_SHUTTERS                         = 0
    KILLING_ENEMIES_OPENS_SHUTTERS                 = 1
    KILLING_RINGLEADER_KILLS_ENEMIES_OPENS_SHUTTERS = 2
    TRIFORCE_OF_POWER_OPENS_SHUTTERS               = 3
    PUSHING_BLOCK_OPENS_SHUTTERS                   = 4
    PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE           = 5
    DEFEATING_NPC_OPENS_SHUTTERS                   = 6
    KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM  = 7

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

class EntranceType(Enum):
    NONE                    = auto()
    OPEN                    = auto()
    BOMB                    = auto()
    LADDER                  = auto()
    LADDER_AND_BOMB         = auto()
    RAFT                    = auto()
    RAFT_AND_BOMB           = auto()
    CANDLE                  = auto()
    RECORDER                = auto()
    POWER_BRACELET          = auto()
    POWER_BRACELET_AND_BOMB = auto()
    LOST_HILLS_HINT         = auto()
    DEAD_WOODS_HINT         = auto()


# Lookup from overworld screen number → EntranceType.
# Screens not in this dict have no entrance (open field, water, etc.) → NONE.
# Lookup from overworld screen number → EntranceType.
SCREEN_ENTRANCE_TYPES: dict[int, "EntranceType"] = {}  # populated after EntranceType defined


def _build_screen_entrance_types() -> dict[int, "EntranceType"]:
    str_to_entrance = {
        "Open":           EntranceType.OPEN,
        "Bomb":           EntranceType.BOMB,
        "Ladder":         EntranceType.LADDER,
        "Ladder+Bomb":    EntranceType.LADDER_AND_BOMB,
        "Raft":           EntranceType.RAFT,
        "Candle":         EntranceType.CANDLE,
        "Recorder":       EntranceType.RECORDER,
        "Power Bracelet": EntranceType.POWER_BRACELET,
    }
    raw = {
        0x00: "Bomb",  0x01: "Bomb",  0x02: "Bomb",  0x03: "Bomb",
        0x04: "Open",  0x05: "Bomb",  0x06: "Recorder", 0x07: "Bomb",
        0x09: "Power Bracelet", 0x0A: "Open", 0x0B: "Open", 0x0C: "Open",
        0x0D: "Bomb",  0x0E: "Open",  0x0F: "Open",  0x10: "Bomb",
        0x11: "Power Bracelet", 0x12: "Bomb", 0x13: "Bomb", 0x14: "Bomb",
        0x15: "Bomb",  0x16: "Bomb",  0x18: "Ladder+Bomb", 0x19: "Ladder+Bomb",
        0x1A: "Open",  0x1B: "Power Bracelet", 0x1C: "Open", 0x1D: "Power Bracelet",
        0x1E: "Bomb",  0x1F: "Open",  0x20: "Open",  0x21: "Open",
        0x22: "Open",  0x23: "Power Bracelet", 0x24: "Open", 0x25: "Open",
        0x26: "Bomb",  0x27: "Bomb",  0x28: "Candle", 0x29: "Recorder",
        0x2B: "Recorder", 0x2C: "Bomb", 0x2D: "Bomb", 0x2F: "Raft",
        0x30: "Recorder", 0x33: "Bomb", 0x34: "Open", 0x37: "Open",
        0x3A: "Recorder", 0x3C: "Recorder", 0x3D: "Open", 0x42: "Recorder",
        0x44: "Open",  0x45: "Raft",  0x46: "Candle", 0x47: "Candle",
        0x48: "Candle", 0x49: "Power Bracelet", 0x4A: "Open", 0x4B: "Candle",
        0x4D: "Candle", 0x4E: "Open", 0x51: "Candle", 0x53: "Candle",
        0x56: "Candle", 0x58: "Recorder", 0x5B: "Candle", 0x5E: "Open",
        0x5F: "Ladder", 0x60: "Recorder", 0x62: "Candle", 0x63: "Candle",
        0x64: "Open",  0x66: "Open",  0x67: "Bomb",  0x68: "Candle",
        0x6A: "Candle", 0x6B: "Candle", 0x6C: "Candle", 0x6D: "Candle",
        0x6E: "Recorder", 0x6F: "Open", 0x70: "Open", 0x71: "Bomb",
        0x72: "Recorder", 0x74: "Open", 0x75: "Open", 0x76: "Bomb",
        0x77: "Open",  0x78: "Candle", 0x79: "Power Bracelet", 0x7B: "Bomb",
        0x7C: "Bomb",  0x7D: "Bomb",
    }
    return {screen: str_to_entrance[label] for screen, label in raw.items()}


SCREEN_ENTRANCE_TYPES = _build_screen_entrance_types()


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


# --- Dataclasses ---

@dataclass
class WallSet:
    north: WallType
    east:  WallType
    south: WallType
    west:  WallType

    _DIR_TO_ATTR: ClassVar[dict[Direction, str]] = {
        Direction.NORTH: 'north',
        Direction.EAST:  'east',
        Direction.SOUTH: 'south',
        Direction.WEST:  'west',
    }

    def __getitem__(self, direction: Direction) -> WallType:
        result: WallType = getattr(self, self._DIR_TO_ATTR[direction])
        return result

    def __setitem__(self, direction: Direction, value: WallType) -> None:
        setattr(self, self._DIR_TO_ATTR[direction], value)


@dataclass
class EnemySpec:
    enemy: Enemy
    is_group: bool = False
    group_members: list[Enemy] | None = None

    def __post_init__(self) -> None:
        if self.is_group:
            assert self.group_members is not None and len(self.group_members) == 8
            self.actual_enemies: list[Enemy] = list(self.group_members)
        else:
            assert self.group_members is None
            self.actual_enemies = [self.enemy]


@dataclass
class Room:
    room_num: int
    room_type: RoomType
    walls: WallSet
    enemy_spec: EnemySpec
    enemy_quantity: int
    item: Item
    item_position: ItemPosition
    room_action: RoomAction
    is_dark: bool
    boss_cry_1: bool
    boss_cry_2: bool
    movable_block: bool
    palette_0: int   # bits 1-0 of table 0 — preserved for round-trip
    palette_1: int   # bits 1-0 of table 1 — preserved for round-trip


@dataclass
class StaircaseRoom:
    room_num: int
    room_type: RoomType             # ITEM_STAIRCASE or TRANSPORT_STAIRCASE
    exit_x: int                     # t2 upper 4 bits — X position exiting staircase
    exit_y: int                     # t2 lower 4 bits — Y position exiting staircase
    # ITEM_STAIRCASE fields
    item: Item | None = None
    return_dest: int | None = None   # screen location Link returns to after item
    # TRANSPORT_STAIRCASE fields
    left_exit: int | None = None    # left door destination (t0 bits 6-0)
    right_exit: int | None = None   # right door destination (t1 bits 6-0)
    # Preserved raw bytes (not semantically meaningful for staircase rooms)
    t5_raw: int = 0


@dataclass
class Level:
    level_num: int
    entrance_room: int
    entrance_direction: Direction
    palette_raw: bytes               # 0x24 bytes: PPU header + 8 groups of 4 color bytes
    fade_palette_raw: bytes          # 0x60 bytes: stairway/death-fade palettes (block +0x7C)
    staircase_room_pool: list[int]
    rooms: list[Room]
    staircase_rooms: list[StaircaseRoom]
    boss_room: int
    enemy_sprite_set: EnemySpriteSet
    boss_sprite_set: BossSpriteSet
    # Preserved for round-trip (not randomized)
    start_y: int
    item_position_table: list[int]  # 4 packed 0xXY bytes: high nibble=X tile, low nibble=Y tile
    map_start: int
    map_cursor_offset: int
    map_data: bytes              # 16 bytes: column occupancy bitmap (block 0x3F–0x4E)
    map_ppu_commands: bytes      # 45 bytes: PPU command sequences (block 0x4F–0x7B)
    qty_table: list[int]         # 4 bytes, preserved
    stairway_data_raw: bytes     # 10 bytes, preserved verbatim for round-trip
    rom_level_num: int = 0       # block[0x33]: ROM's display level number (differs from slot in Q2)
    # Offset in cartridge RAM for screen status (level_info +0x31, 2 bytes).
    # Vanilla value varies per level. Setting to 0xF0xx gives Link invincibility.
    # Preserved verbatim — not randomized.
    screen_status_ram_offset: bytes = b"\x00\x00"

    def palette_colors(self) -> list[int]:
        """Return the 8 color values (byte[1] of each 4-byte group after the 3-byte PPU header)."""
        data = self.palette_raw[3:3 + 32]  # 8 groups x 4 bytes
        return [data[g * 4 + 1] for g in range(8)]



# --- Cave component types ---

@dataclass
class Quote:
    quote_id: int
    text: str

@dataclass
class ShopItem:
    item: Item
    price: int

@dataclass
class HintShopItem:
    quote_id: int
    price: int

# --- Cave definitions ---

@dataclass
class OverworldItem:
    """Item obtainable directly on the overworld, no cave entrance (Armos, Coast)."""
    destination: Destination
    item: Item
    ladder_requirement: bool = False

@dataclass
class ItemCave:
    """Single-item cave with a quote and optional heart requirement (sword caves, letter cave)."""
    destination: Destination
    item: Item
    quote_id: int
    maybe_extra_candle: Item = Item.OVERWORLD_NO_ITEM
    heart_requirement: int = 0

@dataclass
class SecretCave:
    """Rupee secret (under a bush, rock, etc.); positive = reward, negative = penalty."""
    destination: Destination
    quote_id: int
    rupee_value: int

@dataclass
class DoorRepairCave:
    """Cave that charges rupees for a broken door."""
    destination: Destination
    quote_id: int
    cost: int  # vanilla = 20, randomizable; stored positive, applied as a penalty

@dataclass
class HintCave:
    """Cave containing only a hint; no item."""
    destination: Destination
    quote_id: int  # hint variant is derivable from quote_id

@dataclass
class TakeAnyCave:
    """Cave offering a choice of items."""
    destination: Destination
    quote_id: int
    items: list[Item] = field(default_factory=lambda: [Item.RED_POTION, Item.OVERWORLD_NO_ITEM, Item.HEART_CONTAINER])

@dataclass
class Shop:
    """Shop with 2 or 3 priced items; may require letter."""
    destination: Destination
    quote_id: int
    shop_type: ShopType
    letter_requirement: bool
    items: list[ShopItem]  # 2 or 3 items (potion shop has 2)

@dataclass
class HintShop:
    """Shop selling hints at a price, with an entry quote."""
    destination: Destination
    quote_id: int
    hints: list[HintShopItem]  # exactly 3

@dataclass
class MoneyMakingGameCave:
    """The money-making game cave with bet amounts and prize/penalty outcomes."""
    destination: Destination
    quote_id: int
    bet_low: int
    bet_mid: int
    bet_high: int
    lose_small: int    # vanilla = -10
    lose_small_2: int  # vanilla = -10 (second losing bucket)
    lose_large: int    # vanilla = -40
    win_small: int     # vanilla = +20
    win_large: int     # vanilla = +50


@dataclass
class BombUpgrade:
    cost: int    # rupees charged for the upgrade (vanilla = 100)
    count: int   # bombs added to MaxBombs (vanilla = 4)


@dataclass
class Screen:
    screen_num: int
    destination: Destination
    entrance_type: EntranceType
    enemy_spec: EnemySpec
    enemy_quantity: int
    exit_x_position: int
    exit_y_position: int
    has_zola: bool
    has_ocean_sound: bool
    enemies_from_sides: bool
    stairs_position_code: int
    quest_visibility: QuestVisibility  # table 5 bits 7-6
    outer_palette: int   # table 0 bits 1-0: code for outer border palette
    inner_palette: int   # table 1 bits 1-0: code for inner section palette
    screen_code: int     # table 3 bits 6-0: visual map screen code

# --- Union type ---

CaveDefinition = (
    OverworldItem
    | ItemCave
    | SecretCave
    | DoorRepairCave
    | HintCave
    | TakeAnyCave
    | Shop
    | HintShop
    | MoneyMakingGameCave
)

@dataclass
class Overworld:
    screens: list[Screen]
    enemy_sprite_set: EnemySpriteSet
    caves: list[CaveDefinition]
    qty_table: list[int]   # 4-entry quantity lookup (level_info block 0 bytes 0x24-0x27)

    # Direction sequences for the Lost Hills and Dead Woods maze puzzles.
    # Each is a list of 4 OverworldDirection values stored at ROM 0x6DA7-0x6DAE.
    # Dead Woods: 0x6DA7-0x6DAA. Lost Hills: 0x6DAB-0x6DAE.
    dead_woods_directions: list[OverworldDirection]
    lost_hills_directions: list[OverworldDirection]
    # Armos statue lookup tables (ROM 0x10CB2, bank 4): 7 screen IDs and 7 sprite
    # X-positions. The game engine reads armos_screen_ids[0] to find which overworld
    # screen holds the active armos item, and armos_positions[0] for the sprite position.
    armos_screen_ids: list[int]   # 7 entries
    armos_positions:  list[int]   # 7 entries
    bomb_upgrade: BombUpgrade
    any_road_screens: list[int]
    recorder_warp_destinations: list[int]
    recorder_warp_y_coordinates: list[int]
    start_screen: int
    start_position_y: int  # ROM offset 0x19328+header; calculated as screen_widths[start_screen] * 16 + 13

    # Raw cave data preserved for round-trip serialization
    #cave_item_data_raw: bytes = b''
    #cave_price_data_raw: bytes = b''

    def get_cave(self, destination: Destination, cave_type: type[T]) -> T | None:
        """Return the cave at the given destination if it matches cave_type, else None.

        Usage:
            mmg = ow.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
            # mmg is MoneyMakingGameCave | None — no isinstance needed at call site
        """
        for c in self.caves:
            if c.destination == destination and isinstance(c, cave_type):
                return c
        return None

@dataclass
class SpriteData:
    enemy_set_a:        bytearray   # 0x220 bytes at ENEMY_SET_A_SPRITES_ADDRESS
    enemy_set_b:        bytearray   # 0x220 bytes at ENEMY_SET_B_SPRITES_ADDRESS
    enemy_set_c:        bytearray   # 0x220 bytes at ENEMY_SET_C_SPRITES_ADDRESS
    ow_sprites:         bytearray   # 0x640 bytes at OW_SPRITES_ADDRESS
    boss_set_a:         bytearray   # 0x400 bytes at BOSS_SET_A_SPRITES_ADDRESS
    boss_set_b:         bytearray   # 0x400 bytes at BOSS_SET_B_SPRITES_ADDRESS
    boss_set_c:         bytearray   # 0x400 bytes at BOSS_SET_C_SPRITES_ADDRESS
    boss_set_expansion: bytearray   # 0x200 bytes at BOSS_SET_EXPANSION_SPRITES_ADDRESS
    dungeon_common:     bytearray   # 0x100 bytes at DUNGEON_COMMON_SPRITES_ADDRESS


@dataclass
class EnemyData:
    # Tile mapping tables (ROM 0x6E14 / 0x6E93).
    # The pointer table has 0x7F slots:
    #   slot 0          = player (Link) — not an Enemy enum value
    #   slots 1-0x53    = Enemy enum values 0x00-0x52 (slot = enemy_id + 1)
    #   slots 0x54-0x7E = overworld NPC sprite variants (43 entries)
    # Each pointer is an index into the tile_frames buffer.
    # Enemies sharing the same pointer share the same frame list.

    # Slot 0: player character (Link)
    player_pointer: int
    player_tiles:   list[int]

    # Slots 1-0x53: one entry per Enemy enum value (0x00-0x52), keyed by Enemy
    tile_pointers: dict["Enemy", int]    # enemy -> index into frame data buffer
    tile_frames:   dict["Enemy", list[int]]  # enemy -> list of tile codes

    # Slots 0x54-0x7E: overworld NPC sprite variants (43 entries, fixed order)
    overworld_npc_pointers: list[int]          # 43 pointer values
    overworld_npc_frames:   list[list[int]]    # 43 frame tile lists

    # HP for all enemies and bosses, keyed by Enemy enum.
    # Values are raw nibbles (0-15); actual HP in-game = value × 0x10 (value << 4).
    # Stored in ROM as nibble pairs:
    #   Enemy HP table:  0x1FB5E (26 bytes, 52 nibbles, Enemy 0x00-0x33)
    #   Boss HP table:   0x1FB78 (12 bytes, 24 nibbles, Enemy 0x34-0x4B)
    # Entry i occupies: byte = base + (i >> 1), nibble = high if (i & 1 == 0) else low.
    hp: dict["Enemy", int] = field(default_factory=dict)

    # Secondary HP bytes for multi-part bosses. These are separate ROM locations
    # that the engine reads independently from the main hp table above.
    # All values are stored as a full byte = nibble << 4 (i.e. high nibble only).
    #
    # To read from ROM:  value = rom[offset] >> 4
    # To write to ROM:   rom[offset] = value << 4
    #
    # Aquamentus body HP mirrors the main table entry (0x120C6).
    # Aquamentus head HP is independent — randomized separately around a baseline of 6 (0x12735).
    # Ganon mirrors the main table entry (0x12F37).
    # Gleeok mirrors the main table entry (0x114D5).
    # Patra mirrors the main table entry (0x12A45).
    aquamentus_hp: int = 0   # 0x120C6 — body; mirrors hp[Enemy.AQUAMENTUS]
    aquamentus_sp: int = 0   # 0x12735 — head; independently randomized
    ganon_hp: int      = 0   # 0x12F37 — mirrors hp[Enemy.THE_BEAST]
    gleeok_hp: int     = 0   # 0x114D5 — mirrors hp[Enemy.GLEEOK_1] (all Gleeok variants share it)
    patra_hp: int      = 0   # 0x12A45 — mirrors hp[Enemy.PATRA_1] (both Patra variants share it)

    # Set by change_dungeon_enemy_groups after enemy group randomization.
    # Maps each sprite set to the list of Enemy values assigned to that group.
    # Empty dict until the enemy shuffler runs.
    cave_groups: dict["EnemySpriteSet", list["Enemy"]] = field(default_factory=dict)

    # Mixed enemy group definitions: group code (0x62-0x7F) → 8-member list.
    # Populated during parsing from the ROM's mixed enemy data table.
    # Updated by change_dungeon_enemy_groups to keep members compatible with
    # their group's sprite set after shuffling.
    mixed_groups: dict[int, list["Enemy"]] = field(default_factory=dict)

    # Raw mixed enemy data blob and per-group byte offsets within it.
    # Substitutions are applied directly to this blob to preserve the
    # overlapping layout used by the vanilla ROM.  Serialized back as-is.
    mixed_enemy_data: bytearray = field(default_factory=bytearray)
    mixed_group_offsets: dict[int, int] = field(default_factory=dict)

    aquamentus_sprite_ptr: int | None = None
    gleeok_head_sprite_ptr_a: int | None = None
    gleeok_head_sprite_ptr_b: int | None = None
    gleeok_head_sprite_ptr_c: int | None = None


@dataclass
class GameWorld:
    overworld: Overworld
    levels: list[Level]   # exactly 9, index 0 = Level 1
    quotes: list[Quote]   # exactly 38
    sprites: SpriteData
    enemies: EnemyData


# --- Post-definition constants ---


VANILLA_ENEMY_SPRITE_SETS: dict[int, "EnemySpriteSet"] = {
    0: EnemySpriteSet.A,  # overworld
    1: EnemySpriteSet.A, 2: EnemySpriteSet.A, 7: EnemySpriteSet.A,
    3: EnemySpriteSet.B, 5: EnemySpriteSet.B, 8: EnemySpriteSet.B,
    4: EnemySpriteSet.C, 6: EnemySpriteSet.C, 9: EnemySpriteSet.C,
}

VANILLA_BOSS_SPRITE_SETS = {
    1: BossSpriteSet.A, 2: BossSpriteSet.A, 5: BossSpriteSet.A, 7: BossSpriteSet.A,
    3: BossSpriteSet.B, 4: BossSpriteSet.B, 6: BossSpriteSet.B, 8: BossSpriteSet.B,
    9: BossSpriteSet.C,
}
