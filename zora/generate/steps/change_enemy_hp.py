"""Change Enemy HP: "Most" Enemy HP (C09) and Boss HP (C10), post-shapes batch
B8's hit points (post-shapes-b8.md PS-HP). The batch's overworld monster
re-deal (PS-OWM) is shuffle_overworld_monsters; level 9's room records
(PS-L9REC) are applied at write-back (writeback.level9_records).

Order in the flow: after B2's monster re-deal, PS-OWM, then the enemy and
the boss hit-point passes, then the group passes (B4), which read both.
PS-OWM edits the staged overworld model the flow ships; the hit points are
staged in an EnemyHpResult and written into the GameWorld when the pass ships.
"""
from dataclasses import dataclass

from zora.generate.rng import IntRng, discard
from zora.model.enums import Enemy
from zora.model.game_world import GameWorld
from zora.model.sprites import EnemyData

E = Enemy


# --- PS-HP: enemy and boss hit points -----------------------------------------

HP_SEED_DRAWS = 3                  # one number as the pass's (unused) seed, two discarded
# The spec does not state the number's width; a change (r mod 3) and a sign
# (bit 5) taken from a uniform 31-bit number are as near uniform and
# independent as the spec's rule needs.
HP_NUMBER_RANGE = 1 << 31
HP_STEP_CHOICES = 3                # the change is |r mod 3|: 0, 1 or 2
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


def visiting_order(types: range) -> list[Enemy]:
    """PS-HP-01/02: each byte's odd type, then the even type that shares it
    (1, 0, 3, 2, ...); the ranges start on an even type."""
    return [Enemy(object_type ^ 1) for object_type in types]
GLEEOK_HEAD_CHOICES = 5            # (s mod 5) + 4: 4..8
GLEEOK_HEAD_BASE = 4


@dataclass
class EnemyHpResult:
    """The staged hit points: the 74 walked values (by object type), the
    rope's two operands and the five boss operands, as nibble values. A pass
    turned off (C09 or C10 at 0, FL-OFF-06) leaves its values as they were."""
    hp: dict[Enemy, int]
    rope: tuple[int, int] | None
    mirrors: dict[str, int]
    gleeok_head: int

    @classmethod
    def unchanged(cls, enemies: EnemyData) -> "EnemyHpResult":
        """The base ROM's values, before either pass."""
        return cls(dict(enemies.hp), enemies.rope_hp, {}, enemies.gleeok_head_hp)


def _step(value: int, rng: IntRng) -> int:
    """One object type: change |number mod 3|, up when bit 5 is set, clamped 0..15."""
    number = rng.below(HP_NUMBER_RANGE)
    change = number % HP_STEP_CHOICES
    moved = value + change if number & HP_UP_BIT else value - change
    return max(0, min(NIBBLE_MAX, moved))


def change_most_enemy_hp(state: EnemyHpResult, rng: IntRng) -> None:
    """"Most" Enemy HP (C09; PS-HP-01): object types $00-$31 in visiting
    order, then the rope's two operands."""
    discard(rng, HP_SEED_DRAWS, HP_NUMBER_RANGE)
    for enemy in visiting_order(ENEMY_HP_TYPES):
        state.hp[enemy] = _step(state.hp[enemy], rng)
    state.rope = (_step(ROPE_BASES[0], rng), _step(ROPE_BASES[1], rng))


def change_boss_hp(state: EnemyHpResult, rng: IntRng) -> None:
    """Boss HP (C10; PS-HP-02): object types $32-$49 in visiting order, each
    mirrored type's operand written with it, and the Gleeok head's draw right
    after type $43's write."""
    discard(rng, HP_SEED_DRAWS, HP_NUMBER_RANGE)
    for enemy in visiting_order(BOSS_HP_TYPES):
        state.hp[enemy] = _step(state.hp[enemy], rng)
        if enemy in BOSS_MIRRORS:
            state.mirrors[BOSS_MIRRORS[enemy]] = state.hp[enemy]
        if enemy == GLEEOK_HEAD_AFTER:
            state.gleeok_head = rng.below(HP_NUMBER_RANGE) % GLEEOK_HEAD_CHOICES + GLEEOK_HEAD_BASE


def apply_enemy_hp(gw: GameWorld, state: EnemyHpResult) -> None:
    """Write the staged hit points into the GameWorld (ship.py, when the attempt ships)."""
    enemies = gw.enemies
    enemies.hp = dict(state.hp)
    enemies.rope_hp = state.rope
    for name, value in state.mirrors.items():
        setattr(enemies, name, value)
    enemies.gleeok_head_hp = state.gleeok_head
