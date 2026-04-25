"""Scramble dungeon rooms across all levels (full shuffle).

This is the additional shuffle pass that runs AFTER shuffle_dungeon_rooms
(in-dungeon shuffle) when the user enables full shuffle.  It does not
replace shuffle_dungeon_rooms — both run in sequence.

Empirically derived from a 100-seed reference-randomizer corpus, with two
intentional design divergences (see _LEVEL_LOCKED_ROOM_TYPES and
_collect_staircase_bound_rooms below).

Architecture: two independent shuffle passes plus a repair/retry harness.

  Pass A: ROOM-TYPE SHUFFLE (global, across all 9 levels)
    Permutes room_type values across the entire dungeon grid.  Walls stay
    at their grid positions and were re-derived by shuffle_dungeon_rooms's
    door-pair shuffle that ran first.

    Most room_types are eligible.  Four are level-locked and never move:
      ENTRANCE_ROOM, ZELDA_ROOM, GANNON_ROOM, TRIFORCE_ROOM.

    Additionally, any room referenced by a staircase entry stays put —
    its position has a "staircase trigger" role baked in by the per-level
    shuffle, and moving its room_type/movable_block would break access
    to the rooms behind that staircase.

    Movable_block follows the room_type, since it's tied to room mechanics
    (push-block triggers a staircase, etc.).

  Pass B: MINOR-ITEM SHUFFLE (global, across all 9 levels)
    Permutes only the four "minor" items (NOTHING, KEY, BOMBS, FIVE_RUPEES)
    across the entire dungeon's regular rooms.  All other items stay in
    their baseline level (preserved per-level by shuffle_dungeon_rooms).

  Repair + retry harness:
    Pass A can occasionally produce placements that fail one of two
    post-conditions: per-level connectivity (e.g., a chute landing at a
    position whose walls don't carry traffic on the chute's required
    axis), or the L9 kidnapped-neighbor-gate constraint (a push-block
    staircase room ending up adjacent to THE_KIDNAPPED with a shutter
    door facing her room — push-block-stairs and Triforce-of-Power-gate
    can't share a single room_action slot).

    After Pass A we run _fix_constrained_room_doors to open at least one
    door on the valid axis for chute/T_ROOM rooms, then check both
    post-conditions.  If either fails, we restore the pre-scramble state
    and retry with fresh RNG state (up to _MAX_SCRAMBLE_RETRIES).

What this function does NOT do (handled by shuffle_dungeon_rooms):
  - Per-level enemy/item shuffle (already done before we run).
  - Old-man variant reassignment.
  - L9 R$0x66 pinning.
  - Boss-room (L9) tracking.
  - Wall pair shuffles.

DESIGN DIVERGENCES FROM REFERENCE:

  1. AQUAMENTUS_ROOM is NOT level-locked.  The reference pins it; we
     don't, because the AQUAMENTUS *enemy* (which is level-locked by
     shuffle_dungeon_rooms) is unaffected by where the AQUAMENTUS *room
     shape* lands.  The reference's choice was likely cosmetic — players
     expect Aquamentus to be in L1's dragon-arena room.  We trade that
     consistency for more variety.

  2. Rooms referenced by staircase entries are pinned.  Empirically the
     reference doesn't pin these — only 0-8% per baseline type stay put —
     so it must use a different mechanism.  The most likely candidate is
     re-pairing staircase pointers to follow whichever rooms end up with
     stairway-providing types after the global shuffle.  Implementing
     that would unlock more variety; for now we pin, which is simpler
     and validated to produce beatable seeds.

NOTE on the kidnapped-gate constraint:
  fix_pushblock_staircase_shutters runs at two points in the pipeline:
  once after randomize_dungeons (where our scramble ends) and again
  after randomize_enemies.  Our retry harness catches conflicts at the
  first point — but only when the conflict room is shufflable.  Some
  seeds have structurally unresolvable conflicts because the conflict
  room is staircase-bound (pinned), and no retry permutation can change
  its room_type/movable_block.  For those seeds, scramble correctly
  returns False; the outer generate_game.py retry budget handles
  re-rolling with fresh RNG state, which produces a different
  in-dungeon shuffle (different rooms become THE_KIDNAPPED's neighbors,
  different rooms become staircase entries) and typically clears the
  conflict.  In production this is invisible to users.
"""

from zora.data_model import (
    Direction,
    Enemy,
    GameWorld,
    Item,
    Level,
    Room,
    RoomType,
    WallType,
)
from zora.dungeon.shuffle_dungeon_rooms import (
    _DIR_OFFSETS,
    _OPPOSITE_DIR,
    _RoomSnapshot,
    _clear_boss_cry_bits,
    _fix_constrained_room_doors,
    _fix_special_rooms,
    _is_level_connected,
)
from zora.rng import Rng


_LEVEL_LOCKED_ROOM_TYPES: frozenset[RoomType] = frozenset({
    RoomType.ENTRANCE_ROOM,     # 0x21
    RoomType.ZELDA_ROOM,        # 0x27
    RoomType.GANNON_ROOM,       # 0x28
    RoomType.TRIFORCE_ROOM,     # 0x29
})

_MINOR_ITEMS: frozenset[Item] = frozenset({
    Item.NOTHING,       # 0x18
    Item.KEY,           # 0x19
    Item.BOMBS,         # 0x00
    Item.FIVE_RUPEES,   # 0x0F
})

_MAX_SCRAMBLE_RETRIES = 500


def _collect_staircase_bound_rooms(level: Level) -> frozenset[int]:
    """Collect room_nums that are pinned because they trigger a staircase.

    Any room referenced by a transport staircase's left_exit/right_exit, or
    by an item staircase's return_dest, must retain its room_type and
    movable_block — _is_level_connected's _room_has_stairway predicate
    requires an open-staircase room_type or a push-block-with-movable_block
    setup at the staircase entry, and the per-level shuffle has already
    paired specific room_types with specific staircase entries.

    Re-shuffling those room_types breaks BFS access to the staircase,
    leaving entire post-staircase regions unreachable.
    """
    pinned: set[int] = set()
    for sr in level.staircase_rooms:
        if sr.left_exit is not None:
            pinned.add(sr.left_exit)
        if sr.right_exit is not None:
            pinned.add(sr.right_exit)
        if sr.return_dest is not None:
            pinned.add(sr.return_dest)
    return frozenset(pinned)


def _is_eligible_for_shuffle(room: Room, staircase_bound: frozenset[int]) -> bool:
    """Return True if this room's room_type is eligible to participate in the shuffle."""
    if room.room_type in _LEVEL_LOCKED_ROOM_TYPES:
        return False
    if room.room_num in staircase_bound:
        return False
    return True


def _shuffle_room_types_globally(world: GameWorld, rng: Rng) -> None:
    """Permute room_type values across all rooms in all levels.

    Skips:
      - Rooms with level-locked room_types (ENTRANCE/ZELDA/GANNON/TRIFORCE).
      - Rooms whose grid position is referenced by a staircase entry.

    Movable_block goes along with room_type, because mechanics like
    "push-block reveals staircase" are tied to specific room_types.
    """
    pinned_per_level = [
        _collect_staircase_bound_rooms(level) for level in world.levels
    ]

    eligible: list = []
    for level, pinned in zip(world.levels, pinned_per_level):
        for room in level.rooms:
            if _is_eligible_for_shuffle(room, pinned):
                eligible.append(room)

    if len(eligible) < 2:
        return

    payloads: list[tuple[RoomType, bool]] = [
        (room.room_type, room.movable_block) for room in eligible
    ]
    n = len(payloads)
    for i in range(n):
        j = i + int(rng.random() * (n - i))
        if j >= n:
            j = n - 1
        payloads[i], payloads[j] = payloads[j], payloads[i]

    for room, (new_room_type, new_movable_block) in zip(eligible, payloads):
        room.room_type = new_room_type
        room.movable_block = new_movable_block


def _shuffle_minor_items_globally(world: GameWorld, rng: Rng) -> None:
    """Permute minor items (NOTHING, KEY, BOMBS, FIVE_RUPEES) across all levels."""
    eligible: list = []
    for level in world.levels:
        for room in level.rooms:
            if room.item in _MINOR_ITEMS:
                eligible.append(room)

    if len(eligible) < 2:
        return

    items: list[Item] = [room.item for room in eligible]
    n = len(items)
    for i in range(n):
        j = i + int(rng.random() * (n - i))
        if j >= n:
            j = n - 1
        items[i], items[j] = items[j], items[i]

    for room, new_item in zip(eligible, items):
        room.item = new_item


def _snapshot_world(world: GameWorld) -> list[list[_RoomSnapshot]]:
    """Snapshot every room's mutable state across all levels."""
    return [[_RoomSnapshot(r) for r in level.rooms] for level in world.levels]


def _restore_world(world: GameWorld, snapshots: list[list[_RoomSnapshot]]) -> None:
    """Restore every room's state from per-level snapshots."""
    for level, level_snaps in zip(world.levels, snapshots):
        rooms_by_num = {r.room_num: r for r in level.rooms}
        for snap in level_snaps:
            snap.restore(rooms_by_num[snap.room_num])


def _has_kidnapped_gate_conflict(level: Level) -> bool:
    """Return True if this level has a push-block staircase room that is
    also a kidnapped-neighbor gate.

    Mirrors the conflict check raised by fix_pushblock_staircase_shutters
    (zora/dungeon/dungeon.py).  Only L9 can trigger this since
    THE_KIDNAPPED only lives there.
    """
    if level.level_num != 9:
        return False

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

    room_by_num: dict[int, Room] = {r.room_num: r for r in level.rooms}
    kidnapped_neighbor_shutters: set[tuple[int, Direction]] = set()
    for room in level.rooms:
        if room.enemy_spec.enemy != Enemy.THE_KIDNAPPED:
            continue
        rn = room.room_num
        for direction, offset in _DIR_OFFSETS:
            neighbor_num = rn + offset
            if neighbor_num not in room_by_num:
                continue
            facing = _OPPOSITE_DIR[direction]
            kidnapped_neighbor_shutters.add((neighbor_num, facing))
        break

    for room in level.rooms:
        if room.room_num not in stair_trigger_rooms:
            continue
        if room.room_type.has_open_staircase():
            continue
        if not (room.room_type.can_have_push_block() and room.movable_block):
            continue
        for exit_dir, _offset in _DIR_OFFSETS:
            if room.walls[exit_dir] == WallType.SOLID_WALL:
                continue
            if (room.room_num, exit_dir) in kidnapped_neighbor_shutters:
                return True

    return False


def scramble_dungeon_rooms(world: GameWorld, rng: Rng) -> bool:
    """Apply the additional shuffles that distinguish full shuffle from in-dungeon.

    Must be called AFTER shuffle_dungeon_rooms.  Assumes the per-level
    content shuffle (enemies, items, room_actions, old-man reassignment,
    boss-room tracking, walls) has already happened.

    Wraps the two-pass shuffle in a retry harness: if the room_type
    shuffle produces a placement that breaks per-level connectivity OR
    creates a kidnapped-neighbor gate conflict in L9, restore the
    pre-scramble state and retry with fresh RNG.

    Returns:
        True if a valid configuration was found within the retry budget.
        False if all retries failed — caller may want to retry the whole
        seed generation pipeline.
    """
    snapshots = _snapshot_world(world)

    for _attempt in range(_MAX_SCRAMBLE_RETRIES):
        _shuffle_room_types_globally(world, rng)

        for level in world.levels:
            _fix_constrained_room_doors(level, rng)

        all_connected = all(_is_level_connected(level) for level in world.levels)
        no_kidnapped_conflict = not any(
            _has_kidnapped_gate_conflict(level) for level in world.levels
        )

        if all_connected and no_kidnapped_conflict:
            _shuffle_minor_items_globally(world, rng)
            # Re-run room-content fixups: scramble can move (room_type,
            # movable_block) into a slot whose room_action no longer
            # matches (e.g. PUSHING_BLOCK_OPENS_SHUTTERS at a slot whose
            # new occupant has movable_block=False). Mirrors the
            # post-shuffle fixup pass; clear boss_cry first because
            # THE_BEAST may have moved.
            _clear_boss_cry_bits(world)
            for level in world.levels:
                _fix_special_rooms(level, world)
            return True

        _restore_world(world, snapshots)

    return False
