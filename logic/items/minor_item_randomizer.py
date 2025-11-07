from collections import Counter
from random import choice
import logging as log

from ..randomizer_constants import (
    DUNGEON_LEVEL_NUMBERS, Item, RoomType, ValidItemPositions
)
from ..data_table import DataTable
from ..flags import Flags
from ..assignment_solver import AssignmentSolver
from .room_item_collector import RoomItemCollector


class MinorItemRandomizer():

    def __init__(self, data_table: DataTable, flags: Flags) -> None:
        self.data_table = data_table
        self.flags = flags

    def Randomize(self, seed: int) -> bool:
        # Early return if shuffle is disabled
        if not self.flags.shuffle_within_level:
            return True

        collector = RoomItemCollector(self.data_table)
        room_item_pair_lists = collector.CollectAll()

        for level_num in DUNGEON_LEVEL_NUMBERS:
            # Randomize each room's item position
            self._log_level_inventory(level_num, room_item_pair_lists[level_num])
            for pair in room_item_pair_lists[level_num]:
                room_type = self.data_table.GetRoomType(level_num, pair.room_num)
                item_position = choice(ValidItemPositions[room_type])
                self.data_table.SetItemPositionNew(level_num, pair.room_num, item_position)

            if not self.ShuffleItemsWithinLevel(level_num, room_item_pair_lists[level_num], seed):
                return False

        return True

    def ShuffleItemsWithinLevel(self, level_num: int, pairs: list, seed: int | None = None) -> bool:
        """Constraint solver approach using OR-Tools.

        Uses AssignmentSolver to guarantee a valid assignment that satisfies
        all constraints, or reports if constraints are impossible to satisfy.

        Args:
            level_num: The level number to shuffle items within.
            pairs: List of RoomItemPair tuples for this level.
        """
        room_nums = [pair.room_num for pair in pairs]
        items = [pair.item for pair in pairs]

        # Create solver and define the permutation problem
        # Keys: room numbers, Values: items (shuffled assignment)
        solver = AssignmentSolver()
        solver_seed = self._solver_seed(seed, level_num)
        solver.add_permutation_problem(keys=room_nums, values=items, shuffle_seed=solver_seed)

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
        solution = solver.solve(seed=solver_seed, time_limit_seconds=1.0)

        if solution is None:
            log.error(f"Level {level_num}: No valid item shuffle exists with current constraints")
            self._log_solver_failure(level_num, pairs, solver_seed)
            return False

        # Write solution back to data table
        for room_num, item in solution.items():
            self.data_table.SetItem(level_num, room_num, item)

        log.debug(f"Level {level_num}: Found valid item shuffle using constraint solver")
        return True

    def _solver_seed(self, seed: int | None, salt: int) -> int | None:
        """Derive a deterministic solver seed per level for OR-Tools."""
        if seed is None:
            return None
        solver_seed = (seed + salt * 101) % 2147483647
        if solver_seed == 0:
            solver_seed = 1
        return solver_seed

    def _log_solver_failure(self, level_num: int, pairs: list, solver_seed: int | None) -> None:
        """Emit detailed context to help diagnose solver failures."""
        flag_snapshot = {
            "item_stair_can_have_triforce": self.flags.item_stair_can_have_triforce,
            "item_stair_can_have_minor_item": self.flags.item_stair_can_have_minor_item,
            "force_major_item_to_boss": self.flags.force_major_item_to_boss,
            "force_major_item_to_triforce_room": self.flags.force_major_item_to_triforce_room,
        }
        log.error(
            "Level %d solver context — seed=%s, flags=%s",
            level_num,
            solver_seed if solver_seed is not None else "None",
            flag_snapshot,
        )

        for pair in pairs:
            room_num = pair.room_num
            item = pair.item
            room_type = self.data_table.GetRoomType(level_num, room_num)
            enemy = self.data_table.GetRoomEnemy(level_num, room_num)
            is_staircase = self.data_table.IsItemStaircase(level_num, room_num)
            item_position = self.data_table.GetItemPosition(level_num, room_num)
            log.error(
                "  Room 0x%02X: item=%s pos=%s type=%s enemy=%s staircase=%s",
                room_num,
                item.name,
                item_position.name if hasattr(item_position, "name") else item_position,
                room_type.name if hasattr(room_type, "name") else room_type,
                enemy.name if hasattr(enemy, "name") else enemy,
                is_staircase,
            )

    def _log_level_inventory(self, level_num: int, pairs: list) -> None:
        """Log a concise summary of items present in a level before shuffling."""
        counter = Counter(pair.item.name for pair in pairs)
        summary = ", ".join(
            f"{name}x{count}" for name, count in sorted(counter.items())
        )
        log.info("Level %d minor shuffle inventory: %s", level_num, summary)

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
