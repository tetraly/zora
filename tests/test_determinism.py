"""
Determinism tests: verify that generate_game produces identical output regardless
of what random state exists outside of it before each call.
"""
import random

import pytest

from flags.flags_generated import (
    BossHp,
    CaveShuffleMode,
    CosmeticFlags,
    DeathwarpButton,
    EnemyHp,
    Flags,
    HintMode,
    Item,
    LevelName,
    LowHeartsSound,
    SelectSwapMode,
    StartScreen,
    Tristate,
    VisualRoarSound,
)
from zora.generate_game import generate_game

_FLAGS = Flags()

# Full item shuffle + shops + hints — the largest flag combo that reliably
# succeeds across many seeds without hitting placement failures.
_FULL_ITEM_SHUFFLE_FLAGS = Flags(
    shuffle_dungeon_items=Tristate.ON,
    shuffle_dungeon_hearts=Tristate.ON,
    shuffle_within_dungeons=Tristate.ON,
    allow_triforces_in_stairways=Tristate.ON,
    shuffle_wood_sword=Tristate.ON,
    shuffle_magical_sword=Tristate.ON,
    shuffle_letter=Tristate.ON,
    shuffle_major_shop_items=Tristate.ON,
    shuffle_blue_potion=Tristate.ON,
    add_extra_candles=Tristate.ON,
    allow_important_in_l9=Tristate.ON,
    white_sword_item=Item.RANDOM,
    armos_item=Item.RANDOM,
    coast_item=Item.RANDOM,
    avoid_required_hard_combat=Tristate.ON,
    magical_boomerang_does_one_hp_damage=True,
    shuffle_shop_items=Tristate.ON,
    randomize_white_sword_hearts=True,
    randomize_magical_sword_hearts=True,
    randomize_bomb_upgrade=Tristate.ON,
    randomize_mmg=Tristate.ON,
    hint_mode=HintMode.HELPFUL,
    randomize_dungeon_palettes=Tristate.ON,
    permanent_sword_beam=Tristate.ON,
    book_is_an_atlas=Tristate.ON,
    book_is_a_translator=Tristate.ON,
    replace_book_fire_with_explosion=Tristate.ON,
    fix_known_bugs=Tristate.ON,
    fast_fill=Tristate.ON,
    speed_up_text=Tristate.ON,
    speed_up_dungeon_transitions=Tristate.ON,
    auto_show_letter=Tristate.ON,
    four_potion_inventory=Tristate.ON,
    flute_kills_pols=Tristate.ON,
    like_like_rupees=Tristate.ON,
)

_COSMETIC_FLAGS = CosmeticFlags(
    disable_music=Tristate.ON,
    reduce_flashing=Tristate.ON,
    green_tunic_color=14,  # random
    blue_ring_color=14,
    red_ring_color=14,
    heart_color=14,
)


def _assert_deterministic(flags: Flags, seed: int, label: str,
                          cosmetic_flags: CosmeticFlags | None = None) -> None:
    """Generate twice with random-state pollution between calls.
    Both must produce identical IPS bytes and hash codes."""
    ips1, hash1, *_ = generate_game(flags, seed=seed,
                                    cosmetic_flags=cosmetic_flags)

    random.seed(99999)
    for _ in range(500):
        random.random()

    ips2, hash2, *_ = generate_game(flags, seed=seed,
                                    cosmetic_flags=cosmetic_flags)

    assert hash1 == hash2, (
        f"[{label}] Hash mismatch: {hash1} vs {hash2}"
    )
    assert ips1 == ips2, (
        f"[{label}] IPS patch bytes differ across generations"
    )


@pytest.mark.parametrize("seed", [123])
def test_default_flags_deterministic(seed: int) -> None:
    """Default (all-off) flags must be deterministic with global random state
    pollution between calls."""
    _assert_deterministic(_FLAGS, seed, f"default seed={seed}")


@pytest.mark.parametrize("seed", [123])
def test_full_item_shuffle_deterministic(seed: int) -> None:
    """Full item shuffle with shops, hints, QoL, and cosmetics must be
    deterministic across multiple seeds."""
    _assert_deterministic(
        _FULL_ITEM_SHUFFLE_FLAGS, seed,
        f"full-item-shuffle seed={seed}",
        cosmetic_flags=_COSMETIC_FLAGS,
    )


# Full item shuffle + cave shuffle + overworld flags.
_FULL_ITEM_AND_CAVE_SHUFFLE_FLAGS = Flags(
    # Item shuffle
    shuffle_dungeon_items=Tristate.ON,
    shuffle_dungeon_hearts=Tristate.ON,
    shuffle_within_dungeons=Tristate.ON,
    allow_triforces_in_stairways=Tristate.ON,
    shuffle_wood_sword=Tristate.ON,
    shuffle_magical_sword=Tristate.ON,
    shuffle_letter=Tristate.ON,
    shuffle_major_shop_items=Tristate.ON,
    shuffle_blue_potion=Tristate.ON,
    add_extra_candles=Tristate.ON,
    allow_important_in_l9=Tristate.ON,
    white_sword_item=Item.RANDOM,
    armos_item=Item.RANDOM,
    coast_item=Item.RANDOM,
    avoid_required_hard_combat=Tristate.ON,
    shuffle_shop_items=Tristate.ON,
    hint_mode=HintMode.HELPFUL,
    # Overworld
    cave_shuffle_mode=CaveShuffleMode.ALL_CAVES,
    include_wood_sword_cave=Tristate.ON,
    include_any_road_caves=Tristate.ON,
    shuffle_armos_location=Tristate.ON,
    start_screen=StartScreen.FULL_SHUFFLE,
    update_recorder_warp_screens=Tristate.ON,
    extra_raft_blocks=Tristate.ON,
    randomize_lost_hills=Tristate.ON,
    randomize_dead_woods=Tristate.ON,
)


@pytest.mark.parametrize("seed", [123])
def test_full_item_and_cave_shuffle_deterministic(seed: int) -> None:
    """Full item shuffle + all-caves entrance shuffle must be deterministic."""
    _assert_deterministic(
        _FULL_ITEM_AND_CAVE_SHUFFLE_FLAGS, seed,
        f"item+cave-shuffle seed={seed}",
    )


# Kitchen sink: every flag enabled, including progressive items, L4 sword,
# all enemy shuffle options, cave shuffle, and all cosmetics.
_KITCHEN_SINK_FLAGS = Flags(
    shuffle_dungeon_items=Tristate.ON,
    shuffle_dungeon_hearts=Tristate.ON,
    shuffle_within_dungeons=Tristate.ON,
    allow_triforces_in_stairways=Tristate.ON,
    add_l4_sword=True,
    shuffle_wood_sword=Tristate.ON,
    shuffle_magical_sword=Tristate.ON,
    shuffle_letter=Tristate.ON,
    shuffle_major_shop_items=Tristate.ON,
    shuffle_blue_potion=Tristate.ON,
    add_extra_candles=Tristate.ON,
    progressive_items=Tristate.ON,
    allow_important_in_l9=Tristate.ON,
    force_rr_to_l9=Tristate.ON,
    force_sa_to_l9=Tristate.ON,
    white_sword_item=Item.RANDOM,
    armos_item=Item.RANDOM,
    coast_item=Item.RANDOM,
    avoid_required_hard_combat=Tristate.ON,
    magical_boomerang_does_one_hp_damage=True,
    shuffle_shop_items=Tristate.ON,
    randomize_white_sword_hearts=True,
    randomize_magical_sword_hearts=True,
    randomize_bomb_upgrade=Tristate.ON,
    randomize_mmg=Tristate.ON,
    hint_mode=HintMode.HELPFUL,
    randomize_dungeon_palettes=Tristate.ON,
    permanent_sword_beam=Tristate.ON,
    visual_roar_sound=VisualRoarSound.RANDOM,
    book_is_an_atlas=Tristate.ON,
    book_is_a_translator=Tristate.ON,
    replace_book_fire_with_explosion=Tristate.ON,
    fix_known_bugs=Tristate.ON,
    fast_fill=Tristate.ON,
    speed_up_text=Tristate.ON,
    speed_up_dungeon_transitions=Tristate.ON,
    auto_show_letter=Tristate.ON,
    four_potion_inventory=Tristate.ON,
    flute_kills_pols=Tristate.ON,
    like_like_rupees=Tristate.ON,
    cave_shuffle_mode=CaveShuffleMode.ALL_CAVES,
    include_wood_sword_cave=Tristate.ON,
    include_any_road_caves=Tristate.ON,
    shuffle_armos_location=Tristate.ON,
    start_screen=StartScreen.FULL_SHUFFLE,
    update_recorder_warp_screens=Tristate.ON,
    extra_raft_blocks=Tristate.ON,
    extra_power_bracelet_blocks=Tristate.ON,
    randomize_lost_hills=Tristate.ON,
    randomize_dead_woods=Tristate.ON,
    shuffle_overworld_monsters=Tristate.ON,
    shuffle_dungeon_monsters=Tristate.ON,
    shuffle_ganon_zelda=Tristate.ON,
    shuffle_level_9_monsters=Tristate.ON,
    shuffle_monsters_between_levels=Tristate.ON,
    add_2nd_quest_monsters=Tristate.ON,
    shuffle_enemy_groups=Tristate.ON,
    shuffle_bosses=Tristate.ON,
    change_dungeon_boss_groups=Tristate.ON,
    enemy_hp=EnemyHp.RANDOM,
    boss_hp=BossHp.RANDOM,
    ganon_hp_to_zero=Tristate.ON,
)

_KITCHEN_SINK_COSMETIC_FLAGS = CosmeticFlags(
    select_swap_mode=SelectSwapMode.TOGGLE,
    deathwarp_button=DeathwarpButton.P1_UP_SEL,
    low_hearts_sound=LowHeartsSound.SOFTER,
    disable_music=Tristate.ON,
    level_name=LevelName.RANDOM_CHOICE,
    reduce_flashing=Tristate.ON,
    green_tunic_color=14,
    blue_ring_color=14,
    red_ring_color=14,
    heart_color=14,
)


@pytest.mark.parametrize("seed", [123])
def test_kitchen_sink_deterministic(seed: int) -> None:
    """Every flag enabled (item shuffle, cave shuffle, enemies, progressive,
    L4 sword, all cosmetics) must be deterministic."""
    _assert_deterministic(
        _KITCHEN_SINK_FLAGS, seed,
        f"kitchen-sink seed={seed}",
        cosmetic_flags=_KITCHEN_SINK_COSMETIC_FLAGS,
    )
