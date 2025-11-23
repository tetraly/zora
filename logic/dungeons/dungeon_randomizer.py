"""Dungeon layout randomizer using balanced region-growing algorithm."""

import logging as log
from typing import Dict, List, Optional, Set, Tuple, Union
from dataclasses import dataclass

from rng.random_number_generator import RandomNumberGenerator
from ..data_table import DataTable
from ..flags import Flags
from ..randomizer_constants import (
    Direction, Enemy, Item, LevelNum, Range, RoomNum, RoomType, WallType
)

# ============================================================================
# Enemy and Boss Groups by Level (due to NES sprite limitations)
# ============================================================================

# Regular enemy groups (levels share sprite banks)
ENEMY_GROUP_A = [  # L1, L2, L7
    Enemy.BUBBLE, Enemy.BLUE_KEESE, Enemy.RED_KEESE, Enemy.STALFOS,
    Enemy.GEL_1, Enemy.GEL_2, Enemy.ROPE, Enemy.WALLMASTER,
    Enemy.BLUE_GORIYA, Enemy.RED_GORIYA
]

ENEMY_GROUP_B = [  # L3, L5, L8
    Enemy.BUBBLE, Enemy.BLUE_KEESE, Enemy.RED_KEESE,
    Enemy.RED_DARKNUT, Enemy.BLUE_DARKNUT, Enemy.POLS_VOICE,
    Enemy.ZOL, Enemy.GIBDO
]

ENEMY_GROUP_C = [  # L4, L6, L9
    Enemy.BUBBLE, Enemy.BLUE_KEESE, Enemy.RED_KEESE,
    Enemy.VIRE, Enemy.RED_WIZZROBE, Enemy.BLUE_WIZZROBE,
    Enemy.ZOL, Enemy.LIKE_LIKE
]

# Boss groups (levels share sprite banks for bosses)
BOSS_GROUP_A = [  # L1, L2, L5, L7
    Enemy.AQUAMENTUS, Enemy.SINGLE_DIGDOGGER, Enemy.TRIPLE_DIGDOGGER,
    Enemy.SINGLE_DODONGO, Enemy.TRIPLE_DODONGO
]

BOSS_GROUP_B = [  # L3, L4, L6, L8
    Enemy.GLEEOK_1, Enemy.GLEEOK_2, Enemy.MANHANDALA,
    Enemy.RED_GOHMA, Enemy.BLUE_GOHMA
]

BOSS_GROUP_C = [  # L9 only
    Enemy.RED_LANMOLA, Enemy.BLUE_LANMOLA, Enemy.PATRA_1, Enemy.PATRA_2
]

# Map level numbers to their enemy/boss groups
LEVEL_TO_ENEMY_GROUP = {
    1: ENEMY_GROUP_A, 2: ENEMY_GROUP_A, 7: ENEMY_GROUP_A,
    3: ENEMY_GROUP_B, 5: ENEMY_GROUP_B, 8: ENEMY_GROUP_B,
    4: ENEMY_GROUP_C, 6: ENEMY_GROUP_C, 9: ENEMY_GROUP_C,
}

LEVEL_TO_BOSS_GROUP = {
    1: BOSS_GROUP_A, 2: BOSS_GROUP_A, 5: BOSS_GROUP_A, 7: BOSS_GROUP_A,
    3: BOSS_GROUP_B, 4: BOSS_GROUP_B, 6: BOSS_GROUP_B, 8: BOSS_GROUP_B,
    9: BOSS_GROUP_C,
}

# ============================================================================
# Special Items per Dungeon (vanilla configuration)
# ============================================================================

DUNGEON_SPECIAL_ITEMS = {
    1: [Item.BOW, Item.WOOD_BOOMERANG],
    2: [Item.MAGICAL_BOOMERANG],
    3: [Item.RAFT],
    4: [Item.LADDER],
    5: [Item.RECORDER],
    6: [Item.WAND],
    7: [Item.RED_CANDLE],
    8: [Item.MAGICAL_KEY, Item.BOOK],
    9: [Item.RED_RING, Item.SILVER_ARROWS],
}

# ============================================================================
# Room types to use (exclude staircase types)
# ============================================================================

VALID_ROOM_TYPES = [
    RoomType.PLAIN_ROOM,
    RoomType.SPIKE_TRAP_ROOM,
    RoomType.FOUR_SHORT_ROOM,
    RoomType.FOUR_TALL_ROOM,
    RoomType.AQUAMENTUS_ROOM,
    RoomType.GLEEOK_ROOM,
    RoomType.GOHMA_ROOM,
    RoomType.THREE_ROWS,
    RoomType.REVERSE_C,
    RoomType.CIRCLE_WALL,
    RoomType.DOUBLE_BLOCK,
    RoomType.LAVA_MOAT,
    RoomType.MAZE_ROOM,
    RoomType.GRID_ROOM,
    RoomType.VERTICAL_CHUTE_ROOM,
    RoomType.HORIZONTAL_CHUTE_ROOM,
    RoomType.VERTICAL_ROWS,
    RoomType.ZIGZAG_ROOM,
    RoomType.T_ROOM,
    RoomType.VERTICAL_MOAT_ROOM,
    RoomType.CIRCLE_MOAT_ROOM,
    RoomType.POINTLESS_MOAT_ROOM,
    RoomType.CHEVY_ROOM,
    RoomType.NSU,
    RoomType.HORIZONTAL_MOAT_ROOM,
    RoomType.DOUBLE_MOAT_ROOM,
    RoomType.DIAMOND_STAIR_ROOM,
    RoomType.NARROW_STAIR_ROOM,
    RoomType.SPIRAL_STAIR_ROOM,
    RoomType.DOUBLE_SIX_BLOCK_ROOM,
    RoomType.SINGLE_SIX_BLOCK_ROOM,
    RoomType.FIVE_PAIR_ROOM,
    RoomType.TURNSTILE_ROOM,
    RoomType.SINGLE_BLOCK_ROOM,
    RoomType.TWO_FIREBALL_ROOM,
    RoomType.FOUR_FIREBALL_ROOM,
    RoomType.DESERT_ROOM,
    RoomType.BLACK_ROOM,
    RoomType.ZELDA_ROOM,
    RoomType.GANNON_ROOM,
    RoomType.TRIFORCE_ROOM,
]

# ============================================================================
# Default wall type percentages (configurable)
# ============================================================================

DEFAULT_WALL_TYPE_CONFIG = {
    'open_door_percent': 70,      # Percentage of passages that are open doors
    'key_door_percent': 15,       # Percentage of passages that are key doors
    'bomb_hole_percent': 15,      # Percentage of passages that are bomb holes
}

# Grid constants
GRID_ROWS = 8
GRID_COLS = 16
TOTAL_ROOMS = GRID_ROWS * GRID_COLS  # 128

# Bottom row room numbers (0x70-0x7F)
BOTTOM_ROW = range(0x70, 0x80)

# Minimum rooms per level (absolute minimum)
# The algorithm uses a two-phase approach to guarantee this minimum:
# Phase 1: Prioritize growing regions below minimum
# Phase 2: Balanced growth for remaining rooms
MIN_ROOMS_PER_LEVEL = 13

# Number of rooms to leave empty (unassigned) in the grid
ROOMS_TO_REMOVE = 8

# Maximum bounding box width for a region
MAX_REGION_WIDTH = 8


def calculate_max_rooms(num_regions: int, rooms_to_remove: int = ROOMS_TO_REMOVE) -> int:
    """Calculate max rooms per region based on number of regions.

    This ensures we can fill (128 - rooms_to_remove) rooms while keeping regions balanced.
    Formula: ceil((128 - rooms_to_remove) / num_regions) + 50% buffer for flexibility.
    """
    usable_rooms = TOTAL_ROOMS - rooms_to_remove
    base = (usable_rooms + num_regions - 1) // num_regions  # ceiling division
    buffer = max(8, base // 2)  # 50% buffer, minimum 8
    return base + buffer


def room_to_coords(room_num: int) -> Tuple[int, int]:
    """Convert room number to (row, col) coordinates.

    Room numbers are organized as:
    - Row 0: 0x00-0x0F (top)
    - Row 7: 0x70-0x7F (bottom)
    """
    row = room_num >> 4  # room_num // 16
    col = room_num & 0x0F  # room_num % 16
    return (row, col)


def coords_to_room(row: int, col: int) -> int:
    """Convert (row, col) coordinates to room number."""
    return (row << 4) | col  # row * 16 + col


def get_adjacent_rooms(room_num: int) -> List[int]:
    """Get list of adjacent room numbers (cardinal directions only)."""
    row, col = room_to_coords(room_num)
    adjacent = []

    # North
    if row > 0:
        adjacent.append(coords_to_room(row - 1, col))
    # South
    if row < GRID_ROWS - 1:
        adjacent.append(coords_to_room(row + 1, col))
    # West
    if col > 0:
        adjacent.append(coords_to_room(row, col - 1))
    # East
    if col < GRID_COLS - 1:
        adjacent.append(coords_to_room(row, col + 1))

    return adjacent


def get_direction_between_rooms(from_room: int, to_room: int) -> Optional[Direction]:
    """Get the direction from one room to an adjacent room."""
    diff = to_room - from_room
    if diff == Direction.NORTH:
        return Direction.NORTH
    elif diff == Direction.SOUTH:
        return Direction.SOUTH
    elif diff == Direction.EAST:
        return Direction.EAST
    elif diff == Direction.WEST:
        return Direction.WEST
    return None


class DungeonRegion:
    """Represents a region (level) in the dungeon grid."""

    def __init__(self, level_num: int, seed_room: int):
        self.level_num = level_num
        self.rooms: Set[int] = {seed_room}
        self.start_room: int = seed_room  # Entry room in bottom row

    def add_room(self, room_num: int) -> None:
        self.rooms.add(room_num)

    def size(self) -> int:
        return len(self.rooms)

    def get_bounding_box(self) -> Tuple[int, int, int, int]:
        """Return (min_row, max_row, min_col, max_col)."""
        min_row, max_row = GRID_ROWS, -1
        min_col, max_col = GRID_COLS, -1

        for room in self.rooms:
            row, col = room_to_coords(room)
            min_row = min(min_row, row)
            max_row = max(max_row, row)
            min_col = min(min_col, col)
            max_col = max(max_col, col)

        return (min_row, max_row, min_col, max_col)

    def get_width(self) -> int:
        """Get the width of the bounding box in columns."""
        _, _, min_col, max_col = self.get_bounding_box()
        return max_col - min_col + 1

    def can_add_room(self, room_num: int) -> bool:
        """Check if adding this room would violate the max width constraint."""
        if room_num in self.rooms:
            return False

        _, col = room_to_coords(room_num)
        _, _, min_col, max_col = self.get_bounding_box()

        new_min_col = min(min_col, col)
        new_max_col = max(max_col, col)
        new_width = new_max_col - new_min_col + 1

        return new_width <= MAX_REGION_WIDTH

    def get_frontier(self, assigned: Set[int]) -> List[int]:
        """Get unassigned rooms adjacent to this region."""
        frontier = set()
        for room in self.rooms:
            for adj in get_adjacent_rooms(room):
                if adj not in assigned and self.can_add_room(adj):
                    frontier.add(adj)
        return list(frontier)

    def is_contiguous(self) -> bool:
        """Verify all rooms in the region are connected."""
        if not self.rooms:
            return True

        start = next(iter(self.rooms))
        visited = {start}
        stack = [start]

        while stack:
            current = stack.pop()
            for adj in get_adjacent_rooms(current):
                if adj in self.rooms and adj not in visited:
                    visited.add(adj)
                    stack.append(adj)

        return len(visited) == len(self.rooms)


class DungeonLayoutGenerator:
    """Generates dungeon layouts using balanced region-growing algorithm."""

    def __init__(self, num_regions: int, rng: RandomNumberGenerator):
        """Initialize the generator.

        Args:
            num_regions: Number of regions to create (6 for L1-6, 3 for L7-9)
            rng: Random number generator
        """
        self.num_regions = num_regions
        self.rng = rng
        self.regions: List[DungeonRegion] = []
        self.assigned: Set[int] = set()
        # Calculate max rooms dynamically based on number of regions
        self.max_rooms_per_region = calculate_max_rooms(num_regions)

    def generate(self) -> bool:
        """Generate a dungeon layout with the specified number of regions.

        Returns:
            True if successful, False if constraints couldn't be satisfied.
        """
        # Step 1: Place seed points in the bottom row
        if not self._place_seeds():
            log.warning("Failed to place seed points")
            return False

        # Step 2: Grow regions until target rooms are assigned
        if not self._grow_regions():
            log.warning("Failed to grow all regions")
            return False

        # Step 3: Validate the result
        if not self._validate():
            log.warning("Layout validation failed")
            return False

        # Step 4: Sort regions by size (smallest = level 1, largest = level N)
        self._sort_regions_by_size()

        return True

    def _sort_regions_by_size(self) -> None:
        """Sort regions so smaller regions get lower level numbers.

        Level 1 = smallest, Level N = largest.
        """
        # Sort regions by size
        sorted_regions = sorted(self.regions, key=lambda r: r.size())

        # Reassign level numbers based on size order
        for new_level, region in enumerate(sorted_regions, start=1):
            region.level_num = new_level
            # Update start_room to reflect the region's actual entry point
            # (keep the original seed room as the start room)

        # Replace the regions list with the sorted one
        self.regions = sorted_regions

        log.debug(f"Sorted regions by size: {[(r.level_num, r.size()) for r in self.regions]}")

    def _place_seeds(self) -> bool:
        """Place initial seed points in the bottom row, spread apart.

        Uses strict spacing to ensure regions have enough territory to grow.
        For 6 regions in 16 columns, each region gets roughly 2-3 columns.
        """
        # Calculate strict positions for even distribution
        # For 6 regions: columns 1, 4, 6, 9, 11, 14 (spacing ~2.67)
        # For 3 regions: columns 2, 7, 12 (spacing ~5)
        spacing = GRID_COLS / self.num_regions
        base_positions = []
        for i in range(self.num_regions):
            col = int(i * spacing + spacing / 2)
            col = max(0, min(GRID_COLS - 1, col))
            base_positions.append(col)

        # Add small random offset (±1 at most) to add variety
        seed_cols = []
        for col in base_positions:
            offset = self.rng.randint(-1, 1)
            new_col = max(0, min(GRID_COLS - 1, col + offset))
            seed_cols.append(new_col)

        # Ensure minimum spacing between adjacent seeds
        min_spacing = max(1, int(spacing) - 1)
        for i in range(1, len(seed_cols)):
            while abs(seed_cols[i] - seed_cols[i-1]) < min_spacing:
                if seed_cols[i] <= seed_cols[i-1]:
                    seed_cols[i] = min(GRID_COLS - 1, seed_cols[i] + 1)
                else:
                    break

        # Ensure no duplicate columns
        used_cols = set()
        final_cols = []
        for col in seed_cols:
            while col in used_cols:
                col = (col + 1) % GRID_COLS
            used_cols.add(col)
            final_cols.append(col)

        # Shuffle which level gets which position
        level_order = list(range(self.num_regions))
        self.rng.shuffle(level_order)

        # Create regions with seed points
        for level_idx, col in zip(level_order, final_cols):
            room = coords_to_room(GRID_ROWS - 1, col)  # Bottom row
            region = DungeonRegion(level_num=level_idx + 1, seed_room=room)
            self.regions.append(region)
            self.assigned.add(room)

        # Sort regions by level number for consistent ordering
        self.regions.sort(key=lambda r: r.level_num)

        log.debug(f"Placed {self.num_regions} seeds at columns: {final_cols}")
        return True

    def _grow_regions(self) -> bool:
        """Grow regions using a two-phase balanced region-growing algorithm.

        Phase 1 (Round-Robin): Grow each region one cell at a time in strict
                 round-robin fashion until all reach MIN_ROOMS_PER_LEVEL.
                 This prevents any region from getting boxed in early.

        Phase 2 (Balanced): Once all regions have reached minimum size, use
                 balanced growth (smallest region first) for remaining rooms.
        """
        max_iterations = TOTAL_ROOMS * 2  # Safety limit
        iteration = 0

        # Phase 1: Round-robin growth until all regions reach minimum
        stuck_count = 0
        max_stuck_rounds = 10  # Try multiple rounds before giving up
        while any(r.size() < MIN_ROOMS_PER_LEVEL for r in self.regions):
            # Try each region in order, giving each one chance to grow
            any_grew = False
            for region in self.regions:
                if region.size() >= MIN_ROOMS_PER_LEVEL:
                    continue  # This region already at minimum

                iteration += 1
                if iteration > max_iterations:
                    log.warning(f"Phase 1 exceeded max iterations")
                    return False

                # Try to grow this region
                frontier = region.get_frontier(self.assigned)
                if not frontier:
                    # Try with relaxed width constraint
                    for room in region.rooms:
                        for adj in get_adjacent_rooms(room):
                            if adj not in self.assigned:
                                frontier.append(adj)
                    frontier = list(set(frontier))

                if frontier:
                    room_to_add = self.rng.choice(frontier)
                    region.add_room(room_to_add)
                    self.assigned.add(room_to_add)
                    any_grew = True
                    stuck_count = 0  # Reset stuck counter on successful growth
                    log.debug(f"Phase 1: Added room 0x{room_to_add:02X} to region {region.level_num} "
                             f"(size now {region.size()})")

            if not any_grew:
                stuck_count += 1
                if stuck_count >= max_stuck_rounds:
                    stuck_regions = [r for r in self.regions if r.size() < MIN_ROOMS_PER_LEVEL]
                    log.warning(f"Phase 1 stuck after {stuck_count} rounds: {len(stuck_regions)} regions below minimum")
                    break
                # Try one more round - other regions at minimum might grow and unblock
                # Let at-minimum regions grow one cell to potentially unblock others
                for region in self.regions:
                    if region.size() >= MIN_ROOMS_PER_LEVEL and region.size() < self.max_rooms_per_region:
                        frontier = region.get_frontier(self.assigned)
                        if not frontier:
                            for room in region.rooms:
                                for adj in get_adjacent_rooms(room):
                                    if adj not in self.assigned:
                                        frontier.append(adj)
                            frontier = list(set(frontier))
                        if frontier:
                            room_to_add = self.rng.choice(frontier)
                            region.add_room(room_to_add)
                            self.assigned.add(room_to_add)
                            log.debug(f"Phase 1 unblock: Added room 0x{room_to_add:02X} to region {region.level_num}")
                            break  # Only grow one at-minimum region per stuck round

        # Phase 2: Balanced growth for remaining rooms (leave ROOMS_TO_REMOVE empty)
        target_rooms = TOTAL_ROOMS - ROOMS_TO_REMOVE
        while len(self.assigned) < target_rooms and iteration < max_iterations:
            iteration += 1

            # Find all regions that can grow
            all_growable = []
            for region in self.regions:
                if region.size() >= self.max_rooms_per_region:
                    continue
                frontier = region.get_frontier(self.assigned)
                if frontier:
                    all_growable.append((region, frontier))

            if not all_growable:
                # Try fallback with relaxed constraints
                all_growable = self._get_fallback_growable_regions(ignore_max_size=False)
                if not all_growable:
                    all_growable = self._get_fallback_growable_regions(ignore_max_size=True)
                    if not all_growable:
                        if len(self.assigned) < target_rooms:
                            log.warning(f"Phase 2 stuck with {len(self.assigned)} rooms assigned")
                            return False
                        break

            # Prioritize regions below minimum (if any still exist)
            below_min = [(r, f) for r, f in all_growable if r.size() < MIN_ROOMS_PER_LEVEL]
            if below_min:
                growable_regions = below_min
            else:
                growable_regions = all_growable

            # Sort by region size (smallest first)
            growable_regions.sort(key=lambda x: x[0].size())
            min_size = growable_regions[0][0].size()
            smallest_regions = [(r, f) for r, f in growable_regions if r.size() == min_size]

            region, frontier = self.rng.choice(smallest_regions)
            room_to_add = self.rng.choice(frontier)
            region.add_room(room_to_add)
            self.assigned.add(room_to_add)

            log.debug(f"Added room 0x{room_to_add:02X} to region {region.level_num} "
                     f"(size now {region.size()})")

        if len(self.assigned) < target_rooms:
            log.error(f"Failed to assign target rooms. Assigned: {len(self.assigned)}/{target_rooms}")
            return False

        return True

    def _get_fallback_growable_regions(self, ignore_max_size: bool = False) -> List[Tuple['DungeonRegion', List[int]]]:
        """Get growable regions ignoring width constraint (fallback for stuck situations).

        Args:
            ignore_max_size: If True, also ignore the max size constraint (last resort).
        """
        growable_regions = []
        for region in self.regions:
            # Respect max size unless explicitly ignoring it
            if not ignore_max_size and region.size() >= self.max_rooms_per_region:
                continue
            # Get all unassigned adjacent rooms (ignore width constraint)
            frontier = []
            for room in region.rooms:
                for adj in get_adjacent_rooms(room):
                    if adj not in self.assigned:
                        frontier.append(adj)
            if frontier:
                # Remove duplicates
                frontier = list(set(frontier))
                growable_regions.append((region, frontier))
        return growable_regions

    def _validate(self) -> bool:
        """Validate the generated layout meets all constraints."""
        # Allow some overflow in max size for edge cases where fallback was needed
        max_with_buffer = self.max_rooms_per_region + 5

        for region in self.regions:
            # Check size constraints
            if region.size() < MIN_ROOMS_PER_LEVEL:
                log.error(f"Region {region.level_num} has only {region.size()} rooms "
                         f"(minimum: {MIN_ROOMS_PER_LEVEL})")
                return False

            if region.size() > max_with_buffer:
                log.error(f"Region {region.level_num} has {region.size()} rooms "
                         f"(maximum: {max_with_buffer})")
                return False

            # Check width constraint (with buffer for fallback/unblock situations)
            width = region.get_width()
            max_width_with_buffer = MAX_REGION_WIDTH + 4  # Allow more flexibility
            if width > max_width_with_buffer:
                log.error(f"Region {region.level_num} has width {width} "
                         f"(maximum: {max_width_with_buffer})")
                return False

            # Check contiguity
            if not region.is_contiguous():
                log.error(f"Region {region.level_num} is not contiguous")
                return False

            # Check bottom row entry
            has_bottom_room = any(room in BOTTOM_ROW for room in region.rooms)
            if not has_bottom_room:
                log.error(f"Region {region.level_num} has no room in bottom row")
                return False

        # Check empty rooms count
        total_assigned = sum(region.size() for region in self.regions)
        empty_rooms = TOTAL_ROOMS - total_assigned
        log.info(f"Layout validation passed. Region sizes: "
                f"{[r.size() for r in self.regions]}, Empty rooms: {empty_rooms}")
        return True

    def get_room_assignments(self) -> Dict[int, int]:
        """Return mapping of room_num -> level_num."""
        assignments = {}
        for region in self.regions:
            for room in region.rooms:
                assignments[room] = region.level_num
        return assignments

    def get_start_rooms(self) -> Dict[int, int]:
        """Return mapping of level_num -> start_room_num."""
        return {region.level_num: region.start_room for region in self.regions}


class OrganicDungeonLayoutGenerator:
    """Generates dungeon layouts using organic growth algorithm.

    This creates irregular, branching regions with tendril-like shapes
    rather than compact rectangular shapes. It allows for:
    - Empty rooms in the grid
    - Some disconnected level sections
    - Branching, tendril-like growth patterns
    """

    def __init__(self, num_regions: int, rng: RandomNumberGenerator,
                 rooms_to_remove: int = ROOMS_TO_REMOVE, max_disconnected: int = 0):
        """Initialize the organic generator.

        Args:
            num_regions: Number of regions to create (6 for L1-6, 3 for L7-9)
            rng: Random number generator
            rooms_to_remove: Number of rooms to leave empty (default: ROOMS_TO_REMOVE)
            max_disconnected: Number of levels allowed to be disconnected (default: 0)
        """
        self.num_regions = num_regions
        self.rng = rng
        self.rooms_to_remove = rooms_to_remove
        self.max_disconnected = max_disconnected
        self.regions: List[DungeonRegion] = []
        # Grid tracks which level each room belongs to (-1 = unassigned)
        self.grid: List[List[int]] = [[-1] * GRID_COLS for _ in range(GRID_ROWS)]
        # Frontiers track unassigned rooms adjacent to each region
        self.frontiers: List[Set[int]] = []

    def generate(self) -> bool:
        """Generate an organic dungeon layout.

        First tries to generate with fully contiguous levels (max_disconnected=0).
        If that fails after many attempts, falls back to allowing some disconnected levels.

        Returns:
            True if successful, False if constraints couldn't be satisfied.
        """
        # Phase 1: Try with contiguous levels only (many attempts)
        contiguous_attempts = 400
        original_max_disconnected = self.max_disconnected

        for attempt in range(contiguous_attempts):
            self.max_disconnected = 0  # Enforce contiguous
            if self._try_generate():
                log.info(f"Organic layout generated (contiguous) on attempt {attempt + 1}")
                self._sort_regions_by_size()
                return True

            # Reset state for next attempt
            self._reset_state()

        # Phase 2: Fall back to allowing some disconnected levels if original allowed it
        if original_max_disconnected > 0:
            log.warning(f"Failed to generate contiguous layout after {contiguous_attempts} attempts, "
                       f"allowing up to {original_max_disconnected} disconnected levels")
            fallback_attempts = 100
            for attempt in range(fallback_attempts):
                self.max_disconnected = original_max_disconnected
                if self._try_generate():
                    log.info(f"Organic layout generated (with disconnected) on attempt "
                            f"{contiguous_attempts + attempt + 1}")
                    self._sort_regions_by_size()
                    return True

                # Reset state for next attempt
                self._reset_state()

        log.error(f"Failed to generate organic layout after {contiguous_attempts} attempts")
        return False

    def _reset_state(self) -> None:
        """Reset generator state for a new attempt."""
        self.regions = []
        self.grid = [[-1] * GRID_COLS for _ in range(GRID_ROWS)]
        self.frontiers = []

    def _try_generate(self) -> bool:
        """Single attempt at generating an organic layout."""
        # Step 1: Place seed points in the bottom row with jitter
        if not self._place_seeds():
            return False

        # Step 2: Grow regions organically
        if not self._grow_regions_organic():
            return False

        # Step 3: Validate the result
        return self._validate()

    def _sort_regions_by_size(self) -> None:
        """Sort regions so smaller regions get lower level numbers.

        Level 1 = smallest, Level N = largest.
        """
        # Sort regions by size
        sorted_regions = sorted(self.regions, key=lambda r: r.size())

        # Reassign level numbers based on size order
        for new_level, region in enumerate(sorted_regions, start=1):
            region.level_num = new_level

        # Replace the regions list with the sorted one
        self.regions = sorted_regions

        log.debug(f"Organic: Sorted regions by size: {[(r.level_num, r.size()) for r in self.regions]}")

    def _place_seeds(self) -> bool:
        """Place initial seed points in the bottom row with random jitter."""
        spacing = GRID_COLS / self.num_regions
        seed_cols = []

        for i in range(self.num_regions):
            base_col = int(i * spacing + spacing / 2)
            # Larger jitter for more randomness
            if spacing > 3:
                jitter = self.rng.randint(-2, 2)
            else:
                jitter = self.rng.randint(-1, 1)
            col = max(0, min(GRID_COLS - 1, base_col + jitter))
            seed_cols.append(col)

        # Ensure no duplicate columns
        used_cols: Set[int] = set()
        final_cols = []
        for col in seed_cols:
            while col in used_cols:
                col = (col + 1) % GRID_COLS
            used_cols.add(col)
            final_cols.append(col)

        # Shuffle which level gets which position
        level_order = list(range(self.num_regions))
        self.rng.shuffle(level_order)

        # Create regions with seed points (always on bottom row)
        for level_idx, col in zip(level_order, final_cols):
            room = coords_to_room(GRID_ROWS - 1, col)  # Bottom row
            region = DungeonRegion(level_num=level_idx + 1, seed_room=room)
            self.regions.append(region)

            row, col_coord = room_to_coords(room)
            self.grid[row][col_coord] = level_idx

            # Initialize frontier for this region
            frontier: Set[int] = set()
            for adj in get_adjacent_rooms(room):
                adj_row, adj_col = room_to_coords(adj)
                if self.grid[adj_row][adj_col] == -1:
                    frontier.add(adj)
            self.frontiers.append(frontier)

        # Sort regions by level number for consistent ordering
        # Also reorder frontiers to match
        combined = list(zip(self.regions, self.frontiers))
        combined.sort(key=lambda x: x[0].level_num)
        self.regions = [r for r, f in combined]
        self.frontiers = [f for r, f in combined]

        log.debug(f"Organic: Placed {self.num_regions} seeds at columns: {final_cols}")
        return True

    def _organic_score(self, region: DungeonRegion, room_num: int) -> float:
        """Score that encourages irregular, organic growth.

        Prefers cells with 1-2 neighbors (creates branches/tendrils).
        Penalizes cells with 3-4 neighbors (fills in gaps, makes blocky).
        """
        row, col = room_to_coords(room_num)

        # Count adjacent cells that are already in this region
        adjacent_count = 0
        for adj in get_adjacent_rooms(room_num):
            if adj in region.rooms:
                adjacent_count += 1

        # Score based on adjacency
        if adjacent_count == 1:
            adjacency_score = 3.0  # Best - creates tendrils
        elif adjacent_count == 2:
            adjacency_score = 2.0  # Good - continues branches
        elif adjacent_count == 3:
            adjacency_score = -1.0  # Bad - starts filling in
        else:  # adjacent_count == 4
            adjacency_score = -3.0  # Worst - completely fills

        # Add randomness to prevent predictable patterns
        random_factor = self.rng.randint(-100, 100) / 100.0  # -1.0 to 1.0

        return adjacency_score + random_factor

    def _check_width_constraint(self, region: DungeonRegion, room_num: int) -> bool:
        """Check if adding room would violate max width constraint."""
        _, col = room_to_coords(room_num)
        _, _, min_col, max_col = region.get_bounding_box()

        new_min_col = min(min_col, col)
        new_max_col = max(max_col, col)
        new_width = new_max_col - new_min_col + 1

        return new_width <= MAX_REGION_WIDTH

    def _grow_regions_organic(self) -> bool:
        """Grow regions using organic scoring algorithm."""
        target_size = (TOTAL_ROOMS - self.rooms_to_remove) // self.num_regions
        total_assigned = sum(len(r.rooms) for r in self.regions)
        target_total = TOTAL_ROOMS - self.rooms_to_remove

        max_iterations = TOTAL_ROOMS * 3
        iteration = 0

        while total_assigned < target_total and iteration < max_iterations:
            iteration += 1

            # Calculate region sizes
            region_sizes = [len(region.rooms) for region in self.regions]

            # Find best (level, cell) pair using organic scoring
            best_level_idx: Optional[int] = None
            best_cell: Optional[int] = None
            best_score = float('-inf')

            # Sort levels by size (smallest first) but with some randomness
            levels_by_size = sorted(range(self.num_regions), key=lambda x: region_sizes[x])
            # Add shuffling to smaller half to prevent too much ordering
            half = len(levels_by_size) // 2
            if half > 0 and self.rng.randint(0, 100) > 30:
                smaller_half = levels_by_size[:half]
                self.rng.shuffle(smaller_half)
                levels_by_size = smaller_half + levels_by_size[half:]

            for level_idx in levels_by_size:
                frontier = self.frontiers[level_idx]
                if not frontier:
                    continue

                # Sample from frontier (don't check every cell)
                sample_size = min(len(frontier), 10)
                frontier_list = list(frontier)
                cells_to_check = []
                for _ in range(sample_size):
                    idx = self.rng.randint(0, len(frontier_list) - 1)
                    cells_to_check.append(frontier_list[idx])

                for cell in cells_to_check:
                    cell_row, cell_col = room_to_coords(cell)

                    # Skip if already assigned
                    if self.grid[cell_row][cell_col] != -1:
                        continue

                    # Check width constraint
                    if not self._check_width_constraint(self.regions[level_idx], cell):
                        continue

                    # Calculate organic score
                    organic = self._organic_score(self.regions[level_idx], cell)

                    # Size penalty (less aggressive than standard algorithm)
                    size_penalty = (region_sizes[level_idx] / target_size) * 0.5

                    # Final score
                    score = organic - size_penalty

                    if score > best_score:
                        best_score = score
                        best_level_idx = level_idx
                        best_cell = cell

            if best_cell is None:
                break

            # Assign the best cell
            r, c = room_to_coords(best_cell)
            self.regions[best_level_idx].add_room(best_cell)
            self.grid[r][c] = best_level_idx
            total_assigned += 1

            # Update frontiers
            self.frontiers[best_level_idx].discard(best_cell)

            # Add new frontier cells
            for adj in get_adjacent_rooms(best_cell):
                adj_r, adj_c = room_to_coords(adj)
                if self.grid[adj_r][adj_c] == -1:
                    self.frontiers[best_level_idx].add(adj)

            # Occasionally "prune" frontiers to create gaps (5% chance)
            if self.rng.randint(0, 100) < 5:
                for frontier in self.frontiers:
                    if len(frontier) > 5:
                        # Remove a random frontier cell to create gaps
                        frontier_list = list(frontier)
                        idx = self.rng.randint(0, len(frontier_list) - 1)
                        frontier.discard(frontier_list[idx])

        return True

    def _count_connected_components(self, region: DungeonRegion) -> int:
        """Count number of connected components in a region."""
        if not region.rooms:
            return 0

        remaining = set(region.rooms)
        components = 0

        while remaining:
            components += 1
            start = next(iter(remaining))
            visited = {start}
            stack = [start]

            while stack:
                current = stack.pop()
                for adj in get_adjacent_rooms(current):
                    if adj in remaining and adj not in visited:
                        visited.add(adj)
                        stack.append(adj)

            remaining -= visited

        return components

    def _validate(self) -> bool:
        """Validate the generated layout meets all constraints."""
        # Check each region
        for region in self.regions:
            # Minimum size constraint (13 rooms per level)
            if region.size() < MIN_ROOMS_PER_LEVEL:
                log.debug(f"Organic: Region {region.level_num} has only {region.size()} rooms "
                         f"(minimum: {MIN_ROOMS_PER_LEVEL})")
                return False

            # Must have at least one room in bottom row (row 7)
            has_bottom_room = any(room in BOTTOM_ROW for room in region.rooms)
            if not has_bottom_room:
                log.debug(f"Organic: Region {region.level_num} has no room in bottom row")
                return False

            # Width constraint (with small buffer for organic growth)
            width = region.get_width()
            if width > MAX_REGION_WIDTH + 2:
                log.debug(f"Organic: Region {region.level_num} has width {width} "
                         f"(maximum: {MAX_REGION_WIDTH + 2})")
                return False

        # Count disconnected regions
        disconnected_count = sum(1 for region in self.regions
                                if self._count_connected_components(region) > 1)
        if disconnected_count > self.max_disconnected:
            log.debug(f"Organic: Too many disconnected regions: {disconnected_count} "
                     f"(max: {self.max_disconnected})")
            return False

        # Check balance (more lenient for organic shapes)
        sizes = [region.size() for region in self.regions]
        min_size = min(sizes)
        max_size = max(sizes)
        if max_size > min_size * 3.5:
            log.debug(f"Organic: Regions too unbalanced: {max_size}/{min_size} = "
                     f"{max_size/min_size:.2f}")
            return False

        # Count empty cells
        total_cells_assigned = sum(region.size() for region in self.regions)
        empty_cells = TOTAL_ROOMS - total_cells_assigned
        if empty_cells > self.rooms_to_remove + 2:
            log.debug(f"Organic: Too many empty cells: {empty_cells} "
                     f"(target: {self.rooms_to_remove})")
            return False

        log.info(f"Organic layout validation passed. Region sizes: {sizes}, "
                f"Empty rooms: {empty_cells}, Disconnected: {disconnected_count}")
        return True

    def get_room_assignments(self) -> Dict[int, int]:
        """Return mapping of room_num -> level_num."""
        assignments = {}
        for region in self.regions:
            for room in region.rooms:
                assignments[room] = region.level_num
        return assignments

    def get_start_rooms(self) -> Dict[int, int]:
        """Return mapping of level_num -> start_room_num."""
        return {region.level_num: region.start_room for region in self.regions}


class DungeonRandomizer:
    """Randomizer for dungeon layouts."""

    def __init__(self, data_table: DataTable, flags: Flags, rng: RandomNumberGenerator) -> None:
        """Initialize the DungeonRandomizer.

        Args:
            data_table: The DataTable instance to read from and write to
            flags: The Flags instance containing user settings
            rng: Random number generator for shuffling
        """
        self.data_table = data_table
        self.flags = flags
        self.rng = rng

    def Randomize(self, seed: int) -> bool:
        """Main entry point for dungeon layout randomization.

        Args:
            seed: Seed for the random number generator (for logging purposes)

        Returns:
            True if randomization succeeded, False otherwise.
        """
        if not self.flags.randomize_dungeon_layout:
            log.debug("Dungeon layout randomization is disabled")
            return True

        # Determine which algorithm to use
        use_organic = self.flags.organic_dungeon_layout
        algorithm_name = "organic" if use_organic else "balanced region-growing"
        log.info(f"Starting dungeon layout randomization (seed: {seed}, algorithm: {algorithm_name})")

        # Retry logic: try multiple times with different random states
        max_retries = 10
        for attempt in range(max_retries):
            if attempt > 0:
                log.info(f"Retry attempt {attempt}/{max_retries - 1} for dungeon layout generation")
                # Advance the RNG state by consuming some random values
                # This ensures different random choices on each retry
                for _ in range(attempt * 100):
                    self.rng.randint(0, 1000)

            # Generate layout for levels 1-6 (6 regions)
            log.info("Generating layout for levels 1-6...")
            if use_organic:
                layout_1_6: Union[DungeonLayoutGenerator, OrganicDungeonLayoutGenerator] = \
                    OrganicDungeonLayoutGenerator(num_regions=6, rng=self.rng)
            else:
                layout_1_6 = DungeonLayoutGenerator(num_regions=6, rng=self.rng)
            if not layout_1_6.generate():
                log.warning(f"Failed to generate layout for levels 1-6 (attempt {attempt + 1})")
                continue

            # Generate layout for levels 7-9 (3 regions)
            log.info("Generating layout for levels 7-9...")
            if use_organic:
                layout_7_9: Union[DungeonLayoutGenerator, OrganicDungeonLayoutGenerator] = \
                    OrganicDungeonLayoutGenerator(num_regions=3, rng=self.rng)
            else:
                layout_7_9 = DungeonLayoutGenerator(num_regions=3, rng=self.rng)
            if not layout_7_9.generate():
                log.warning(f"Failed to generate layout for levels 7-9 (attempt {attempt + 1})")
                continue

            # Both layouts generated successfully
            # Apply layouts to DataTable (sets walls and entrance rooms)
            self._apply_layout(layout_1_6, is_level_7_9=False)
            self._apply_layout(layout_7_9, is_level_7_9=True)

            # Initialize dungeons (room types, enemies, paired walls, items)
            self._initialize_dungeons(layout_1_6, is_level_7_9=False)
            self._initialize_dungeons(layout_7_9, is_level_7_9=True)

            log.info(f"Dungeon layout randomization completed successfully (attempt {attempt + 1})")
            return True

        log.error(f"Failed to generate dungeon layouts after {max_retries} attempts")
        return False

    def _apply_layout(self, layout: Union[DungeonLayoutGenerator, OrganicDungeonLayoutGenerator],
                      is_level_7_9: bool) -> None:
        """Apply a generated layout to the DataTable.

        Args:
            layout: The generated layout (either standard or organic)
            is_level_7_9: True if this is for levels 7-9, False for levels 1-6
        """
        assignments = layout.get_room_assignments()
        start_rooms = layout.get_start_rooms()

        # Adjust level numbers for 7-9 grid
        # For levels 1-6, we use level 1 as the reference (they share room data)
        # For levels 7-9, we use level 7 as the reference (they share room data)
        level_offset = 6 if is_level_7_9 else 0
        reference_level = LevelNum(7 if is_level_7_9 else 1)

        # Step 1: Reset all rooms to blank state
        self._reset_rooms(reference_level)

        # Step 2: Set walls between different regions to SOLID_WALL,
        #         and walls within regions to OPEN_DOOR
        self._set_walls(reference_level, assignments)

        # Step 3: Set up entrance rooms
        for local_level, room_num in start_rooms.items():
            actual_level = local_level + level_offset

            # Set room type to ENTRANCE_ROOM
            self.data_table.SetRoomType(reference_level, RoomNum(room_num), RoomType.ENTRANCE_ROOM)

            # Set start room in level_info using the new API
            self.data_table.SetLevelStartRoom(actual_level, room_num)

            log.info(f"Level {actual_level} entrance at room 0x{room_num:02X}")

    def _reset_rooms(self, level_num: LevelNum) -> None:
        """Reset all rooms to a blank state.

        Args:
            level_num: Reference level number (1 for L1-6 grid, 7 for L7-9 grid)
        """
        for room_num in Range.VALID_ROOM_NUMBERS:
            room_type = self.data_table.GetRoomType(level_num, RoomNum(room_num))

            # Skip staircase rooms - they have special data format
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            # Reset room type to PLAIN_ROOM
            self.data_table.SetRoomType(level_num, RoomNum(room_num), RoomType.PLAIN_ROOM)

            # Reset item to NO_ITEM (Item.RUPEE = 0x18 is used as NO_ITEM in this codebase)
            self.data_table.SetItem(level_num, RoomNum(room_num), Item.RUPEE)

            # Reset enemy to NOTHING
            self.data_table.SetEnemy(level_num, RoomNum(room_num), Enemy.NOTHING)

            # Reset walls to SOLID_WALL (will be opened as needed)
            for direction in [Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST]:
                self.data_table.SetWall(level_num, RoomNum(room_num), direction, WallType.SOLID_WALL)

    def _set_walls(self, level_num: LevelNum, assignments: Dict[int, int]) -> None:
        """Set wall types based on region assignments.

        Walls between rooms in the same region -> OPEN_DOOR
        Walls between rooms in different regions -> SOLID_WALL

        Args:
            level_num: Reference level number (1 for L1-6 grid, 7 for L7-9 grid)
            assignments: Mapping of room_num -> region level_num
        """
        for room_num in Range.VALID_ROOM_NUMBERS:
            room_level = assignments.get(room_num, 0)

            # Skip staircase rooms
            room_type = self.data_table.GetRoomType(level_num, RoomNum(room_num))
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            for adj_room_num in get_adjacent_rooms(room_num):
                adj_level = assignments.get(adj_room_num, 0)
                direction = get_direction_between_rooms(room_num, adj_room_num)

                if direction is None:
                    continue

                if room_level == adj_level and room_level > 0:
                    # Same region - open door
                    self.data_table.SetWall(level_num, RoomNum(room_num), direction, WallType.OPEN_DOOR)
                else:
                    # Different regions - solid wall
                    self.data_table.SetWall(level_num, RoomNum(room_num), direction, WallType.SOLID_WALL)

    def _initialize_dungeons(self, layout: Union[DungeonLayoutGenerator, OrganicDungeonLayoutGenerator],
                             is_level_7_9: bool,
                             wall_config: Optional[Dict[str, int]] = None) -> None:
        """Initialize all dungeons in the layout with rooms, enemies, walls, and items.

        Args:
            layout: The generated layout
            is_level_7_9: True if this is for levels 7-9, False for levels 1-6
            wall_config: Optional dict with wall type percentages
        """
        if wall_config is None:
            wall_config = DEFAULT_WALL_TYPE_CONFIG

        level_offset = 6 if is_level_7_9 else 0
        reference_level = LevelNum(7 if is_level_7_9 else 1)

        # Process each region (dungeon level)
        for region in layout.regions:
            actual_level = region.level_num + level_offset
            rooms_list = list(region.rooms)

            log.info(f"Initializing Level {actual_level} with {len(rooms_list)} rooms")

            # Step 1: Set random room types for all rooms
            self._set_room_types(reference_level, rooms_list, actual_level)

            # Step 2: Set enemies for all non-entrance rooms
            self._set_enemies(reference_level, rooms_list, actual_level, region.start_room)

            # Step 3: Set paired wall types (key doors, bomb holes)
            key_door_count = self._set_paired_walls(reference_level, rooms_list, wall_config)

            # Step 4: Place items (includes key balancing)
            self._place_items(reference_level, rooms_list, actual_level, key_door_count)

            # Step 5: Special L9 handling
            if actual_level == 9:
                self._setup_level_9_special(reference_level, rooms_list)

    def _set_room_types(self, reference_level: LevelNum, rooms: List[int], actual_level: int) -> None:
        """Set random room types for all rooms in a level.

        Args:
            reference_level: Reference level for the grid (1 or 7)
            rooms: List of room numbers in this level
            actual_level: The actual level number (1-9)
        """
        for room_num in rooms:
            # Skip entrance rooms (already set)
            room_type = self.data_table.GetRoomType(reference_level, RoomNum(room_num))
            if room_type == RoomType.ENTRANCE_ROOM:
                continue

            # Skip staircase rooms
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            # Pick a random room type
            new_room_type = self.rng.choice(VALID_ROOM_TYPES)
            self.data_table.SetRoomType(reference_level, RoomNum(room_num), new_room_type)

    def _set_enemies(self, reference_level: LevelNum, rooms: List[int],
                     actual_level: int, entrance_room: int) -> None:
        """Set enemies for all rooms in a level.

        Args:
            reference_level: Reference level for the grid (1 or 7)
            rooms: List of room numbers in this level
            actual_level: The actual level number (1-9)
            entrance_room: Room number of the entrance (no enemies here)
        """
        enemy_group = LEVEL_TO_ENEMY_GROUP.get(actual_level, ENEMY_GROUP_A)
        boss_group = LEVEL_TO_BOSS_GROUP.get(actual_level, BOSS_GROUP_A)

        # Pick one room to be the boss room (not the entrance)
        non_entrance_rooms = [r for r in rooms if r != entrance_room]
        if non_entrance_rooms:
            boss_room = self.rng.choice(non_entrance_rooms)
        else:
            boss_room = None

        for room_num in rooms:
            # Skip entrance room - no enemies
            if room_num == entrance_room:
                continue

            # Skip staircase rooms
            room_type = self.data_table.GetRoomType(reference_level, RoomNum(room_num))
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            # Boss room gets a boss
            if room_num == boss_room:
                enemy = self.rng.choice(boss_group)
            else:
                # Regular room - pick random enemy from the group
                enemy = self.rng.choice(enemy_group)

            self.data_table.SetEnemy(reference_level, RoomNum(room_num), enemy)

            # Set enemy quantity (0-3)
            quantity = self.rng.randint(0, 3)
            self.data_table.SetEnemyQuantity(reference_level, RoomNum(room_num), quantity)

    def _set_paired_walls(self, reference_level: LevelNum, rooms: List[int],
                          wall_config: Dict[str, int]) -> int:
        """Set paired wall types (key doors, bomb holes) for passages within a level.

        Returns the number of key doors placed (for key balancing).

        Args:
            reference_level: Reference level for the grid (1 or 7)
            rooms: List of room numbers in this level
            wall_config: Dict with wall type percentages

        Returns:
            Number of key door pairs placed
        """
        rooms_set = set(rooms)
        processed_pairs: Set[Tuple[int, int]] = set()
        key_door_count = 0

        open_percent = wall_config.get('open_door_percent', 70)
        key_percent = wall_config.get('key_door_percent', 15)
        # bomb_percent is the remainder

        for room_num in rooms:
            # Skip staircase rooms
            room_type = self.data_table.GetRoomType(reference_level, RoomNum(room_num))
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            for adj_room_num in get_adjacent_rooms(room_num):
                # Only process passages within this level
                if adj_room_num not in rooms_set:
                    continue

                # Skip already processed pairs
                pair = (min(room_num, adj_room_num), max(room_num, adj_room_num))
                if pair in processed_pairs:
                    continue
                processed_pairs.add(pair)

                # Get the direction from room to adjacent
                direction = get_direction_between_rooms(room_num, adj_room_num)
                if direction is None:
                    continue

                # Skip if either room is a staircase
                adj_room_type = self.data_table.GetRoomType(reference_level, RoomNum(adj_room_num))
                if adj_room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                    continue

                # Randomly decide wall type
                roll = self.rng.randint(0, 99)
                if roll < open_percent:
                    wall_type = WallType.OPEN_DOOR
                elif roll < open_percent + key_percent:
                    wall_type = WallType.LOCKED_DOOR_1
                    key_door_count += 1
                else:
                    wall_type = WallType.BOMB_HOLE

                # Set the wall type on both sides (paired)
                self.data_table.SetWall(reference_level, RoomNum(room_num), direction, wall_type)
                opposite_dir = direction.inverse()
                self.data_table.SetWall(reference_level, RoomNum(adj_room_num), opposite_dir, wall_type)

        return key_door_count

    def _place_items(self, reference_level: LevelNum, rooms: List[int],
                     actual_level: int, key_door_count: int) -> None:
        """Place items in the dungeon.

        Places: map, compass, triforce (L1-8), heart container, special items,
        then fills with bombs, 5 rupees, and keys (matching key door count).

        Args:
            reference_level: Reference level for the grid (1 or 7)
            rooms: List of room numbers in this level
            actual_level: The actual level number (1-9)
            key_door_count: Number of key doors (determines key count)
        """
        # Get list of rooms that can have items (exclude entrance and staircases)
        item_rooms = []
        entrance_room = None
        for room_num in rooms:
            room_type = self.data_table.GetRoomType(reference_level, RoomNum(room_num))
            if room_type == RoomType.ENTRANCE_ROOM:
                entrance_room = room_num
                continue
            if room_type in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue
            item_rooms.append(room_num)

        if not item_rooms:
            log.warning(f"No rooms available for items in level {actual_level}")
            return

        # Shuffle rooms for random placement
        self.rng.shuffle(item_rooms)

        # Build list of items to place
        items_to_place: List[Item] = []

        # Always place map and compass
        items_to_place.append(Item.MAP)
        items_to_place.append(Item.COMPASS)

        # Triforce for levels 1-8 (not 9)
        if actual_level != 9:
            items_to_place.append(Item.TRIFORCE)

        # Heart container for levels 1-8 (not 9)
        if actual_level != 9:
            items_to_place.append(Item.HEART_CONTAINER)

        # Special items for this level
        special_items = DUNGEON_SPECIAL_ITEMS.get(actual_level, [])
        items_to_place.extend(special_items)

        # Keys (match key door count)
        for _ in range(key_door_count):
            items_to_place.append(Item.KEY)

        # Fill remaining rooms with bombs and 5 rupees
        filler_items = [Item.BOMBS, Item.FIVE_RUPEES]
        remaining_rooms = len(item_rooms) - len(items_to_place)
        for _ in range(max(0, remaining_rooms)):
            items_to_place.append(self.rng.choice(filler_items))

        # Place items in rooms
        for i, room_num in enumerate(item_rooms):
            if i < len(items_to_place):
                self.data_table.SetItem(reference_level, RoomNum(room_num), items_to_place[i])
            else:
                # No more items to place
                self.data_table.SetItem(reference_level, RoomNum(room_num), Item.NO_ITEM)

    def _setup_level_9_special(self, reference_level: LevelNum, rooms: List[int]) -> None:
        """Set up Level 9 special elements: Ganon and Zelda.

        Args:
            reference_level: Reference level for the grid (1 or 7)
            rooms: List of room numbers in this level
        """
        # Get list of rooms that can have special NPCs (exclude entrance and staircases)
        available_rooms = []
        for room_num in rooms:
            room_type = self.data_table.GetRoomType(reference_level, RoomNum(room_num))
            if room_type in [RoomType.ENTRANCE_ROOM, RoomType.ITEM_STAIRCASE,
                             RoomType.TRANSPORT_STAIRCASE]:
                continue
            available_rooms.append(room_num)

        if len(available_rooms) < 2:
            log.warning("Not enough rooms for Ganon and Zelda in Level 9")
            return

        # Pick rooms for Ganon and Zelda
        self.rng.shuffle(available_rooms)
        ganon_room = available_rooms[0]
        zelda_room = available_rooms[1]

        # Set up Ganon's room
        self.data_table.SetRoomType(reference_level, RoomNum(ganon_room), RoomType.GANNON_ROOM)
        self.data_table.SetEnemy(reference_level, RoomNum(ganon_room), Enemy.THE_BEAST)
        self.data_table.SetItem(reference_level, RoomNum(ganon_room), Item.TRIFORCE_OF_POWER)

        # Set up Zelda's room
        self.data_table.SetRoomType(reference_level, RoomNum(zelda_room), RoomType.ZELDA_ROOM)
        self.data_table.SetEnemy(reference_level, RoomNum(zelda_room), Enemy.THE_KIDNAPPED)

        log.info(f"Level 9: Ganon at 0x{ganon_room:02X}, Zelda at 0x{zelda_room:02X}")
