"""
Debug Beast — convenience hacks for quickly exercising Level 9.

Behavior (only when ``config.debug_beast`` is True):

  1. Swap the overworld entrance destinations of the Wood Sword Cave and
     Level 9. Walking into the L9 entrance puts you in the wood sword cave
     (and vice versa) — i.e. you can enter L9 from the start screen.

  2. Open every internal wall in Level 9 to a regular door, on both sides,
     excluding walls touching the entrance room or the triforce-check gate
     room one north of it. Effectively: treat those two rooms as if they
     aren't part of L9 for the wall-opening pass.

This step is destructive to game integrity (the validator and assumed_fill
won't have planned around the modified layout) so it must run AFTER
assumed_fill and integrity_check, and BEFORE serialize_game_world.
"""

from __future__ import annotations

from zora.data_model import (
    Destination,
    Direction,
    GameWorld,
    QuestVisibility,
    WallType,
    is_l9_entry_gate,
)
from zora.game_config import GameConfig
from zora.rng import Rng


_DIR_TO_OFFSET: dict[Direction, int] = {
    Direction.NORTH: -0x10,
    Direction.SOUTH: +0x10,
    Direction.EAST:  +1,
    Direction.WEST:  -1,
}

_OPPOSITE_DIR: dict[Direction, Direction] = {
    Direction.NORTH: Direction.SOUTH,
    Direction.SOUTH: Direction.NORTH,
    Direction.EAST:  Direction.WEST,
    Direction.WEST:  Direction.EAST,
}


def _swap_l9_and_wood_sword_overworld(world: GameWorld) -> None:
    # Z1 has two L9 entrances on the overworld (one per quest). We only swap
    # the first-quest one with the (single) wood sword cave entrance.
    l9_screen = next(
        (s for s in world.overworld.screens
         if s.destination == Destination.LEVEL_9
         and s.quest_visibility != QuestVisibility.SECOND_QUEST),
        None,
    )
    ws_screen = next(
        (s for s in world.overworld.screens if s.destination == Destination.WOOD_SWORD_CAVE),
        None,
    )
    if l9_screen is None or ws_screen is None:
        return
    l9_screen.destination, ws_screen.destination = (
        ws_screen.destination,
        l9_screen.destination,
    )


def _open_l9_internal_walls(world: GameWorld) -> None:
    level = world.levels[8]  # L9 is index 8
    if level.level_num != 9:
        return

    # Treat the entrance and entry-gate rooms as out-of-level for this pass.
    excluded_room_nums = {level.entrance_room}
    for r in level.rooms:
        if is_l9_entry_gate(level, r):
            excluded_room_nums.add(r.room_num)

    eligible_room_nums = frozenset(
        r.room_num for r in level.rooms if r.room_num not in excluded_room_nums
    )
    rooms_by_num = {r.room_num: r for r in level.rooms}

    for room in level.rooms:
        if room.room_num not in eligible_room_nums:
            continue
        for direction, offset in _DIR_TO_OFFSET.items():
            neighbor_num = room.room_num + offset
            if neighbor_num not in eligible_room_nums:
                continue
            neighbor = rooms_by_num[neighbor_num]
            room.walls[direction] = WallType.OPEN_DOOR
            neighbor.walls[_OPPOSITE_DIR[direction]] = WallType.OPEN_DOOR


def apply_debug_beast(world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """Apply debug_beast effects in place. No-op when the flag is off.

    Signature matches the standard randomizer step (game_world, config, rng).
    """
    if not config.debug_beast:
        return
    _swap_l9_and_wood_sword_overworld(world)
    _open_l9_internal_walls(world)
