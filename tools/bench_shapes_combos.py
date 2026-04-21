"""Benchmark dungeon_shapes flag combos, 10 seeds each.

Prints each seed's generation time in real time, then a summary line.

Historical results (10 seeds, seeds 1-10):

  Before any fixes:
    shapes only                               stuck= 18  fails=0  mean=7.40s
    shapes + shuffle_rooms                    stuck=  3  fails=0  mean=3.75s
    shapes + shuffle_within                   stuck= 21  fails=0  mean=7.42s
    shapes + cave_shuffle                     stuck= 48  fails=1  mean=13.16s
    shapes + shuffle_rooms + within           stuck=  6  fails=0  mean=4.91s
    full heavy                                stuck=  3  fails=0  mean=3.60s

  After shutter door fix (item + transport staircases):
    shapes only                               stuck= 15  fails=0  mean=7.69s
    shapes + shuffle_rooms                    stuck=  3  fails=0  mean=3.61s
    shapes + shuffle_within                   stuck= 15  fails=0  mean=6.19s
    shapes + cave_shuffle                     stuck= 21  fails=0  mean=7.80s
    shapes + shuffle_rooms + within           stuck=  6  fails=0  mean=4.00s
    full heavy                                stuck=  3  fails=0  mean=3.56s

  After shutter fix + early connectivity check + retry on disconnected shapes:
    shapes only                               stuck=  9  fails=0  mean=5.30s
    shapes + shuffle_rooms                    stuck= 10  fails=0  mean=5.28s
    shapes + shuffle_within                   stuck=  9  fails=0  mean=4.84s
    shapes + cave_shuffle                     stuck= 10  fails=0  mean=5.61s
    shapes + shuffle_rooms + within           stuck= 12  fails=0  mean=5.29s
    full heavy                                stuck=  9  fails=0  mean=4.73s

NOTE: Seed 4 is consistently slow across all flag combos. Investigate in a
future session to determine whether it's an assumed-fill dead end, a layout
issue the connectivity check doesn't catch, or something else.
"""
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "flags"))

from flags.flags_generated import CaveShuffleMode, Flags, HintMode, Item, Tristate
from zora.generate_game import generate_game

BASE = dict(
    shuffle_dungeon_items=Tristate.ON,
    shuffle_dungeon_hearts=Tristate.ON,
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
    shuffle_armos_location=Tristate.ON,
    progressive_items=Tristate.ON,
    fast_fill=Tristate.ON,
    fix_known_bugs=Tristate.ON,
    dungeon_shapes=Tristate.ON,
)


def make_flags(**overrides: object) -> Flags:
    d = dict(BASE)
    d.update(overrides)
    return Flags(**d)


COMBOS = [
    ("shapes only",
     make_flags(shuffle_within_dungeons=Tristate.OFF,
                cave_shuffle_mode=CaveShuffleMode.VANILLA)),
    ("shapes + shuffle_rooms",
     make_flags(shuffle_dungeon_rooms=Tristate.ON,
                shuffle_within_dungeons=Tristate.OFF,
                cave_shuffle_mode=CaveShuffleMode.VANILLA)),
    ("shapes + shuffle_within",
     make_flags(shuffle_within_dungeons=Tristate.ON,
                cave_shuffle_mode=CaveShuffleMode.VANILLA)),
    ("shapes + cave_shuffle",
     make_flags(shuffle_within_dungeons=Tristate.OFF,
                cave_shuffle_mode=CaveShuffleMode.ALL_CAVES)),
    ("shapes + shuffle_rooms + within",
     make_flags(shuffle_dungeon_rooms=Tristate.ON,
                shuffle_within_dungeons=Tristate.ON,
                cave_shuffle_mode=CaveShuffleMode.VANILLA)),
    ("full heavy",
     make_flags(shuffle_dungeon_rooms=Tristate.ON,
                shuffle_within_dungeons=Tristate.ON,
                cave_shuffle_mode=CaveShuffleMode.ALL_CAVES,
                include_wood_sword_cave=Tristate.ON,
                include_any_road_caves=Tristate.ON)),
]

stuck_count = 0


class StuckCounter(logging.Handler):
    def emit(self, record: logging.LogRecord) -> None:
        global stuck_count
        if "assumed_fill STUCK" in record.getMessage():
            stuck_count += 1


logger = logging.getLogger("zora.item_randomizer")
logger.setLevel(logging.DEBUG)
logger.addHandler(StuckCounter())

NUM = 10

for label, flags in COMBOS:
    stuck_count = 0
    times: list[float] = []
    fails = 0

    sys.stdout.write(f"{label:40s}  ")
    sys.stdout.flush()

    for seed in range(1, NUM + 1):
        t0 = time.monotonic()
        try:
            generate_game(flags, seed=seed)
            times.append(time.monotonic() - t0)
            sys.stdout.write(f"{times[-1]:.1f} ")
            sys.stdout.flush()
        except Exception:
            fails += 1
            times.append(time.monotonic() - t0)
            sys.stdout.write(f"{times[-1]:.1f}F ")
            sys.stdout.flush()

    mean_t = sum(times) / len(times)
    print(f" | stuck={stuck_count:3d} fails={fails} mean={mean_t:.2f}s", flush=True)
