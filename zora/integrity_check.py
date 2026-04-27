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
from zora.dungeon.shuffle_dungeon_rooms import _is_level_connected

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

_BLACK_ROOM_REQUIRED_ENEMIES: frozenset[Enemy] = frozenset({
    Enemy.OLD_MAN, Enemy.OLD_MAN_2, Enemy.OLD_MAN_3, Enemy.OLD_MAN_4,
    Enemy.OLD_MAN_5, Enemy.OLD_MAN_6,
    Enemy.BOMB_UPGRADER, Enemy.MUGGER,
    Enemy.HUNGRY_GORIYA,
})

_KIDNAPPED_FORBIDDEN_ROOM_TYPES: frozenset[RoomType] = frozenset({
    RoomType.DIAMOND_STAIR_ROOM,
    RoomType.NARROW_STAIR_ROOM,
    RoomType.SPIRAL_STAIR_ROOM,
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

        has_beast = neighbor.enemy_spec.enemy == Enemy.THE_BEAST
        has_top = neighbor.item == Item.TRIFORCE_OF_POWER
        if not (has_beast or has_top):
            shutter_count = sum(
                1 for d in (Direction.NORTH, Direction.SOUTH,
                            Direction.EAST, Direction.WEST)
                if neighbor.walls[d] == WallType.SHUTTER_DOOR
            )
            if shutter_count != 1:
                errors.append(
                    f"Level 9 room 0x{neighbor_num:02X}: adjacent to "
                    f"THE_KIDNAPPED (0x{rn:02X}) has {shutter_count} shutter "
                    f"doors (expected exactly 1 facing the kidnapped room) — "
                    f"extra shutters could allow bypassing the Triforce of "
                    f"Power gate"
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


def _staircase_trigger_rooms(level: Level) -> set[int]:
    """Return room_nums whose floor block / shutter trigger reveals a staircase."""
    stair_rooms: set[int] = set()
    for sr in level.staircase_rooms:
        if sr.room_type == RoomType.ITEM_STAIRCASE:
            if sr.return_dest is not None:
                stair_rooms.add(sr.return_dest)
        else:
            if sr.left_exit is not None:
                stair_rooms.add(sr.left_exit)
            if sr.right_exit is not None:
                stair_rooms.add(sr.right_exit)
    return stair_rooms


def _check_pushblock_stair_shutter_conflict(game_world: GameWorld, errors: list[str]) -> None:
    for level in game_world.levels:
        stair_rooms = _staircase_trigger_rooms(level)

        for room in level.rooms:
            if room.room_num not in stair_rooms:
                continue
            if room.room_type.has_open_staircase():
                continue
            if not (room.room_type.can_have_push_block() and room.movable_block):
                continue
            for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
                if room.walls[direction] == WallType.SHUTTER_DOOR:
                    errors.append(
                        f"Level {level.level_num} room 0x{room.room_num:02X}: "
                        f"push-block staircase room has SHUTTER_DOOR on "
                        f"{direction.name} — push block will open shutters "
                        f"instead of staircase"
                    )
                    break


def _check_npc_black_room(game_world: GameWorld, errors: list[str]) -> None:
    """Old men, bomb upgraders, muggers, and hungry enemies must live in BLACK_ROOM."""
    for level in game_world.levels:
        for room in level.rooms:
            if room.enemy_spec.enemy not in _BLACK_ROOM_REQUIRED_ENEMIES:
                continue
            if room.room_type == RoomType.BLACK_ROOM:
                continue
            errors.append(
                f"Level {level.level_num} room 0x{room.room_num:02X}: "
                f"{room.enemy_spec.enemy.name} requires RoomType.BLACK_ROOM, "
                f"got {room.room_type.name}"
            )


def _check_kidnapped_room_type(game_world: GameWorld, errors: list[str]) -> None:
    """THE_KIDNAPPED (Zelda) must not be placed in a staircase room type."""
    level_9 = game_world.levels[8]
    for room in level_9.rooms:
        if room.enemy_spec.enemy != Enemy.THE_KIDNAPPED:
            continue
        if room.room_type in _KIDNAPPED_FORBIDDEN_ROOM_TYPES:
            errors.append(
                f"Level 9 room 0x{room.room_num:02X}: THE_KIDNAPPED placed in "
                f"forbidden room type {room.room_type.name}"
            )


def _check_pushblock_purpose(game_world: GameWorld, errors: list[str]) -> None:
    """Every movable_block must do something — open shutters or reveal a stair.

    Either:
      (a) the room has at least one SHUTTER_DOOR wall and room_action ==
          PUSHING_BLOCK_OPENS_SHUTTERS, or
      (b) the room is a staircase trigger and room_action ==
          PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE.

    A pushblock that satisfies neither is dead weight (player pushes it,
    nothing happens).

    Exemption: rooms whose room_type has an always-visible staircase
    (DIAMOND_STAIR_ROOM, NARROW_STAIR_ROOM, SPIRAL_STAIR_ROOM — see
    RoomType.has_open_staircase). These rooms display a permanent
    staircase regardless of pushblock or action state, so a movable_block
    here is decorative/legacy. 14 of 15 vanilla violations were such
    rooms. The remaining vanilla case (L9 R0x37, TWO_FIREBALL_ROOM with
    no stair trigger and no shutter) is a known vanilla weirdness left
    intentionally not allowlisted for now.
    """
    for level in game_world.levels:
        stair_rooms = _staircase_trigger_rooms(level)
        for room in level.rooms:
            if not room.movable_block:
                continue
            if room.room_type.has_open_staircase():
                continue

            has_shutter = any(
                room.walls[d] == WallType.SHUTTER_DOOR
                for d in (Direction.NORTH, Direction.SOUTH,
                          Direction.EAST, Direction.WEST)
            )
            opens_shutters = (
                has_shutter
                and room.room_action == RoomAction.PUSHING_BLOCK_OPENS_SHUTTERS
            )
            opens_stairway = (
                room.room_num in stair_rooms
                and room.room_action == RoomAction.PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE
            )
            if opens_shutters or opens_stairway:
                continue

            errors.append(
                f"Level {level.level_num} room 0x{room.room_num:02X}: "
                f"movable_block but does nothing — needs either "
                f"(SHUTTER_DOOR + PUSHING_BLOCK_OPENS_SHUTTERS) or "
                f"(staircase trigger + PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE); "
                f"has shutter={has_shutter}, is stair trigger="
                f"{room.room_num in stair_rooms}, action={room.room_action.name}"
            )


def _check_pushblock_stairway_action_requires_block(
    game_world: GameWorld, errors: list[str],
) -> None:
    """A room with PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE must actually have a block."""
    for level in game_world.levels:
        for room in level.rooms:
            if room.room_action != RoomAction.PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE:
                continue
            if room.movable_block:
                continue
            errors.append(
                f"Level {level.level_num} room 0x{room.room_num:02X}: "
                f"room_action is PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE but "
                f"movable_block is False"
            )


def _check_l9_triforce_gate(game_world: GameWorld, errors: list[str]) -> None:
    """The L9 Triforce-of-Power gate room (one row north of the entrance) must
    have south=OPEN_DOOR and N/E/W ∈ {SOLID_WALL, SHUTTER_DOOR}.

    Identified by position (entrance_room - 16) rather than enemy, since the
    gate's NPC may be removed once the player holds 8 triforces.
    """
    level_9 = game_world.levels[8]
    gate_num = level_9.entrance_room - 16
    gate = next((r for r in level_9.rooms if r.room_num == gate_num), None)
    if gate is None:
        errors.append(
            f"Level 9: Triforce gate room 0x{gate_num:02X} "
            f"(entrance 0x{level_9.entrance_room:02X} - 0x10) not found"
        )
        return

    allowed = {WallType.SOLID_WALL, WallType.SHUTTER_DOOR}
    if gate.walls.south != WallType.OPEN_DOOR:
        errors.append(
            f"Level 9 room 0x{gate.room_num:02X}: Triforce gate south wall "
            f"is {gate.walls.south.name}, expected OPEN_DOOR"
        )
    for direction in (Direction.NORTH, Direction.EAST, Direction.WEST):
        wall = gate.walls[direction]
        if wall not in allowed:
            errors.append(
                f"Level 9 room 0x{gate.room_num:02X}: Triforce gate "
                f"{direction.name} wall is {wall.name}, expected "
                f"SOLID_WALL or SHUTTER_DOOR"
            )


def _check_dungeon_connectivity(game_world: GameWorld, errors: list[str]) -> None:
    for level in game_world.levels:
        if not _is_level_connected(level):
            errors.append(
                f"Level {level.level_num}: not all rooms reachable from "
                f"entrance (room 0x{level.entrance_room:02X})"
            )


_ALL_CHECKS: list[Callable[[GameWorld, list[str]], None]] = [
    _check_level_count,
    _check_dungeon_items,
    _check_enemy_codes,
    _check_npc_north_wall,
    _check_kidnapped,
    _check_wall_reciprocity,
    _check_pushblock_stair_shutter_conflict,
    _check_npc_black_room,
    _check_kidnapped_room_type,
    _check_pushblock_purpose,
    _check_pushblock_stairway_action_requires_block,
    _check_l9_triforce_gate,
]

_DUNGEON_TOPOLOGY_PHASES: frozenset[str] = frozenset({
    "generate_dungeon_shapes",
    "randomize_dungeons",
})


def integrity_check(game_world: GameWorld, phase_name: str) -> None:
    """Run all integrity checks. Raises IntegrityError if any fail."""
    errors: list[str] = []
    for check in _ALL_CHECKS:
        check(game_world, errors)
    if phase_name in _DUNGEON_TOPOLOGY_PHASES:
        _check_dungeon_connectivity(game_world, errors)
    if errors:
        msg = f"Integrity check failed after {phase_name}:\n" + "\n".join(
            f"  - {e}" for e in errors
        )
        logger.error(msg)
        raise IntegrityError(msg)
