"""
Debug Beast — convenience hacks for quickly exercising dungeon levels.

Behavior (only when ``config.debug_beast`` is True):

  1. Force the first-quest dungeon entrances to land on fixed overworld
     screens close to the start, so you can walk into any dungeon without
     traversing the whole overworld:

       0x46  0x47  0x48    L6   L7   L8
       0x66  0x67  0x68    L2   L3   L4
       0x76  0x77  0x78    L1   L9   L5

     Each destination that was previously at the target screen gets swapped
     back onto the screen the moved dungeon used to occupy, so no cave or
     entrance is lost — only positions change.

  2. Open every internal wall in all dungeons (L1–L9) to a regular door,
     on both sides. The following rooms are excluded from wall-opening to
     preserve engine behavior:

       - The entrance room of each level.
       - For L9 only: the triforce-check gate room one tile north of the
         entrance (its shutters are controlled by the engine at Triforce-
         collection time).
       - Any room containing THE_BEAST (Ganon) or THE_KIDNAPPED (Zelda),
         whose shutter behavior the engine reads at boss-defeat time.

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
    Level,
    QuestVisibility,
    WallType,
    is_l9_entry_gate,
)
from zora.game_config import GameConfig
from zora.rng import Rng


# Dungeons to relocate: (Destination, target screen number).
# All are first-quest only; second-quest entrances are left untouched.
#
# Laid out as a 3×3 cluster with L9 at the start screen (0x77):
#
#   0x46  0x47  0x48    ←  L6   L7   L8
#   0x66  0x67  0x68    ←  L2   L3   L4
#   0x76  0x77  0x78    ←  L1   L9   L5
#
_DUNGEON_SCREEN_TARGETS: list[tuple[Destination, int]] = [
    (Destination.LEVEL_9, 0x77),  # centre — vanilla wood sword cave screen
    (Destination.LEVEL_1, 0x76),
    (Destination.LEVEL_5, 0x78),
    (Destination.LEVEL_2, 0x66),
    (Destination.LEVEL_3, 0x67),
    (Destination.LEVEL_4, 0x68),
    (Destination.LEVEL_6, 0x46),
    (Destination.LEVEL_7, 0x47),
    (Destination.LEVEL_8, 0x48),
]


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


def _force_dungeons_onto_nearby_screens(world: GameWorld) -> None:
    """Relocate first-quest dungeon entrances to fixed nearby overworld screens.

    Processes _DUNGEON_SCREEN_TARGETS in order. For each (destination, target
    screen), find the screen currently holding the dungeon entrance and swap
    its destination with whatever is at the target screen. If either screen
    cannot be found, or the dungeon is already at its target, the step is
    skipped silently.
    """
    screens_by_num = {s.screen_num: s for s in world.overworld.screens}

    for dest, target_num in _DUNGEON_SCREEN_TARGETS:
        target = screens_by_num.get(target_num)
        if target is None:
            continue
        src = next(
            (s for s in world.overworld.screens
             if s.destination == dest
             and s.quest_visibility != QuestVisibility.SECOND_QUEST),
            None,
        )
        if src is None or src is target:
            continue
        src.destination, target.destination = target.destination, src.destination


def _open_level_internal_walls(level: Level) -> None:
    """Open every eligible internal wall in *level* to OPEN_DOOR on both sides.

    Excluded rooms (walls left untouched):
      - The entrance room.
      - For L9: the triforce-check gate room immediately north of the entrance.
      - Any room containing THE_BEAST or THE_KIDNAPPED.
    """
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
    _force_dungeons_onto_nearby_screens(world)
    for level in world.levels:
        _open_level_internal_walls(level)
