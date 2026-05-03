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


def _fix_l9_old_man_walls(level: Level) -> None:
    """Force the wall layout that _fix_special_rooms (Block 5) will set
    on L9 OLD_MAN NPC rooms: north=SOLID (mirrored), south=OPEN, non-
    SOLID west/east → SHUTTER. Lifted into the orchestrator so the
    reachability check inside generate_dungeon_shapes sees the same
    layout the integrity check will see."""
    if level.level_num != 9:
        return
    room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}
    for room in level.rooms:
        if room.enemy_spec.enemy != Enemy.OLD_MAN:
            continue
        w = room.walls
        if w.north != WallType.SOLID_WALL:
            w.north = WallType.SOLID_WALL
            above = room_map.get(room.room_num - 16)
            if above is not None:
                above.walls.south = WallType.SOLID_WALL
        w.south = WallType.OPEN_DOOR
        if w.west != WallType.SOLID_WALL:
            w.west = WallType.SHUTTER_DOOR
        if w.east != WallType.SOLID_WALL:
            w.east = WallType.SHUTTER_DOOR


def _fix_l9_entrance_room_walls(level: Level) -> None:
    """Force the wall layout that _fix_special_rooms (Block 6) will set
    on the L9 ENTRANCE_ROOM: west/east=SOLID, north/south=OPEN, with
    east/west neighbors' facing walls also forced to SOLID."""
    if level.level_num != 9:
        return
    room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}
    for room in level.rooms:
        if room.room_type != RoomType.ENTRANCE_ROOM:
            continue
        room.walls.west = WallType.SOLID_WALL
        room.walls.east = WallType.SOLID_WALL
        room.walls.south = WallType.OPEN_DOOR
        room.walls.north = WallType.OPEN_DOOR
        rn = room.room_num
        col = rn % 16
        if col > 0:
            left = room_map.get(rn - 1)
            if left is not None:
                left.walls.east = WallType.SOLID_WALL
        if col < 15:
            right = room_map.get(rn + 1)
            if right is not None:
                right.walls.west = WallType.SOLID_WALL


def _fix_l9_entry_gate(level: Level) -> None:
    """Normalize the L9 entry-gate room walls to satisfy the integrity
    check (south=OPEN_DOOR, N/E/W ∈ {SOLID_WALL, SHUTTER_DOOR}).

    The gate is the room immediately north of the L9 entrance. The
    upstream pipeline (new_level_doors + _merge_wall_segments) assigns
    these walls without awareness of the gate's structural role, so
    this post-fix normalizes them and mirrors the change onto each
    adjacent neighbor's facing wall.

    Rule for each of N/E/W:
      - SOLID_WALL or SHUTTER_DOOR → already valid, leave alone.
      - Anything else (OPEN_DOOR, LOCKED_DOOR_*, BOMB_HOLE, WALK_THROUGH)
        means the random pipeline placed a passage there. Convert it to
        SHUTTER_DOOR on the gate side and OPEN_DOOR on the neighbor side
        — preserving the connection while letting the gate's
        Triforce-of-Power logic gate progression.

    Exception: if the neighbor is THE_KIDNAPPED, force SOLID on both
    sides regardless of the original wall. The kidnapped room and the
    entry gate use incompatible shutter-opening triggers, so the wall
    between them must be sealed (the rest of L9 will be reached via
    other adjacencies, validated separately by the connectivity check).
    """
    if level.level_num != 9:
        return

    gate_num = level.entrance_room - 0x10
    room_map: dict[int, Room] = {r.room_num: r for r in level.rooms}
    gate = room_map.get(gate_num)
    if gate is None:
        return

    neighbor_offsets: dict[Direction, int] = {
        Direction.NORTH: -0x10,
        Direction.SOUTH: 0x10,
        Direction.EAST: 1,
        Direction.WEST: -1,
    }

    # South is always OPEN (faces the entrance below).
    target_walls: dict[Direction, WallType] = {Direction.SOUTH: WallType.OPEN_DOOR}

    for direction in (Direction.NORTH, Direction.EAST, Direction.WEST):
        neighbor_num = gate_num + neighbor_offsets[direction]
        neighbor = (room_map.get(neighbor_num)
                    if 0 <= neighbor_num <= 0x7F else None)

        # Kidnapped exception: seal the wall on both sides.
        if neighbor is not None and neighbor.enemy_spec.enemy == Enemy.THE_KIDNAPPED:
            target_walls[direction] = WallType.SOLID_WALL
            continue

        current = gate.walls[direction]
        if current in (WallType.SOLID_WALL, WallType.SHUTTER_DOOR):
            target_walls[direction] = current
        else:
            target_walls[direction] = WallType.SHUTTER_DOOR

    for direction, target in target_walls.items():
        if gate.walls[direction] != target:
            gate.walls[direction] = target
        neighbor_num = gate_num + neighbor_offsets[direction]
        if neighbor_num < 0 or neighbor_num > 0x7F:
            continue
        neighbor = room_map.get(neighbor_num)
        if neighbor is None:
            continue
        opposite = _OPPOSITE_DIR[direction]
        # Mirror: gate-side SHUTTER becomes OPEN on the neighbor (the
        # neighbor sees a normal doorway, the engine reads the gate
        # side's SHUTTER state). For SOLID and OPEN, mirror identically.
        neighbor_target = (WallType.OPEN_DOOR
                           if target == WallType.SHUTTER_DOOR
                           else target)
        if neighbor.walls[opposite] != neighbor_target:
            neighbor.walls[opposite] = neighbor_target


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

    stair_trigger_rooms: set[int] = set()
    for sr in level.staircase_rooms:
        if sr.room_type == RoomType.ITEM_STAIRCASE:
            if sr.return_dest is not None:
                stair_trigger_rooms.add(sr.return_dest)
        else:
            if sr.left_exit is not None:
                stair_trigger_rooms.add(sr.left_exit)
            if sr.right_exit is not None:
                stair_trigger_rooms.add(sr.right_exit)

    for direction, neighbor_num in neighbors:
        if neighbor_num < 0 or neighbor_num > 0x7F:
            continue
        neighbor = room_map.get(neighbor_num)
        if neighbor is None:
            continue
        if is_l9_entry_gate(level, neighbor):
            # The two L9 gates (entry gate uses NOTHING_OPENS_SHUTTERS +
            # engine 8-Triforce-of-Wisdom special case; kidnapped gate uses
            # TRIFORCE_OF_POWER_OPENS_SHUTTERS) can't share state. Sever the
            # wall so the entry gate keeps its semantics; the kidnapped gate
            # will be enforced through one of the other neighbors.
            kidnapped_room.walls[direction] = WallType.SOLID_WALL
            neighbor.walls[_OPPOSITE_DIR[direction]] = WallType.SOLID_WALL
            continue

        # Stair-trigger pushblock rooms can't be kidnapped neighbors:
        # the kidnapped gate needs room_action=TRIFORCE_OF_POWER_OPENS_SHUTTERS
        # and a SHUTTER_DOOR wall, but a stair-trigger pushblock room needs
        # room_action=PUSHING_BLOCK_MAKES_STAIRWAY_VISIBLE and NO shutter
        # walls (otherwise the engine opens the shutter instead of revealing
        # the staircase). Sever the wall and let one of the other neighbors
        # carry the kidnapped-gate role; if no other neighbor is available,
        # _check_l9_full_reachability will reject the layout and the
        # orchestrator re-rolls.
        if (neighbor.movable_block
                and neighbor.room_num in stair_trigger_rooms
                and not neighbor.room_type.has_open_staircase()):
            kidnapped_room.walls[direction] = WallType.SOLID_WALL
            neighbor.walls[_OPPOSITE_DIR[direction]] = WallType.SOLID_WALL
            continue

        kidnapped_wall = kidnapped_room.walls[direction]
        if kidnapped_wall == WallType.SOLID_WALL:
            continue

        facing_dir = _OPPOSITE_DIR[direction]
        if neighbor.walls[facing_dir] != WallType.SHUTTER_DOOR:
            neighbor.walls[facing_dir] = WallType.SHUTTER_DOOR
        if neighbor.room_action != RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS:
            neighbor.room_action = RoomAction.TRIFORCE_OF_POWER_OPENS_SHUTTERS
        # The kidnapped-gate role requires room_action=
        # TRIFORCE_OF_POWER_OPENS_SHUTTERS, which conflicts with the
        # pushblock-purpose rule (movable_block must pair with action=4
        # or =5). Clear the movable_block bit so the room is purely a
        # kidnapped-gate; the room_type's floor layout is preserved,
        # only the block sprite goes away. (Stair-trigger pushblock
        # rooms were already severed above.)
        if neighbor.movable_block:
            neighbor.movable_block = False
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

        if not valid:
            continue

        # Run post-fixes inside the loop so we can validate the
        # post-fixed layout. Wall normalizers can change reachability,
        # so checking validator reachability before the fixes would
        # accept layouts the integrity check then rejects (and reject
        # layouts the fixes would have repaired).
        enemy_ptrs = output.sprite_table[:_SPRITE_PTR_SIZE]
        boss_ptrs = output.sprite_table[_SPRITE_PTR_SIZE:]
        all_rooms: list[Room] = []
        for level in levels:
            level.enemy_sprite_set = parse_enemy_sprite_set(
                enemy_ptrs, level.level_num)
            level.boss_sprite_set = parse_boss_sprite_set(
                boss_ptrs, level.level_num)
            level.item_position_table = list(_STANDARD_ITEM_POSITION_TABLE)
            fix_npc_shutter_doors(level)
            _fix_pushblock_stair_shutter_doors(level)
            _fix_l9_entry_gate(level)
            _fix_kidnapped_neighbors(level)
            # Mirror the L9-specific wall mutations that _fix_special_rooms
            # in generate_game.py applies post-orchestrator. Without these
            # the inner-loop reachability check evaluates a layout the
            # integrity check (run after _fix_special_rooms) won't see.
            _fix_l9_old_man_walls(level)
            _fix_l9_entrance_room_walls(level)
            all_rooms.extend(level.rooms)

        _assign_valid_item_positions(all_rooms, rng)

        # Re-check connectivity post-fix: the wall normalizers above can
        # convert non-solid walls to SOLID (e.g. _fix_l9_entry_gate's
        # kidnapped exception, _fix_kidnapped_neighbors severing entry
        # gate), which can disconnect rooms that were reachable before.
        post_fix_connected = True
        for level in levels:
            if not _is_level_connected(level):
                post_fix_connected = False
                break
        if not post_fix_connected:
            continue

        # Reject layouts where L9 has rooms unreachable with full
        # inventory. Same check _check_l9_full_reachability runs after
        # this phase, but moved into the inner loop so a bad layout
        # triggers a cheap shapes-retry instead of burning a full
        # pipeline-level retry (~1-15s on randomize_items).
        game_world.levels = levels
        if not _l9_fully_reachable(game_world):
            continue

        return
    raise RuntimeError(
        f"Shapes generation failed after {_MAX_SHAPES_ATTEMPTS} attempts"
    )


def _l9_fully_reachable(game_world: GameWorld) -> bool:
    """Return True iff every L9 room is reachable from the entrance with
    a full inventory (every item + 8 Triforces + 99 keys + virtual beast
    flag). Mirrors _check_l9_full_reachability in integrity_check.py."""
    from zora.game_validator import GameValidator
    from zora.inventory import Inventory

    level_9 = game_world.levels[8]

    inventory = Inventory(progressive_items=False)
    for item in Item:
        inventory.items.add(item)
    inventory.items.add(Item.BEAST_DEFEATED_VIRTUAL_ITEM)
    for lvl in range(1, 9):
        inventory.levels_with_triforce_obtained.append(lvl)
    inventory.num_keys = 99

    validator = GameValidator(game_world, avoid_required_hard_combat=False,
                              progressive_items=False)
    validator.get_reachable_locations(assumed_inventory=inventory)

    l9_room_nums = {r.room_num for r in level_9.rooms}
    reachable_l9 = {rn for (lvl, rn) in validator.visited_rooms if lvl == 9}
    return l9_room_nums.issubset(reachable_l9)
