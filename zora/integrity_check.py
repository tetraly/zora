"""Post-phase integrity checks for the GameWorld data model.

Run after critical pipeline phases to catch structural invariants that, if
violated, indicate a bug in the randomizer phase that just ran.  Every
failure is a hard error — the pipeline must not continue.
"""

import logging
from typing import Callable

from zora.data_model import (
    Direction,
    Enemy,
    GameWorld,
    Item,
    Level,
    Room,
    RoomAction,
    RoomType,
    WallType,
)

logger = logging.getLogger(__name__)

_GLITCH_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.ENEMY_0x19,
    Enemy.ENEMY_0x25,
    Enemy.ENEMY_0x29,
})

_NPC_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3, Enemy.OLD_MAN_4,
    Enemy.BOMB_UPGRADER, Enemy.OLD_MAN_5, Enemy.MUGGER, Enemy.OLD_MAN_6,
})

_OPPOSITE: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}

_PASSABLE_WALL_TYPES: frozenset[WallType] = frozenset({
    WallType.OPEN_DOOR,
    WallType.WALK_THROUGH_WALL_1,
    WallType.WALK_THROUGH_WALL_2,
    WallType.BOMB_HOLE,
    WallType.LOCKED_DOOR_1,
    WallType.LOCKED_DOOR_2,
    WallType.SHUTTER_DOOR,
})


class IntegrityError(RuntimeError):
    """Raised when a post-phase integrity check fails."""


def _count_item_in_level(level: Level, item: Item) -> int:
    count = 0
    for room in level.rooms:
        if room.item == item:
            count += 1
    for sr in level.staircase_rooms:
        if sr.item == item:
            count += 1
    return count


def _check_level_count(game_world: GameWorld, errors: list[str]) -> None:
    if len(game_world.levels) != 9:
        errors.append(f"Expected 9 levels, got {len(game_world.levels)}")


def _check_dungeon_items(game_world: GameWorld, errors: list[str]) -> None:
    for level in game_world.levels:
        n = level.level_num
        maps = _count_item_in_level(level, Item.MAP)
        if maps != 1:
            errors.append(f"Level {n}: expected 1 MAP, found {maps}")
        compasses = _count_item_in_level(level, Item.COMPASS)
        if compasses != 1:
            errors.append(f"Level {n}: expected 1 COMPASS, found {compasses}")
        if n <= 8:
            triforces = _count_item_in_level(level, Item.TRIFORCE)
            if triforces != 1:
                errors.append(f"Level {n}: expected 1 TRIFORCE, found {triforces}")
        else:
            tops = _count_item_in_level(level, Item.TRIFORCE_OF_POWER)
            if tops != 1:
                errors.append(f"Level 9: expected 1 TRIFORCE_OF_POWER, found {tops}")


def _check_enemy_codes(game_world: GameWorld, errors: list[str]) -> None:
    for level in game_world.levels:
        for room in level.rooms:
            enemy = room.enemy_spec.enemy
            if enemy in _GLITCH_ENEMIES:
                errors.append(
                    f"Level {level.level_num} room 0x{room.room_num:02X}: "
                    f"glitch enemy {enemy.name} (0x{enemy.value:02X})"
                )


def _check_npc_north_wall(game_world: GameWorld, errors: list[str]) -> None:
    level_9 = game_world.levels[8]
    l9_old_man_exception = level_9.entrance_room - 0x10

    for level in game_world.levels:
        for room in level.rooms:
            if room.enemy_spec.enemy in _NPC_ENEMIES:
                if (level.level_num == 9
                        and room.enemy_spec.enemy == Enemy.OLD_MAN
                        and room.room_num == l9_old_man_exception):
                    continue
                if room.walls.north != WallType.SOLID_WALL:
                    errors.append(
                        f"Level {level.level_num} room 0x{room.room_num:02X}: "
                        f"NPC {room.enemy_spec.enemy.name} has non-solid north wall "
                        f"({room.walls.north.name})"
                    )


def _check_kidnapped(game_world: GameWorld, errors: list[str]) -> None:
    level_9 = game_world.levels[8]
    room_map: dict[int, Room] = {r.room_num: r for r in level_9.rooms}
    level_9_room_nums: frozenset[int] = frozenset(room_map.keys())

    kidnapped_rooms = [
        r for r in level_9.rooms if r.enemy_spec.enemy == Enemy.THE_KIDNAPPED
    ]
    if len(kidnapped_rooms) != 1:
        errors.append(
            f"Level 9: expected 1 THE_KIDNAPPED room, found {len(kidnapped_rooms)}"
        )
        return

    kidnapped = kidnapped_rooms[0]
    rn = kidnapped.room_num

    neighbors: list[tuple[Direction, int]] = [
        (Direction.NORTH, rn - 0x10),
        (Direction.SOUTH, rn + 0x10),
        (Direction.EAST, rn + 1),
        (Direction.WEST, rn - 1),
    ]

    for direction, neighbor_num in neighbors:
        if neighbor_num < 0 or neighbor_num > 0x7F:
            continue
        if neighbor_num not in level_9_room_nums:
            continue

        kidnapped_wall = kidnapped.walls[direction]
        if kidnapped_wall == WallType.SOLID_WALL:
            continue

        neighbor = room_map[neighbor_num]
        facing_dir = _OPPOSITE[direction]
        neighbor_wall = neighbor.walls[facing_dir]

        if neighbor_wall != WallType.SHUTTER_DOOR:
            errors.append(
                f"Level 9 room 0x{neighbor_num:02X}: adjacent to THE_KIDNAPPED "
                f"(0x{rn:02X}) via {direction.name} with non-solid wall, but "
                f"{facing_dir.name} wall is {neighbor_wall.name} instead of SHUTTER_DOOR"
            )

        if neighbor.room_action != RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS:
            errors.append(
                f"Level 9 room 0x{neighbor_num:02X}: adjacent to THE_KIDNAPPED "
                f"(0x{rn:02X}) via {direction.name} with non-solid wall, but "
                f"room_action is {neighbor.room_action.name} instead of "
                f"TRIFORCE_OF_POWER_OPENS_SHUTTERS"
            )


def _check_wall_reciprocity(game_world: GameWorld, errors: list[str]) -> None:
    for level in game_world.levels:
        room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}
        level_room_nums = frozenset(room_map.keys())

        for room in level.rooms:
            rn = room.room_num

            right_num = rn + 1
            if (rn & 0x0F) < 0x0F and right_num in level_room_nums:
                east_wall = room.walls.east
                west_wall = room_map[right_num].walls.west
                if not _walls_compatible(east_wall, west_wall):
                    errors.append(
                        f"Level {level.level_num} rooms 0x{rn:02X}-0x{right_num:02X}: "
                        f"wall mismatch east={east_wall.name} vs west={west_wall.name}"
                    )

            below_num = rn + 0x10
            if below_num <= 0x7F and below_num in level_room_nums:
                south_wall = room.walls.south
                north_wall = room_map[below_num].walls.north
                if not _walls_compatible(south_wall, north_wall):
                    errors.append(
                        f"Level {level.level_num} rooms 0x{rn:02X}-0x{below_num:02X}: "
                        f"wall mismatch south={south_wall.name} vs north={north_wall.name}"
                    )


def _walls_compatible(wall_a: WallType, wall_b: WallType) -> bool:
    a_passable = wall_a in _PASSABLE_WALL_TYPES
    b_passable = wall_b in _PASSABLE_WALL_TYPES
    return a_passable == b_passable


_ALL_CHECKS: list[Callable[[GameWorld, list[str]], None]] = [
    _check_level_count,
    _check_dungeon_items,
    _check_enemy_codes,
    _check_npc_north_wall,
    _check_kidnapped,
    _check_wall_reciprocity,
]


def integrity_check(game_world: GameWorld, phase_name: str) -> None:
    """Run all integrity checks. Raises IntegrityError if any fail."""
    errors: list[str] = []
    for check in _ALL_CHECKS:
        check(game_world, errors)
    if errors:
        msg = f"Integrity check failed after {phase_name}:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        logger.error(msg)
        raise IntegrityError(msg)
