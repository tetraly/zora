from collections import defaultdict, namedtuple
from random import choice
import logging as log

from .randomizer_constants import (
    CARDINAL_DIRECTIONS, DUNGEON_LEVEL_NUMBERS, Direction, Enemy, Item,
    LevelNum, RoomNum, RoomType, ValidItemPositions, WallType
)
from .data_table import DataTable
from .flags import Flags
from .assignment_solver import AssignmentSolver

RoomItemPair = namedtuple('RoomItemPair', ['room_num', 'item'])
# room_num: int - the room number
# item: Item - the item in that room


class NewItemRandomizer():

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags
        # Track visited rooms with their items, organized by level number
        self.visited_rooms: dict[int, list[RoomItemPair]] = defaultdict(list)

    def Randomize(self) -> None:
        # Early return if shuffle is disabled
        if not self.flags.shuffle_within_level:
            return
        
        self.data_table.NormalizeItemPositions()
        self.data_table.NormalizeNoItemCode()
        self.VisitAllRooms()
        for level_num in DUNGEON_LEVEL_NUMBERS:
            self.FilterOutImpossibleItemRooms(level_num)
            self.RandomizeItemPositionsInLevel(level_num)
            self.ShuffleItemsWithinLevel(level_num)

    def FilterOutImpossibleItemRooms(self, level_num: int) -> None:
        self.visited_rooms[level_num] = [
            pair for pair in self.visited_rooms[level_num]
            if self._IsPossibleItemRoom(level_num, pair.room_num)
        ]

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

    def RandomizeItemPositionsInLevel(self, level_num: int) -> None:
        for pair in self.visited_rooms[level_num]:
            room_type = self.data_table.GetRoomType(level_num, pair.room_num)
            item_position = choice(ValidItemPositions[room_type])
            self.data_table.SetItemPosition(level_num, pair.room_num, item_position)


    def ShuffleItemsWithinLevel(self, level_num: int) -> None:
        """Constraint solver approach using OR-Tools.

        Uses AssignmentSolver to guarantee a valid assignment that satisfies
        all constraints, or reports if constraints are impossible to satisfy.
        """

        pairs = self.visited_rooms[level_num]
        room_nums = [pair.room_num for pair in pairs]
        items = [pair.item for pair in pairs]

        # Create solver and define the permutation problem
        # Keys: room numbers, Values: items (shuffled assignment)
        solver = AssignmentSolver()
        solver.add_permutation_problem(keys=room_nums, values=items)

        # Special constraint: TRIFORCE_OF_POWER (0x0E) should never be shuffled
        # Find the room that has it and require it to stay there
        for pair in pairs:
            if pair.item == Item.TRIFORCE_OF_POWER:
                solver.require(source=pair.room_num, target=Item.TRIFORCE_OF_POWER)
                log.debug(f"Level {level_num}: TRIFORCE_OF_POWER in room 0x{pair.room_num:02X} must stay in place")
                break

        # Add constraint: item staircases must have items (not NO_ITEM)
        self._ForbidItemInStaircases(solver, level_num, room_nums, items, Item.NO_ITEM)

        # Triforce constraint in Levels 1-8: if flag is unchecked, triforce cannot be in item staircase
        if not self.flags.item_stair_can_have_triforce and level_num != 9:
            self._ForbidItemInStaircases(solver, level_num, room_nums, items, Item.TRIFORCE)

        # Heart container constraint for Levels 1-8: if flag is unchecked, heart container cannot be in item staircase
        if not self.flags.item_stair_can_have_heart_container and level_num != 9:
            self._ForbidItemInStaircases(solver, level_num, room_nums, items, Item.HEART_CONTAINER)

        # Minor item constraint: if flag is unchecked, minor items cannot be in item staircase
        if not self.flags.item_stair_can_have_minor_item:
            for item in items:
                if item.IsMinorItem():
                    self._ForbidItemInStaircases(solver, level_num, room_nums, items, item)

        # Force major item to boss room constraint
        if self.flags.force_major_item_to_boss:
            def is_boss_room(room_num):
                enemy = self.data_table.GetRoomEnemy(level_num, room_num)
                return enemy.IsBoss()
            self._RequireMajorItemInRoomType(solver, level_num, room_nums, items, is_boss_room, "force_major_item_to_boss")

        # Force major item to triforce room constraint
        if self.flags.force_major_item_to_triforce_room:
            def is_triforce_room(room_num):
                room_type = self.data_table.GetRoomType(level_num, room_num)
                return room_type == RoomType.TRIFORCE_ROOM
            self._RequireMajorItemInRoomType(solver, level_num, room_nums, items, is_triforce_room, "force_major_item_to_triforce_room")

        # Solve with current random seed (could pass self.flags.seed or similar)
        solution = solver.solve(seed=None, time_limit_seconds=1.0)

        if solution is None:
            log.error(f"Level {level_num}: No valid item shuffle exists with current constraints")
            return

        # Write solution back to data table
        for room_num, item in solution.items():
            self.data_table.SetItem(level_num, room_num, item)

        log.debug(f"Level {level_num}: Found valid item shuffle using constraint solver")

    def _ForbidItemInStaircases(self, solver: AssignmentSolver, level_num: int, room_nums: list[int], items: list[Item], item_to_forbid: Item) -> None:
        """Helper to forbid a specific item from appearing in any item staircase.

        Args:
            solver: The constraint solver
            level_num: Current level number
            room_nums: List of room numbers being shuffled
            items: List of items being shuffled
            item_to_forbid: The item that should not appear in item staircases
        """
        if item_to_forbid not in items:
            log.warning(f"Level {level_num}: Constraint requested for {item_to_forbid.name} but it doesn't exist in this level")
            return  # Item doesn't exist in this level, nothing to forbid

        for room_num in room_nums:
            if self.data_table.IsItemStaircase(level_num, room_num):
                solver.forbid(source=room_num, target=item_to_forbid)

    def _RequireMajorItemInRoomType(self, solver: AssignmentSolver, level_num: int, room_nums: list[int], items: list[Item], room_predicate, constraint_name: str) -> None:
        """Helper to require at least one major item in rooms matching a predicate.

        Args:
            solver: The constraint solver
            level_num: Current level number
            room_nums: List of room numbers being shuffled
            items: List of items being shuffled
            room_predicate: Function that takes room_num and returns True if room matches criteria
            constraint_name: Name of constraint for error messages
        """
        # Find all major items
        major_items = [item for item in items if item.IsMajorItemOrTriforce()]
        if not major_items:
            log.fatal(f"Level {level_num}: No major items found for {constraint_name} constraint")
            raise ValueError(f"Level {level_num}: No major items found for {constraint_name} constraint")

        # Find matching rooms
        matching_rooms = [room_num for room_num in room_nums if room_predicate(room_num)]
        if not matching_rooms:
            log.fatal(f"Level {level_num}: No rooms found for {constraint_name} constraint")
            raise ValueError(f"Level {level_num}: No rooms found for {constraint_name} constraint")

        # At least one matching room must have a major item
        solver.at_least_one_of(sources=matching_rooms, targets=major_items)


    def VisitAllRooms(self) -> None:
        for level_num in DUNGEON_LEVEL_NUMBERS:
            rooms_to_visit = [self.data_table.GetLevelStartRoomNumber(level_num)]
            while rooms_to_visit:
                new_rooms = self._VisitRoom(level_num, rooms_to_visit.pop())
                if new_rooms:
                    rooms_to_visit.extend(new_rooms)

    def _VisitRoom(self, level_num: int, room_num: RoomNum):
        if room_num not in range(0, 0x80):
            return []

        # Check if this room has already been visited
        if any(pair.room_num == room_num for pair in self.visited_rooms[level_num]):
            return []
        log.debug(f"Visiting level {level_num} room {room_num}")

        # Get the item in this room and store as a RoomItemPair
        item = self.data_table.GetItem(level_num, room_num)
        self.visited_rooms[level_num].append(RoomItemPair(room_num, item))
        rooms_to_visit = []

        for direction in CARDINAL_DIRECTIONS:
            wall_type = self.data_table.GetRoomWallType(level_num, room_num, direction)
            if wall_type != WallType.SOLID_WALL:
                rooms_to_visit.append(RoomNum(room_num + direction))

        # Check for stairways and add any connected rooms
        if self._HasStairway(level_num, room_num):
            stairway_rooms = self._VisitStairways(level_num, room_num)
            rooms_to_visit.extend(stairway_rooms)

        return rooms_to_visit

    def _HasStairway(self, level_num: LevelNum, room_num: RoomNum) -> bool:
        room_type = self.data_table.GetRoomType(level_num, room_num)

        # Spiral Stair, Narrow Stair, and Diamond Stair rooms always have a stairway
        if room_type.HasOpenStaircase():
            return True

        # Check if there are any shutter doors in this room. If so, they'll open when a middle
        # row pushblock is pushed instead of a stairway appearing
        for direction in CARDINAL_DIRECTIONS:
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
        stairways_to_visit = []
        for stairway_room_num in self.data_table.GetLevelStaircaseRoomNumberList(level_num):
            left_exit = self.data_table.GetStaircaseLeftExit(level_num, stairway_room_num)
            right_exit = self.data_table.GetStaircaseRightExit(level_num, stairway_room_num)

            # Item stairway.
            if left_exit == room_num and right_exit == room_num:
                item = self.data_table.GetItem(level_num, stairway_room_num)
                self.visited_rooms[level_num].append(RoomItemPair(stairway_room_num, item))

            # Transport stairway. Add the connecting room to be checked.
            elif left_exit == room_num and right_exit != room_num:
                stairways_to_visit.append(right_exit)
                # Stop looking for additional stairways after finding one
                break
            elif right_exit == room_num and left_exit != room_num:
                stairways_to_visit.append(left_exit)
                # Stop looking for additional stairways after finding one
                break

        return stairways_to_visit

