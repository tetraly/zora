"""Benchmark seed generation with dungeon_shapes enabled."""

import sys
import time
import statistics
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import (
    CaveShuffleMode,
    Flags,
    HintMode,
    Item,
    Tristate,
)
from zora.generate_game import generate_game

HEAVY_SHAPES_FLAGS = Flags(
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
    randomize_white_sword_hearts=True,
    randomize_magical_sword_hearts=True,
    randomize_bomb_upgrade=Tristate.ON,
    randomize_mmg=Tristate.ON,
    hint_mode=HintMode.HELPFUL,
    randomize_dungeon_palettes=Tristate.ON,
    cave_shuffle_mode=CaveShuffleMode.ALL_CAVES,
    include_wood_sword_cave=Tristate.ON,
    include_any_road_caves=Tristate.ON,
    shuffle_dungeon_rooms=Tristate.ON,
    shuffle_armos_location=Tristate.ON,
    progressive_items=Tristate.ON,
    fast_fill=Tristate.ON,
    fix_known_bugs=Tristate.ON,
    dungeon_shapes=Tristate.ON,
)

NUM_SEEDS = 50
START_SEED = 1


def main() -> None:
    num = int(sys.argv[1]) if len(sys.argv) > 1 else NUM_SEEDS
    start_seed = int(sys.argv[2]) if len(sys.argv) > 2 else START_SEED

    times: list[float] = []
    retries: list[int] = []
    failures = 0

    print(f"heavy+shapes {num} seeds from {start_seed}", flush=True)

    for i in range(num):
        seed = start_seed + i
        attempt_count = 0

        original_parse = __import__(
            "zora.generate_game", fromlist=["parse_game_world"]
        ).parse_game_world

        def counting_parse(bins, _orig=original_parse):
            nonlocal attempt_count
            attempt_count += 1
            return _orig(bins)

        t0 = time.monotonic()
        try:
            with patch("zora.generate_game.parse_game_world", counting_parse):
                generate_game(HEAVY_SHAPES_FLAGS, seed=seed)
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            retries.append(attempt_count - 1)
            r_str = f" r{attempt_count - 1}" if attempt_count > 1 else ""
            print(f"  {seed}: {elapsed:.2f}s{r_str}", flush=True)
        except Exception as e:
            elapsed = time.monotonic() - t0
            failures += 1
            print(f"  {seed}: {elapsed:.2f}s FAIL ({e})", flush=True)

    print(flush=True)
    print("=" * 40)
    if times:
        times_sorted = sorted(times)
        total_retries = sum(retries)
        seeds_with_retries = sum(1 for r in retries if r > 0)
        print(f"Seeds:         {num}")
        print(f"Successes:     {len(times)}")
        print(f"Failures:      {failures}")
        print(f"Retries:       {total_retries} across {seeds_with_retries} seeds")
        print(f"Min:           {min(times):.2f}s")
        print(f"Max:           {max(times):.2f}s")
        print(f"Mean:          {statistics.mean(times):.2f}s")
        print(f"Median:        {statistics.median(times):.2f}s")
        print(f"P90:           {times_sorted[int(len(times)*0.9)]:.2f}s")
        print(f"P95:           {times_sorted[int(len(times)*0.95)]:.2f}s")
        if len(times) > 1:
            print(f"Stdev:         {statistics.stdev(times):.2f}s")
        print()
        for threshold in (3, 5, 10):
            count = sum(1 for t in times if t > threshold)
            print(f"Seeds > {threshold}s:    {count}")
    else:
        print("No successful generations!")


if __name__ == "__main__":
    main()
