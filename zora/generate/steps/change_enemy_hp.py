"""Change Enemy HP: "Most" Enemy HP (C09) and Boss HP (C10) at every value, and Set Ganon HP
to 0 (B41), post-shapes batch B8's hit points (post-shapes-b8.md PS-HP). The batch's overworld monster
re-deal (PS-OWM) is shuffle_overworld_monsters; level 9's room records
(PS-L9REC) are applied at write-back (writeback.level9_records).

Order in the flow: after B2's monster re-deal, PS-OWM, then the enemy and
the boss hit-point passes and B41, then the group passes (B4), which read
Zol's value as the enemy pass left it (PS-EGRP-01).
PS-OWM edits the staged overworld model the flow ships; the hit points are
staged in an EnemyHpResult and written into the GameWorld when the pass ships.
"""
from dataclasses import dataclass

from ...flags.fields import HitPointChange
from ...model.enums import Enemy
from ...model.game_world import GameWorld
from ...model.sprites import EnemyData
from ..rng import IntRng, discard

E = Enemy


# --- PS-HP: enemy and boss hit points -----------------------------------------

HP_SEED_DRAWS = 3                  # one number as the pass's (unused) seed, two discarded
# The spec does not state the number's width; a change (r mod (m + 1)) and a sign
# (bit 5) taken from a uniform 31-bit number are as near uniform and
# independent as the spec's rule needs.
HP_NUMBER_RANGE = 1 << 31
HP_UP_BIT = 0x20
NIBBLE_MAX = 0x0F
# ObjectTypeToHpPairs holds two object types to a byte, the even type in
# the high nibble (ExtractHitPointValue); the data layer keys EnemyData.hp
# by object type.
ENEMY_HP_TYPES = range(0x00, 0x32)     # PS-HP-01: the first 25 bytes, from 0x1FB5E
BOSS_HP_TYPES = range(0x32, 0x4A)      # PS-HP-02: the next 12 bytes, from 0x1FB77
ROPE_BASES = (1, 4)                # InitRope's quest-1 and quest-2 operands / $10
# PS-HP-02's mirrored operands: object type -> the EnemyData field it sets
BOSS_MIRRORS = {E.GLEEOK_2: "gleeok_neck_hp", E.THE_BEAST: "ganon_hp",
                E.MOLDORM: "moldorm_segment_hp", E.RED_LANMOLA: "lamnola_segment_hp"}
GLEEOK_HEAD_AFTER = E.GLEEOK_2     # the head draw follows type $43's write, before $42's
GLEEOK_HEAD_MIDDLE = 6             # PS-HP-02: the head operand is uniform over 6 - m .. 6 + m
GANON = E.THE_BEAST                # PS-HP-05 leaves him alone; PS-HP-06 zeroes him
GANON_RETURN_HP = 0x41             # PS-HP-06: the hit points he returns to after each brown spell


def visiting_order(types: range) -> list[Enemy]:
    """PS-HP-01/02: each byte's odd type, then the even type that shares it
    (1, 0, 3, 2, ...); the ranges start on an even type."""
    return [Enemy(object_type ^ 1) for object_type in types]


@dataclass
class EnemyHpResult:
    """The staged hit points: the 74 walked values (by object type), the
    rope's two operands and the five boss operands, as nibble values, and
    Ganon's return byte under B41. A pass turned off (C09 or C10 at 0,
    FL-OFF-06) leaves its values as they were."""
    hp: dict[Enemy, int]
    rope: tuple[int, int] | None
    mirrors: dict[str, int]
    gleeok_head: int
    ganon_return: int | None = None

    @classmethod
    def unchanged(cls, enemies: EnemyData) -> "EnemyHpResult":
        """The base ROM's values, before either pass."""
        return cls(dict(enemies.hp), enemies.rope_hp, {}, enemies.gleeok_head_hp)


def _step(value: int, most: int, rng: IntRng) -> int:
    """One value: change |number mod (most + 1)|, up when bit 5 is set, clamped 0..15."""
    number = rng.below(HP_NUMBER_RANGE)
    change = number % (most + 1)
    moved = value + change if number & HP_UP_BIT else value - change
    return max(0, min(NIBBLE_MAX, moved))


def _most(change: HitPointChange) -> int:
    most = change.max_shift
    assert most, f"{change.name} is not a walk"
    return most


def change_most_enemy_hp(state: EnemyHpResult, change: HitPointChange, rng: IntRng) -> None:
    """"Most" Enemy HP (C09): a walk of up to 2 or 4 (PS-HP-01) over object types $00-$31 in
    visiting order, then the rope's two operands; or all zero (PS-HP-04), with no draw."""
    discard(rng, HP_SEED_DRAWS, HP_NUMBER_RANGE)
    if change is HitPointChange.ALL_ZERO:
        state.hp.update(dict.fromkeys(visiting_order(ENEMY_HP_TYPES), 0))
        state.rope = (0, 0)
        return
    most = _most(change)
    for enemy in visiting_order(ENEMY_HP_TYPES):
        state.hp[enemy] = _step(state.hp[enemy], most, rng)
    state.rope = (_step(ROPE_BASES[0], most, rng), _step(ROPE_BASES[1], most, rng))


def change_boss_hp(state: EnemyHpResult, change: HitPointChange, rng: IntRng) -> None:
    """Boss HP (C10): a walk of up to 2 or 4 (PS-HP-02) over object types $32-$49 in visiting
    order, each mirrored type's operand written with it and the Gleeok head's draw right after
    type $43's write; or all zero but Ganon (PS-HP-05), the operands too, with no draw."""
    discard(rng, HP_SEED_DRAWS, HP_NUMBER_RANGE)
    if change is HitPointChange.ALL_ZERO:
        for enemy in visiting_order(BOSS_HP_TYPES):
            if enemy != GANON:
                state.hp[enemy] = 0
                if enemy in BOSS_MIRRORS:
                    state.mirrors[BOSS_MIRRORS[enemy]] = 0
        state.gleeok_head = 0
        return
    most = _most(change)
    for enemy in visiting_order(BOSS_HP_TYPES):
        state.hp[enemy] = _step(state.hp[enemy], most, rng)
        if enemy in BOSS_MIRRORS:
            state.mirrors[BOSS_MIRRORS[enemy]] = state.hp[enemy]
        if enemy == GLEEOK_HEAD_AFTER:
            state.gleeok_head = rng.below(HP_NUMBER_RANGE) % (2 * most + 1) + GLEEOK_HEAD_MIDDLE - most


def zero_ganon_hp(state: EnemyHpResult) -> None:
    """Set Ganon HP to 0 (B41; PS-HP-06), after the boss pass whatever C10 holds: his value 0,
    and the hit points he returns to $41. No draw."""
    state.hp[GANON] = 0
    state.mirrors[BOSS_MIRRORS[GANON]] = 0
    state.ganon_return = GANON_RETURN_HP


def apply_enemy_hp(gw: GameWorld, state: EnemyHpResult) -> None:
    """Write the staged hit points into the GameWorld (ship.py, when the attempt ships)."""
    enemies = gw.enemies
    enemies.hp = dict(state.hp)
    enemies.rope_hp = state.rope
    for name, value in state.mirrors.items():
        setattr(enemies, name, value)
    enemies.gleeok_head_hp = state.gleeok_head
    enemies.ganon_return_hp = state.ganon_return
