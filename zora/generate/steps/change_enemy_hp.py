"""Change Enemy HP: "Most" Enemy HP (C09) and Boss HP (C10) at every value, Set Ganon HP
to 0 (B41) and Maximum Enemy and Boss Health (B45, B46), post-shapes batch B8's hit points,
and the owner's level-9 Vire cap (tetraly/zora#14, on the shipped world) (post-shapes-b8.md
PS-HP). The batch's overworld monster re-deal (PS-OWM) is shuffle_overworld_monsters; level 9's room records
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
from ...model.levels import Level
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


MAXIMUM_HP = NIBBLE_MAX           # PS-HP-07: every boss value and the five operands (operand $F0)


def maximum_boss_hp(state: EnemyHpResult) -> None:
    """Maximum Boss Health (B46; PS-HP-07), after the boss pass and B41 whatever C10 holds: every
    boss value 15, the four mirrored operands and Gleeok's head operand too. No draw. (B41 and B46
    never both apply: FL-DEP-01 rule 3.)"""
    for enemy in visiting_order(BOSS_HP_TYPES):
        state.hp[enemy] = MAXIMUM_HP
    state.mirrors.update(dict.fromkeys(BOSS_MIRRORS.values(), MAXIMUM_HP))
    state.gleeok_head = MAXIMUM_HP


def maximum_enemy_hp(state: EnemyHpResult) -> None:
    """Maximum Enemy Health (B45; PS-HP-08), after the boss pass and B41 and before B46 and the group
    passes, whatever C09 holds: every enemy value (object types $00-$31) 15 and both Rope operands
    $F0. No draw. The group pass then reads Zol at 15, so Vire is never in its coverage set
    (PS-EGRP-01); the level-9 Vire cap (cap_level_9_vire_hp) still runs on the shipped world."""
    state.hp.update(dict.fromkeys(visiting_order(ENEMY_HP_TYPES), MAXIMUM_HP))
    state.rope = (MAXIMUM_HP, MAXIMUM_HP)


def apply_enemy_hp(gw: GameWorld, state: EnemyHpResult) -> None:
    """Write the staged hit points into the GameWorld (ship.py, when the attempt ships)."""
    enemies = gw.enemies
    enemies.hp = dict(state.hp)
    enemies.rope_hp = state.rope
    for name, value in state.mirrors.items():
        setattr(enemies, name, value)
    enemies.gleeok_head_hp = state.gleeok_head
    enemies.ganon_return_hp = state.ganon_return


# --- Vires as level 9's only bomb droppers (owner rule, tetraly/zora#14) ------------------------

# The ordinary monsters on the drop table's rows that hold bombs: rows 2 (DropItemMonsterTypes2)
# and 3 (every type on no other list). Make Important Items Drops (B39) replaces only rupees and
# hearts, so the bombs stay. Bosses, Lanmolas and the overworld-only monsters of row 3 are left
# out: leaving a dropper out can only cap the Vires where the cap was not needed.
BOMB_DROPPERS = frozenset({
    E.BLUE_LYNEL, E.BLUE_MOBLIN, E.RED_GORIYA, E.BLUE_OCTOROK_1, E.BLUE_OCTOROK_2, E.RED_DARKNUT, E.VIRE,
    E.BLUE_WIZZROBE, E.GIBDO,                                   # row 2
    E.RED_LYNEL, E.BLUE_GORIYA, E.BLUE_DARKNUT,                 # row 3
})
# A Vire harmed but not killed splits into two red Keese (CheckVireCollisions), which drop nothing
# (NoDropMonsterTypes). At 4 or less (64 hit points) the magical sword's or a bomb's hit kills it
# outright, so it can drop bombs.
VIRE_MOST_HP = 4
LEVEL_9 = 9


def level_monsters(gw: GameWorld, level: Level) -> set[int]:
    """The monster types the level's rooms hold, a mixed list's members by their own types (as
    many as the room's count, from the list blob the passes left: EnemyData.mixed_groups is the
    base ROM's)."""
    lists, starts = gw.enemies.mixed_enemy_data, gw.enemies.mixed_group_offsets
    monsters: set[int] = set()
    for room in level.rooms:
        if room.enemy in starts:
            start = starts[room.enemy]
            monsters.update(lists[start:start + level.enemy_quantity(room)])
        else:
            monsters.add(room.enemy)
    return monsters


def cap_level_9_vire_hp(gw: GameWorld) -> bool:
    """When Vires are the only bomb droppers in level 9, their hit points are at most 4, so bombs
    can still drop there; True when the cap changed them. On the shipped world, after every pass
    that places monsters (the enemy groups, Oops All, the room exchange); no draw."""
    level_9 = next(level for level in gw.levels if level.level_num == LEVEL_9)
    droppers = level_monsters(gw, level_9) & BOMB_DROPPERS
    if droppers != {E.VIRE} or gw.enemies.hp[E.VIRE] <= VIRE_MOST_HP:
        return False
    gw.enemies.hp[E.VIRE] = VIRE_MOST_HP
    return True
