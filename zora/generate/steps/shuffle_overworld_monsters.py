"""Shuffle Overworld Monsters (B31; PS-OWM-01, -02)."""

from dataclasses import dataclass

from zora.generate.rng import IntRng
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.overworld import Overworld
from zora.model.rooms import COUNT_INDEX_SHIFT, MONSTER_LIST_BITS, EnemySpec

E = Enemy

# --- PS-OWM: the overworld monster re-deal ------------------------------------

EXCLUDED_MONSTER_BYTES = frozenset({0x00, 0x21, 0x2F})    # never candidates
MIXED_CODE_BIT = 0x40              # the model's enemy code for a table-D-flagged screen
FIRST_MIXED_LIST = 0x62            # $62 names the first of the thirty mixed lists
BRACELET_SCREENS = frozenset({9, 17, 27, 29, 35, 73, 121})
PEAHAT_BARRED_SCREENS = frozenset({63, 85})
LEEVER_BARRED_SCREENS = frozenset({7})
BLUE_MOBLIN_VALUE = 3
PEAHAT_VALUE = 26
LEEVER_VALUE = 16
LEEVER_LIST_CODES = frozenset({38, 39})   # flagged leever pairs: low six bits, no list lookup


@dataclass(frozen=True)
class MonsterPair:
    """One candidate screen's PS-OWM pair as the model holds it: the enemy
    spec (its code carries the table-D flag as $40) and the quantity."""
    spec: EnemySpec
    quantity: int

    @property
    def code(self) -> int:
        return int(self.spec.enemy.value)

    @property
    def is_flagged(self) -> bool:
        return self.code >= MIXED_CODE_BIT

    @property
    def low_six(self) -> int:
        return self.code & MONSTER_LIST_BITS


def _monster_byte(overworld: Overworld, screen: int) -> int:
    """The screen's whole table-C byte: count index and low six bits."""
    screen_info = overworld.screens[screen]
    return (overworld.qty_table.index(screen_info.enemy_quantity) << COUNT_INDEX_SHIFT) \
        | (screen_info.enemy_spec.enemy.value & MONSTER_LIST_BITS)


def mixed_list(gw: GameWorld, code: int) -> bytes:
    """A mixed-group list as the GameWorld holds it now (PRG0's before the
    group passes ship, PS-EGRP-04's after)."""
    enemies = gw.enemies
    offsets = sorted(enemies.mixed_group_offsets.values())
    start = enemies.mixed_group_offsets[code]
    later = [offset for offset in offsets if offset > start]
    end = later[0] if later else len(enemies.mixed_enemy_data)
    return bytes(enemies.mixed_enemy_data[start:end])


def _holds(gw: GameWorld, pair: MonsterPair, value: int) -> bool:
    """PS-OWM-02's test: unflagged with low six bits = value, or flagged and
    naming a mixed list (low six + $40 at least $62) that holds value."""
    if not pair.is_flagged:
        return pair.low_six == value
    code = pair.low_six | MIXED_CODE_BIT
    return code >= FIRST_MIXED_LIST and code in gw.enemies.mixed_group_offsets \
        and value in mixed_list(gw, code)


def _is_barred(gw: GameWorld, pair: MonsterPair, screen: int) -> bool:
    """PS-OWM-02: the three placements the walk refuses."""
    if screen in BRACELET_SCREENS and _holds(gw, pair, BLUE_MOBLIN_VALUE):
        return True
    if screen in PEAHAT_BARRED_SCREENS and _holds(gw, pair, PEAHAT_VALUE):
        return True
    if screen in LEEVER_BARRED_SCREENS:
        return (pair.low_six in LEEVER_LIST_CODES) if pair.is_flagged else pair.low_six == LEEVER_VALUE
    return False


def shuffle_overworld_monsters(gw: GameWorld, overworld: Overworld, rng: IntRng) -> int:
    """PS-OWM-01: re-deal the candidate screens' (monster byte, flag) pairs
    by a forward walk; an attempt barred by PS-OWM-02 for either pair keeps
    its draw spent and repeats the position. overworld starts as PRG0's
    (the staged copy). Returns the number of rejected attempts."""
    candidates = [screen_info.screen_num for screen_info in overworld.screens
                  if _monster_byte(overworld, screen_info.screen_num) not in EXCLUDED_MONSTER_BYTES]
    pairs = [MonsterPair(overworld.screens[screen].enemy_spec, overworld.screens[screen].enemy_quantity)
             for screen in candidates]
    rejected = 0
    count = len(pairs)
    for position in range(count):
        while True:
            other = position + rng.below(count - position)
            if not (_is_barred(gw, pairs[position], candidates[other])
                    or _is_barred(gw, pairs[other], candidates[position])):
                break
            rejected += 1
        pairs[position], pairs[other] = pairs[other], pairs[position]
    for screen, pair in zip(candidates, pairs, strict=True):
        overworld.screens[screen].enemy_spec = pair.spec
        overworld.screens[screen].enemy_quantity = pair.quantity
    return rejected
