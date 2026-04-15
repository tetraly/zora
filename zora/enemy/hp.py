from zora.data_model import Enemy, EnemyData, GameWorld
from zora.game_config import GameConfig
from zora.rng import Rng


def randomize_hp(game_world: GameWorld, config: GameConfig, rng: Rng) -> None:
    """
    Top-level HP randomization dispatcher. Mirrors the conditional logic in
    RomGenerator.cs lines 207-225:

        if ChangeEnemyHP > 0 and not EnemyHPto0  → _randomize_enemy_hp()
        if EnemyHPto0                             → _set_enemy_hp_to_zero()
        if ShuffleBossHP > 0                      → _randomize_boss_hp()
        if BossHPto0                              → _set_boss_hp_to_zero()
        if GannonHPto0                            → _set_ganon_hp_to_zero()   (no RNG)
        if MaxEnemyHealth                         → _set_enemy_hp_to_max()    (no RNG)
        if MaxBossHealth                          → _set_boss_hp_to_max()     (no RNG)

    Note: enemy and boss HP are independent — both branches can fire in the same run.
    """
    if config.change_enemy_hp > 0 and not config.enemy_hp_to_zero:
        _randomize_enemy_hp(game_world.enemies, config.change_enemy_hp, rng)
    if config.enemy_hp_to_zero:
        _set_enemy_hp_to_zero(game_world.enemies, rng)
    if config.shuffle_boss_hp > 0:
        _randomize_boss_hp(game_world.enemies, config.shuffle_boss_hp, rng)
    if config.boss_hp_to_zero:
        _set_boss_hp_to_zero(game_world.enemies, rng)
    if config.ganon_hp_to_zero:
        _set_ganon_hp_to_zero(game_world.enemies)
    if config.max_enemy_health:
        _set_enemy_hp_to_max(game_world.enemies)
    if config.max_boss_health:
        _set_boss_hp_to_max(game_world.enemies, config.swordless)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _randomize_enemy_hp(enemies: EnemyData, max_change: int, rng: Rng) -> None:
    """
    Randomizes non-boss enemy HP by +/- max_change nibbles.
    Port of remapEnemyHP (Module.cs:86285-86363).

    C# operates only on the enemy HP table (ROM 129886–129910, 50 nibbles).
    It discards 2 RNG values at entry, consumes one per enemy nibble, then
    two more for SpecialBossHP1 (ROM 70355) and SpecialBossHP2 (ROM 70367).

    NOTE: The C# RNG uses integer bit manipulation for sign/magnitude. The
    Python Rng protocol only exposes random() → float. The logic below
    approximates the intent but will not produce bit-identical output.
    If exact C# parity is needed, add a next_int() method to the Rng protocol.
    """
    rng.random()  # discard 1
    rng.random()  # discard 2

    for enemy in list(enemies.hp.keys()):
        if enemy.is_boss:
            continue
        r = rng.random()
        change = int(r * (max_change + 1))
        sign = 1 if r > 0.5 else -1
        enemies.hp[enemy] = max(0, min(15, enemies.hp[enemy] + sign * change))

    # Special boss HP 1 — baseline 1 (ROM 70355)
    r1 = rng.random()
    change1 = int(r1 * (max_change + 1))
    sign1 = 1 if r1 > 0.5 else -1
    enemies.aquamentus_hp = max(0, min(15, sign1 * change1 + 1))

    # Special boss HP 2 — baseline 4 (ROM 70367)
    r2 = rng.random()
    change2 = int(r2 * (max_change + 1))
    sign2 = 1 if r2 > 0.5 else -1
    enemies.aquamentus_sp = max(0, min(15, sign2 * change2 + 4))


def _set_enemy_hp_to_zero(enemies: EnemyData, rng: Rng) -> None:
    """
    Sets all non-boss enemy HP to 0 (one-hit kills).
    Port of remapEnemyHPto0 (Module.cs:86219-86250).

    C# operates only on the enemy HP table (ROM 129886–129910) — NOT the boss
    table. Discards 2, zeroes every non-boss nibble, discards 1 more, then
    zeroes SpecialBossHP1 (ROM 70355) and SpecialBossHP2 (ROM 70367).
    """
    rng.random()  # discard 1
    rng.random()  # discard 2

    for enemy in enemies.hp:
        if not enemy.is_boss:
            enemies.hp[enemy] = 0

    rng.random()  # discard 3 (mirrors decompiled line 86247)

    enemies.aquamentus_hp = 0
    enemies.aquamentus_sp = 0


def _randomize_boss_hp(enemies: EnemyData, max_change: int, rng: Rng) -> None:
    """
    Randomizes boss HP by +/- max_change nibbles, with mirror writes for
    Aquamentus, Ganon, Gleeok, and Patra.
    Port of remapBossHP (Module.cs:86367-86461).

    C# iterates the boss HP table (ROM 129911–129922, 24 nibbles), consuming
    one RNG value per nibble. The Aquamentus SP draw happens inline when the
    Aquamentus entry is reached, not after the loop — preserving RNG order
    relative to subsequent entries.
    """
    rng.random()  # discard 1
    rng.random()  # discard 2

    for enemy in list(enemies.hp.keys()):
        if not enemy.is_boss:
            continue
        r = rng.random()
        change = int(r * (max_change + 1))
        sign = 1 if r > 0.5 else -1
        enemies.hp[enemy] = max(0, min(15, enemies.hp[enemy] + sign * change))

        # Aquamentus SP draw happens inline when Aquamentus is hit (mirrors C# switch
        # inside the loop at line 86390-86392), not after iteration.
        if enemy is Enemy.AQUAMENTUS:
            r_sp = rng.random()
            change_sp = int(r_sp * (max_change * 2 + 1))
            enemies.aquamentus_sp = max(0, min(15, change_sp - max_change + 6))
            enemies.aquamentus_hp = enemies.hp[Enemy.AQUAMENTUS]

        elif enemy is Enemy.THE_BEAST:
            enemies.ganon_hp = enemies.hp[Enemy.THE_BEAST]

        elif enemy is Enemy.GLEEOK_1:
            enemies.gleeok_hp = enemies.hp[Enemy.GLEEOK_1]

        elif enemy is Enemy.PATRA_1:
            enemies.patra_hp = enemies.hp[Enemy.PATRA_1]


def _set_boss_hp_to_zero(enemies: EnemyData, rng: Rng) -> None:
    """
    Sets all boss HP to 0, skipping Ganon (he keeps his HP).
    Port of remapBossHPto0 (Module.cs:86469-86533).

    C# discards 2, then for each boss nibble consumes one RNG value and zeroes
    it — EXCEPT for the Ganon entry, which is skipped entirely (no RNG consumed,
    no write). Mirror fields are zeroed inline as entries are processed.
    """
    rng.random()  # discard 1
    rng.random()  # discard 2

    for enemy in list(enemies.hp.keys()):
        if not enemy.is_boss:
            continue
        if enemy is Enemy.THE_BEAST:
            continue  # Ganon: no RNG consumed, no write (mirrors C# skip)
        rng.random()
        enemies.hp[enemy] = 0

        if enemy is Enemy.AQUAMENTUS:
            enemies.aquamentus_hp = 0
            enemies.aquamentus_sp = 0
        elif enemy is Enemy.GLEEOK_1:
            enemies.gleeok_hp = 0
        elif enemy is Enemy.PATRA_1:
            enemies.patra_hp = 0
    # ganon_hp intentionally left unchanged


def _set_ganon_hp_to_zero(enemies: EnemyData) -> None:
    """
    Sets only Ganon's HP to 0. No RNG consumed.
    Port of remapGannonHPto0 (Module.cs:86463).

    C# clears the high nibble at ROM[129917] and writes 0x41 to ROM[77607].
    """
    enemies.hp[Enemy.THE_BEAST] = 0
    enemies.ganon_hp = 0


def _set_enemy_hp_to_max(enemies: EnemyData) -> None:
    """
    Sets all non-boss enemy HP to maximum (nibble = 15). No RNG consumed.
    Port of remapEnemyHPtoMax (Module.cs:86252-86283).

    C# operates only on the enemy HP table (ROM 129886–129910) — NOT the boss
    table. Also maxes SpecialBossHP1 (ROM 70355) and SpecialBossHP2 (ROM 70367).
    """
    for enemy in enemies.hp:
        if not enemy.is_boss:
            enemies.hp[enemy] = 15
    enemies.aquamentus_hp = 15
    enemies.aquamentus_sp = 15


def _set_boss_hp_to_max(enemies: EnemyData, swordless: bool) -> None:
    """
    Sets all boss HP to maximum (nibble = 15). No RNG consumed.
    Port of remapBossHPtoMax (Module.cs:86535-86597).

    If swordless is True, the caller must also write ROM[99857] = 7 during
    ROM serialization — there is no corresponding field in EnemyData for that patch.
    """
    for enemy in list(enemies.hp.keys()):
        if enemy.is_boss:
            enemies.hp[enemy] = 15
    enemies.aquamentus_hp = 15
    enemies.aquamentus_sp = 15
    enemies.ganon_hp      = 15
    enemies.gleeok_hp     = 15
    enemies.patra_hp      = 15
