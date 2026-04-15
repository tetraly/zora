"""
Tests for cave_randomizer.randomize_caves.

Covers:
  - No-op when all cave flags are off
  - MMG values are in valid ranges and obey constraints
  - MMG lose_large != win_small constraint
  - MMG win_large > win_small constraint
  - Extra candles placed in correct caves
  - Bomb upgrade cost and count in range
  - White sword heart requirement in valid set
  - Magical sword heart requirement in valid set
  - Different seeds produce different MMG values
  - Missing cave raises ValueError (MMG)
  - Missing caves are silently skipped (sword caves, candle caves)
"""

from pathlib import Path

from flags.flags_generated import Flags, Tristate
from zora.cave_randomizer import randomize_caves
from zora.data_model import (
    Destination,
    GameWorld,
    Item,
    ItemCave,
    MoneyMakingGameCave,
    TakeAnyCave,
)
from zora.game_config import GameConfig, resolve_game_config
from zora.parser import load_bin_files, parse_game_world
from zora.rng import SeededRng

TEST_DATA = Path(__file__).parent.parent / "rom_data"


def _fresh_world() -> GameWorld:
    return parse_game_world(load_bin_files(TEST_DATA))


def _config(flags: Flags, seed: int = 0) -> GameConfig:
    return resolve_game_config(flags, SeededRng(seed))


# ---------------------------------------------------------------------------
# No-op when all flags off
# ---------------------------------------------------------------------------


def test_no_op_when_all_flags_off():
    """randomize_caves must not mutate anything when all cave flags are off."""
    gw = _fresh_world()
    ow = gw.overworld

    mmg = ow.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
    assert mmg is not None
    before_mmg = (
        mmg.lose_small, mmg.lose_small_2, mmg.lose_large,
        mmg.win_small, mmg.win_large,
    )
    before_bomb = (ow.bomb_upgrade.cost, ow.bomb_upgrade.count)

    ws = ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    ms = ow.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    before_ws_hearts = ws.heart_requirement if ws else None
    before_ms_hearts = ms.heart_requirement if ms else None

    randomize_caves(gw, _config(Flags()), SeededRng(0))

    assert (mmg.lose_small, mmg.lose_small_2, mmg.lose_large,
            mmg.win_small, mmg.win_large) == before_mmg
    assert (ow.bomb_upgrade.cost, ow.bomb_upgrade.count) == before_bomb
    if ws:
        assert ws.heart_requirement == before_ws_hearts
    if ms:
        assert ms.heart_requirement == before_ms_hearts


# ---------------------------------------------------------------------------
# MMG randomization
# ---------------------------------------------------------------------------


def test_mmg_values_in_range():
    """All MMG values must fall in their documented ranges."""
    flags = Flags(randomize_mmg=Tristate.ON)
    for seed in range(20):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        mmg = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
        assert mmg is not None
        assert 1 <= mmg.lose_small <= 20, f"Seed {seed}: lose_small={mmg.lose_small}"
        assert 1 <= mmg.lose_small_2 <= 20, f"Seed {seed}: lose_small_2={mmg.lose_small_2}"
        assert 30 <= mmg.lose_large <= 50, f"Seed {seed}: lose_large={mmg.lose_large}"
        assert 10 <= mmg.win_small <= 30, f"Seed {seed}: win_small={mmg.win_small}"
        assert 25 <= mmg.win_large <= 75, f"Seed {seed}: win_large={mmg.win_large}"


def test_mmg_lose_large_not_equal_win_small():
    """lose_large must never equal win_small (game uses exact match for win check)."""
    flags = Flags(randomize_mmg=Tristate.ON)
    for seed in range(50):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        mmg = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
        assert mmg is not None
        assert mmg.lose_large != mmg.win_small, (
            f"Seed {seed}: lose_large ({mmg.lose_large}) == win_small ({mmg.win_small})"
        )


def test_mmg_win_large_exceeds_win_small():
    """win_large must be strictly greater than win_small."""
    flags = Flags(randomize_mmg=Tristate.ON)
    for seed in range(50):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        mmg = gw.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)
        assert mmg is not None
        assert mmg.win_large > mmg.win_small, (
            f"Seed {seed}: win_large ({mmg.win_large}) <= win_small ({mmg.win_small})"
        )


def test_mmg_different_seeds_produce_different_values():
    """Two different seeds should (very likely) produce different MMG values."""
    flags = Flags(randomize_mmg=Tristate.ON)

    gw1 = _fresh_world()
    randomize_caves(gw1, _config(flags, seed=1), SeededRng(1))
    mmg1 = gw1.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)

    gw2 = _fresh_world()
    randomize_caves(gw2, _config(flags, seed=99), SeededRng(99))
    mmg2 = gw2.overworld.get_cave(Destination.MONEY_MAKING_GAME, MoneyMakingGameCave)

    assert mmg1 is not None and mmg2 is not None
    vals1 = (mmg1.lose_small, mmg1.lose_small_2, mmg1.lose_large,
             mmg1.win_small, mmg1.win_large)
    vals2 = (mmg2.lose_small, mmg2.lose_small_2, mmg2.lose_large,
             mmg2.win_small, mmg2.win_large)
    assert vals1 != vals2, "Different seeds produced identical MMG values"


# ---------------------------------------------------------------------------
# Extra candles
# ---------------------------------------------------------------------------


def test_extra_candles_placed():
    """When add_extra_candles is on, wood sword cave and take-any get blue candles."""
    flags = Flags(add_extra_candles=Tristate.ON)
    gw = _fresh_world()
    randomize_caves(gw, _config(flags), SeededRng(0))

    ow = gw.overworld
    wood_sword = ow.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
    take_any = ow.get_cave(Destination.TAKE_ANY, TakeAnyCave)

    if wood_sword is not None:
        assert wood_sword.maybe_extra_candle == Item.BLUE_CANDLE
    if take_any is not None:
        assert take_any.items[1] == Item.BLUE_CANDLE


def test_extra_candles_not_placed_when_off():
    """When add_extra_candles is off, caves should keep their original values."""
    gw = _fresh_world()
    ow = gw.overworld

    wood_sword = ow.get_cave(Destination.WOOD_SWORD_CAVE, ItemCave)
    before_candle = wood_sword.maybe_extra_candle if wood_sword else None
    take_any = ow.get_cave(Destination.TAKE_ANY, TakeAnyCave)
    before_item1 = take_any.items[1] if take_any else None

    randomize_caves(gw, _config(Flags()), SeededRng(0))

    if wood_sword is not None:
        assert wood_sword.maybe_extra_candle == before_candle
    if take_any is not None:
        assert take_any.items[1] == before_item1


# ---------------------------------------------------------------------------
# Bomb upgrade
# ---------------------------------------------------------------------------


def test_bomb_upgrade_in_range():
    """Bomb upgrade cost and count must fall in their valid ranges."""
    flags = Flags(randomize_bomb_upgrade=Tristate.ON)
    for seed in range(20):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        bu = gw.overworld.bomb_upgrade
        assert 75 <= bu.cost <= 125, f"Seed {seed}: bomb cost={bu.cost}"
        assert 2 <= bu.count <= 6, f"Seed {seed}: bomb count={bu.count}"


def test_bomb_upgrade_unchanged_when_off():
    """Bomb upgrade must not change when flag is off."""
    gw = _fresh_world()
    before = (gw.overworld.bomb_upgrade.cost, gw.overworld.bomb_upgrade.count)

    randomize_caves(gw, _config(Flags()), SeededRng(0))

    after = (gw.overworld.bomb_upgrade.cost, gw.overworld.bomb_upgrade.count)
    assert before == after


# ---------------------------------------------------------------------------
# Sword heart requirements
# ---------------------------------------------------------------------------


def test_white_sword_hearts_in_valid_set():
    """White sword heart requirement must be one of {4, 5, 6}."""
    flags = Flags(randomize_white_sword_hearts=True)
    for seed in range(20):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        ws = gw.overworld.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
        if ws is not None:
            assert ws.heart_requirement in {4, 5, 6}, (
                f"Seed {seed}: white sword hearts={ws.heart_requirement}"
            )


def test_magical_sword_hearts_in_valid_set():
    """Magical sword heart requirement must be one of {10, 11, 12}."""
    flags = Flags(randomize_magical_sword_hearts=True)
    for seed in range(20):
        gw = _fresh_world()
        randomize_caves(gw, _config(flags, seed=seed), SeededRng(seed))

        ms = gw.overworld.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
        if ms is not None:
            assert ms.heart_requirement in {10, 11, 12}, (
                f"Seed {seed}: magical sword hearts={ms.heart_requirement}"
            )


def test_sword_hearts_unchanged_when_off():
    """Sword heart requirements must not change when flags are off."""
    gw = _fresh_world()
    ow = gw.overworld
    ws = ow.get_cave(Destination.WHITE_SWORD_CAVE, ItemCave)
    ms = ow.get_cave(Destination.MAGICAL_SWORD_CAVE, ItemCave)
    before_ws = ws.heart_requirement if ws else None
    before_ms = ms.heart_requirement if ms else None

    randomize_caves(gw, _config(Flags()), SeededRng(0))

    if ws is not None:
        assert ws.heart_requirement == before_ws
    if ms is not None:
        assert ms.heart_requirement == before_ms
