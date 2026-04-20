"""Orchestrator: generate new dungeon shapes and inject into GameWorld."""
from __future__ import annotations

from zora.data_model import (
    Direction,
    GameWorld,
    Level,
    RoomAction,
    WallType,
)
from zora.dungeon.scramble_dungeon_rooms import (
    _STANDARD_ITEM_POSITION_TABLE,
    _assign_valid_item_positions,
)
from zora.game_config import GameConfig
from zora.level_gen.api import NewLevelInput, generate_new_levels
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


def _fix_npc_shutter_doors(level: Level) -> None:
    """Replace shutter doors with open doors on rooms where unkillable NPCs
    make shutter-opening room actions impossible."""
    for room in level.rooms:
        if not room.enemy_spec.enemy.is_unkillable():
            continue
        if room.room_action not in _SHUTTER_KILL_ACTIONS:
            continue
        for direction in (Direction.NORTH, Direction.SOUTH, Direction.EAST, Direction.WEST):
            if room.walls[direction] == WallType.SHUTTER_DOOR:
                room.walls[direction] = WallType.OPEN_DOOR


def generate_dungeon_shapes(
    game_world: GameWorld,
    bins: RawBinFiles,
    config: GameConfig,
    rng: Rng,
) -> None:
    """Replace game_world.levels with freshly generated dungeon layouts."""
    if not config.dungeon_shapes:
        return

    seed = int(rng.random() * 0xFFFFFFFF)
    inputs = _build_input(bins)
    output = generate_new_levels(seed, inputs)

    enemy_ptrs = output.sprite_table[:_SPRITE_PTR_SIZE]
    boss_ptrs = output.sprite_table[_SPRITE_PTR_SIZE:]

    levels = parse_levels_from_bins(
        level_1_6_data=output.level_1_6_grid,
        level_7_9_data=output.level_7_9_grid,
        level_info=output.level_info,
        mixed_enemy_data=bins.mixed_enemy_data,
        mixed_enemy_pointers=bins.mixed_enemy_pointers,
    )

    all_rooms = []
    for level in levels:
        level.enemy_sprite_set = parse_enemy_sprite_set(enemy_ptrs, level.level_num)
        level.boss_sprite_set = parse_boss_sprite_set(boss_ptrs, level.level_num)
        level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
        _fix_npc_shutter_doors(level)
        all_rooms.extend(level.rooms)

    _assign_valid_item_positions(all_rooms, rng)

    game_world.levels = levels
