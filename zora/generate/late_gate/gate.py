"""The late room-deal acceptance gate (docs/spec/late-gate.md @ 641f51a).

Levels 1 to 9 are processed one at a time, and all levels share one budget of
1,000 attempts per pass. Every attempt counts, accepted ones included. When the
budget runs out the pass fails and the whole generation restarts; nothing
partial ships. One attempt (VA-REJ-03):
  1. Re-deal the level's room contents: the exact draw procedure, the
     swap-safety rules and the 1,000-draw limit.
  2. Staircase exits: a distinct-room remap before the deal; after it, the
     exits follow their rooms.
  3. Re-deal internal door units. Pinned pairs take wall/wall. Record the
     walled pairs.
  4. Wipe the boss-sound bits.
  5-6. The special-room fixes.
  7. The placement check (VA-REJ-01.1).
  8. Level 9: the rewrite around Zelda's room.
  9. The connectivity walk and repair (VA-REJ-01.2), then level 9's extras
     (VA-REJ-01.3).
A rejected attempt restores the set's room block. After all nine levels are
accepted, the tail runs. The gate works on the pass's staged levels and their
blocks (ship.build_sets); the walks live in walk.py and the byte views on Room
(zora/model/rooms.py). Spec ambiguities are marked with their QUESTIONS.md numbers or
changelog amendments (Axx).
"""
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from zora.generate.errors import GenerationFailure
from zora.generate.late_gate.blocks import GateBlock, _rooms, _set_trigger, gate_blocks
from zora.generate.late_gate.deal import _deal_level
from zora.generate.late_gate.fixes import (
    _first_special_room_fix,
    _level9_extras,
    _placement_check,
    _reforce_level9_person_sides,
    _second_special_room_fix,
    _tail,
    _wipe_boss_sound,
    _zelda_rewrite,
    zelda_cell,
)
from zora.generate.rng import Rng
from zora.generate.shapes.numbering import spatial_pieces_of
from zora.generate.shapes.world import D_BOMB, D_OPEN, D_SHUTTER, set_side
from zora.model.enums import RoomAction, Side
from zora.model.levels import GANON_LIST, LEVEL_9, Level
from zora.model.rooms import DoorPair

if TYPE_CHECKING:
    from zora.generate.late_gate.walk import WalkResult


GATE_BUDGET = 1000


@dataclass
class GateStats:
    rejections: int = 0        # attempts that failed the checks
    accepted_levels: int = 0
    per_level: dict[int, int] = field(default_factory=dict)
    kinds: dict[str, int] = field(default_factory=dict)
    exhaustion: list[tuple[int, tuple[int, ...]]] = field(default_factory=list)
    # exhaustion entries: (blocking level, piece sizes at exhaustion)
    # Survey-only (filled when SURVEY is True): one record per attempt,
    # (level, kind, plain_walk_ok, repair_invoked, pairs_opened, accepted);
    # kind = "accept" or the rejection kind; plain_walk_ok is the verdict
    # BEFORE the repair (None when the walk was not reached).
    survey: list[tuple[int, str, bool | None, bool, int, bool]] = field(
        default_factory=list
    )


# Survey switches — instrumentation for measurement runs only. SURVEY records
# per-attempt facts without drawing randomness or touching state, so it never
# changes output. REPAIR_ENABLED=False is a counterfactual used only by survey
# scripts (it DOES change behaviour); production keeps it True.
SURVEY = False
REPAIR_ENABLED = True


def _connectivity_repair(level: Level, recorded: list[DoorPair], rng: Rng,
                         walk: "WalkResult") -> "tuple[int, WalkResult]":
    """VA-REJ-01.2 repair: take the recorded pairs in recording order and
    open the first one with exactly one of its two rooms reached that does
    not touch Zelda's room ("reached" = the forward walk's rooms, or the
    reverse walk's when the forward passed and the reverse failed); re-walk;
    repeat until connected or none qualifies. Both sides set alike: E-W
    always open (A23), N-S bombable one time in three else open; a side on
    Ganon's room becomes a shutter; rooms with trigger 0/2 get trigger 1.
    A pair the repair opened is marked used for the attempt (A37); step 6's
    and placement's openings never change the recorded list."""
    from zora.generate.late_gate.walk import connectivity_walk
    zelda = zelda_cell(_rooms(level))
    opened = 0
    remaining = list(recorded)
    while not walk.passed and remaining:
        reached = walk.repair_reached()
        pick = None
        for index, (first, second, _axis) in enumerate(remaining):
            if (first in reached) != (second in reached) and zelda not in (first, second):
                pick = index
                break
        if pick is None:
            break
        first, second, axis = remaining.pop(pick)
        if axis == Side.EAST:
            wall_type = D_OPEN
        else:
            wall_type = D_BOMB if rng.chance(1, 3) else D_OPEN
        for room_number, side in ((first, axis), (second, axis.opposite)):
            room = level.block.room(room_number)
            set_side(room, side, D_SHUTTER if room.enemy == GANON_LIST else wall_type)
            if room.room_action in (RoomAction.NONE, RoomAction.RINGLEADER):
                _set_trigger(room, RoomAction.ALL_DEAD)
        opened += 1
        walk = connectivity_walk(level)
    return opened, walk


_Snap = tuple[list[tuple[dict[str, object], dict[str, object]]], list[dict[str, object]]]


def _snapshot(gate_block: GateBlock) -> _Snap:
    """The block as an attempt can change it (a rejected attempt restores
    the 0x300-byte room block, A27): every owned room, and every staircase
    with its exits. The cells no level owns are not written during an
    attempt, only by the tail.

    Fast-pathed (it runs once per attempt): each cell is copied through its
    instance dict. A room's four groups are immutable, so the copy shares
    them; its walls are a mutable WallSet, copied the same way."""
    return ([(room.__dict__.copy(), room.walls.__dict__.copy()) for room in gate_block.owned_rooms],
            [stair.__dict__.copy() for stair in gate_block.staircases])


def _restore(gate_block: GateBlock, snapshot: _Snap) -> None:
    rooms, stairs = snapshot
    for room, (fields, walls) in zip(gate_block.owned_rooms, rooms, strict=True):
        room.__dict__.update(fields)           # the original WallSet object comes back with them
        room.walls.__dict__.update(walls)
    for stair, fields in zip(gate_block.staircases, stairs, strict=True):
        stair.__dict__.update(fields)


def _connectivity_verdict(level: Level) -> str | None:
    """None when the level walks through; else a kind label."""
    from zora.generate.late_gate.walk import gate_walk
    return gate_walk(level)


def late_gate(levels: list[Level], rng: Rng, stats: GateStats | None = None) -> GateStats:
    """Attempt loop over levels 1..9 sharing one 1,000-attempt budget, on
    the pass's staged levels.

    EVERY attempt counts against the budget, accepted ones included
    (VA-REJ-04). Accepted levels persist; a rejected attempt is rolled
    back and the same level retried. Running out raises (the pass fails,
    whole generation restarts)."""
    stats = stats or GateStats()
    blocks = gate_blocks(levels)
    used = 0
    for gate_block in blocks:
        for level in gate_block.levels:
            if not level.room_nums:
                continue
            while True:
                if used >= GATE_BUDGET:
                    piece_sizes = sorted((len(piece) for piece in spatial_pieces_of(set(level.room_nums))),
                                         reverse=True)
                    stats.exhaustion.append((level.level_num, tuple(piece_sizes)))
                    raise GenerationFailure("late gate budget exhausted")
                used += 1
                snapshot = _snapshot(gate_block)
                kind, plain_walk_passed, repair_ran, pairs_opened = _attempt(gate_block, level, rng)
                if SURVEY:
                    stats.survey.append(
                        (level.level_num, kind, plain_walk_passed, repair_ran, pairs_opened,
                         kind == "accept")
                    )
                if kind == "accept":
                    stats.accepted_levels += 1
                    break
                stats.rejections += 1
                stats.per_level[level.level_num] = stats.per_level.get(level.level_num, 0) + 1
                stats.kinds[kind] = stats.kinds.get(kind, 0) + 1
                _restore(gate_block, snapshot)
    for gate_block in blocks:
        _tail(gate_block)
    return stats


def _attempt(gate_block: GateBlock, level: Level,
             rng: Rng) -> tuple[str, bool | None, bool, int]:
    """One attempt (VA-REJ-03 steps 1-9). Returns (kind, plain_walk_ok,
    repair_invoked, pairs_opened); kind is "accept" or the rejection
    kind."""
    recorded = _deal_level(level, rng)
    if recorded is None:
        return "swap", None, False, 0
    _wipe_boss_sound(level)
    _first_special_room_fix(gate_block, level)
    _second_special_room_fix(gate_block, level, recorded)
    if not _placement_check(level, recorded):
        plain_walk_passed = (_connectivity_verdict(level) is None) if SURVEY else None
        return "placement", plain_walk_passed, False, 0
    if level.level_num == LEVEL_9 and not _zelda_rewrite(gate_block, level):
        return "l9door", None, False, 0
    # step 9: connectivity (walk, then repair), then level 9's extras
    from zora.generate.late_gate.walk import connectivity_walk
    walk = connectivity_walk(level)
    plain_walk_passed = walk.passed
    repair_ran, pairs_opened = False, 0
    if not walk.passed and recorded and REPAIR_ENABLED:
        repair_ran = True
        pairs_opened, walk = _connectivity_repair(level, recorded, rng, walk)
    if not walk.passed:
        return "connectivity", plain_walk_passed, repair_ran, pairs_opened
    if level.level_num == LEVEL_9:
        _reforce_level9_person_sides(level)
    if level.level_num == LEVEL_9 and not _level9_extras(gate_block, level):
        return "l9extra", plain_walk_passed, repair_ran, pairs_opened
    return "accept", plain_walk_passed, repair_ran, pairs_opened
