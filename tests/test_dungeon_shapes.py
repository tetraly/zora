"""Tests for dungeon_shapes generation: verify the full pipeline completes
with dungeon_shapes enabled across multiple seeds."""

from unittest.mock import patch

import pytest

from flags.flags_generated import Flags, Tristate
from zora.generate_game import generate_game
from zora.level_gen.orchestrator import (
    _MAX_SHAPES_ATTEMPTS,
    generate_dungeon_shapes,
)
from zora.rng import SeededRng


def test_dungeon_shapes_single_seed() -> None:
    """Full generate_game pipeline completes with dungeon_shapes enabled."""
    flags = Flags(dungeon_shapes=Tristate.ON)
    ips_bytes, hash_names, *_ = generate_game(flags, seed=42)
    assert len(ips_bytes) > 0
    assert len(hash_names) == 4


def test_dungeon_shapes_multiple_seeds() -> None:
    """Pipeline completes across several seeds with dungeon_shapes enabled."""
    flags = Flags(dungeon_shapes=Tristate.ON)
    for seed in range(10):
        ips_bytes, hash_names, *_ = generate_game(flags, seed=seed)
        assert len(ips_bytes) > 0, f"seed {seed} produced empty IPS"
        assert len(hash_names) == 4, f"seed {seed} produced wrong hash count"


def test_shapes_retries_on_room_count_mismatch(bins, fresh_game_world) -> None:
    """generate_dungeon_shapes retries when parsed rooms < grid cells."""
    from zora.game_config import GameConfig
    from zora.level_gen.api import generate_new_levels, NewLevelOutput

    config = GameConfig(dungeon_shapes=True)

    # Generate valid output by trying seeds until we find one that passes
    from zora.level_gen.orchestrator import _build_input
    from zora.dungeon.shuffle_dungeon_rooms import _is_level_connected
    from zora.parser import parse_levels_from_bins

    inputs = _build_input(bins)

    # Find a seed that produces valid shapes
    good_output = None
    for try_seed in range(100):
        candidate = generate_new_levels(try_seed, inputs)
        levels = parse_levels_from_bins(
            level_1_6_data=candidate.level_1_6_grid,
            level_7_9_data=candidate.level_7_9_grid,
            level_info=candidate.level_info,
            mixed_enemy_data=bins.mixed_enemy_data,
            mixed_enemy_pointers=bins.mixed_enemy_pointers,
        )
        expected: dict[int, int] = {}
        for grid in (candidate.grid_16, candidate.grid_79):
            for row in grid:
                for cell in row:
                    if cell > 0:
                        expected[cell] = expected.get(cell, 0) + 1
        ok = all(len(lv.rooms) >= expected.get(lv.level_num, 0) for lv in levels)
        if ok and all(_is_level_connected(lv) for lv in levels):
            good_output = candidate
            break

    assert good_output is not None, "Could not find a valid shapes seed for test"

    # Create bad output: inflate grid so level 1 claims one extra cell
    bad_grid = [row[:] for row in good_output.grid_16]
    for r in range(8):
        for c in range(16):
            if bad_grid[r][c] == 0:
                bad_grid[r][c] = 1
                break
        else:
            continue
        break

    bad_output = NewLevelOutput(
        level_1_6_grid=good_output.level_1_6_grid,
        level_7_9_grid=good_output.level_7_9_grid,
        level_info=good_output.level_info,
        sprite_table=good_output.sprite_table,
        grid_16=bad_grid,
        grid_79=good_output.grid_79,
        dungeon_order=good_output.dungeon_order,
    )

    call_count = 0

    def mock_generate(seed, inp, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count <= 3:
            return bad_output
        return good_output

    rng = SeededRng(99)
    with patch(
        "zora.level_gen.orchestrator.generate_new_levels", side_effect=mock_generate
    ):
        generate_dungeon_shapes(fresh_game_world, bins, config, rng)

    assert call_count == 4
    assert len(fresh_game_world.levels) == 9


def test_shapes_raises_after_max_attempts(bins, fresh_game_world) -> None:
    """generate_dungeon_shapes raises RuntimeError when all attempts fail."""
    from zora.game_config import GameConfig
    from zora.level_gen.api import generate_new_levels, NewLevelOutput

    config = GameConfig(dungeon_shapes=True)
    rng = SeededRng(1)

    from zora.level_gen.orchestrator import _build_input
    inputs = _build_input(bins)
    good_seed = int(rng.random() * 0xFFFFFFFF)
    good_output = generate_new_levels(good_seed, inputs)

    # Inflate grid so every attempt fails validation
    bad_grid = [row[:] for row in good_output.grid_16]
    for r in range(8):
        for c in range(16):
            if bad_grid[r][c] == 0:
                bad_grid[r][c] = 1
                break
        else:
            continue
        break

    always_bad = NewLevelOutput(
        level_1_6_grid=good_output.level_1_6_grid,
        level_7_9_grid=good_output.level_7_9_grid,
        level_info=good_output.level_info,
        sprite_table=good_output.sprite_table,
        grid_16=bad_grid,
        grid_79=good_output.grid_79,
        dungeon_order=good_output.dungeon_order,
    )

    rng2 = SeededRng(99)
    with patch(
        "zora.level_gen.orchestrator.generate_new_levels", return_value=always_bad
    ):
        with pytest.raises(RuntimeError, match="failed after"):
            generate_dungeon_shapes(fresh_game_world, bins, config, rng2)
