"""Shuffle dungeon room positions within each level.

Rearranges which room contents appear at which grid positions in each dungeon
level, then fixes up door/wall connectivity and special rooms. The physical
dungeon wall layout is preserved — only the room *contents* move between
positions.

Ported from remapDungeonRooms (Module.cs:99997-102900+).
C# source: ShuffleDungeonRooms.cs (main method) and
           ShuffleDungeonRoomsHelpers.cs (helper methods, not ported yet).


# =============================================================================
# HOW THE NES DUNGEON GRID WORKS
# =============================================================================
#
# Dungeon rooms live in an 8x16 grid (128 positions, numbered 0-127).
# Room N is at row N//16, column N%16. Adjacent rooms:
#   - Left:  N-1  (if N%16 != 0)
#   - Right: N+1  (if N%16 != 15)
#   - Above: N-16 (if N >= 16)
#   - Below: N+16 (if N < 112)
#
# Multiple levels SHARE the same 128-room grid:
#   - Levels 1-6 share one grid  (ROM tables at 0x18700)
#   - Levels 7-9 share a second grid (ROM tables at 0x18A00)
#   - Q2 has its own copies of each grid
#
# The game engine doesn't track level membership explicitly. It places Link
# at a starting room (from the level info block at 0x19300+) and the levels
# are physically isolated by solid walls within the grid. Rooms belong to a
# level by virtue of being reachable from that level's start room.
#
# Our parser.py uses flood fill from each level's start room to determine
# level membership, so Level.rooms already contains exactly the right rooms.
#
#
# =============================================================================
# THE 6 ROM TABLES (per grid)
# =============================================================================
#
# Each grid has 6 parallel tables of 128 bytes (0x80 each), totaling 0x300
# bytes. The tables are:
#
# Table 0 (ROM 0x18700 for grid A) — North/South walls + palette
#   For regular rooms:
#     Bits 7-5: Type of door on north wall (WallType enum, 0-7)
#     Bits 4-2: Type of door on south wall (WallType enum, 0-7)
#     Bits 1-0: Palette 0 code (outer border palette)
#   For staircase rooms (underground passages):
#     Bits 6-0: Destination screen for left exit
#
# Table 1 (ROM 0x18780) — West/East walls + palette
#   For regular rooms:
#     Bits 7-5: Type of door on west wall (WallType enum, 0-7)
#     Bits 4-2: Type of door on east wall (WallType enum, 0-7)
#     Bits 1-0: Palette 1 code (inner section palette)
#   For staircase rooms:
#     Bits 6-0: Destination screen for right exit
#
# Table 2 (ROM 0x18800) — Enemy data
#   For regular rooms:
#     Bits 7-6: Quantity code (0=1, 1=4, 2=5, 3=6 enemies)
#     Bits 5-0: Enemy code (Enemy enum value, 6 bits)
#   For staircase rooms:
#     Bits 7-4: X position exiting underground
#     Bits 3-0: Y position exiting underground
#
# Table 3 (ROM 0x18880) — Screen attributes
#     Bits 5-0: Screen code (RoomType enum value)
#     Bit 6:    Movable block in room (when room is cleared)
#     Bit 7:    Enemies are mixed types (is_group flag)
#
# Table 4 (ROM 0x18900) — Item data
#     Bits 4-0: Room item (Item enum value)
#     Bit 5:    Boss cry sound 1 (Aquamentus, Manhandla, Gleeok, Digdogger)
#     Bit 6:    Boss cry sound 2 (Dodongo, Gohma)
#     Bit 7:    Room is dark
#
# Table 5 (ROM 0x18980) — Room action / item position
#     Bits 5-4: Item position code (ItemPosition enum)
#     Bit 2:    Secret activated / item appears when room is cleared
#     Bit 1:    Room has master enemy (ringleader)
#     Bit 0:    Shutters open / stairway appears when room is cleared
#     Bits 7-6: Unused (never set in vanilla)
#     Bit 3:    Unused
#
#
# =============================================================================
# MAPPING C# VARIABLES TO ROM TABLES
# =============================================================================
#
# The decompiled C# uses misleading variable names. The actual mapping is:
#
#   C# variable  | ROM address | Actual table | Data model fields
#   -------------|-------------|--------------|----------------------------------
#   num2         | 0x18710     | Table 0      | walls.north, walls.south, palette_0
#   num3         | 0x18790     | Table 1      | walls.west, walls.east, palette_1
#   num5         | 0x18810     | Table 2      | enemy_spec, enemy_quantity
#   num6         | 0x18890     | Table 3      | room_type, movable_block, is_group
#   num4         | 0x18910     | Table 4      | item, boss_cry_1, boss_cry_2, is_dark
#   num7         | 0x18990     | Table 5      | item_position, room_action
#
# NOTE: The C# addresses include the 0x10-byte NES header (file offsets).
# The "num4"/"num5"/"num6" labels in the decompilation do NOT correspond to
# Table 4/5/6 — the decompiler named them arbitrarily.
#
#
# =============================================================================
# MAPPING DATA MODEL FIELDS TO ROM TABLE BITS
# =============================================================================
#
#   Data model field       | Table | Bits    | Notes
#   -----------------------|-------|---------|-----------------------------
#   room.walls.north       | 0     | 7-5     | WallType (0-7)
#   room.walls.south       | 0     | 4-2     | WallType (0-7)
#   room.palette_0         | 0     | 1-0     | Outer border palette code
#   room.walls.west        | 1     | 7-5     | WallType (0-7)
#   room.walls.east        | 1     | 4-2     | WallType (0-7)
#   room.palette_1         | 1     | 1-0     | Inner section palette code
#   room.enemy_quantity     | 2     | 7-6     | Quantity code (via qty_table)
#   room.enemy_spec.enemy  | 2     | 5-0     | Enemy code (6 bits)
#   room.room_type         | 3     | 5-0     | RoomType (screen code)
#   room.movable_block     | 3     | 6       | Push block present
#   room.enemy_spec.is_group| 3    | 7       | Mixed enemy types flag
#   room.item              | 4     | 4-0     | Item enum value
#   room.boss_cry_1        | 4     | 5       | Aquamentus/Manhandla/Gleeok/Digdogger sound
#   room.boss_cry_2        | 4     | 6       | Dodongo/Gohma sound
#   room.is_dark           | 4     | 7       | Dark room flag
#   room.item_position     | 5     | 5-4     | ItemPosition (0-3)
#   room.room_action       | 5     | 2,1,0   | Combined from 3 bits (see RoomAction)
#
#
# =============================================================================
# WHAT THIS FUNCTION DOES AT A GAME LEVEL
# =============================================================================
#
# For each dungeon level (1-9):
#
# STEP 1: Identify shufflable rooms
#   The rooms in Level.rooms are already known. We exclude:
#     - Staircase rooms (TRANSPORT_STAIRCASE, ITEM_STAIRCASE) — these are in
#       Level.staircase_rooms, not Level.rooms, so already excluded.
#     - The entrance room (room_type == ENTRANCE_ROOM, 0x21)
#     - The Gannon room in level 9 (enemy == THE_BEAST with is_group set,
#       or more precisely: Table 2 enemy code == 0x0B and Table 3 bit 7 set
#       and level == 9 — needs careful mapping)
#
# STEP 2: Shuffle room contents between grid positions
#   The room's CONTENTS are detached from their grid positions and randomly
#   reassigned to different positions within the same level. "Contents" means:
#     - room_type, movable_block, is_group (Table 3)
#     - item, boss_cry_1, boss_cry_2, is_dark (Table 4)
#     - item_position, room_action (Table 5)
#     - enemy_spec, enemy_quantity (Table 2)
#     - palette_0 (Table 0 bits 1-0)
#     - palette_1 (Table 1 bits 1-0)
#
#   What does NOT move (stays at grid position):
#     - Wall types (Table 0 bits 7-2, Table 1 bits 7-2) — these define the
#       physical dungeon layout and must stay put.
#
#   Adjacency constraints during the shuffle:
#     - T_ROOM (0x12): destination position must have a room below (pos+16)
#       that belongs to the same level
#     - ZELDA_ROOM (0x27): destination must have room below in same level
#     - HORIZONTAL_CHUTE_ROOM (0x0F): destination must have both left (pos-1)
#       and right (pos+1) neighbors in same level, and not be on column 0
#       or column 15
#     - VERTICAL_CHUTE_ROOM (0x0E): destination must have room above (pos-16)
#       and room below (pos+16) in same level
#
#   The shuffle is a constrained Fisher-Yates: for each position, pick a
#   random swap target. If the swap violates any adjacency constraint, retry
#   with a new random target. If retries exceed 1000, restart the entire
#   level.
#
# STEP 3: Update the level's entrance room
#   After shuffling, the entrance_room is updated. The C# iterates through
#   shuffled rooms and sets the entrance to the last room that is NOT a
#   Triforce room (item != TRIFORCE) and is NOT an ungrouped Kidnapped room
#   (enemy != THE_KIDNAPPED unless is_group is set).
#
#   TODO: This entrance update logic seems odd — setting it to the "last"
#   qualifying room depends on iteration order. Need to verify whether this
#   is intentional or a side effect of the C# loop structure.
#
# STEP 4: Shuffle horizontal door pairs (HELPER — not ported yet)
#   For each pair of horizontally adjacent rooms (room i and room i+1) that
#   both belong to the current level:
#     - Extract the "door pair value": a 6-bit value encoding the wall types
#       on both sides of the boundary:
#         (east_wall_of_left_room << 3) | west_wall_of_right_room
#       From Table 1: ((Table1[i] >> 2) & 7) << 3 | (Table1[i+1] >> 5)
#     - Classify the pair as "locked" or "shufflable":
#       Locked if either room has room_type ZELDA_ROOM or NARROW_STAIR_ROOM,
#       or if specific enemy conditions are met (see below).
#     - Locked pairs are forced to door pair value 9 (= wall on both sides?
#       9 = 0b001_001 = SOLID_WALL on both sides).
#     - Shufflable pairs are Fisher-Yates shuffled among themselves.
#     - Write the shuffled door values back to Table 1, updating both rooms'
#       east/west wall bits.
#
#   Horizontal lock conditions (DetermineHorizDoorLocked):
#     - Either room has room_type ZELDA_ROOM (0x27) → locked
#     - Either room has room_type NARROW_STAIR_ROOM (0x1B) → locked
#     - The right room has Table 3 byte == 0xA6 (is_group + BLACK_ROOM, NO
#       movable_block) AND the right room's raw 6-bit enemy field is in
#       range 11-18.  These are NPC rooms (OLD_MAN variants, BOMB_UPGRADER)
#       whose door pairs must not be shuffled.  Verified against ROM data:
#       this fires for rooms in levels 7, 8, AND 9 (not just level 9).
#       For level 9 the range is 12-18 and the left room's packed Table 2
#       byte must satisfy (T2 & 0x8F) != 17.
#
# STEP 5: Shuffle vertical door pairs (HELPER — not ported yet)
#   Same logic as horizontal, but for vertically adjacent rooms (room i and
#   room i+16). The door pair value encodes:
#     (south_wall_of_upper_room << 3) | north_wall_of_lower_room
#   From Table 0: ((Table0[i] >> 2) & 7) << 3 | (Table0[i+16] >> 5)
#
#   Vertical lock conditions (DetermineVertDoorLocked):
#     - Lower room has room_type ZELDA_ROOM (0x27) → locked
#     - Lower room has room_type NARROW_STAIR_ROOM (0x1B) → locked
#     - Pair where one room has enemy THE_KIDNAPPED and the other has a
#       specific enemy → locked (prevents breaking Zelda accessibility)
#     - If mustBeatGanon: pair where one room has ZOLA-coded enemy and the
#       other has THE_KIDNAPPED → locked
#       TODO: The enemy checks use Table 2 & 0x7F which includes the low
#       quantity bit. Values 0x0B, 0x37, 0x11 may not map cleanly to single
#       enemies. Need to verify against actual ROM data.
#
# STEP 6: Clear boss cry bits (Phase 9 in C#)
#   After all shuffling, clear boss_cry_1 and boss_cry_2 on ALL rooms in the
#   128-room grid (not just the current level). This is done by clearing
#   bits 6-5 of Table 4 for every room. In our model: set boss_cry_1=False
#   and boss_cry_2=False on all rooms sharing this level's grid.
#
#   NOTE: This clears boss cries for ALL levels in the grid (levels 1-6 or
#   levels 7-9), not just the current level. Each level iteration re-clears.
#
# STEP 7: Fix special rooms (HELPER — not ported yet)
#   FixSpecialRooms iterates all rooms in the level and applies corrections:
#
#   a) Wall/bomb door fixes: If any wall direction has value 7 (SHUTTER_DOOR),
#      and the room's door type is:
#        - 5 (PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE): clear the shutter bits
#        - 0 or 2 (open/locked variants): change door type to 1
#          (KILLING_ENEMIES_OPENS_SHUTTERS)
#
#   b) Door type 4 without shutters: If room_action is 4
#      (PUSHING_BLOCK_OPENS_SHUTTERS) but no wall has SHUTTER_DOOR, clear
#      the movable_block flag.
#
#   c) Push-block rooms (door type 3): If room_action is
#      TRIFORCE_OF_POWER_OPENS_SHUTTERS and item is not TRANSPORT_STAIRCASE,
#      clear bit 1 of room_action (the master enemy bit). If the item's low
#      5 bits == 14 (TRIFORCE_OF_POWER), set the item byte to 3 (MAGICAL_SWORD).
#      TODO: This logic is confusing — verify the game-level intent.
#
#   d) Empty rooms (Table 2 enemy byte == 0x3E = TRANSPORT_STAIRCASE):
#      Actually this checks if the enemy code equals 0x3E... which in our
#      Enemy enum doesn't map to anything meaningful as a regular enemy.
#      TODO: Clarify what "empty room" means here. Possibly rooms with no
#      enemy that use 0x3E as a sentinel.
#      For these rooms: set all non-locked walls to SHUTTER_DOOR (7), set
#      enemy to 0x8E (dark + TRIFORCE_OF_POWER?), set room_action to 3
#      (TRIFORCE_OF_POWER_OPENS_SHUTTERS). Also set bit 5 (boss_cry_1) on
#      all neighboring rooms that belong to level 9.
#
#   e) Level 9 Gannon room fix: Ensures Gannon's room has proper wall
#      connections (shutter walls where needed, open where needed).
#
#   f) Zelda room fix: Sets specific wall patterns to ensure Zelda's room
#      is accessible. Updates neighboring rooms' wall values.
#
# STEP 8: Fix peninsula rooms and stair adjacency (HELPER — not ported yet)
#   FixPeninsulaAndStairs handles:
#
#   a) Stair rooms (room_action == 6, which is DEFEATING_NPC_OPENS_SHUTTERS):
#      If walls have value 0 (OPEN_DOOR) or 5 (LOCKED_DOOR_1) in any
#      direction, set them to SHUTTER_DOOR (7). This ensures stair rooms
#      have proper shutter doors that open when conditions are met.
#
#   b) T_ROOM (0x12) and ZELDA_ROOM (0x27) with south wall == 1
#      (SOLID_WALL) and a room below in the same level: track these for
#      stair-adjacency fixes. Later, clear the south wall of this room
#      and the north wall of the room below.
#
#   c) Bomb-upgrade rooms (room_type BLACK_ROOM 0x36 or similar): If any
#      wall direction has SHUTTER_DOOR (7), clear it. This ensures bomb
#      upgrade rooms don't have lingering shutter doors.
#
#   d) Apply stair-adjacency fixes: For tracked rooms, clear the wall
#      between the room and the room below to ensure staircase connectivity.
#
#
# =============================================================================
# PHASE 2 IN THE C# — THE "SCREEN LAYOUT SHUFFLE"
# =============================================================================
#
# The C# has a preliminary shuffle (Phase 2) that shuffles Table 0/1 byte
# VALUES among rooms, building a remap from old values to new values. This
# appears to shuffle which wall configurations appear at which grid positions.
# After this shuffle, it updates Table 2 (enemy data) based on screen types
# at the new positions — setting specific item difficulty codes (0x69, 0x65,
# 0xB8).
#
# However, this phase has decompilation artifacts that make it hard to
# understand. It uses Table 0 values as indices into Table 3
# (rom[Table3_base + Table0_value]), which only makes sense if the Table 0
# value happens to be a valid room index (< 128). For staircase rooms this
# works (Table 0 encodes a destination room index in bits 6-0), but staircase
# rooms are explicitly skipped. For regular rooms, Table 0 values like 0xA6
# (166) would read past the 128-byte Table 3 into Table 4, producing
# nonsensical results.
#
# POSSIBLE EXPLANATIONS:
# 1. The decompilation has a bug and the index should be the room position
#    `i`, not `Table0[i]`.
# 2. The RoomTypeMapping bounds check (screenLayoutByte < Count) filters
#    out rooms with Table 0 values >= 128 before lines 240-243 execute,
#    so those rooms are never reached. But this would mean many Level 1
#    rooms (which have Table 0 values like 0xA2, 0xA6) are skipped.
# 3. RoomTypeMapping has 256 entries (one per possible byte value).
#
# FOR OUR PORT: We skip this phase entirely. Our data model already has
# wall types and room types as separate structured fields. The "screen
# layout shuffle" is a ROM-level operation that has no clean equivalent
# in our model, and its game-level effect (shuffling wall configurations)
# is subsumed by the room content shuffle (Step 2 above), which preserves
# walls at their grid positions while moving room contents.
#
# TODO: Verify that skipping Phase 2 doesn't lose any game-level behavior.
# The item difficulty reassignment (0x69/0x65/0xB8 writes to Table 2) may
# have a game effect we're not capturing.
#
#
# =============================================================================
# DOOR PAIR VALUES — HOW WALL TYPES BETWEEN ADJACENT ROOMS ARE ENCODED
# =============================================================================
#
# When two rooms are adjacent (horizontally or vertically), the wall between
# them is defined by TWO wall type values — one from each room's perspective.
# These are packed into a single 6-bit "door pair value":
#
# Horizontal pair (room i, room i+1):
#   door_pair = (room_i.walls.east << 3) | room_i_plus_1.walls.west
#   Stored in Table 1:
#     room_i:     bits 4-2 = east wall
#     room_i+1:   bits 7-5 = west wall
#
# Vertical pair (room i, room i+16):
#   door_pair = (room_i.walls.south << 3) | room_i_plus_16.walls.north
#   Stored in Table 0:
#     room_i:     bits 4-2 = south wall
#     room_i+16:  bits 7-5 = north wall
#
# Door pair value 9 = 0b001_001 = SOLID_WALL(1) on both sides = sealed wall.
# Locked door pairs are forced to value 9 (sealed).
#
# The door pair shuffle randomizes which wall-type combinations appear between
# adjacent room pairs, while keeping "locked" pairs fixed.
#
#
# =============================================================================
# RETRY STRUCTURE
# =============================================================================
#
# The C# has nested retry logic:
#   - Outer loop: iterates levels 1-9. A global retry counter (retryCount)
#     is shared across all levels. If it exceeds 1000, the entire function
#     fails and returns false.
#   - Inner loop (Phase 4): constrained Fisher-Yates with a per-level retry
#     counter (shuffleRetries). If it exceeds 1000, the current level is
#     retried from scratch (num17 is decremented, outer loop continues).
#
# In our port, we should use max_attempts limits with clear fallback behavior.
"""

from zora.data_model import (
    Direction,
    Enemy,
    EnemySpec,
    GameWorld,
    Item,
    ItemPosition,
    Level,
    Room,
    RoomAction,
    RoomType,
    StaircaseRoom,
    WallType,
)
from zora.game_validator import _CONSTRAINED_VALID_DIRS
from zora.rng import Rng


# Maximum retries for the constrained Fisher-Yates before restarting a level.
_MAX_SHUFFLE_RETRIES = 1_000

# Maximum times we'll restart a single level from scratch before giving up.
_MAX_LEVEL_RETRIES = 50


# Room types that require specific neighbors to function correctly.
# These impose adjacency constraints during the shuffle.
#
# Chute rooms have internal walls that divide them into lanes/rows.
# To access all regions of the room, doors must exist into each region:
#   - Vertical chute: vertical walls create left/center/right lanes.
#     Left lane needs WEST, right lane needs EAST, center needs N or S.
#   - Horizontal chute: horizontal walls create top/middle/bottom rows.
#     Top row needs NORTH, bottom needs SOUTH, middle needs E or W.
# We require neighbors on the axes that feed the side regions, since
# center/middle is almost always reachable from the remaining doors.
_NEEDS_ROOM_BELOW: frozenset[RoomType] = frozenset({
    RoomType.T_ROOM,              # 0x12 — stem extends south
    RoomType.ZELDA_ROOM,          # 0x27 — Zelda's room needs a room below
})

# _NEEDS_ROOM_ABOVE_AND_BELOW: frozenset[RoomType] = frozenset({
#     RoomType.HORIZONTAL_CHUTE_ROOM,  # 0x0F — top row needs north, bottom needs south
# })

# _NEEDS_LEFT_AND_RIGHT: frozenset[RoomType] = frozenset({
#     RoomType.VERTICAL_CHUTE_ROOM,  # 0x0E — left lane needs west, right lane needs east
# })


def _level_room_nums(level: Level) -> frozenset[int]:
    """Return the set of room_num values belonging to this level."""
    return frozenset(r.room_num for r in level.rooms)


def _is_level9_fixed_room(room: Room, level_num: int) -> bool:
    """Check if a room should be excluded from the shuffle in level 9.

    The C# Phase 3 excludes rooms where ``Table2_byte == 0x0B &&
    (Table3_byte & 0x80) != 0 && level == 9``.

    IMPORTANT: The decompiler labels this "Skip Ganon's room" but that's
    WRONG. The Gannon room has enemy=THE_BEAST (0x3E), not Table 2 = 0x0B.
    The actual room this catches has:
      - Table 2 byte = 0x0B → 6-bit enemy field = 0x0B
      - Table 3 bit 7 (is_group) set → parser computes enemy_code =
        0x0B + 0x40 = 0x4B = Enemy.OLD_MAN
      - But 0x4B is NOT in the mixed_groups dict (0x62-0x7F), so the parser
        produces EnemySpec(enemy=OLD_MAN, is_group=False), DROPPING the
        is_group flag.

    This room is most likely an NPC room (old man hint) in level 9 that
    must stay at its grid position. Since the parser drops is_group for
    non-mixed-group codes, we identify it by enemy=OLD_MAN in level 9.

    TODO: Verify against actual ROM data which specific level-9 room this
    is and what its room_type is. The OLD_MAN check may be too broad if
    level 9 has multiple OLD_MAN rooms with different roles.
    """
    return level_num == 9 and room.enemy_spec.enemy == Enemy.OLD_MAN


def _is_shufflable(room: Room, level_num: int) -> bool:
    """Return True if a room's contents should participate in the shuffle.

    Excludes entrance rooms and the fixed NPC room in level 9.
    Staircase rooms are already in Level.staircase_rooms, not Level.rooms.
    """
    if room.room_type == RoomType.ENTRANCE_ROOM:
        return False
    if _is_level9_fixed_room(room, level_num):
        return False
    return True


def _has_neighbor_in_level(
    room_num: int,
    direction: Direction,
    level_room_nums: frozenset[int],
) -> bool:
    """Check if the room at room_num has a neighbor in the given direction
    that belongs to the same level."""
    col = room_num % 16
    if direction == Direction.SOUTH:
        neighbor = room_num + 16
        return neighbor < 128 and neighbor in level_room_nums
    elif direction == Direction.NORTH:
        neighbor = room_num - 16
        return neighbor >= 0 and neighbor in level_room_nums
    elif direction == Direction.WEST:
        neighbor = room_num - 1
        return col > 0 and neighbor in level_room_nums
    elif direction == Direction.EAST:
        neighbor = room_num + 1
        return col < 15 and neighbor in level_room_nums
    return False


def _check_adjacency_constraints(
    room_type: RoomType,
    dest_pos: int,
    level_room_nums: frozenset[int],
) -> bool:
    """Check whether placing a room with the given room_type at dest_pos
    satisfies adjacency constraints.

    Returns True if valid, False if the placement would violate constraints.
    """
    if room_type in _NEEDS_ROOM_BELOW:
        if not _has_neighbor_in_level(dest_pos, Direction.SOUTH, level_room_nums):
            return False

    # if room_type in _NEEDS_ROOM_ABOVE_AND_BELOW:
    #     if not _has_neighbor_in_level(dest_pos, Direction.NORTH, level_room_nums):
    #         return False
    #     if not _has_neighbor_in_level(dest_pos, Direction.SOUTH, level_room_nums):
    #         return False

    # if room_type in _NEEDS_LEFT_AND_RIGHT:
    #     col = dest_pos % 16
    #     if col == 0 or col == 15:
    #         return False
    #     if not _has_neighbor_in_level(dest_pos, Direction.WEST, level_room_nums):
    #         return False
    #     if not _has_neighbor_in_level(dest_pos, Direction.EAST, level_room_nums):
    #         return False

    return True


def _is_swap_valid(
    room_type_i: RoomType,
    room_type_j: RoomType,
    pos_i: int,
    pos_j: int,
    level_room_nums: frozenset[int],
    enemy_i: Enemy = Enemy.NOTHING,
    enemy_j: Enemy = Enemy.NOTHING,
    north_walls: dict[int, WallType] | None = None,
) -> bool:
    """Check if swapping room contents between positions i and j is valid.

    After the swap, room_type_i would be at pos_j and room_type_j at pos_i.
    Both placements must satisfy adjacency constraints. NPC enemies must
    land at positions with a solid north wall (NES engine constraint).
    """
    if not _check_adjacency_constraints(room_type_i, pos_j, level_room_nums):
        return False
    if not _check_adjacency_constraints(room_type_j, pos_i, level_room_nums):
        return False
    if north_walls is not None:
        if enemy_i in _NPC_ENEMIES_IN_BLACK_ROOM:
            if north_walls.get(pos_j) != WallType.SOLID_WALL:
                return False
        if enemy_j in _NPC_ENEMIES_IN_BLACK_ROOM:
            if north_walls.get(pos_i) != WallType.SOLID_WALL:
                return False
    return True


class _RoomContents:
    """The movable parts of a room — everything except walls and grid position.

    When we shuffle rooms, walls stay at their grid position while these
    contents move to a different position.
    """
    __slots__ = (
        'room_type', 'movable_block', 'enemy_spec', 'enemy_quantity',
        'item', 'item_position', 'room_action', 'is_dark',
        'boss_cry_1', 'boss_cry_2', 'palette_0', 'palette_1',
    )

    def __init__(self, room: Room) -> None:
        self.room_type = room.room_type
        self.movable_block = room.movable_block
        self.enemy_spec = room.enemy_spec
        self.enemy_quantity = room.enemy_quantity
        self.item = room.item
        self.item_position = room.item_position
        self.room_action = room.room_action
        self.is_dark = room.is_dark
        self.boss_cry_1 = room.boss_cry_1
        self.boss_cry_2 = room.boss_cry_2
        self.palette_0 = room.palette_0
        self.palette_1 = room.palette_1

    def apply_to(self, room: Room) -> None:
        """Write these contents into a room, preserving its walls and room_num."""
        room.room_type = self.room_type
        room.movable_block = self.movable_block
        room.enemy_spec = self.enemy_spec
        room.enemy_quantity = self.enemy_quantity
        room.item = self.item
        room.item_position = self.item_position
        room.room_action = self.room_action
        room.is_dark = self.is_dark
        room.boss_cry_1 = self.boss_cry_1
        room.boss_cry_2 = self.boss_cry_2
        room.palette_0 = self.palette_0
        room.palette_1 = self.palette_1


def _horiz_door_pair_value(left: Room, right: Room) -> int:
    """Encode the horizontal door pair value between two adjacent rooms.

    Returns a 6-bit value: (left.walls.east << 3) | right.walls.west.
    """
    return (left.walls.east.value << 3) | right.walls.west.value


# NPC enemies whose door pairs should be locked when in a BLACK_ROOM.
#
# The C# checks Table 3 == 0xA6 (is_group | room_type BLACK_ROOM, no
# movable_block) then checks the raw 6-bit enemy field in range 11-18.
# These raw values map to enemy codes 0x4B-0x52 after the +0x40 is_group
# offset.  Our parser drops the is_group flag for these NPC enemies (they
# aren't in the mixed_groups dict), so we identify them by enemy enum value
# + room_type == BLACK_ROOM instead.
#
# Verified against ROM data: these rooms exist in levels 7, 8, and 9 and
# the condition fires for real horizontal pairs.
_NPC_ENEMIES_IN_BLACK_ROOM: frozenset[Enemy] = frozenset({
    Enemy.OLD_MAN,       # raw 6-bit = 11
    Enemy.OLD_MAN_2,     # raw 6-bit = 12
    Enemy.OLD_MAN_3,     # raw 6-bit = 13
    Enemy.OLD_MAN_4,     # raw 6-bit = 14
    Enemy.BOMB_UPGRADER,  # raw 6-bit = 15
    Enemy.OLD_MAN_5,     # raw 6-bit = 16
    Enemy.MUGGER,        # raw 6-bit = 17 (excluded from non-L9 lock)
    Enemy.OLD_MAN_6,     # raw 6-bit = 18
})

# For non-level-9, the C# excludes raw_6bit == 17 (MUGGER).
_NPC_ENEMIES_NON_L9: frozenset[Enemy] = _NPC_ENEMIES_IN_BLACK_ROOM - {Enemy.MUGGER}

# For level 9, the C# uses (T2 & 0x7F) in 12-18 instead of (T2 & 0x3F)
# in 11-18.  The & 0x7F mask includes the low quantity bit (bit 6), so
# only rooms with quantity_code bit 0 == 0 can match.  The range 12-18
# also excludes OLD_MAN (raw=11).  In vanilla ROM data the quantity bits
# are always 0 for these NPC rooms, so we just check the enemy range.
_NPC_ENEMIES_L9: frozenset[Enemy] = _NPC_ENEMIES_IN_BLACK_ROOM - {
    Enemy.OLD_MAN,  # raw 6-bit = 11, outside L9 range 12-18
    Enemy.MUGGER,   # raw 6-bit = 17, excluded by the left-room check in practice
}


def _is_horiz_pair_locked(
    left: Room,
    right: Room,
    level_num: int,
) -> bool:
    """Determine if a horizontal door pair should be locked (not shuffled).

    Locked pairs are forced to door pair value 9 (SOLID_WALL on both sides).

    Lock conditions from DetermineHorizDoorLocked:
    1. Either room has ZELDA_ROOM or NARROW_STAIR_ROOM -> locked.
    2. The right room is an NPC room in a BLACK_ROOM layout (the C# checks
       Table 3 == 0xA6 = is_group | BLACK_ROOM, then checks the enemy field
       against a numeric range).  This protects NPC rooms (old men, bomb
       upgrader) from having their wall configurations disrupted.
    """
    # Condition 1: ZELDA_ROOM or NARROW_STAIR_ROOM on either side
    locked_types = (RoomType.ZELDA_ROOM, RoomType.NARROW_STAIR_ROOM)
    if left.room_type in locked_types or right.room_type in locked_types:
        return True

    # Level 9 exception: the right room is an NPC-in-BLACK_ROOM.
    # The C# also checks (T2[left] & 0x8F) != 17.  This masks
    # the left room's packed Table 2 byte to keep the high
    # quantity bit and low 4 enemy bits.  In vanilla ROM data
    # this always passes (no left neighbor has that exact
    # combination).  We omit it because our model stores the
    # decoded quantity (1/4/5/6), not the raw 2-bit code, so
    # we can't reconstruct the packed byte faithfully.
    if level_num == 9 and right.room_type == RoomType.BLACK_ROOM:
        if right.enemy_spec.enemy in _NPC_ENEMIES_L9:
            return True

    return False


# Door pair value 9 = SOLID_WALL(1) on both sides = sealed wall.
_SEALED_DOOR_PAIR = (WallType.SOLID_WALL.value << 3) | WallType.SOLID_WALL.value


def _fix_horizontal_door_pairs(level: Level, rng: Rng) -> None:
    """Shuffle horizontal door pairs within a level.

    For each pair of horizontally adjacent rooms (room i, room i+1) that both
    belong to the level, extract the door pair value encoding both rooms' wall
    types at the shared boundary.

    Locked pairs (containing ZELDA_ROOM, NARROW_STAIR_ROOM, or certain
    Gannon-area configurations) are forced to SOLID_WALL on both sides.
    Unlocked pairs are Fisher-Yates shuffled among themselves.

    Finally, write the shuffled wall types back to the room objects.
    """
    level_room_nums = _level_room_nums(level)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    # Collect horizontal pairs: adjacent rooms (i, i+1) both in this level.
    pair_positions: list[int] = []       # room_num of the left room
    pair_values: list[int] = []          # 6-bit door pair value
    pair_locked: list[bool] = []

    for room in sorted(level.rooms, key=lambda r: r.room_num):
        room_num = room.room_num
        # Skip rooms on the rightmost column — no right neighbor.
        if room_num % 16 == 15:
            continue
        right_num = room_num + 1
        if right_num not in level_room_nums:
            continue

        left_room = room
        right_room = room_by_num[right_num]

        pair_positions.append(room_num)
        pair_values.append(_horiz_door_pair_value(left_room, right_room))
        pair_locked.append(_is_horiz_pair_locked(left_room, right_room, level.level_num))

    if not pair_positions:
        return

    # Force locked pairs to the sealed value (9).
    # The C# first tries to swap with an unlocked pair that already has value 9,
    # preserving the total distribution. If none found, it force-sets to 9.
    for i in range(len(pair_locked)):
        if not pair_locked[i]:
            continue
        if pair_values[i] == _SEALED_DOOR_PAIR:
            continue
        # Try to find an unlocked pair with value 9 to swap with.
        swapped = False
        for j in range(len(pair_locked)):
            if pair_values[j] == _SEALED_DOOR_PAIR and not pair_locked[j]:
                pair_values[i], pair_values[j] = pair_values[j], pair_values[i]
                swapped = True
                break
        if not swapped:
            pair_values[i] = _SEALED_DOOR_PAIR

    # Fisher-Yates shuffle on unlocked pairs only.
    # The C# retries (i--) when a locked swap target is picked.
    count = len(pair_values)
    i = 0
    while i < count:
        if pair_locked[i]:
            i += 1
            continue
        remaining = count - i
        j = i + int(rng.random() * remaining)
        if pair_locked[j]:
            # Retry this index with a new random target (C# does i--).
            # No infinite loop risk: locked pairs already have value 9, so
            # at least one unlocked pair exists in [i..count) (pair i itself).
            continue
        pair_values[i], pair_values[j] = pair_values[j], pair_values[i]
        i += 1

    # Write shuffled door pair values back to room wall fields.
    for pos, val in zip(pair_positions, pair_values):
        left_room = room_by_num[pos]
        right_room = room_by_num[pos + 1]
        left_room.walls.east = WallType((val >> 3) & 7)
        right_room.walls.west = WallType(val & 7)


def _vert_door_pair_value(upper: Room, lower: Room) -> int:
    """Encode the vertical door pair value between two adjacent rooms.

    Returns a 6-bit value: (upper.walls.south << 3) | lower.walls.north.
    """
    return (upper.walls.south.value << 3) | lower.walls.north.value


def _pack_table2_7bit(room: Room) -> int:
    """Reconstruct the 7-bit packed Table 2 value for a room.

    Table 2 layout: bits [7:6] = quantity_code, bits [5:0] = enemy_code.
    The ``& 0x7F`` mask used in the C# keeps bit 6 (low quantity bit) +
    the 6-bit enemy code.

    NOTE: Our model stores the decoded quantity (1, 4, 5, 6), not the raw
    2-bit quantity code.  We reverse the standard qty_table [1, 4, 5, 6]
    to recover it.  This is only approximate — if a level's qty_table
    differs from vanilla, the reconstruction will be wrong.  In practice
    this function is only used in the vertical lock conditions 2-3, which
    are a no-op safety net (staircase rooms aren't in Level.rooms), so
    any inaccuracy has no effect.
    """
    _QTY_REVERSE = {1: 0, 4: 1, 5: 2, 6: 3}
    qty_code = _QTY_REVERSE.get(room.enemy_quantity, 0)
    return ((qty_code & 1) << 6) | (room.enemy_spec.enemy.value & 0x3F)


def _is_vert_pair_locked(
    upper: Room,
    lower: Room,
    must_beat_gannon: bool,
) -> bool:
    """Determine if a vertical door pair should be locked (not shuffled).

    Differences from the horizontal lock logic (_is_horiz_pair_locked):
      - Only checks the LOWER room for ZELDA_ROOM / NARROW_STAIR_ROOM
        (horizontal checks BOTH rooms).
      - Does NOT have the grouped+movable_block+BLACK_ROOM enemy-range
        check that horizontal has.
      - Instead has packed-Table-2-byte pair checks (conditions 2-3 below),
        which horizontal does not have.

    Lock conditions from DetermineVertDoorLocked:

    1. Lower room has ZELDA_ROOM or NARROW_STAIR_ROOM → locked.

    2. One room's packed Table 2 byte (& 0x7F) is 0x37 and the other's is
       0x0B → locked.

    3. If mustBeatGanon: one room is 0x37 and the other is 0x11 → locked.

    NOTE on conditions 2-3: These almost certainly protect vertical pairs
    where one room is a STAIRCASE and the other contains THE_KIDNAPPED.
    For staircase rooms, Table 2 encodes exit X/Y position (upper 4 bits =
    X, lower 4 = Y), NOT an enemy code. The values 0x0B and 0x11 are
    specific staircase exit coordinates — they are NOT RED_DARKNUT or ZOLA
    (those enemy codes only coincidentally share the same numeric values).
    The C# doesn't filter staircases out of the door pair loop, so these
    checks prevent staircase "door pairs" (which aren't real doors) from
    being shuffled, preserving staircase-to-Zelda connectivity.

    In our model, staircase rooms live in Level.staircase_rooms (not
    Level.rooms), so our door pair loop never encounters these pairs.
    We reproduce the checks as a faithful safety net, but they should
    effectively never trigger.
    """
    # Condition 1: lower room is ZELDA_ROOM or NARROW_STAIR_ROOM
    if lower.room_type in (RoomType.ZELDA_ROOM, RoomType.NARROW_STAIR_ROOM):
        return True

    # Condition 2: lower room is an NPC room — lock its north wall.
    # The NES engine lets Link walk off the top of the screen if the north
    # wall isn't solid. The original C# only checked BLACK_ROOM NPCs, but
    # the content shuffle can place NPCs in any room type.
    if lower.enemy_spec.enemy in _NPC_ENEMIES_IN_BLACK_ROOM:
        return True

    # ── Conditions 3-4: staircase-adjacent-to-Zelda protection ──────────
    #
    # IMPORTANT: The hex values below (0x0B, 0x11) are NOT enemy codes.
    # They are staircase exit positions that happen to share numeric values
    # with Enemy.RED_DARKNUT (0x0B) and Enemy.ZOLA (0x11). Do NOT
    # "refactor" these into Enemy enum comparisons — that would be wrong.
    #
    # Context: Table 2 has dual meaning depending on room type:
    #   Regular rooms  → bits [7:6] = quantity, bits [5:0] = enemy code
    #   Staircase rooms → bits [7:4] = exit X,  bits [3:0] = exit Y
    #
    # The C# doesn't filter staircases from the door pair loop, so it
    # encounters pairs where one room is a staircase. These checks detect
    # that case (staircase with specific exit coords next to THE_KIDNAPPED)
    # and lock the pair to prevent breaking staircase-to-Zelda connectivity.
    #
    # In our model, staircase rooms are in Level.staircase_rooms (not
    # Level.rooms), so our loop never sees these pairs. These checks are
    # a faithful no-op safety net.
    # ──────────────────────────────────────────────────────────────────────
    upper_t2 = _pack_table2_7bit(upper)
    lower_t2 = _pack_table2_7bit(lower)

    # Condition 2: THE_KIDNAPPED (0x37) adjacent to staircase exit pos 0x0B
    if upper_t2 == 0x0B and lower_t2 == 0x37:
        return True
    if upper_t2 == 0x37 and lower_t2 == 0x0B:
        return True

    # Condition 3: THE_KIDNAPPED (0x37) adjacent to staircase exit pos 0x11
    if must_beat_gannon:
        if upper_t2 == 0x11 and lower_t2 == 0x37:
            return True
        if upper_t2 == 0x37 and lower_t2 == 0x11:
            return True

    return False


def _fix_vertical_door_pairs(
    level: Level,
    rng: Rng,
    must_beat_gannon: bool,
) -> None:
    """Shuffle vertical door pairs within a level.

    Same overall structure as _fix_horizontal_door_pairs: collect pairs,
    classify as locked/unlocked, force locked to sealed, Fisher-Yates
    shuffle unlocked, write back.

    Differences from horizontal:
      - Pairs are vertically adjacent (room i, room i+16) instead of
        (i, i+1).
      - Door pair value uses walls.south/north (Table 0) instead of
        walls.east/west (Table 1).
      - Lock logic only checks the LOWER room for special room types,
        and uses staircase-exit-position pair checks instead of the
        BLACK_ROOM configuration check. See _is_vert_pair_locked for
        details.
    """
    level_room_nums = _level_room_nums(level)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    pair_positions: list[int] = []
    pair_values: list[int] = []
    pair_locked: list[bool] = []

    for room in sorted(level.rooms, key=lambda r: r.room_num):
        room_num = room.room_num
        # Skip rooms on the last row — no room below.
        if room_num // 16 == 7:
            continue
        below_num = room_num + 16
        if below_num not in level_room_nums:
            continue

        upper_room = room
        lower_room = room_by_num[below_num]

        pair_positions.append(room_num)
        pair_values.append(_vert_door_pair_value(upper_room, lower_room))
        pair_locked.append(_is_vert_pair_locked(
            upper_room, lower_room, must_beat_gannon,
        ))

    if not pair_positions:
        return

    # Force locked pairs to the sealed value (9).
    for i in range(len(pair_locked)):
        if not pair_locked[i]:
            continue
        if pair_values[i] == _SEALED_DOOR_PAIR:
            continue
        swapped = False
        for j in range(len(pair_locked)):
            if pair_values[j] == _SEALED_DOOR_PAIR and not pair_locked[j]:
                pair_values[i], pair_values[j] = pair_values[j], pair_values[i]
                swapped = True
                break
        if not swapped:
            pair_values[i] = _SEALED_DOOR_PAIR

    # Fisher-Yates shuffle on unlocked pairs only.
    count = len(pair_values)
    i = 0
    while i < count:
        if pair_locked[i]:
            i += 1
            continue
        remaining = count - i
        j = i + int(rng.random() * remaining)
        if pair_locked[j]:
            continue
        pair_values[i], pair_values[j] = pair_values[j], pair_values[i]
        i += 1

    # Write shuffled door pair values back to room wall fields.
    for pos, val in zip(pair_positions, pair_values):
        upper_room = room_by_num[pos]
        lower_room = room_by_num[pos + 16]
        upper_room.walls.south = WallType((val >> 3) & 7)
        lower_room.walls.north = WallType(val & 7)


def _fix_constrained_room_doors(level: Level, rng: Rng) -> None:
    """Ensure movement-constrained rooms have at least one door on a required axis.

    After the door pair shuffle, a constrained room may end up with solid walls
    on all of its valid traversal directions, making it unreachable or a dead
    end that splits the level. This repair pass guarantees at least one
    valid-direction door exists by opening a randomly chosen wall on the
    needed axis.
    """
    level_room_nums = _level_room_nums(level)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    for room in level.rooms:
        rt = room.room_type
        if rt not in _CONSTRAINED_VALID_DIRS:
            continue

        rn = room.room_num

        if rt == RoomType.HORIZONTAL_CHUTE_ROOM:
            if room.walls.east != WallType.SOLID_WALL or room.walls.west != WallType.SOLID_WALL:
                continue
            candidates: list[Direction] = []
            if rn + 1 in level_room_nums and rn % 16 < 15:
                candidates.append(Direction.EAST)
            if rn - 1 in level_room_nums and rn % 16 > 0:
                candidates.append(Direction.WEST)
            if not candidates:
                continue
            pick = rng.choice(candidates)
            room.walls[pick] = WallType.OPEN_DOOR
            neighbor = room_by_num[rn + (1 if pick == Direction.EAST else -1)]
            neighbor.walls[_OPPOSITE_DIR[pick]] = WallType.OPEN_DOOR

        elif rt == RoomType.VERTICAL_CHUTE_ROOM:
            if room.walls.north != WallType.SOLID_WALL or room.walls.south != WallType.SOLID_WALL:
                continue
            candidates = []
            if rn - 16 in level_room_nums and rn >= 16:
                candidates.append(Direction.NORTH)
            if rn + 16 in level_room_nums and rn < 112:
                below = room_by_num.get(rn + 16)
                if below is None or below.enemy_spec.enemy not in _NPC_ENEMIES_IN_BLACK_ROOM:
                    candidates.append(Direction.SOUTH)
            if not candidates:
                continue
            pick = rng.choice(candidates)
            room.walls[pick] = WallType.OPEN_DOOR
            neighbor = room_by_num[rn + (-16 if pick == Direction.NORTH else 16)]
            neighbor.walls[_OPPOSITE_DIR[pick]] = WallType.OPEN_DOOR

        elif rt == RoomType.T_ROOM:
            if room.walls.south != WallType.SOLID_WALL:
                continue
            if rn + 16 in level_room_nums and rn < 112:
                below = room_by_num.get(rn + 16)
                if below is not None and below.enemy_spec.enemy in _NPC_ENEMIES_IN_BLACK_ROOM:
                    continue
                room.walls.south = WallType.OPEN_DOOR
                if below is not None:
                    below.walls.north = WallType.OPEN_DOOR


def _shuffle_level(level: Level, rng: Rng) -> bool:
    """Shuffle room contents within a single dungeon level.

    Performs a constrained Fisher-Yates shuffle: for each position in the
    shufflable room list, pick a random swap target. If the swap would
    violate adjacency constraints, retry with a new target. If retries
    are exhausted, restart the entire level.

    Returns True on success, False if the level couldn't be shuffled
    within the retry budget.
    """
    shufflable = [
        room for room in level.rooms
        if _is_shufflable(room, level.level_num)
    ]

    if len(shufflable) < 2:
        return True

    level_room_nums = _level_room_nums(level)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
    north_walls: dict[int, WallType] = {r.room_num: r.walls.north for r in level.rooms}

    for _level_attempt in range(_MAX_LEVEL_RETRIES):
        # Extract contents from rooms (fresh each attempt since we swap in-place)
        contents = [_RoomContents(room) for room in shufflable]
        positions = [room.room_num for room in shufflable]
        # Track where each content originated so we can remap staircase refs.
        orig_positions = list(positions)
        pool_size = len(shufflable)

        retry_count = 0
        i = 0
        success = True

        while i < pool_size:
            retry_count += 1
            if retry_count > _MAX_SHUFFLE_RETRIES:
                success = False
                break

            # Pick a random swap target from the remaining unprocessed positions.
            # The C# uses `rng.Next() % remaining` where remaining = total count,
            # not (count - i). This means the swap target can be any position,
            # not just unprocessed ones. This is the C#'s actual behavior.
            j = int(rng.random() * pool_size)

            if not _is_swap_valid(
                contents[i].room_type, contents[j].room_type,
                positions[i], positions[j],
                level_room_nums,
                enemy_i=contents[i].enemy_spec.enemy,
                enemy_j=contents[j].enemy_spec.enemy,
                north_walls=north_walls,
            ):
                continue

            # Swap contents only — positions are fixed grid slots.
            contents[i], contents[j] = contents[j], contents[i]
            orig_positions[i], orig_positions[j] = orig_positions[j], orig_positions[i]
            i += 1

        if success:
            # Write shuffled contents back to rooms at their new positions.
            for pos, content in zip(positions, contents):
                room = room_by_num[pos]
                content.apply_to(room)

            # Build remap: old_position → new_position.
            remap = {orig: dest for orig, dest in zip(orig_positions, positions)}

            # Update staircase refs to follow shuffled room contents.
            for sr in level.staircase_rooms:
                if sr.return_dest is not None and sr.return_dest in remap:
                    sr.return_dest = remap[sr.return_dest]
                if sr.left_exit is not None and sr.left_exit in remap:
                    sr.left_exit = remap[sr.left_exit]
                if sr.right_exit is not None and sr.right_exit in remap:
                    sr.right_exit = remap[sr.right_exit]

            return True

    return False


def _get_level9_room_nums(world: GameWorld) -> frozenset[int]:
    """Return room_nums belonging to level 9, for cross-level neighbor checks."""
    for level in world.levels:
        if level.level_num == 9:
            return frozenset(r.room_num for r in level.rooms)
    return frozenset()


def _grid_room_lookup(world: GameWorld, level: Level) -> dict[int, Room]:
    """Build a room_num → Room dict for all levels sharing a grid with *level*.

    Levels 1-6 share one grid; levels 7-9 share another.  The boss-cry
    neighbor fix in FixSpecialRooms needs to look up rooms across levels.
    """
    if level.level_num <= 6:
        grid_levels = [lv for lv in world.levels if lv.level_num <= 6]
    else:
        grid_levels = [lv for lv in world.levels if lv.level_num >= 7]
    result: dict[int, Room] = {}
    for lv in grid_levels:
        for room in lv.rooms:
            result[room.room_num] = room
    return result


def _has_any_shutter_door(room: Room) -> bool:
    """Return True if any wall direction on *room* is SHUTTER_DOOR."""
    w = room.walls
    return (
        w.north == WallType.SHUTTER_DOOR
        or w.south == WallType.SHUTTER_DOOR
        or w.west == WallType.SHUTTER_DOOR
        or w.east == WallType.SHUTTER_DOOR
    )


def _is_kidnapped_gate_room(room: Room, level: Level) -> bool:
    """Return True if *room* is a kidnapped-neighbor gate room in level 9.

    A kidnapped-gate room is a cardinal neighbor of THE_KIDNAPPED's room
    where the kidnapped room's wall toward this neighbor is non-SOLID
    (i.e. THE_KIDNAPPED can be reached from this neighbor). These rooms
    legitimately carry RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS as
    set by _fix_kidnapped_neighbors — zora's implementation of the
    "force boss fight" mechanic that makes the player defeat Ganon
    before reaching Zelda.
    """
    if level.level_num != 9:
        return False
    rn = room.room_num
    for kid_room in level.rooms:
        if kid_room.enemy_spec.enemy != Enemy.THE_KIDNAPPED:
            continue
        krn = kid_room.room_num
        for direction, offset in _DIR_OFFSETS:
            if krn + offset != rn:
                continue
            if kid_room.walls[direction] != WallType.SOLID_WALL:
                return True
        return False
    return False


def _fix_special_rooms(level: Level, world: GameWorld) -> None:
    """Fix wall/door interactions after the content shuffle.

    Ported from ShuffleDungeonRoomsHelpers.cs FixSpecialRooms (lines 426-601).
    """
    level_room_nums = _level_room_nums(level)
    level9_room_nums = _get_level9_room_nums(world)
    grid_rooms = _grid_room_lookup(world, level)

    for room in level.rooms:
        walls = room.walls
        action = room.room_action

        # ── Block 1: Shutter door + room_action fixes ────────────────
        # If any wall has SHUTTER_DOOR (7) and the room_action is incompatible,
        # either clear the shutter walls or change the room_action.
        has_shutter = _has_any_shutter_door(room)

        if has_shutter:
            if action == RoomAction.PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE:
                # Clear shutter walls → OPEN_DOOR.
                if walls.south == WallType.SHUTTER_DOOR:
                    walls.south = WallType.OPEN_DOOR
                if walls.north == WallType.SHUTTER_DOOR:
                    walls.north = WallType.OPEN_DOOR
                if walls.east == WallType.SHUTTER_DOOR:
                    walls.east = WallType.OPEN_DOOR
                if walls.west == WallType.SHUTTER_DOOR:
                    walls.west = WallType.OPEN_DOOR
            elif action in (
                RoomAction.NOTHING_OPENS_SHUTTERS,
                RoomAction.KILLING_RINGLEADER_KILLS_ENEMIES_OPENS_SHUTTERS,
            ):
                room.room_action = RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS
            elif (
                action == RoomAction.PUSHING_BLOCK_OPENS_SHUTTERS
                and not room.movable_block
            ):
                room.room_action = RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS

        # ── Block 2: PUSHING_BLOCK_OPENS_SHUTTERS without shutters ───
        # Demote the action to KILLING_ENEMIES_OPENS_SHUTTERS. Previously
        # this cleared movable_block and kept the action, which left the
        # room in a latent inconsistent state: any later phase (e.g.
        # scramble) that brought a shutter into the room would then
        # violate the PUSHING_BLOCK_OPENS_SHUTTERS invariant (action set
        # but no movable block). Demoting the action makes the room
        # consistent regardless of later wall changes.
        if (
            action == RoomAction.PUSHING_BLOCK_OPENS_SHUTTERS
            and not _has_any_shutter_door(room)
        ):
            room.room_action = RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS

        # ── Block 2.5: KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM with no item ──
        # Without an actual item, the game's drop logic reads the
        # Item.NOTHING code (0x03 in the dungeon item byte) which collides
        # with MAGICAL_SWORD (also 0x03), producing a phantom Magical
        # Sword drop. Demote the action so the room still opens shutters
        # but doesn't trigger the broken drop logic. The reference 100-seed
        # full-shuffle corpus has 0/7400 such rooms — confirms direction.
        if (
            room.room_action == RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM
            and room.item == Item.NOTHING
        ):
            room.room_action = RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS

        # ── Block 3: TRIFORCE_OF_POWER_OPENS_SHUTTERS legitimacy ─────
        # This action has two legitimate uses in zora:
        #   1. THE_BEAST's room itself (Block 4 sets this canonically).
        #   2. Kidnapped-neighbor rooms — the gate that ensures the
        #      player must defeat Ganon and obtain Triforce of Power
        #      before reaching Zelda. Set by _fix_kidnapped_neighbors
        #      in zora/enemy/shuffle_monsters.py and orchestrator.py.
        #
        # Historically Block 3 only ran post-shuffle (before kidnapped-
        # gate assignment), so demoting any non-beast action-3 was
        # correct then. Now that we re-run post-enemy-randomization,
        # kidnapped-gate rooms are already set and must be preserved.
        # NOTE: The C# original wrote raw byte 0x03 for the cleared
        # item, which is the vanilla dungeon nothing sentinel — NOT
        # Item.MAGICAL_SWORD.
        if action == RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS:
            is_beast_room = room.enemy_spec.enemy == Enemy.THE_BEAST
            is_kidnapped_gate = _is_kidnapped_gate_room(room, level)
            if not (is_beast_room or is_kidnapped_gate):
                room.room_action = RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS
                if room.item == Item.TRIFORCE_OF_POWER:
                    room.item = Item.NOTHING
                    room.is_dark = False
                    room.boss_cry_1 = False
                    room.boss_cry_2 = False

        # ── Block 4: THE_BEAST rooms (boss rooms) ────────────────────
        # The C# identifies these by Table 2 enemy byte == 0x3E.  In our
        # model, 0x3E = Enemy.THE_BEAST.  These rooms get:
        #   - All non-SOLID_WALL / non-BOMB_HOLE walls set to SHUTTER_DOOR
        #   - Enemy set to dark TRIFORCE_OF_POWER configuration
        #   - Room_action = TRIFORCE_OF_POWER_OPENS_SHUTTERS
        #   - Neighboring level-9 rooms get boss_cry_1 set
        if room.enemy_spec.enemy == Enemy.THE_BEAST:
            _keep_walls = (WallType.SOLID_WALL, WallType.BOMB_HOLE)
            if walls.south not in _keep_walls:
                walls.south = WallType.SHUTTER_DOOR
            if walls.north not in _keep_walls:
                walls.north = WallType.SHUTTER_DOOR
            if walls.east not in _keep_walls:
                walls.east = WallType.SHUTTER_DOOR
            if walls.west not in _keep_walls:
                walls.west = WallType.SHUTTER_DOOR

            # Set item to TRIFORCE_OF_POWER, dark, no boss cries.
            # C# sets Table 4 byte = 0x8E: bit 7 = dark, low 5 = 0x0E = TRIFORCE_OF_POWER.
            room.item = Item.TRIFORCE_OF_POWER
            room.is_dark = True
            room.boss_cry_1 = False
            room.boss_cry_2 = False

            # C# sets Table 5 byte = 0x03: room_action = 3 = TRIFORCE_OF_POWER_OPENS_SHUTTERS,
            # item_position bits = 0.
            room.room_action = RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS
            room.item_position = ItemPosition.POSITION_A

            # Set boss_cry_1 on neighboring rooms that belong to level 9.
            rn = room.room_num
            for neighbor_num in (rn - 16, rn + 16, rn - 1, rn + 1):
                # Bounds check: skip left/right wrap and grid edges.
                if neighbor_num < 0 or neighbor_num >= 128:
                    continue
                # Prevent left-right wrap across row boundaries.
                if neighbor_num == rn - 1 and rn % 16 == 0:
                    continue
                if neighbor_num == rn + 1 and rn % 16 == 15:
                    continue
                if neighbor_num in level9_room_nums and neighbor_num in grid_rooms:
                    grid_rooms[neighbor_num].boss_cry_1 = True

    # ── Block 5: Level 9 OLD_MAN NPC room wall fix ───────────────────
    # The C# identifies this room by Table2 == 0x0B && Table3 & 0x80 &&
    # level == 9.  As documented in CLAUDE.md, the parser drops is_group
    # for this NPC enemy, so we identify by enemy == OLD_MAN && level == 9.
    # Fix walls: north must be SOLID (NES engine constraint), south → OPEN,
    # non-SOLID west/east → SHUTTER.
    if level.level_num == 9:
        for room in level.rooms:
            if room.enemy_spec.enemy == Enemy.OLD_MAN:
                w = room.walls
                if w.north != WallType.SOLID_WALL:
                    w.north = WallType.SOLID_WALL
                    above_num = room.room_num - 16
                    if above_num >= 0 and above_num in grid_rooms:
                        grid_rooms[above_num].walls.south = WallType.SOLID_WALL
                w.south = WallType.OPEN_DOOR
                if w.west != WallType.SOLID_WALL:
                    w.west = WallType.SHUTTER_DOOR
                if w.east != WallType.SOLID_WALL:
                    w.east = WallType.SHUTTER_DOOR

    # ── Block 6: Level 9 ENTRANCE_ROOM wall fix ──────────────────────
    # The C# checks Table3 == 0x21 (ENTRANCE_ROOM with no flags) in level 9.
    # Sets west/east walls to SOLID_WALL, clears north/south to OPEN_DOOR.
    # Also fixes neighboring rooms' shared walls to SOLID_WALL.
    if level.level_num == 9:
        for room in level.rooms:
            if room.room_type == RoomType.ENTRANCE_ROOM:
                room.walls.west = WallType.SOLID_WALL
                room.walls.east = WallType.SOLID_WALL
                room.walls.south = WallType.OPEN_DOOR
                room.walls.north = WallType.OPEN_DOOR

                rn = room.room_num
                col = rn % 16

                # Left neighbor: set its east wall to SOLID_WALL.
                left_num = rn - 1
                if col > 0 and left_num in level9_room_nums and left_num in grid_rooms:
                    grid_rooms[left_num].walls.east = WallType.SOLID_WALL

                # Right neighbor: set its west wall to SOLID_WALL.
                right_num = rn + 1
                if col < 15 and right_num in level9_room_nums and right_num in grid_rooms:
                    grid_rooms[right_num].walls.west = WallType.SOLID_WALL


def _fix_peninsula_and_stairs(level: Level, world: GameWorld) -> None:
    """Fix stair rooms, peninsula rooms, and bomb upgrade room doors.

    Ported from ShuffleDungeonRoomsHelpers.cs FixPeninsulaAndStairs (lines 607-705).
    """
    level_room_nums = _level_room_nums(level)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    stair_fix_rooms: list[Room] = []

    for room in level.rooms:
        walls = room.walls

        # ── Part 1: Stair rooms (room_action == DEFEATING_NPC_OPENS_SHUTTERS) ─
        # The C# checks: Table2 byte in [0x0B, 0x13] && Table3 >= 128 (is_group)
        # && doorType == 6 (DEFEATING_NPC_OPENS_SHUTTERS).
        # In our model the enemy range 0x0B-0x13 with is_group maps to various
        # NPC/grouped enemies.  The key condition is room_action == 6.
        # For these rooms: if any wall is OPEN_DOOR or LOCKED_DOOR_1, upgrade
        # to SHUTTER_DOOR so the stair mechanic works properly.
        enemy_val = room.enemy_spec.enemy.value
        if (
            0x0B <= enemy_val <= 0x13
            and room.enemy_spec.is_group
            and room.room_action == RoomAction.DEFEATING_NPC_OPENS_SHUTTERS
        ):
            _upgrade = (WallType.OPEN_DOOR, WallType.LOCKED_DOOR_1)
            if walls.south in _upgrade:
                walls.south = WallType.SHUTTER_DOOR
            if walls.north in _upgrade:
                walls.north = WallType.SHUTTER_DOOR
            if walls.east in _upgrade:
                walls.east = WallType.SHUTTER_DOOR
            if walls.west in _upgrade:
                walls.west = WallType.SHUTTER_DOOR

        # ── Part 2: T_ROOM/ZELDA_ROOM with south wall == SOLID_WALL ──────────
        # If the room below exists in this level, track for stair-adjacency fix:
        # clear the wall between this room and the room below.
        if room.room_type in (RoomType.T_ROOM, RoomType.ZELDA_ROOM) and not room.movable_block:
            if walls.south == WallType.SOLID_WALL:
                below_num = room.room_num + 16
                if below_num < 128 and below_num in level_room_nums:
                    stair_fix_rooms.append(room)

        # ── Part 3: HUNGRY_GORIYA rooms — clear lingering shutter doors ───────
        # The C# checks ScreenType_0x36 against Table 3 (room_type field) and
        # also Table 2 (enemy byte).  Since 0x36 is not a valid RoomType in
        # our model, the Table 3 check can never fire.  The Table 2 check
        # identifies rooms with enemy == HUNGRY_GORIYA (0x36) and is_group=False
        # (sf < 128).  For these rooms, clear any SHUTTER_DOOR walls.
        if (
            room.enemy_spec.enemy == Enemy.HUNGRY_GORIYA
            and not room.enemy_spec.is_group
        ):
            if walls.south == WallType.SHUTTER_DOOR:
                walls.south = WallType.OPEN_DOOR
            if walls.north == WallType.SHUTTER_DOOR:
                walls.north = WallType.OPEN_DOOR
            if walls.east == WallType.SHUTTER_DOOR:
                walls.east = WallType.OPEN_DOOR
            if walls.west == WallType.SHUTTER_DOOR:
                walls.west = WallType.OPEN_DOOR

    # ── Apply stair-adjacency fixes ───────────────────────────────────────
    # For tracked T_ROOM/ZELDA_ROOM rooms, clear the south wall of this room
    # and the north wall of the room below, opening a passage between them.
    # Skip if the room below is an NPC room — its north wall must stay solid.
    for room in stair_fix_rooms:
        below_num = room.room_num + 16
        below_room = room_by_num.get(below_num)
        if below_room is not None:
            if below_room.enemy_spec.enemy in _NPC_ENEMIES_IN_BLACK_ROOM:
                continue
            room.walls.south = WallType.OPEN_DOOR
            below_room.walls.north = WallType.OPEN_DOOR


# Per-level OLD_MAN variant reassignment. The reference randomizer rewrites
# the variant of each old-man room in the level after shuffling, by a fixed
# table (deliberate divergence from the C# decompilation, established
# empirically from the reference 100-seed corpus).
#
# For L9, the pinned room at R$0x66 (identified via _is_level9_fixed_room)
# keeps OLD_MAN; the other 3 old-man rooms get {OLD_MAN_2, OLD_MAN_3,
# OLD_MAN_4} assigned in ascending room_num order.
_OLD_MAN_REASSIGNMENT: dict[int, list[Enemy]] = {
    1: [Enemy.OLD_MAN_3],
    2: [Enemy.OLD_MAN_2],
    3: [Enemy.OLD_MAN_3],
    4: [Enemy.OLD_MAN],
    5: [Enemy.OLD_MAN, Enemy.OLD_MAN_4],
    6: [Enemy.OLD_MAN_2, Enemy.OLD_MAN_4],
    9: [Enemy.OLD_MAN_2, Enemy.OLD_MAN_3, Enemy.OLD_MAN_4],
}

_OLD_MAN_VARIANTS: frozenset[Enemy] = frozenset({
    Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3, Enemy.OLD_MAN_4,
})


def _reassign_old_man_variants(level: Level) -> None:
    """Rewrite the OLD_MAN variant of each old-man room per the reference table.

    For L9 the room pinned by _is_level9_fixed_room (R$0x66 in vanilla)
    keeps OLD_MAN; the remaining old-man rooms in the level are paired with
    the table entries by ascending room_num.
    """
    table = _OLD_MAN_REASSIGNMENT.get(level.level_num)
    if table is None:
        return

    candidates = [
        r for r in level.rooms
        if r.enemy_spec.enemy in _OLD_MAN_VARIANTS
        and not _is_level9_fixed_room(r, level.level_num)
    ]
    candidates.sort(key=lambda r: r.room_num)

    for room, new_variant in zip(candidates, table):
        room.enemy_spec = EnemySpec(enemy=new_variant, is_group=False)


def _clear_boss_cry_bits(world: GameWorld) -> None:
    """Clear boss_cry_1 and boss_cry_2 on all rooms in the grid.

    The C# clears bits 6-5 of Table 4 for every room in the 128-room grid
    after each level's shuffle. Since levels 1-6 share one grid and levels
    7-9 share another, this clears boss cries for all co-located levels.

    We clear across all levels since we process all levels sequentially.
    """
    for level in world.levels:
        for room in level.rooms:
            room.boss_cry_1 = False
            room.boss_cry_2 = False


# ---------------------------------------------------------------------------
#  Connectivity check — flood fill from the entrance room
# ---------------------------------------------------------------------------

# Maximum times to retry the full shuffle+fixup sequence for a single level
# when the result isn't fully connected.
_MAX_CONNECTIVITY_RETRIES = 500


class _RoomSnapshot:
    """Complete snapshot of a Room's mutable state for save/restore."""
    __slots__ = (
        'room_num', 'room_type', 'walls_north', 'walls_east', 'walls_south',
        'walls_west', 'enemy_spec', 'enemy_quantity', 'item',
        'item_position', 'room_action', 'is_dark', 'boss_cry_1',
        'boss_cry_2', 'movable_block', 'palette_0', 'palette_1',
    )

    def __init__(self, room: Room) -> None:
        self.room_num = room.room_num
        self.room_type = room.room_type
        self.walls_north = room.walls.north
        self.walls_east = room.walls.east
        self.walls_south = room.walls.south
        self.walls_west = room.walls.west
        self.enemy_spec = room.enemy_spec
        self.enemy_quantity = room.enemy_quantity
        self.item = room.item
        self.item_position = room.item_position
        self.room_action = room.room_action
        self.is_dark = room.is_dark
        self.boss_cry_1 = room.boss_cry_1
        self.boss_cry_2 = room.boss_cry_2
        self.movable_block = room.movable_block
        self.palette_0 = room.palette_0
        self.palette_1 = room.palette_1

    def restore(self, room: Room) -> None:
        room.room_type = self.room_type
        room.walls.north = self.walls_north
        room.walls.east = self.walls_east
        room.walls.south = self.walls_south
        room.walls.west = self.walls_west
        room.enemy_spec = self.enemy_spec
        room.enemy_quantity = self.enemy_quantity
        room.item = self.item
        room.item_position = self.item_position
        room.room_action = self.room_action
        room.is_dark = self.is_dark
        room.boss_cry_1 = self.boss_cry_1
        room.boss_cry_2 = self.boss_cry_2
        room.movable_block = self.movable_block
        room.palette_0 = self.palette_0
        room.palette_1 = self.palette_1


class _StaircaseSnapshot:
    """Snapshot of a StaircaseRoom's mutable refs."""
    __slots__ = ('room_num', 'return_dest', 'left_exit', 'right_exit')

    def __init__(self, sr: StaircaseRoom) -> None:
        self.room_num = sr.room_num
        self.return_dest = sr.return_dest
        self.left_exit = sr.left_exit
        self.right_exit = sr.right_exit

    def restore(self, sr: StaircaseRoom) -> None:
        sr.return_dest = self.return_dest
        sr.left_exit = self.left_exit
        sr.right_exit = self.right_exit


class _LevelSnapshot:
    """Complete snapshot of a level's mutable state for retry."""
    __slots__ = ('room_snaps', 'staircase_snaps', 'entrance_room')

    def __init__(self, level: Level) -> None:
        self.room_snaps = [_RoomSnapshot(r) for r in level.rooms]
        self.staircase_snaps = [_StaircaseSnapshot(sr) for sr in level.staircase_rooms]
        self.entrance_room = level.entrance_room

    def restore(self, level: Level) -> None:
        by_num = {r.room_num: r for r in level.rooms}
        for snap in self.room_snaps:
            snap.restore(by_num[snap.room_num])
        sr_by_num = {sr.room_num: sr for sr in level.staircase_rooms}
        for sr_snap in self.staircase_snaps:
            sr_snap.restore(sr_by_num[sr_snap.room_num])
        level.entrance_room = self.entrance_room


_OPPOSITE_DIR: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST:  Direction.WEST,
    Direction.WEST:  Direction.EAST,
}

_DIR_OFFSETS: list[tuple[Direction, int]] = [
    (Direction.NORTH, -16),
    (Direction.SOUTH,  16),
    (Direction.WEST,   -1),
    (Direction.EAST,    1),
]


def _is_path_obstructed(
    room_type: RoomType,
    entry_dir: Direction,
    exit_dir: Direction,
) -> bool:
    """Check if traversal through a room is blocked by movement constraints.

    Uses the same constraint tables as game_validator. Assumes no ladder
    (conservative — items aren't placed yet).
    """
    if entry_dir == Direction.STAIRCASE:
        return False
    if room_type in _CONSTRAINED_VALID_DIRS:
        valid = _CONSTRAINED_VALID_DIRS[room_type]
        if entry_dir not in valid or exit_dir not in valid:
            return True
    return False


def _room_has_stairway(room: Room) -> bool:
    """Check if a room provides access to a staircase.

    Matches game_validator._has_stairway: open staircase room types always
    have access; push-block rooms have access only if movable_block is set
    AND no shutter doors are present (shutters consume the push block action).
    """
    if room.room_type.has_open_staircase():
        return True
    for wall in (room.walls.north, room.walls.east, room.walls.south, room.walls.west):
        if wall == WallType.SHUTTER_DOOR:
            return False
    return room.room_type.can_have_push_block() and room.movable_block


def _fix_narrow_stair_east_walls_level(level: Level) -> None:
    """Force NARROW_STAIR_ROOM east walls to SOLID_WALL within a single level.

    Must run before the connectivity check so that layouts broken by this
    constraint are rejected immediately rather than discovered post-fixup.
    """
    rooms_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
    for room in level.rooms:
        if room.room_type != RoomType.NARROW_STAIR_ROOM:
            continue
        room.walls.east = WallType.SOLID_WALL
        right_num = room.room_num + 1
        if room.room_num % 16 < 15:
            right = rooms_by_num.get(right_num)
            if right is not None:
                right.walls.west = WallType.SOLID_WALL


def _is_level_connected(level: Level) -> bool:
    """Check that every room in the level is reachable from the entrance.

    Direction-aware flood fill: tracks (room_num, entry_direction) states
    so that movement-restricted rooms (chutes, T-rooms, moat rooms) only
    allow traversal through valid direction pairs, matching the constraint
    tables in game_validator.

    Also follows transport staircase connections: if either exit room has
    been reached, both exits become reachable seeds (entered via
    Direction.STAIRCASE, which bypasses movement restrictions).

    Returns True if all rooms in level.rooms are reached from any direction.
    """
    level_room_nums = frozenset(r.room_num for r in level.rooms)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    visited_states: set[tuple[int, Direction]] = set()
    reached_rooms: set[int] = set()
    queue: list[tuple[int, Direction]] = [
        (level.entrance_room, level.entrance_direction),
    ]

    def _expand(rn: int, entry_dir: Direction) -> None:
        state = (rn, entry_dir)
        if state in visited_states:
            return
        visited_states.add(state)
        reached_rooms.add(rn)
        if rn not in room_by_num:
            return
        room = room_by_num[rn]
        row, col = rn >> 4, rn & 0xF
        for exit_dir, offset in _DIR_OFFSETS:
            if exit_dir == Direction.NORTH and row == 0:
                continue
            if exit_dir == Direction.SOUTH and row == 7:
                continue
            if exit_dir == Direction.WEST and col == 0:
                continue
            if exit_dir == Direction.EAST and col == 15:
                continue
            if room.walls[exit_dir] == WallType.SOLID_WALL:
                continue
            if _is_path_obstructed(room.room_type, entry_dir, exit_dir):
                continue
            neighbor = rn + offset
            if neighbor not in level_room_nums:
                continue
            neighbor_entry = _OPPOSITE_DIR[exit_dir]
            if (neighbor, neighbor_entry) not in visited_states:
                queue.append((neighbor, neighbor_entry))

    while queue:
        rn, entry_dir = queue.pop()
        _expand(rn, entry_dir)

    # Follow transport staircases: if either exit room has been reached
    # AND that room provides stairway access, both exits become seeds
    # entered via STAIRCASE.
    changed = True
    while changed:
        changed = False
        for sr in level.staircase_rooms:
            if sr.room_num in reached_rooms:
                continue
            if sr.room_type != RoomType.TRANSPORT_STAIRCASE:
                continue
            assert sr.left_exit is not None and sr.right_exit is not None
            can_enter = False
            for exit_rn in (sr.left_exit, sr.right_exit):
                if exit_rn in reached_rooms and exit_rn in room_by_num:
                    if _room_has_stairway(room_by_num[exit_rn]):
                        can_enter = True
                        break
            if can_enter:
                reached_rooms.add(sr.room_num)
                for exit_rn in (sr.left_exit, sr.right_exit):
                    state = (exit_rn, Direction.STAIRCASE)
                    if state not in visited_states:
                        queue.append(state)
                        changed = True
                while queue:
                    rn, entry_dir = queue.pop()
                    _expand(rn, entry_dir)

    return level_room_nums.issubset(reached_rooms)


def shuffle_dungeon_rooms(
    world: GameWorld,
    rng: Rng,
    must_beat_gannon: bool = True,
) -> bool:
    """Shuffle dungeon room positions within each level.

    Rearranges which room contents appear at which grid positions in each
    dungeon level. The physical wall layout is preserved — only the room
    contents (room type, enemies, items, darkness, palettes, etc.) move
    between positions.

    After shuffling, door pairs are fixed, special rooms are corrected,
    and boss cry bits are cleared. Each level is then checked for full
    connectivity (all rooms reachable from the entrance via non-solid
    walls and transport staircases). If a level isn't connected, the
    shuffle is retried for that level.

    Args:
        world: The game world to modify.
        rng: Seeded RNG for deterministic output.
        must_beat_gannon: If True, enforce door lock constraints that ensure
            the player must fight Gannon to reach Zelda.

    Returns:
        True on success, False if any level's shuffle exhausted its retry
        budget (caller should retry the entire seed generation).
    """
    # Clear boss cry bits across the whole grid up front. _fix_special_rooms
    # sets boss_cry_1=True on the cardinal neighbors of THE_BEAST's room
    # (only L9 has THE_BEAST), and we want those bits to survive. The C#
    # reference clears the grid before each level's special-rooms fixup;
    # since only L9 sets boss_cry_1, a single up-front pass is equivalent.
    _clear_boss_cry_bits(world)

    for level in world.levels:
        snapshot = _LevelSnapshot(level)
        connected = False

        for _attempt in range(_MAX_CONNECTIVITY_RETRIES):
            snapshot.restore(level)

            if not _shuffle_level(level, rng):
                continue

            _fix_horizontal_door_pairs(level, rng)
            _fix_vertical_door_pairs(level, rng, must_beat_gannon)
            _fix_constrained_room_doors(level, rng)

            _fix_special_rooms(level, world)
            _fix_peninsula_and_stairs(level, world)
            _reassign_old_man_variants(level)
            _fix_narrow_stair_east_walls_level(level)

            for room in level.rooms:
                if room.enemy_spec.enemy == Enemy.THE_BEAST:
                    level.boss_room = room.room_num
                    break

            if _is_level_connected(level):
                connected = True
                break

        if not connected:
            return False

    return True
