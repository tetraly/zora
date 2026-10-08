"""Shuffle Dungeon Text's figures (post-shapes-b25.md): the hint assignment."""

from collections.abc import Callable

from zora.measure.checkpoints.summaries import BOMB_UPGRADE_LIST
from zora.model.enums import UnderworldPersonInit
from zora.model.game_world import GameWorld
from zora.model.levels import MERCHANT_LIST
from zora.model.rooms import Room

# --- B2.5: hint assignment ----------------------------------------------------

HINT_CODES = tuple(range(0x0B, 0x13))            # person lists $0B-$12
HINT_CENSUS_SPEC = {                             # the checkpoint table's columns, L1-L9
    0x0B: "0.201 0.257 0.184 0.180 0.637 0.521 0.014 0.006 1.000",
    0x0C: "0.243 0.215 0.221 0.199 0.563 0.375 0.137 0.047 0.781",
    0x0D: "0.146 0.153 0.152 0.172 0.464 0.302 0.446 0.157 0.817",
    0x0E: "0.092 0.063 0.104 0.091 0.272 0.119 0.710 0.442 0.792",
    0x0F: "0.133 0.119 0.146 0.163 0.549 0.309 0.587 0.733 0.000",
    0x10: "0.010 0.015 0.012 0.012 0.042 0.029 0.498 0.254 0.000",
    0x11: "0.109 0.116 0.120 0.123 0.314 0.226 0.320 0.249 0.412",
    0x12: "0.000 0.000 0.001 0.004 0.003 0.001 0.105 0.011 0.000",
}
HELPFUL_STREAM = (0x0B, 0x0C, 0x0D, 0x0E, 0x0F, 0x10, 0x12)
UNHELPFUL_STREAM = (0x0B, 0x0C, 0x0D, 0x0E, 0x10, 0x12)
HELPFUL_LEVEL_COUNTS = (4, 3, 2)
UNHELPFUL_ROOM_COUNTS = (5, 6)
VANILLA_HELPFUL_LEVELS = frozenset({3, 4, 6, 8})


def _flagged_list(code: int) -> Callable[[Room], bool]:
    return lambda room: room.has_monster_bit and room.monster_list == code


def _helpful_levels(gw: GameWorld) -> set[int]:
    return {level for level, init in enumerate(gw.person_inits, start=1)
            if init == UnderworldPersonInit.B}


def _hint_rooms(gw: GameWorld) -> list[tuple[int, Room]]:
    """Levels 1-8's flag-set rooms with lists $0B-$12, as (level, room)."""
    return [(level.level_num, room) for level in gw.levels[:8] for room in level.rooms
            if room.has_monster_bit and room.monster_list in HINT_CODES]


def helpful_level_count(gw: GameWorld) -> int:
    return len(_helpful_levels(gw))


def kept_bomb_upgrade_rooms(gw: GameWorld) -> dict[str, bool]:
    """PS-HINT-02: exactly two flag-set $0F rooms in unhelpful levels; they
    lie in vanilla-helpful levels 3/4/6/8; both in one level."""
    helpful = _helpful_levels(gw)
    kept = [level for level, room in _hint_rooms(gw)
            if room.monster_list == BOMB_UPGRADE_LIST and level not in helpful]
    return {"exactly two": len(kept) == 2,
            "in 3/4/6/8": any(level in VANILLA_HELPFUL_LEVELS for level in kept),
            "same level": len(kept) == 2 and kept[0] == kept[1]}


def unhelpful_room_count(gw: GameWorld) -> int:
    """PS-HINT-04: counted rooms of unhelpful levels ($11 in, kept $0F out)."""
    helpful = _helpful_levels(gw)
    return sum(level not in helpful and room.monster_list != BOMB_UPGRADE_LIST
               for level, room in _hint_rooms(gw))


def hint_streams_hold(gw: GameWorld) -> bool:
    """Each stream's rooms (merchants and kept $0F rooms aside) are the
    first n values of that counter's sequence."""
    helpful = _helpful_levels(gw)
    streams: dict[bool, list[int]] = {True: [], False: []}
    for level, room in _hint_rooms(gw):
        code = room.monster_list
        is_helpful = level in helpful
        if code == MERCHANT_LIST or (code == BOMB_UPGRADE_LIST and not is_helpful):
            continue
        streams[is_helpful].append(code)
    return all(sorted(streams[flag]) == list(sequence[:len(streams[flag])])
               and len(streams[flag]) <= len(sequence)
               for flag, sequence in ((True, HELPFUL_STREAM), (False, UNHELPFUL_STREAM)))
