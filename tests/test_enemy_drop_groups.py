"""Shuffle Enemy Drop Groups (B38; post-shapes-b8.md PS-EDROP-03) on the spec's Check strings: the four
drop-class lists start $5D (kept) and $1B (blue Keese never drops), their other 29 slots hold 29
different types of the 38 dealt; class C's slots 3 to 5 hold a type of dungeon group 0, 1 and 2 (PRG0's
groups with Shuffle Enemy Groups off); under Maximum Enemy Health (B45) neither Vire nor Zol is drawn.
With B38 off the lists stay PRG0's."""
import pytest

from tests.needs import needs_base_rom
from zora.flags.codec import decode, encode
from zora.flags.fields import ThreeState
from zora.flags.presets import MVP_BASELINE_LEVEL_ENCODING_OFF
from zora.generate.pipeline import generate_rom
from zora.generate.rng import ScriptedRng
from zora.generate.steps.shuffle_enemy_drop_groups import (
    CLASS_C_START,
    DEALT_TYPES,
    KEPT_NO_DROP_TYPE,
    OVERWORLD_PICKS,
    OVERWORLD_TYPES,
    PRG0_DUNGEON_GROUPS,
    shuffle_enemy_drop_groups,
)
from zora.model.enums import Enemy
from zora.rom.base_rom import remember_repo_base_rom
from zora.rom.layout import ENEMY_DROP_CLASSES_ADDRESS, ENEMY_DROP_CLASSES_SIZE

SEEDS = (1, 2, 3)
SHAPES_GROUPS_OFF = {"B38": ThreeState.ON, "B42": ThreeState.OFF}
LOW_HIT_POINTS = 2


def drop_classes(toggles: dict[str, ThreeState], seed: int) -> bytes:
    flags = encode(decode(MVP_BASELINE_LEVEL_ENCODING_OFF).updated(toggles=toggles))
    rom = generate_rom(flags, seed, remember_repo_base_rom()).rom
    return rom[ENEMY_DROP_CLASSES_ADDRESS:ENEMY_DROP_CLASSES_ADDRESS + ENEMY_DROP_CLASSES_SIZE]


def assert_dealt(lists: bytes) -> None:
    assert lists[:2] == bytes([KEPT_NO_DROP_TYPE, Enemy.BLUE_KEESE])
    assert len(set(lists[2:])) == len(lists) - 2 and set(lists[2:]) <= set(DEALT_TYPES)


@needs_base_rom
@pytest.mark.parametrize("seed", SEEDS)
def test_the_lists_are_dealt_and_class_c_holds_the_group_types(seed: int) -> None:
    lists = drop_classes(SHAPES_GROUPS_OFF, seed)
    assert_dealt(lists)
    class_c = lists[CLASS_C_START:]
    assert len(set(class_c[:OVERWORLD_PICKS])) == OVERWORLD_PICKS
    assert set(class_c[:OVERWORLD_PICKS]) <= set(OVERWORLD_TYPES)
    for group, members in enumerate(PRG0_DUNGEON_GROUPS):
        assert class_c[OVERWORLD_PICKS + group] in members


@needs_base_rom
def test_with_the_enemy_groups_shuffled_the_lists_are_dealt() -> None:
    for seed in SEEDS:
        assert_dealt(drop_classes({"B38": ThreeState.ON}, seed))


@needs_base_rom
def test_off_keeps_prg0s_lists() -> None:
    base = remember_repo_base_rom()
    prg0 = base[ENEMY_DROP_CLASSES_ADDRESS:ENEMY_DROP_CLASSES_ADDRESS + ENEMY_DROP_CLASSES_SIZE]
    assert drop_classes({}, 1) == prg0


def test_a_vire_or_zol_is_drawn_again_while_the_other_has_more_than_four_hit_points() -> None:
    """Quirk: each reads the other's nibble. Scripted: the shuffle's draws, the three overworld picks,
    then group 2 draws Vire (redrawn: Zol has 5) and Like Like."""
    groups = ((Enemy.STALFOS,), (Enemy.GIBDO,), (Enemy.VIRE, Enemy.LIKE_LIKE))
    shuffle_draws = [0] * (len(DEALT_TYPES) - 1)
    lists = shuffle_enemy_drop_groups(ScriptedRng([*shuffle_draws, 0, 0, 0, 0, 0, 0, 1]), groups,
                                      vire_hit_points=LOW_HIT_POINTS, zol_hit_points=5)
    assert lists[CLASS_C_START + OVERWORLD_PICKS + 2] == Enemy.LIKE_LIKE
    lists = shuffle_enemy_drop_groups(ScriptedRng([*shuffle_draws, 0, 0, 0, 0, 0, 0]), groups,
                                      vire_hit_points=LOW_HIT_POINTS, zol_hit_points=LOW_HIT_POINTS)
    assert lists[CLASS_C_START + OVERWORLD_PICKS + 2] == Enemy.VIRE
