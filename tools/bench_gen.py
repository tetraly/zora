"""Benchmark seed generation times across many seeds and flag combos."""

import sys
import time
import statistics
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import (
    CaveShuffleMode,
    CosmeticFlags,
    Flags,
    HintMode,
    Item,
    Tristate,
)
from zora.generate_game import generate_game

# Most expensive flag combo: all shuffles enabled
HEAVY_FLAGS = Flags(
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
)

NUM_SEEDS = 50
START_SEED = 1

def main() -> None:
    num = int(sys.argv[1]) if len(sys.argv) > 1 else NUM_SEEDS
    start_seed = int(sys.argv[2]) if len(sys.argv) > 2 else START_SEED

    times: list[float] = []
    failures = 0

    print(f"Benchmarking {num} seeds starting at {start_seed} with HEAVY flags...")
    print(f"{'Seed':>6}  {'Time (s)':>8}  Status")
    print("-" * 30)

    for i in range(num):
        seed = start_seed + i
        t0 = time.monotonic()
        try:
            generate_game(HEAVY_FLAGS, seed=seed)
            elapsed = time.monotonic() - t0
            times.append(elapsed)
            status = "SLOW!" if elapsed > 5 else "ok"
            print(f"{seed:>6}  {elapsed:>8.2f}  {status}")
        except Exception as e:
            elapsed = time.monotonic() - t0
            failures += 1
            print(f"{seed:>6}  {elapsed:>8.2f}  FAIL: {e}")

    print()
    print("=" * 40)
    if times:
        times.sort()
        print(f"Seeds tested:  {num}")
        print(f"Successes:     {len(times)}")
        print(f"Failures:      {failures}")
        print(f"Min:           {min(times):.2f}s")
        print(f"Max:           {max(times):.2f}s")
        print(f"Mean:          {statistics.mean(times):.2f}s")
        print(f"Median:        {statistics.median(times):.2f}s")
        print(f"P90:           {times[int(len(times)*0.9)]:.2f}s")
        print(f"P95:           {times[int(len(times)*0.95)]:.2f}s")
        print(f"P99:           {times[int(len(times)*0.99)]:.2f}s")
        print(f"Stdev:         {statistics.stdev(times):.2f}s" if len(times) > 1 else "")
        print()
        slow = [t for t in times if t > 10]
        print(f"Seeds > 10s:   {len(slow)}")
        slow5 = [t for t in times if t > 5]
        print(f"Seeds > 5s:    {len(slow5)}")
        slow3 = [t for t in times if t > 3]
        print(f"Seeds > 3s:    {len(slow3)}")
    else:
        print("No successful generations!")


if __name__ == "__main__":
    main()
