"""
Debug Beast — convenience hacks for quickly exercising Level 9.

Behavior (only when ``config.debug_beast`` is True):

  1. Force the first-quest Level 9 entrance to land on the vanilla wood
     sword cave overworld screen (0x77), regardless of where any cave or
     start-screen shuffle moved things. Whatever destination was at 0x77
     gets swapped back into L9's old screen so no cave is lost.

  2. Open every internal wall in Level 9 to a regular door, on both
     sides, excluding walls touching the entrance room, the triforce-
     check gate room one north of it, the THE_BEAST (Ganon) room, and
     the THE_KIDNAPPED (Zelda) room. Treating those rooms as out-of-
     level preserves their boss/gate shutter behavior, which the engine
     reads at boss-defeat time and from the entry-gate triforce check.

This step is destructive to game integrity (the validator and assumed_fill
won't have planned around the modified layout) so it must run AFTER
assumed_fill and integrity_check, and BEFORE serialize_game_world.
"""

from __future__ import annotations

from zora.data_model import (
    Destination,
    Direction,
    Enemy,
    GameWorld,
    QuestVisibility,
    WallType,
    is_l9_entry_gate,
)
from zora.game_config import GameConfig
from zora.rng import Rng


# Vanilla overworld screen for the wood sword cave entrance. We force L9 to
# land here even when cave_shuffle_mode has rearranged things.
_VANILLA_WOOD_SWORD_SCREEN_NUM = 0x77


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


def _force_l9_onto_vanilla_wood_sword_screen(world: GameWorld) -> None:
    """Put the first-quest L9 entrance at screen 0x77 (the vanilla wood sword
    cave screen). Swap whatever destination is currently there back onto the
    screen L9 used to occupy, so the Q1 L9 always lives at 0x77 by the time
    debug_beast is done.

    No-op if either screen can't be found or L9 is already at 0x77.
    """
    screens_by_num = {s.screen_num: s for s in world.overworld.screens}
    target = screens_by_num.get(_VANILLA_WOOD_SWORD_SCREEN_NUM)
    if target is None:
        return

    # Z1 has two L9 entrances on the overworld (Q1 + Q2). Only the
    # first-quest one matters for normal play; leave the Q2 entrance alone.
    l9_screen = next(
        (s for s in world.overworld.screens
         if s.destination == Destination.LEVEL_9
         and s.quest_visibility != QuestVisibility.SECOND_QUEST),
        None,
    )
    if l9_screen is None or l9_screen is target:
        return

    l9_screen.destination, target.destination = (
        target.destination,
        l9_screen.destination,
    )


def _open_l9_internal_walls(world: GameWorld) -> None:
    level = world.levels[8]  # L9 is index 8
    if level.level_num != 9:
        return

    # Treat structural rooms as out-of-level for this pass: their walls
    # encode boss-defeat shutters and gate semantics that the engine
    # reads at runtime. Replacing those walls with OPEN_DOOR can hard-
    # lock the game on boss defeat or break the triforce check.
    excluded_room_nums = {level.entrance_room}
    for r in level.rooms:
        if is_l9_entry_gate(level, r):
            excluded_room_nums.add(r.room_num)
        if r.enemy_spec.enemy in (Enemy.THE_BEAST, Enemy.THE_KIDNAPPED):
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
    _force_l9_onto_vanilla_wood_sword_screen(world)
    _open_l9_internal_walls(world)
