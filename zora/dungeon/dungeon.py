"""Dungeon randomization orchestrator.

Called by generate_game as a single pipeline step. Dispatches to the
individual dungeon randomization functions in the correct order, gating
each on the appropriate GameConfig flags.

Call order:
1. shuffle_dungeon_rooms — shuffles room contents within each level
2. scramble_dungeon_rooms — scrambles room contents across all levels
"""

from __future__ import annotations

from zora.data_model import GameWorld, Room, RoomType, WallType
from zora.dungeon.scramble_dungeon_rooms import (
    _STANDARD_ITEM_POSITION_TABLE,
    _assign_valid_item_positions,
    scramble_dungeon_rooms,
)
from zora.dungeon.shuffle_dungeon_rooms import shuffle_dungeon_rooms
from zora.game_config import GameConfig
from zora.rng import Rng


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
            level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
        all_rooms = [room for level in game_world.levels for room in level.rooms]
        _assign_valid_item_positions(all_rooms, rng)


def _fix_narrow_stair_east_walls(world: GameWorld) -> None:
    """Force NARROW_STAIR_ROOM east walls to SOLID_WALL.

    The NARROW_STAIR layout has a solid wall baked into its right side
    at the tile level. If the door data says anything other than
    SOLID_WALL, the player sees an open doorway into an impassable wall.
    """
    grid_rooms: dict[int, Room] = {}
    for level in world.levels:
        for room in level.rooms:
            grid_rooms[room.room_num] = room

    for room in grid_rooms.values():
        if room.room_type != RoomType.NARROW_STAIR_ROOM:
            continue
        if room.walls.east != WallType.SOLID_WALL:
            room.walls.east = WallType.SOLID_WALL
        right_num = room.room_num + 1
        if room.room_num % 16 < 15 and right_num in grid_rooms:
            if grid_rooms[right_num].walls.west != WallType.SOLID_WALL:
                grid_rooms[right_num].walls.west = WallType.SOLID_WALL
