"""The monster passes' figures (post-shapes-b2.md): bank tiers and the census."""

import statistics
from collections.abc import Callable

from zora.model.enums import BossSpriteSet, EnemySpriteSet, Item, RoomAction
from zora.model.game_world import GameWorld
from zora.model.levels import GANON_LIST
from zora.model.rooms import LAYOUT_ID_MASK, Room
from zora_measure.checkpoints.shapes_and_gate import _ganon_room, _zelda_room, layout_byte
from zora_measure.checkpoints.summaries import Summary

# --- B2 (post-shapes-b2.md's checkpoint) -------------------------------------------

BOSS_BANK_TIER = {BossSpriteSet.A: 0, BossSpriteSet.B: 1, BossSpriteSet.C: 2}
ENEMY_BANK_TIER = {EnemySpriteSet.A: 0, EnemySpriteSet.B: 1, EnemySpriteSet.C: 2}
TIERS = (0, 1, 2)


def boss_bank_tiers(gw: GameWorld) -> list[int]:
    """Levels 1-8's boss sprite-bank tiers ($9F / $A3 / $A7 high bytes)."""
    return [BOSS_BANK_TIER[level.boss_sprite_set] for level in gw.levels[:8]]


def enemy_bank_tiers(gw: GameWorld) -> list[int]:
    """Levels 1-9's enemy sprite-bank tiers (pairs $BB/$9D, $7B/$98, $9B/$9A)."""
    return [ENEMY_BANK_TIER[level.enemy_sprite_set] for level in gw.levels]


def tiers_by_level(values: list[list[int]]) -> str:
    """Per level, how many ROMs drew tier 0 / 1 / 2."""
    return " ".join(f"L{i + 1} " + "/".join(str(sum(v[i] == t for v in values)) for t in TIERS)
                    for i in range(len(values[0])))


TIER_SUMMARY = Summary(tiers_by_level, lambda tiers: {
    f"L{i + 1} tier {t}": float(tier == t) for i, tier in enumerate(tiers) for t in TIERS
})

# PS-MONLV-01's per-seed tier counts (tier 0, tier 1, tier 2), in the spec's order
TIER_MIXES = ((3, 2, 4), (3, 3, 3), (3, 4, 2), (4, 2, 3), (4, 3, 2), (5, 2, 2))


def enemy_tier_mix(gw: GameWorld) -> tuple[int, ...]:
    tiers = enemy_bank_tiers(gw)
    return tuple(tiers.count(t) for t in TIERS)


def ganon_room_item_and_trigger(gw: GameWorld) -> bool:
    """Ganon's room: item byte $8E (dark, Triforce of Power) and trigger
    byte $03."""
    ganon = _ganon_room(gw)
    return (ganon is not None and ganon.item == Item.TRIFORCE_OF_POWER and ganon.is_dark
            and ganon.room_action == RoomAction.LAST_BOSS
            and ganon.item_position == 0)


# The barred layouts (layout byte's low six bits), as B2 and the shape stage
# state them; the families by monster value.
LANMOLA_BARRED = frozenset({1, 4, 9, 11, 12, 15, 17, 18, 22, 23, 27, 28, 32, 39, 41, 51})
RUPEE_BARRED = frozenset({9, 11, 12, 14, 15, 16, 18, 19, 20, 22, 23, 24, 25, 26, 30, 32})
TRAP_BARRED = frozenset({7, 8, 9, 12, 15, 18, 28, 41})
GLEEOK_BARRED = frozenset({9, 11, 14, 15, 18, 20, 35, 36})
FOUR_HEAD_BARRED = frozenset({11, 18, 19, 20, 21, 22, 23, 24, 25})
GOHMA_BARRED = frozenset({11, 14, 15, 18})
DODONGO_BARRED = frozenset({9, 11, 14, 15, 18})
GANON_BARRED = frozenset({1, 3, *range(5, 19), *range(26, 33), 34, 35, 36, 39, 41})
ZELDA_BARRED = frozenset({9, 15, 16, 30, 27, 28})
LANMOLA_LISTS = (0x3A, 0x3B)
RUPEE_LIST = 0x35
TRAP_LISTS = (0x09, 0x0A, 0x2D, 0x2E, 0x36, 0x37)
GLEEOK_LISTS = (0x02, 0x03, 0x04, 0x05)          # one to four heads, with the monster bit
FOUR_HEAD_LIST = 0x05
GOHMA_LISTS, DODONGO_LISTS = (0x33, 0x34), (0x31, 0x32)


def _barred(rooms: list[Room], family: Callable[[Room], bool],
            bars: Callable[[Room], bool]) -> tuple[int, int]:
    members = [room for room in rooms if family(room)]
    return sum(bars(room) for room in members), len(members)


def _layout_in(barred: frozenset[int]) -> Callable[[Room], bool]:
    return lambda room: room.layout_code & LAYOUT_ID_MASK in barred


def _plain(lists: tuple[int, ...], count_zero: bool = False) -> Callable[[Room], bool]:
    return lambda room: (not room.has_monster_bit and room.monster_list in lists
                         and (room.count_index == 0 or not count_zero))


def _flagged(lists: tuple[int, ...]) -> Callable[[Room], bool]:
    return lambda room: room.has_monster_bit and room.monster_list in lists


def _level_rooms(gw: GameWorld) -> list[Room]:
    return [room for level in gw.levels for room in level.rooms]


def monster_bar_violations(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """B2 checkpoint: rooms of each family on its barred layouts, as
    (barred, rooms). Lanmolas and $35 are plain (monster bit clear); flagged
    $3A/$3B are mixed groups outside every Lanmola rule."""
    rooms = _level_rooms(gw)
    return {
        "lanmola": _barred(rooms, _plain(LANMOLA_LISTS), _layout_in(LANMOLA_BARRED)),
        "lanmola count 0": _barred(rooms, _plain(LANMOLA_LISTS, count_zero=True),
                                   _layout_in(LANMOLA_BARRED)),
        "$35": _barred(rooms, _plain((RUPEE_LIST,)), _layout_in(RUPEE_BARRED)),
        "traps": _barred(rooms, _flagged(TRAP_LISTS), _layout_in(TRAP_BARRED)),
        "gleeok": _barred(rooms, _flagged(GLEEOK_LISTS), _layout_in(GLEEOK_BARRED)),
        "ganon": _barred(rooms, _plain((GANON_LIST,)), _layout_in(GANON_BARRED)),
        "flagged $3A/$3B": _barred(rooms, _flagged(LANMOLA_LISTS), _layout_in(LANMOLA_BARRED)),
    }


def boss_bar_violations(gw: GameWorld) -> dict[str, tuple[int, int]]:
    """PS-BOSS-04's check: Gohma, Gleeok with the push bit, four-headed
    Gleeok on its extra layouts, Dodongo; as (barred, rooms)."""
    rooms = _level_rooms(gw)
    return {
        "gohma": _barred(rooms, _plain(GOHMA_LISTS), _layout_in(GOHMA_BARRED)),
        "gleeok push": _barred(rooms, _flagged(GLEEOK_LISTS), lambda room: room.movable_block),
        "four heads": _barred(rooms, _flagged((FOUR_HEAD_LIST,)), _layout_in(FOUR_HEAD_BARRED)),
        "dodongo": _barred(rooms, _plain(DODONGO_LISTS), _layout_in(DODONGO_BARRED)),
    }


def zelda_on_barred_layout(gw: GameWorld) -> bool:
    zelda = _zelda_room(gw)
    return zelda is not None and (zelda.layout_code & LAYOUT_ID_MASK in ZELDA_BARRED
                                  or zelda.movable_block)


# B2's monster-bit census: cells per level by exact layout byte, person
# rooms (low six bits 11-18 with the monster bit) and flagged rooms.
CENSUS_LAYOUT_BYTES = (0xA6, 0x9B, 0x92, 0xA7, 0x26, 0x1B, 0x12, 0x27)


def census_by_level(count: Callable[[Room], bool]) -> Callable[[GameWorld], list[int]]:
    return lambda gw: [sum(count(room) for room in level.rooms) for level in gw.levels]


def _layout_byte_is(code: int) -> Callable[[Room], bool]:
    return lambda room: layout_byte(room) == code


def per_level_means(values: list[list[int]]) -> str:
    return " ".join(f"{statistics.mean(v[i] for v in values):.3f}" for i in range(len(values[0])))


PER_LEVEL_SUMMARY = Summary(per_level_means, lambda counts: {
    f"L{i + 1}": float(n) for i, n in enumerate(counts)
})

# The spec's census table, one column per checkpoint, levels 1-9.
CENSUS_SPEC = {
    0xA6: "0.988 1.077 1.134 1.322 3.091 2.253 3.275 2.457 4.281",
    0x9B: "0.134 0.050 0.102 0.098 0.231 0.180 0.177 0.215 0.670",
    0x92: "0.002 0.007 0.008 0.054 0.097 0.022 0.018 0.024 0.041",
    0xA7: "0.009 0.020 0.012 0.021 0.017 0.046 0.030 0.045 0.074",
    0x26: "0.229 0.436 0.606 0.946 0.750 1.193 1.363 1.499 1.798",
    0x1B: "0.297 0.109 0.252 0.265 0.570 0.459 0.467 0.597 1.678",
    0x12: "0.008 0.025 0.021 0.186 0.319 0.096 0.071 0.144 0.173",
    0x27: "0.012 0.042 0.045 0.059 0.030 0.112 0.125 0.143 0.158",
}
CENSUS_PERSONS_SPEC = "0.934 0.938 0.940 0.944 2.844 1.882 2.817 1.899 3.802"
CENSUS_FLAGGED_SPEC = "4.119 4.528 4.935 5.368 7.595 9.109 9.326 10.327 14.399"
