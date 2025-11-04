from collections import defaultdict, namedtuple
import logging as log

from ..randomizer_constants import (
    CARDINAL_DIRECTIONS, DUNGEON_LEVEL_NUMBERS, Direction, Enemy, Item,
    LevelNum, RoomNum, RoomType, ValidItemPositions, WallType
)
from ..data_table import DataTable


RoomItemPair = namedtuple('RoomItemPair', ['room_num', 'item'])
# room_num: int - the room number
# item: Item - the item in that room


class RoomItemCollector():
    """Collects room-item pairs from all accessible dungeon rooms.

    Traverses each dungeon level to discover all reachable rooms and their items,
    filtering out rooms that cannot contain items (entrance rooms, NPCs, etc.).
    """

    def __init__(self, data_table: DataTable):
        self.data_table = data_table
        # Track visited rooms with their items, organized by level number
        self.visited_rooms: dict[int, list[RoomItemPair]] = defaultdict(list)

    def CollectAll(self) -> dict[int, list[RoomItemPair]]:
        filtered_location_item_pair_lists: dict[int, list[RoomItemPair]] = defaultdict(list)
        for level_num in DUNGEON_LEVEL_NUMBERS:
            rooms_to_visit = [self.data_table.GetLevelStartRoomNumber(level_num)]
            while rooms_to_visit:
                new_rooms = self._VisitRoom(level_num, rooms_to_visit.pop())
                if new_rooms:
                    rooms_to_visit.extend(new_rooms)

            # Filter out rooms that can't have a item
            filtered_location_item_pair_lists[level_num] = [
                pair for pair in self.visited_rooms[level_num]
                if self._IsPossibleItemRoom(level_num, pair.room_num)
            ]
        return filtered_location_item_pair_lists

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
