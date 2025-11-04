from typing import DefaultDict, List, Tuple, Iterable
from collections import defaultdict
from random import randint, shuffle, choice
import logging as log

from .randomizer_constants import Direction, Enemy, Item, LevelNum, Range, RoomNum, RoomType, ValidItemPositions, WallType
from .data_table import DataTable
from .flags import Flags
from .assignment_solver import AssignmentSolver


class NewItemRandomizer():

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags
        # Track visited rooms organized by level number
        self.visited_rooms: dict[int, list[int]] = defaultdict(list)

    def Randomize(self) -> None:
        self.data_table.NormalizeItemPositions()
        self.data_table.NormalizeNoItemCode()
        self.VisitAllRooms()
        for level_num in range(1, 10):  # Levels 1-9 (dungeons only, not overworld)
            self.FilterOutImpossibleItemRooms(level_num)
            self.RandomizeItemPositionsInLevel(level_num)
            self.ShuffleItemsWithinLevel(level_num)

    def FilterOutImpossibleItemRooms(self, level_num: int) -> None: 
            filtered_rooms = []
            for room_num in self.visited_rooms[level_num]:
                if self._IsPossibleItemRoom(level_num, room_num):
                    filtered_rooms.append(room_num)
            self.visited_rooms[level_num] = filtered_rooms

    def _IsPossibleItemRoom(self, level_num: int, room_num: RoomNum) -> bool:
        room_type = self.data_table.GetRoomType(level_num, room_num)

        # Item staircases can have an item but entrance rooms and transport staircases can't 
        if room_type in [RoomType.ENTRANCE_ROOM, RoomType.TRANSPORT_STAIRCASE]:
            return False
        elif room_type == RoomType.ITEM_STAIRCASE:
            return True

        # Exclude rooms with NPCs (including bomb upgraders, muggers, and hungry enemies)
        # Note: Don't check enemy data for staircase rooms since that byte is repurposed as return coordinates
        if self.data_table.GetRoomEnemy(level_num, room_num).IsNPC():
            return False

        return True

    def ShuffleItemsWithinLevel(self, level_num: int) -> None:
        """Constraint solver approach using OR-Tools.

        Uses AssignmentSolver to guarantee a valid assignment that satisfies
        all constraints, or reports if constraints are impossible to satisfy.
        """
        room_nums = self.visited_rooms[level_num]

        # Collect all items from these rooms
        items = []
        for room_num in room_nums:
            item = self.data_table.GetItem(level_num, room_num)
            items.append(item)

        # Create solver and define the permutation problem
        # Keys: room numbers, Values: items (shuffled assignment)
        solver = AssignmentSolver()
        solver.add_permutation_problem(keys=room_nums, values=items)

        # Add constraint: item staircases must have items (not NO_ITEM)
        for room_num in room_nums:
            if self.data_table.IsItemStaircase(level_num, room_num):
                # This room cannot get NO_ITEM
                if Item.NO_ITEM in items:
                    solver.forbid(source=room_num, target=Item.NO_ITEM)

        # Solve with current random seed (could pass self.flags.seed or similar)
        solution = solver.solve(seed=None, time_limit_seconds=10.0)

        if solution is None:
            log.error(f"Level {level_num}: No valid item shuffle exists with current constraints")
            return

        # Write solution back to data table
        for room_num, item in solution.items():
            self.data_table.SetItem(level_num, room_num, item)

        log.debug(f"Level {level_num}: Found valid item shuffle using constraint solver")

    def _IsItemStaircase(self, level_num: int, room_num: RoomNum) -> bool:
        """Check if a room is an item staircase (left_exit == right_exit)."""
        staircase_rooms = self.data_table.GetLevelStaircaseRoomNumberList(level_num)

        for stairway_room_num in staircase_rooms:
            if stairway_room_num == room_num:
                left_exit = self.data_table.GetStaircaseLeftExit(level_num, stairway_room_num)
                right_exit = self.data_table.GetStaircaseRightExit(level_num, stairway_room_num)
                return left_exit == right_exit

        return False

    def RandomizeItemPositionsInLevel(self, level_num: int) -> None:
        room_nums = self.visited_rooms[level_num]
        for room_num in room_nums:
            room_type = self.data_table.GetRoomType(level_num, room_num)
            item_position = choice(ValidItemPositions[room_type])
            self.data_table.SetItemPosition(level_num, room_num, item_position)

    def VisitAllRooms(self) -> None:
        for level_num in range(1, 10):  # Levels 1-9 (dungeons only)
            rooms_to_visit = [self.data_table.GetLevelStartRoomNumber(level_num)]
            while rooms_to_visit:
                new_rooms = self._VisitRoom(level_num, rooms_to_visit.pop())
                if new_rooms:
                    rooms_to_visit.extend(new_rooms)

    def _VisitRoom(self, level_num: int, room_num: RoomNum):
        if room_num not in range(0, 0x80):
            return []

        # Check if this room has already been visited
        if room_num in self.visited_rooms[level_num]:
            return []
        log.debug("Visiting level %d room %x" % (level_num, room_num))
        self.visited_rooms[level_num].append(room_num)
        tbr = []

        for direction in (Direction.WEST, Direction.NORTH, Direction.EAST, Direction.SOUTH):
            wall_type = self.data_table.GetRoomWallType(level_num, room_num, direction)
            if wall_type != WallType.SOLID_WALL:
                tbr.append(RoomNum(room_num + direction))

        # Check for stairways and add any connected rooms
        if self._HasStairway(level_num, room_num):
            stairway_rooms = self._VisitStairways(level_num, room_num)
            tbr.extend(stairway_rooms)

        return tbr

    def _HasStairway(self, level_num: LevelNum, room_num: RoomNum) -> bool:
        room_type = self.data_table.GetRoomType(level_num, room_num)

        # Spiral Stair, Narrow Stair, and Diamond Stair rooms always have a stairway
        if room_type.HasOpenStaircase():
            return True

        # Check if there are any shutter doors in this room. If so, they'll open when a middle
        # row pushblock is pushed instead of a stairway appearing
        for direction in [Direction.NORTH, Direction.EAST, Direction.SOUTH, Direction.WEST]:
            if self.data_table.GetRoomWallType(level_num, room_num, direction) == WallType.SHUTTER_DOOR:
                return False

        # Check if "Movable block" bit is set in a room_type that has a middle row pushblock
        if room_type.CanHavePushBlock() and self.data_table.HasMovableBlockBit(level_num, room_num):
            return True
        return False

    def _VisitStairways(self, level_num: int, room_num: RoomNum):
        """Visit stairways connected to the current room.

        Returns list of rooms to visit next (transport stairway destinations).
        Also adds item stairway rooms to visited_rooms.
        """
        tbr = []
        for stairway_room_num in self.data_table.GetLevelStaircaseRoomNumberList(level_num):
            left_exit = self.data_table.GetStaircaseLeftExit(level_num, stairway_room_num)
            right_exit = self.data_table.GetStaircaseRightExit(level_num, stairway_room_num)

            # Item stairway.
            if left_exit == room_num and right_exit == room_num:
                self.visited_rooms[level_num].append(stairway_room_num)

            # Transport stairway. Add the connecting room to be checked.
            elif left_exit == room_num and right_exit != room_num:
                tbr.append(right_exit)
                # Stop looking for additional stairways after finding one
                break
            elif right_exit == room_num and left_exit != room_num:
                tbr.append(left_exit)
                # Stop looking for additional stairways after finding one
                break

        return tbr

