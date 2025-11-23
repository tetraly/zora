"""Dungeon layout randomizer using balanced region-growing algorithm."""

import logging as log
from typing import Dict, List, Optional, Set, Tuple

from rng.random_number_generator import RandomNumberGenerator
from ..data_table import DataTable
from ..flags import Flags
from ..randomizer_constants import (
    Direction, Enemy, Item, LevelNum, Range, RoomNum, RoomType, WallType
)

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
MIN_ROOMS_PER_LEVEL = 15

# Maximum bounding box width for a region
MAX_REGION_WIDTH = 8


def calculate_max_rooms(num_regions: int) -> int:
    """Calculate max rooms per region based on number of regions.

    This ensures we can fill all 128 rooms while keeping regions balanced.
    Formula: ceil(128 / num_regions) + 50% buffer for flexibility.
    """
    base = (TOTAL_ROOMS + num_regions - 1) // num_regions  # ceiling division
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

        # Step 2: Grow regions until all rooms are assigned
        if not self._grow_regions():
            log.warning("Failed to grow all regions")
            return False

        # Step 3: Validate the result
        if not self._validate():
            log.warning("Layout validation failed")
            return False

        return True

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

        # Phase 2: Balanced growth for remaining rooms
        while len(self.assigned) < TOTAL_ROOMS and iteration < max_iterations:
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
                        if len(self.assigned) < TOTAL_ROOMS:
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

        if len(self.assigned) < TOTAL_ROOMS:
            log.error(f"Failed to assign all rooms. Assigned: {len(self.assigned)}/{TOTAL_ROOMS}")
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

        log.info(f"Layout validation passed. Region sizes: "
                f"{[r.size() for r in self.regions]}")
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

        log.info(f"Starting dungeon layout randomization (seed: {seed})")

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
            layout_1_6 = DungeonLayoutGenerator(num_regions=6, rng=self.rng)
            if not layout_1_6.generate():
                log.warning(f"Failed to generate layout for levels 1-6 (attempt {attempt + 1})")
                continue

            # Generate layout for levels 7-9 (3 regions)
            log.info("Generating layout for levels 7-9...")
            layout_7_9 = DungeonLayoutGenerator(num_regions=3, rng=self.rng)
            if not layout_7_9.generate():
                log.warning(f"Failed to generate layout for levels 7-9 (attempt {attempt + 1})")
                continue

            # Both layouts generated successfully
            # Apply layouts to DataTable
            self._apply_layout(layout_1_6, is_level_7_9=False)
            self._apply_layout(layout_7_9, is_level_7_9=True)

            log.info(f"Dungeon layout randomization completed successfully (attempt {attempt + 1})")
            return True

        log.error(f"Failed to generate dungeon layouts after {max_retries} attempts")
        return False

    def _apply_layout(self, layout: DungeonLayoutGenerator, is_level_7_9: bool) -> None:
        """Apply a generated layout to the DataTable.

        Args:
            layout: The generated layout
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
