"""Dungeon randomization orchestrator.

Called by generate_game as a single pipeline step. Dispatches to the
individual dungeon randomization functions in the correct order, gating
each on the appropriate GameConfig flags.

Call order:
1. shuffle_dungeon_rooms — shuffles room contents within each level
2. scramble_dungeon_rooms — scrambles room contents across all levels
"""

from __future__ import annotations

import logging

from zora.data_model import (
    Direction,
    GameWorld,
    Level,
    Room,
    RoomType,
    WallType,
)
from zora.dungeon.scramble_dungeon_rooms import (
    _REQUIRED_DIRECTIONS,
    _STANDARD_ITEM_POSITION_TABLE,
    _VALID_ITEM_POSITIONS,
    _assign_valid_item_positions,
    scramble_dungeon_rooms,
)
from zora.dungeon.shuffle_dungeon_rooms import (
    _DIR_OFFSETS,
    _OPPOSITE_DIR,
    _is_level_connected,
    _is_path_obstructed,
    shuffle_dungeon_rooms,
)
from zora.game_config import GameConfig
from zora.level_gen.orchestrator import _fix_kidnapped_neighbors
from zora.rng import Rng

logger = logging.getLogger(__name__)


def randomize_dungeons(
    game_world: GameWorld,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Run all dungeon randomization steps in order.

    Each sub-function either self-gates on its config flags or is gated
    here. The call order matters — scramble runs after shuffle so that
    intra-level shuffling happens before cross-level scrambling.

    Args:
        game_world: The game state to modify in place.
        config: Resolved game configuration.
        rng: Shared RNG instance (state flows between steps).
    """
    if config.shuffle_dungeon_rooms:
        if not shuffle_dungeon_rooms(game_world, rng):
            raise RuntimeError("Dungeon room shuffle failed")
    if config.scramble_dungeon_rooms:
        if not scramble_dungeon_rooms(
            game_world,
            rng,
            shuffle_gannon_and_zelda=config.shuffle_ganon_zelda,
            shuffle_drops=True,
        ):
            raise RuntimeError("Dungeon room scramble failed")

    if config.shuffle_dungeon_rooms or config.scramble_dungeon_rooms:
        _fix_narrow_stair_east_walls(game_world)
        for level in game_world.levels:
            _fix_kidnapped_neighbors(level)
            level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
        all_rooms = [room for level in game_world.levels for room in level.rooms]
        _assign_valid_item_positions(all_rooms, rng)
        _fix_direction_sensitive_item_positions(game_world, rng)

        if not all(_is_level_connected(level) for level in game_world.levels):
            raise RuntimeError("Dungeon post-fixup connectivity check failed")


def _get_entry_directions(level: Level) -> dict[int, set[Direction]]:
    """Run a connectivity flood-fill and return the set of entry directions
    for each room_num in the level."""
    level_room_nums = frozenset(r.room_num for r in level.rooms)
    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}

    visited_states: set[tuple[int, Direction]] = set()
    entry_dirs: dict[int, set[Direction]] = {}
    queue: list[tuple[int, Direction]] = [
        (level.entrance_room, level.entrance_direction),
    ]

    def _expand(rn: int, entry_dir: Direction) -> None:
        state = (rn, entry_dir)
        if state in visited_states:
            return
        visited_states.add(state)
        entry_dirs.setdefault(rn, set()).add(entry_dir)
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

    # Follow transport staircases
    changed = True
    while changed:
        changed = False
        for sr in level.staircase_rooms:
            if sr.room_num in entry_dirs:
                continue
            if sr.room_type != RoomType.TRANSPORT_STAIRCASE:
                continue
            if sr.left_exit is None or sr.right_exit is None:
                continue
            if sr.left_exit in entry_dirs or sr.right_exit in entry_dirs:
                entry_dirs[sr.room_num] = set()
                for exit_rn in (sr.left_exit, sr.right_exit):
                    state = (exit_rn, Direction.STAIRCASE)
                    if state not in visited_states:
                        queue.append(state)
                        changed = True
                while queue:
                    rn, entry_dir = queue.pop()
                    _expand(rn, entry_dir)

    return entry_dirs


def _fix_direction_sensitive_item_positions(
    world: GameWorld,
    rng: Rng,
) -> None:
    """Re-randomize item positions in direction-sensitive rooms when the
    current position isn't reachable from any actual entry direction."""
    for level in world.levels:
        entry_dirs = _get_entry_directions(level)
        for room in level.rooms:
            valid_positions = _VALID_ITEM_POSITIONS.get(room.room_type)
            if not valid_positions:
                continue
            required = _REQUIRED_DIRECTIONS.get(
                (room.room_type, room.item_position),
            )
            if required is None:
                continue
            dirs = entry_dirs.get(room.room_num, set())
            if dirs & required:
                continue
            # Current position unreachable — find positions that work
            reachable_positions = []
            for pos in valid_positions:
                pos_required = _REQUIRED_DIRECTIONS.get(
                    (room.room_type, pos),
                )
                if pos_required is None or (dirs & pos_required):
                    reachable_positions.append(pos)
            if reachable_positions:
                room.item_position = rng.choice(reachable_positions)
                logger.info(
                    "L%d R%s: re-randomized %s item position to %s "
                    "(entry dirs: %s)",
                    level.level_num, f"{room.room_num:#04x}",
                    room.room_type.name, room.item_position.name,
                    [d.name for d in dirs],
                )
            else:
                logger.warning(
                    "L%d R%s: no valid item position reachable from %s "
                    "for %s",
                    level.level_num, f"{room.room_num:#04x}",
                    [d.name for d in dirs], room.room_type.name,
                )


def _fix_narrow_stair_east_walls(world: GameWorld) -> None:
    """Force NARROW_STAIR_ROOM east walls to SOLID_WALL.

    The NARROW_STAIR layout has a solid wall baked into its right side
    at the tile level. If the door data says anything other than
    SOLID_WALL, the player sees an open doorway into an impassable wall.
    """
    for level in world.levels:
        rooms_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
        for room in level.rooms:
            if room.room_type != RoomType.NARROW_STAIR_ROOM:
                continue
            if room.walls.east != WallType.SOLID_WALL:
                room.walls.east = WallType.SOLID_WALL
            right_num = room.room_num + 1
            right = rooms_by_num.get(right_num)
            if room.room_num % 16 < 15 and right is not None:
                if right.walls.west != WallType.SOLID_WALL:
                    right.walls.west = WallType.SOLID_WALL
