from typing import NewType
from enum import IntEnum

LevelNum = int
CaveNum = int
RoomNum = NewType("RoomNum", int)
PositionNum = NewType("PositionNum", int)


class Range():
  VALID_ROOM_NUMBERS = range(0, 0x80)  # 128 rooms (0-indexed)
  VALID_ROOM_TABLE_NUMBERS = range(0, 6)  # Six tables (0-indexed)
  VALID_LEVEL_NUMBERS = range(1, 10)  # Levels 1-9 (1-indexed)
  VALID_LEVEL_AND_CAVE_NUMBERS = range(1, 11)  # L1-9 plus L10 repreenting OW caves (1-indexed)
  VALID_ITEM_NUMBERS = range(0, 0x40)
  VALID_CAVE_NUMBERS = range(0, 0x16)  # Includes 20 actual +2 virtual caves 0-19, 20-21.
  VALID_CAVE_POSITION_NUMBERS = range(1, 4)  # Three possible positions per cave (1-indexed)


class Direction(IntEnum):
    NORTH = -0x10
    WEST = -0x1
    STAIRCASE = 0
    EAST = 0x1
    SOUTH = 0x10

    def inverse(self) -> "Direction":
      if self == Direction.NORTH:
          return Direction.SOUTH
      elif self == Direction.SOUTH:
          return Direction.NORTH
      elif self == Direction.WEST:
          return Direction.EAST
      elif self == Direction.EAST:
          return Direction.WEST
      return Direction.STAIRCASE


class Item(IntEnum):
  BOMBS = 0x00
  WOOD_SWORD = 0x01
  WHITE_SWORD = 0x02
  MAGICAL_SWORD = 0x03
  NO_ITEM = 0x03
  BAIT = 0x04
  RECORDER = 0x05
  BLUE_CANDLE = 0x06
  RED_CANDLE = 0x07
  WOOD_ARROWS = 0x08
  SILVER_ARROWS = 0x09
  BOW = 0x0A
  MAGICAL_KEY = 0x0B
  RAFT = 0x0C
  LADDER = 0x0D
  TRIFORCE_OF_POWER = 0x0E
  FIVE_RUPEES = 0x0F
  WAND = 0x10
  BOOK = 0x11
  BLUE_RING = 0x12
  RED_RING = 0x13
  POWER_BRACELET = 0x14
  LETTER = 0x15
  COMPASS = 0x16
  MAP = 0x17
  RUPEE = 0x18
  KEY = 0x19
  HEART_CONTAINER = 0x1A
  TRIFORCE = 0x1B
  MAGICAL_SHIELD = 0x1C
  WOOD_BOOMERANG = 0x1D
  MAGICAL_BOOMERANG = 0x1E
  BLUE_POTION = 0x1F
  RED_POTION = 0x20
  SINGLE_HEART = 0x22
  FAIRY = 0x23
  OVERWORLD_NO_ITEM = 0x3F
  BEAST_DEFEATED_VIRTUAL_ITEM = 0x98
  KIDNAPPED_RESCUED_VIRTUAL_ITEM = 0x99
  LOST_HILLS_HINT_VIRTUAL_ITEM = 0x9A
  DEAD_WOODS_HINT_VIRTUAL_ITEM = 0x9B

  def IsProgressiveUpgradeItem(self):
    return self in [Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.BLUE_CANDLE, Item.RED_CANDLE,
       Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.BLUE_RING, Item.RED_RING]

  def IsMinorDungeonItem(self):
    """Returns True for minor dungeon items that can be shuffled (bombs, keys, rupees).

    Note: MAP and COMPASS are not considered minor items as they never shuffle between levels.
    """
    return self in [Item.BOMBS, Item.FIVE_RUPEES, Item.KEY]

  def IsMajorItem(self):
      # Check if the current item is one of the sword items
      return self in [Item.WOOD_SWORD, Item.WHITE_SWORD, Item.MAGICAL_SWORD, Item.RECORDER,
          Item.BLUE_CANDLE, Item.RED_CANDLE, Item.WOOD_ARROWS, Item.SILVER_ARROWS, Item.BOW,
          Item.MAGICAL_KEY, Item.RAFT, Item.LADDER, Item.WAND, Item.BOOK, Item.BLUE_RING, 
          Item.RED_RING, Item.POWER_BRACELET, Item.HEART_CONTAINER, Item.WOOD_BOOMERANG, 
          Item.MAGICAL_BOOMERANG]

class RoomType(IntEnum):
  PLAIN_ROOM = 0x00
  SPIKE_TRAP_ROOM = 0x01
  FOUR_SHORT_ROOM = 0x02
  FOUR_TALL_ROOM = 0x03
  AQUAMENTUS_ROOM = 0x04
  GLEEOK_ROOM = 0x05
  GOHMA_ROOM = 0x06
  THREE_ROWS = 0x07
  REVERSE_C = 0x08
  CIRCLE_WALL = 0x09
  DOUBLE_BLOCK = 0x0A
  LAVA_MOAT = 0x0B
  MAZE_ROOM = 0x0C
  GRID_ROOM = 0x0D
  VERTICAL_CHUTE_ROOM = 0x0E
  HORIZONTAL_CHUTE_ROOM = 0x0F
  VERTICAL_ROWS = 0x10
  ZIGZAG_ROOM = 0x11
  T_ROOM = 0x12
  VERTICAL_MOAT_ROOM = 0x13
  CIRCLE_MOAT_ROOM = 0x14
  POINTLESS_MOAT_ROOM = 0x15
  CHEVY_ROOM = 0x16
  NSU = 0x17
  HORIZONTAL_MOAT_ROOM = 0x18
  DOUBLE_MOAT_ROOM = 0x19
  DIAMOND_STAIR_ROOM = 0x1A
  NARROW_STAIR_ROOM = 0x1B
  SPIRAL_STAIR_ROOM = 0x1C
  DOUBLE_SIX_BLOCK_ROOM = 0x1D
  SINGLE_SIX_BLOCK_ROOM = 0x1E
  FIVE_PAIR_ROOM = 0x1F
  TURNSTILE_ROOM = 0x20
  ENTRANCE_ROOM = 0x21
  SINGLE_BLOCK_ROOM = 0x22
  TWO_FIREBALL_ROOM = 0x23
  FOUR_FIREBALL_ROOM = 0x24
  DESERT_ROOM = 0x25
  BLACK_ROOM = 0x26
  ZELDA_ROOM = 0x27
  GANNON_ROOM = 0x28
  TRIFORCE_ROOM = 0x29
  TRANSPORT_STAIRCASE = 0x3E
  ITEM_STAIRCASE = 0x3F
  
  def HasOpenStaircase(self):
    return self in [
        RoomType.DIAMOND_STAIR_ROOM,
        RoomType.NARROW_STAIR_ROOM,
        RoomType.SPIRAL_STAIR_ROOM
    ]

  def CanHavePushBlock(self):
    return self in [
        RoomType.SPIKE_TRAP_ROOM,
        RoomType.GOHMA_ROOM,
        RoomType.THREE_ROWS,
        RoomType.REVERSE_C,
        RoomType.CIRCLE_WALL,
        RoomType.DOUBLE_BLOCK,
        RoomType.MAZE_ROOM,
        RoomType.GRID_ROOM,
        RoomType.ZIGZAG_ROOM,
        RoomType.FIVE_PAIR_ROOM,
        RoomType.SINGLE_BLOCK_ROOM,
    ]
    
class DropLocation(IntEnum):
    MIDDLE = 0
    TOP_RIGHT = 1
    BOTTOM_LEFT = 2
    RIGHT = 3

ValidDropLocations = {
    RoomType.PLAIN_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.SPIKE_TRAP_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.FOUR_SHORT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.FOUR_TALL_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.AQUAMENTUS_ROOM: [DropLocation.RIGHT, DropLocation.MIDDLE, DropLocation.BOTTOM_LEFT],
    RoomType.GLEEOK_ROOM: [DropLocation.BOTTOM_LEFT, DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.GOHMA_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT],
    RoomType.THREE_ROWS: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.REVERSE_C: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.CIRCLE_WALL: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.DOUBLE_BLOCK: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.LAVA_MOAT: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.MAZE_ROOM: [DropLocation.RIGHT, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.GRID_ROOM: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.VERTICAL_CHUTE_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.HORIZONTAL_CHUTE_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.VERTICAL_ROWS: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.ZIGZAG_ROOM: [DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.T_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.VERTICAL_MOAT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.CIRCLE_MOAT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.POINTLESS_MOAT_ROOM: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.CHEVY_ROOM: [DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.NSU: [DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.HORIZONTAL_MOAT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.DOUBLE_MOAT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.DIAMOND_STAIR_ROOM: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.NARROW_STAIR_ROOM: [DropLocation.MIDDLE, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.SPIRAL_STAIR_ROOM: [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.DOUBLE_SIX_BLOCK_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.SINGLE_SIX_BLOCK_ROOM: [DropLocation.RIGHT, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.FIVE_PAIR_ROOM: [DropLocation.RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.TOP_RIGHT],
    RoomType.TURNSTILE_ROOM: [DropLocation.RIGHT],
    RoomType.ENTRANCE_ROOM: [DropLocation.MIDDLE],
    RoomType.SINGLE_BLOCK_ROOM: [DropLocation.RIGHT, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.TWO_FIREBALL_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.FOUR_FIREBALL_ROOM: [DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.DESERT_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.BLACK_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT],
    RoomType.ZELDA_ROOM: [DropLocation.MIDDLE],
    RoomType.GANNON_ROOM: [DropLocation.MIDDLE, DropLocation.RIGHT],
    RoomType.TRIFORCE_ROOM: [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT],
    RoomType.TRANSPORT_STAIRCASE: [],
    RoomType.ITEM_STAIRCASE: []
}

def getAccessibleItemLocations(room, entry_direction, has_ladder):
    if ( room == RoomType.LAVA_MOAT ):
        if ( entry_direction == Direction.SOUTH ):
            if ( has_ladder ):
                return [DropLocation.BOTTOM_LEFT, DropLocation.MIDDLE]
            else:
                return [DropLocation.MIDDLE]
        elif ( entry_direction == Direction.WEST ):
            if ( has_ladder ):
                return [DropLocation.BOTTOM_LEFT, DropLocation.MIDDLE]
            else:
                return [DropLocation.BOTTOM_LEFT]
        else:
            return [DropLocation.TOP_RIGHT]

    if ( room == RoomType.VERTICAL_CHUTE_ROOM ):
        if ( entry_direction == Direction.WEST ):
            return [DropLocation.BOTTOM_LEFT]
        elif ( entry_direction == Direction.EAST ):
            return [DropLocation.RIGHT, DropLocation.TOP_RIGHT]
        else:
            return [DropLocation.MIDDLE]

    if ( room == RoomType.HORIZONTAL_CHUTE_ROOM ):
        if ( entry_direction == Direction.SOUTH ):
            return [DropLocation.BOTTOM_LEFT]
        elif ( entry_direction == Direction.NORTH ):
            return [DropLocation.RIGHT, DropLocation.TOP_RIGHT]
        else:
            return [DropLocation.MIDDLE, DropLocation.RIGHT]

    if ( room == RoomType.T_ROOM ):
        if ( entry_direction == Direction.SOUTH ):
            return [DropLocation.MIDDLE]
        else:
            return [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT]

    if ( room == RoomType.VERTICAL_MOAT_ROOM ):
        if ( has_ladder ):
            return [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT]
        elif ( entry_direction == Direction.EAST ):
            return [DropLocation.RIGHT, DropLocation.TOP_RIGHT]
        else:
            return [DropLocation.MIDDLE, DropLocation.BOTTOM_LEFT]

    if ( room == RoomType.HORIZONTAL_MOAT_ROOM ):
        if ( has_ladder ):
            return [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT]
        elif ( entry_direction == Direction.NORTH ):
            return [DropLocation.TOP_RIGHT]
        else:
            return [DropLocation.MIDDLE, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT]

    if ( room == RoomType.CIRCLE_MOAT_ROOM ):
        if ( has_ladder ):
            return [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT]
        else:
            return [DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT]

    if ( room == RoomType.CHEVY_ROOM ):
        if ( has_ladder ):
            return [DropLocation.MIDDLE, DropLocation.RIGHT]
        elif ( entry_direction == Direction.EAST ):
            return [DropLocation.RIGHT]
        else:
            return []
            
    if ( room == RoomType.DOUBLE_MOAT_ROOM ):
        if ( has_ladder ):
            return [DropLocation.MIDDLE, DropLocation.TOP_RIGHT, DropLocation.BOTTOM_LEFT, DropLocation.RIGHT]
        elif ( entry_direction == Direction.WEST or entry_direction == Direction.EAST ):
            return [DropLocation.MIDDLE, DropLocation.RIGHT]
        else:
            return []

    return ValidDropLocations[room]

class Enemy(IntEnum):
  NOTHING = 0x00
  BLUE_LYNEL = 0x01
  RED_LYNEL =  0x02
  BLUE_MOBLIN = 0x03
  RED_MOBLIN = 0x04
  BLUE_GORIYA = 0x05
  RED_GORIYA = 0x06
  RED_OCTOROK_1 = 0x07
  RED_OCTOROK_2 = 0x08
  BLUE_OCTOROK_1 = 0x09
  BLUE_OCTOROK_2 = 0x0A
  RED_DARKNUT = 0x0B
  BLUE_DARKNUT = 0x0C
  BLUE_TEKTITE = 0x0D
  RED_TEKTITE = 0x0E
  BLUE_LEVER = 0x0F
  RED_LEVER = 0x10
  VIRE = 0x12
  ZOL = 0x13
  GEL_1 = 0x14
  GEL_2 = 0x15
  POLS_VOICE = 0x16
  LIKE_LIKE = 0x17
  PEAHAT = 0x1A
  BLUE_KEESE = 0x1B
  RED_KEESE = 0x1C
  DARK_KEESE = 0x1D
  ARMOS = 0x1E
  FALLING_ROCKS = 0x1F
  FALLING_ROCK = 0x20
  GHINI_1 = 0x21
  GHINI_2 = 0x22
  RED_WIZZROBE = 0x23
  BLUE_WIZZROBE = 0x24
  WALLMASTER = 0x27
  ROPE = 0x28
  STALFOS = 0x2A
  BUBBLE = 0x2B
  BLUE_BUBBLE = 0x2C
  RED_BUBBLE = 0x2D
  GIBDO = 0x30
  TRIPLE_DODONGO = 0x31
  SINGLE_DODONGO = 0x32
  BLUE_GOHMA = 0x33
  RED_GOHMA = 0x34
  RUPEE_BOSS = 0x35
  HUNGRY_GORIYA = 0x36
  THE_KIDNAPPED = 0x37
  TRIPLE_DIGDOGGER = 0x38
  SINGLE_DIGDOGGER = 0x39
  RED_LANMOLA = 0x3A
  BLUE_LANMOLA = 0x3B
  MANHANDALA = 0x3C
  AQUAMENTUS = 0x3D
  THE_BEAST = 0x3E
  MOLDORM = 0x41
  GLEEOK_1 = 0x42
  GLEEOK_2 = 0x43
  GLEEOK_3 = 0x44
  GLEEOK_4 = 0x45
  PATRA_2 = 0x47
  PATRA_1 = 0x48
  THREE_PAIRS_OF_TRAPS = 0x49
  CORNER_TRAPS = 0x4A
  OLD_MAN = 0x4B
  OLD_MAN_2 = 0x4C
  OLD_MAN_3 = 0x4D
  OLD_MAN_4 = 0x4E
  BOMB_UPGRADER = 0x4F
  OLD_MAN_5 = 0x50
  MUGGER = 0x51
  OLD_MAN_6 = 0x52

  # Mixed enemy groups (0x62-0x7F) are read dynamically from ROM data
  # These enum values are placeholders that represent mixed groups
  # The actual enemies in each group are determined by reading the ROM
  MIXED_ENEMY_GROUP_1 = 0x62
  MIXED_ENEMY_GROUP_2 = 0x63
  MIXED_ENEMY_GROUP_3 = 0x64
  MIXED_ENEMY_GROUP_4 = 0x65
  MIXED_ENEMY_GROUP_5 = 0x66
  MIXED_ENEMY_GROUP_6 = 0x67
  MIXED_ENEMY_GROUP_7 = 0x68
  MIXED_ENEMY_GROUP_8 = 0x69
  MIXED_ENEMY_GROUP_9 = 0x6A
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
  
  def IsGleeokOrPatra(self):
    return self in [
      Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.GLEEOK_3, Enemy.GLEEOK_4, Enemy.PATRA_1, Enemy.PATRA_2
    ]


class WallType(IntEnum):
  OPEN_DOOR = 0
  SOLID_WALL = 1
  WALK_THROUGH_WALL_1 = 2
  WALK_THROUGH_WALL_2 = 3
  BOMB_HOLE = 4
  LOCKED_DOOR_1 = 5
  LOCKED_DOOR_2 = 6
  SHUTTER_DOOR = 7

class CaveType(IntEnum):
  NONE = 0x00
  LEVEL_1 = 0x01
  LEVEL_2 = 0x02
  LEVEL_3 = 0x03
  LEVEL_4 = 0x04
  LEVEL_5 = 0x05
  LEVEL_6 = 0x06
  LEVEL_7 = 0x07
  LEVEL_8 = 0x08
  LEVEL_9 = 0x09
  WOOD_SWORD_CAVE = 0x10
  TAKE_ANY = 0x11
  WHITE_SWORD_CAVE = 0x12
  MAGICAL_SWORD_CAVE = 0x13
  ANY_ROAD = 0x14
  LOST_HILLS_HINT = 0x15
  MONEY_MAKING_GAME = 0x16
  DOOR_REPAIR = 0x17
  LETTER_CAVE = 0x18
  DEAD_WOODS_HINT = 0x19
  POTION_SHOP = 0x1A
  HINT_SHOP_1 = 0x1B
  HINT_SHOP_2 = 0x1C
  SHOP_1 = 0x1D
  SHOP_2 = 0x1E
  SHOP_3 = 0x1F
  SHOP_4 = 0x20
  MEDIUM_SECRET = 0x21
  LARGE_SECRET = 0x22
  SMALL_SECRET = 0x23
  # Virtual caves for overworld items (Armos and Coast)
  ARMOS_ITEM = 0x24
  COAST_ITEM = 0x25


class RoomAction(IntEnum):
  """Room action codes that determine what triggers open shutters/spawn items.

  These codes are stored in the lowest 3 bits of room table 5 (0-indexed).
  Also known as SecretTrigger codes in the disassembly.
  """
  NothingOpensShutters = 0
  KillingEnemiesOpensShutters = 1
  KillingRingleaderKillsEnemiesAndOpensShutters = 2
  TriforceOfPowerOpensShutters = 3
  PushingBlockOpensShutters = 4
  PushingBlockMakesStairwayVisible = 5
  DefeatingNPCOpensShutters = 6
  KillingEnemiesOpensShuttersAndDropsItem = 7


class HintType(IntEnum):
  WOOD_SWORD_CAVE = 1
  MAGICAL_SWORD_CAVE = 2
  ANY_ROAD = 3
  LOST_HILLS_HINT = 4
  MONEY_MAKING_GAME = 5
  DOOR_REPAIR = 6
  LETTER_CAVE = 7
  DEAD_WOODS_HINT = 8
  POTION_SHOP = 9
  HINT_10 = 10
  WHITE_SWORD_CAVE = 11
  HINT_12 = 12
  HINT_13 = 13
  HINT_14 = 14
  SHOP_1 = 15
  SHOP_2 = 16
  TAKE_ANY = 17
  SECRET = 18
  HUNGRY_ENEMY = 19
  HINT_20 = 20
  HINT_21 = 21
  HINT_22 = 22
  HINT_23 = 23
  HINT_24 = 24
  HINT_25 = 25
  BOMB_UPGRADE = 26
  MUGGER = 27
  HINT_28 = 28
  HINT_29 = 29
  HINT_30 = 30
  HINT_31 = 31
  HINT_32 = 32
  HINT_33 = 33
  TRIFORCE_CHECK = 34
  HINT_35 = 35
  HINT_36 = 36
  HINT_37 = 37
  HINT_38 = 38
  OTHER = 39
