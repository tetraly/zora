"""Hint Type (C03), post-shapes pass B2.5: hint assignment (docs/spec/post-shapes-b25.md @ a123227).

Runs after the merchants (PS-MERCH) and before the boss shuffle (PS-BOSS).
It draws nothing (PS-HINT-06): it picks which levels' persons are helpful,
rewrites each listed person's whole monster byte with a hint id from one of
two counters, and records each level's person init routine. The hint text
and the tables selecting it belong to a later pass and are not written.
"""
from dataclasses import dataclass, field

from zora.generate.shapes.world import blocks_of
from zora.model.enums import UnderworldPersonInit
from zora.model.levels import HINT_LEVELS, MERCHANT_LIST, Level
from zora.model.rooms import MONSTER_VALUE_BIT, EnemyInfo, Room

BOMB_UPGRADE_CODE = 0x0F
INITIAL_HELPFUL = frozenset({3, 4, 6, 8})        # PS-HINT-03, no draw
BALANCED_UNHELPFUL_ROOMS = (5, 6)                # PS-HINT-04's target sum
FIRST_HINT_ID = 0x0B
# PS-HINT-05: the values each counter jumps over, after its increment.
HELPFUL_SKIPS = {0x11: 0x12}
UNHELPFUL_SKIPS = {0x0F: 0x10, 0x11: 0x12}


@dataclass
class HintAssignmentResult:
    """What the pass decided outside the room blocks."""
    helpful: set[int] = field(default_factory=set)
    old_man_levels: list[int] = field(default_factory=list)   # kept $0F rooms' levels
    listed: int = 0
    # (level, hint id) of each listed room as PS-HINT-05 wrote it, in list order; the
    # hint-room selectors (HT-SEL-01) walk it.
    hint_ids: list[tuple[int, int]] = field(default_factory=list)

    def person_inits(self) -> tuple[UnderworldPersonInit, ...]:
        """PS-HINT-06: $69 (B) for a helpful level, $23 (A) otherwise."""
        return tuple(UnderworldPersonInit.B if level in self.helpful else UnderworldPersonInit.A
                     for level in HINT_LEVELS)


def _person_rooms(levels: list[Level]) -> list[tuple[Room, int]]:
    """Levels 1-8's persons with their level numbers, in scan order: the
    levels 1-6 block's rooms $00-$7F, then the levels 7-9 block's."""
    persons: list[tuple[Room, int]] = []
    for block in blocks_of(levels):
        in_block = [(room, level.level_num) for level in levels
                    if level.block is block and level.level_num in HINT_LEVELS
                    for room in level.rooms if room.is_person]
        persons.extend(sorted(in_block, key=lambda entry: entry[0].room_num))
    return persons


def collect_hint_rooms(levels: list[Level], bomb_levels: set[int],
                       state: HintAssignmentResult) -> tuple[list[tuple[Room, int]], dict[int, int]]:
    """PS-HINT-01/02: scan both quest-1 blocks, rooms $00-$7F in order.
    Returns the hint list (room, level) and each level's room count ($11
    merchants counted, kept bomb-upgrade persons not)."""
    hint_list: list[tuple[Room, int]] = []
    counts = dict.fromkeys(HINT_LEVELS, 0)
    for room, level in _person_rooms(levels):
        if room.monster_list == BOMB_UPGRADE_CODE and level in bomb_levels:
            state.old_man_levels.append(level)       # kept; not listed, not counted
            continue
        counts[level] += 1
        if room.monster_list != MERCHANT_LIST:
            hint_list.append((room, level))
    return hint_list, counts


def _half_start(level: int) -> int:
    return 1 if level <= 4 else 5


def move_helpful_markers(state: HintAssignmentResult) -> None:
    """PS-HINT-03: each old-man level ends unhelpful; a helpful one first
    moves its marker to the first level from its half's start up to 8 that
    is not helpful, not itself and not the previous entry's level."""
    previous: int | None = None
    for level in state.old_man_levels:
        if level in state.helpful:
            target = next((other for other in range(_half_start(level), HINT_LEVELS.stop)
                           if other not in state.helpful and other not in (level, previous)),
                          None)
            if target is not None:
                state.helpful.add(target)
        state.helpful.discard(level)
        previous = level


def balance_levels(state: HintAssignmentResult, counts: dict[int, int]) -> None:
    """PS-HINT-04: flip levels until the unhelpful levels hold 5 or 6
    counted rooms. A flip with no candidate ends the loop (MAY; never
    reached)."""
    while True:
        unhelpful = [level for level in HINT_LEVELS if level not in state.helpful]
        total = sum(counts[level] for level in unhelpful)
        if total in BALANCED_UNHELPFUL_ROOMS:
            return
        if total > max(BALANCED_UNHELPFUL_ROOMS):
            flip = next((level for level in unhelpful if level not in state.old_man_levels), None)
            if flip is None:
                return
            state.helpful.add(flip)
        else:
            if 1 in state.helpful:
                flip = 1
            else:
                flip = next((level for level in range(2, HINT_LEVELS.stop)
                             if level in state.helpful), None)
                if flip is None:
                    return
            state.helpful.discard(flip)


def write_hint_ids(hint_list: list[tuple[Room, int]], state: HintAssignmentResult) -> None:
    """PS-HINT-05: each listed room's whole monster byte becomes its level's
    counter (count bits cleared, the flag kept); counters are shared across
    levels and blocks and skip their reserved values after incrementing."""
    counters = {True: FIRST_HINT_ID, False: FIRST_HINT_ID}
    skips = {True: HELPFUL_SKIPS, False: UNHELPFUL_SKIPS}
    for room, level in hint_list:
        helpful = level in state.helpful
        room.enemy_info = EnemyInfo.from_monster_value(counters[helpful] | MONSTER_VALUE_BIT)
        state.hint_ids.append((level, counters[helpful]))
        counters[helpful] += 1
        counters[helpful] = skips[helpful].get(counters[helpful], counters[helpful])
    state.listed = len(hint_list)


def assign_hints_for_hint_type(levels: list[Level], bomb_levels: tuple[int, int] | None) -> HintAssignmentResult:
    """PS-HINT-01..06 (B2.5), on the pass's staged levels. bomb_levels:
    PS-BOMB-03's recorded levels (P24: the hint pass reads them)."""
    state = HintAssignmentResult(helpful=set(INITIAL_HELPFUL))
    hint_list, counts = collect_hint_rooms(levels, set(bomb_levels or ()), state)
    move_helpful_markers(state)
    balance_levels(state, counts)
    write_hint_ids(hint_list, state)
    return state
