"""
Bait Blocker - Makes hungry goriya block access to separate dungeon regions.

This module implements a partition-based approach to modify dungeon walls:
1. Find the hungry goriya room
2. Create two partitions (A and B) separated by the hungry goriya
3. Expand both partitions via flood-fill
4. Solidify all walls between the two partitions

This forces players to use bait to pass through the hungry goriya room to reach partition B.
"""

from typing import Optional, Set
from collections import deque
import logging as log

from .randomizer_constants import Direction, Range, RoomNum, WallType
from .data_table import DataTable


class BaitBlocker:
    """Modifies dungeon layouts to make hungry goriya block progress."""

    def __init__(self, data_table: DataTable):
        self.data_table = data_table

    def TryToMakeHungryGoriyaBlockProgress(self, level_num: int) -> bool:
        """
        Partition-based approach: Create two regions (A and B) separated by the hungry goriya.
        Makes all walls between regions solid, forcing passage through hungry goriya room.

        Returns:
            True if successfully created partitions, False if impossible/no hungry goriya
        """
        log.debug(f"=== Level {level_num}: Starting bait blocker ===")

        # Find the hungry goriya room
        hungry_goriya_room_num = self._FindHungryGoriyaRoom(level_num)
        if hungry_goriya_room_num is None:
            log.debug(f"Level {level_num}: No hungry goriya found")
            return False

        log.debug(f"Level {level_num}: Found hungry goriya in room 0x{hungry_goriya_room_num:02X}")

        hungry_goriya_room = self.data_table.GetRoom(level_num, hungry_goriya_room_num)

        # Check if north wall exists (not solid and not out of bounds)
        north_room_num = RoomNum(hungry_goriya_room_num + Direction.NORTH)
        if (hungry_goriya_room.GetWallType(Direction.NORTH) == WallType.SOLID_WALL or
            north_room_num not in Range.VALID_ROOM_NUMBERS):
            log.debug(f"Level {level_num}: Hungry goriya room 0x{hungry_goriya_room_num:02X} has no accessible north exit")
            return False

        # Initialize partitions
        partition_a = set()  # Hungry goriya room + west/east/south neighbors
        partition_b = set()  # Room to the north

        # Seed partition B (room to the north)
        partition_b.add(north_room_num)

        # Seed partition A (hungry goriya + west/east/south neighbors)
        partition_a.add(hungry_goriya_room_num)
        for direction in [Direction.WEST, Direction.EAST, Direction.SOUTH]:
            neighbor_num = RoomNum(hungry_goriya_room_num + direction)
            if (neighbor_num in Range.VALID_ROOM_NUMBERS and
                hungry_goriya_room.GetWallType(direction) != WallType.SOLID_WALL):
                partition_a.add(neighbor_num)

        log.debug(f"Level {level_num}: Initial partition A (south of hungry goriya): {sorted([f'0x{r:02X}' for r in partition_a])}")
        log.debug(f"Level {level_num}: Initial partition B (north of hungry goriya): {sorted([f'0x{r:02X}' for r in partition_b])}")

        # Expand both partitions via flood-fill
        self._ExpandPartitions(level_num, partition_a, partition_b)

        log.debug(f"Level {level_num}: Final partition A has {len(partition_a)} rooms: {sorted([f'0x{r:02X}' for r in partition_a])}")
        log.debug(f"Level {level_num}: Final partition B has {len(partition_b)} rooms: {sorted([f'0x{r:02X}' for r in partition_b])}")

        # Solidify all walls between partition A and B (except the hungry goriya passage)
        walls_modified = self._SolidifyWallsBetweenPartitions(level_num, partition_a, partition_b, hungry_goriya_room_num)

        log.debug(f"Level {level_num}: Modified {walls_modified} walls between partitions")

        return True

    def _FindHungryGoriyaRoom(self, level_num: int) -> Optional[RoomNum]:
        """Find the room number containing the hungry goriya by traversing from entrance."""
        # Start from the level entrance
        start_room_num = self.data_table.GetLevelStartRoomNumber(level_num)
        entry_direction = self.data_table.GetLevelEntranceDirection(level_num)

        rooms_to_visit = [(start_room_num, entry_direction)]
        visited = set()
        goriya_room_num = None

        while rooms_to_visit:
            room_num, from_direction = rooms_to_visit.pop()

            # Skip if out of bounds or already visited
            if room_num not in Range.VALID_ROOM_NUMBERS or room_num in visited:
                continue

            visited.add(room_num)
            room = self.data_table.GetRoom(level_num, room_num)

            # Check if this room has the hungry goriya
            try:
                if room.HasHungryGoriya():
                    goriya_room_num = room_num
                    # Don't return yet - we need to continue visiting rooms for the partition algorithm
            except ValueError as e:
                # Skip rooms with invalid enemy codes
                enemy_code = room.rom_data[2] & 0x3F
                if room.rom_data[3] & 0x80 > 0:
                    enemy_code += 0x40
                log.debug(f"Level {level_num} Room 0x{room_num:02X}: Invalid enemy code {enemy_code} (0x{enemy_code:02X}) - {e}")
                continue

            # Add adjacent rooms that are accessible (not solid walls)
            for direction in [Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH]:
                if room.GetWallType(direction) != WallType.SOLID_WALL:
                    neighbor_num = RoomNum(room_num + direction)
                    if neighbor_num not in visited:
                        rooms_to_visit.append((neighbor_num, direction.inverse()))

        return goriya_room_num

    def _ExpandPartitions(self, level_num: int, partition_a: Set[RoomNum],
                         partition_b: Set[RoomNum]) -> None:
        """
        Expand both partitions via flood-fill until all reachable rooms are assigned.
        Rooms already in one partition cannot be claimed by the other.
        Alternates between expanding A and B for fairness.
        """
        # Sort sets to ensure deterministic iteration order
        queue_a = deque(sorted(partition_a))
        queue_b = deque(sorted(partition_b))

        # Alternate between expanding A and B for fairness
        while queue_a or queue_b:
            # Expand partition A
            if queue_a:
                current_room_num = queue_a.popleft()
                room = self.data_table.GetRoom(level_num, current_room_num)

                for direction in [Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH]:
                    if room.GetWallType(direction) != WallType.SOLID_WALL:
                        neighbor_num = RoomNum(current_room_num + direction)

                        # Only claim if not already in either partition
                        if (neighbor_num in Range.VALID_ROOM_NUMBERS and
                            neighbor_num not in partition_a and
                            neighbor_num not in partition_b):
                            partition_a.add(neighbor_num)
                            queue_a.append(neighbor_num)

            # Expand partition B
            if queue_b:
                current_room_num = queue_b.popleft()
                room = self.data_table.GetRoom(level_num, current_room_num)

                for direction in [Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH]:
                    if room.GetWallType(direction) != WallType.SOLID_WALL:
                        neighbor_num = RoomNum(current_room_num + direction)

                        # Only claim if not already in either partition
                        if (neighbor_num in Range.VALID_ROOM_NUMBERS and
                            neighbor_num not in partition_a and
                            neighbor_num not in partition_b):
                            partition_b.add(neighbor_num)
                            queue_b.append(neighbor_num)

    def _SolidifyWallsBetweenPartitions(self, level_num: int, partition_a: Set[RoomNum],
                                       partition_b: Set[RoomNum], hungry_goriya_room_num: RoomNum) -> int:
        """
        Make all walls between partition A and partition B into solid walls.
        This forces all travel between partitions to go through the hungry goriya room.

        IMPORTANT: Does NOT solidify the wall between hungry goriya room and the room to its north,
        as that's the passage that should remain open (after feeding bait).

        Returns:
            Number of walls modified
        """
        from .randomizer_constants import RoomType

        walls_modified = 0

        # Sort partition_a to ensure deterministic iteration order
        for room_num in sorted(partition_a):
            room = self.data_table.GetRoom(level_num, room_num)

            # Skip staircase rooms - they don't have walls in the traditional sense
            if room.GetType() in [RoomType.ITEM_STAIRCASE, RoomType.TRANSPORT_STAIRCASE]:
                continue

            for direction in [Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH]:
                log.debug("Direction is %x" % direction)
                # Skip if there's already a solid wall - no need to process this neighbor
                if room.GetWallType(direction) == WallType.SOLID_WALL:
                    continue
                neighbor_num = RoomNum(room_num + direction)

                # SPECIAL CASE: Don't solidify the wall from hungry goriya room to north
                # This is the passage that should remain open after feeding bait
                if room_num == hungry_goriya_room_num and direction == Direction.NORTH:
                    log.debug(f"  Skipping hungry goriya passage: room 0x{room_num:02X} {direction} -> 0x{neighbor_num:02X}")
                    continue

                # If neighbor is in partition B, solidify the wall
                if neighbor_num in partition_b:
                    neighbor_room = self.data_table.GetRoom(level_num, neighbor_num)
                    log.debug("Neighbor room num is %0x" % neighbor_num)

                    # Only modify if not already solid
                    if room.GetWallType(direction) != WallType.SOLID_WALL:
                        room.SetWallType(direction, WallType.SOLID_WALL)
                        walls_modified += 1
                        log.debug(f"  Solidified wall: room {room_num:02X} {direction} -> {neighbor_num:02X}")

                    # Also solidify from the other side
                    log.debug("Direction is %s  %x" % (direction.name, direction))
                    opposite_direction = direction.inverse()
                    log.debug("Opposite direction is %s  %x" % (opposite_direction.name, opposite_direction))
                    if neighbor_room.GetWallType(opposite_direction) != WallType.SOLID_WALL:
                        neighbor_room.SetWallType(opposite_direction, WallType.SOLID_WALL)
                        walls_modified += 1
                        log.debug(f"  Solidified wall: room {neighbor_num:02X} {opposite_direction} -> {room_num:02X}")

        return walls_modified
