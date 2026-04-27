"""Orchestrator: generate new dungeon shapes and inject into GameWorld."""
from __future__ import annotations

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
    is_l9_entry_gate,
)
from zora.dungeon.item_positions import (
    _STANDARD_ITEM_POSITION_TABLE,
    _assign_valid_item_positions,
)
from zora.dungeon.shuffle_dungeon_rooms import _is_level_connected
from zora.game_config import GameConfig
from zora.level_gen.api import NewLevelInput, generate_new_levels
from zora.level_gen.place_items import ItemPlacementError
from zora.parser import (
    RawBinFiles,
    parse_boss_sprite_set,
    parse_enemy_sprite_set,
    parse_levels_from_bins,
)
from zora.rng import Rng

_OW_ENEMY_TABLES_OFFSET = 0x100
_OW_ENEMY_TABLES_SIZE = 256
_SPRITE_PTR_SIZE = 20

_SHUTTER_KILL_ACTIONS = frozenset({
    RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS,
    RoomAction.KILLING_RINGLEADER_KILLS_ENEMIES_OPENS_SHUTTERS,
    RoomAction.KILLING_ENEMIES_OPENS_SHUTTERS_AND_DROPS_ITEM,
    RoomAction.DEFEATING_NPC_OPENS_SHUTTERS,
})


def _build_input(bins: RawBinFiles) -> NewLevelInput:
    ow_enemy_tables = bins.overworld_data[
        _OW_ENEMY_TABLES_OFFSET:_OW_ENEMY_TABLES_OFFSET + _OW_ENEMY_TABLES_SIZE
    ]
    sprite_table = bytes(bins.level_sprite_set_pointers) + bytes(bins.boss_sprite_set_pointers)
    return NewLevelInput(
        overworld_enemy_tables=ow_enemy_tables,
        level_info=bins.level_info,
        sprite_table=sprite_table,
    )


def fix_npc_shutter_doors(level: Level) -> None:
    """Replace shutter doors with open doors on rooms where unkillable NPCs
    make shutter-opening room actions impossible."""
    for room in level.rooms:
        if is_l9_entry_gate(level, room):
            continue
        if not room.enemy_spec.enemy.is_unkillable():
            continue
        if room.room_action not in _SHUTTER_KILL_ACTIONS:
            continue
        for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if room.walls[direction] == WallType.SHUTTER_DOOR:
                room.walls[direction] = WallType.OPEN_DOOR


def _fix_pushblock_stair_shutter_doors(level: Level) -> None:
    """Replace shutter doors with open doors on rooms where a push-block
    stairway conflicts with shutter doors.

    The validator's _has_stairway() returns False when a push-block room has
    shutter doors (the push block opens shutters, not a stairway). This makes
    any staircase behind that room unreachable. Affects both item staircases
    (return_dest) and transport staircases (left_exit / right_exit)."""
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

    if not stair_rooms:
        return

    for room in level.rooms:
        if room.room_num not in stair_rooms:
            continue
        if room.room_type.has_open_staircase():
            continue
        if not (room.room_type.can_have_push_block() and room.movable_block):
            continue
        for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if room.walls[direction] == WallType.SHUTTER_DOOR:
                room.walls[direction] = WallType.OPEN_DOOR


_OPPOSITE_DIR: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST: Direction.WEST,
    Direction.WEST: Direction.EAST,
}



def _fix_kidnapped_neighbors(level: Level) -> None:
    """Ensure rooms adjacent to THE_KIDNAPPED have shutter doors facing
    the kidnapped room and TRIFORCE_OF_POWER_OPENS_SHUTTERS action."""
    if level.level_num != 9:
        return

    room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}

    kidnapped_room: Room | None = None
    for room in level.rooms:
        if room.enemy_spec.enemy == Enemy.THE_KIDNAPPED:
            kidnapped_room = room
            break
    if kidnapped_room is None:
        return

    rn = kidnapped_room.room_num
    neighbors: list[tuple[Direction, int]] = [
        (Direction.NORTH, rn - 0x10),
        (Direction.SOUTH, rn + 0x10),
        (Direction.EAST, rn + 1),
        (Direction.WEST, rn - 1),
    ]

    for direction, neighbor_num in neighbors:
        if neighbor_num < 0 or neighbor_num > 0x7F:
            continue
        neighbor = room_map.get(neighbor_num)
        if neighbor is None:
            continue

        kidnapped_wall = kidnapped_room.walls[direction]
        if kidnapped_wall == WallType.SOLID_WALL:
            continue

        facing_dir = _OPPOSITE_DIR[direction]
        if neighbor.walls[facing_dir] != WallType.SHUTTER_DOOR:
            neighbor.walls[facing_dir] = WallType.SHUTTER_DOOR
        if neighbor.room_action != RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS:
            neighbor.room_action = RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS
        has_beast = neighbor.enemy_spec.enemy == Enemy.THE_BEAST
        has_top = neighbor.item == Item.TRIFORCE_OF_POWER
        if not (has_beast or has_top):
            for d in (Direction.NORTH, Direction.SOUTH,
                      Direction.EAST, Direction.WEST):
                if d != facing_dir and neighbor.walls[d] == WallType.SHUTTER_DOOR:
                    neighbor.walls[d] = WallType.OPEN_DOOR


_MAX_SHAPES_ATTEMPTS = 50


def generate_dungeon_shapes(
    game_world: GameWorld,
    bins: RawBinFiles,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Replace game_world.levels with freshly generated dungeon layouts.

    Retries shape generation internally (up to _MAX_SHAPES_ATTEMPTS) when the
    result has missing rooms or disconnected levels.  This is cheap (~0.04s per
    attempt) compared to the full item-placement pipeline, so we keep retrying
    here rather than burning expensive pipeline-level retries.
    """
    if not config.dungeon_shapes:
        return

    inputs = _build_input(bins)

    for shapes_attempt in range(_MAX_SHAPES_ATTEMPTS):
        seed = int(rng.random() * 0xFFFFFFFF)
        try:
            output = generate_new_levels(seed, inputs)
        except ItemPlacementError:
            continue

        levels = parse_levels_from_bins(
            level_1_6_data=output.level_1_6_grid,
            level_7_9_data=output.level_7_9_grid,
            level_info=output.level_info,
            mixed_enemy_data=bins.mixed_enemy_data,
            mixed_enemy_pointers=bins.mixed_enemy_pointers,
        )

        # Verify room counts match the grid.
        expected_counts: dict[int, int] = {}
        for grid in (output.grid_16, output.grid_79):
            for row in grid:
                for cell in row:
                    if cell > 0:
                        expected_counts[cell] = expected_counts.get(cell, 0) + 1

        valid = True
        for level in levels:
            expected = expected_counts.get(level.level_num, 0)
            if len(level.rooms) < expected:
                valid = False
                break

        if valid:
            for level in levels:
                if not _is_level_connected(level):
                    valid = False
                    break

        if valid:
            break
    else:
        raise RuntimeError(
            f"Shapes generation failed after {_MAX_SHAPES_ATTEMPTS} attempts"
        )

    enemy_ptrs = output.sprite_table[:_SPRITE_PTR_SIZE]
    boss_ptrs = output.sprite_table[_SPRITE_PTR_SIZE:]

    all_rooms = []
    for level in levels:
        level.enemy_sprite_set = parse_enemy_sprite_set(enemy_ptrs, level.level_num)
        level.boss_sprite_set = parse_boss_sprite_set(boss_ptrs, level.level_num)
        level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
        fix_npc_shutter_doors(level)
        _fix_pushblock_stair_shutter_doors(level)
        _fix_kidnapped_neighbors(level)
        all_rooms.extend(level.rooms)

    _assign_valid_item_positions(all_rooms, rng)

    game_world.levels = levels
