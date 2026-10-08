"""Which flag-switched steps a generation runs (flags-behavior.md FL-OFF-01 to
FL-OFF-07).

One field per step, named after the step function it switches; each step is
one entry of generation_pass.STEPS, whose enabled predicate tests its field. A turned-off step
does not run: what it would have written keeps the value it held before
(PRG0's, unless an earlier pass or the shape stage wrote it), and every other
pass runs as specified, in the same order. The defaults are the MVP
baseline: everything runs.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class FlagSteps:
    # Overworld passes (FL-OFF-02)
    recorder_to_new_dungeons: bool = True        # B01, OW-WARP-01
    shuffle_shop_items: bool = True              # B08, OW-SHOP-02 to OW-SHOP-04
    extra_candles: bool = True                   # B09, OW-SHOP-05
    shuffle_armos: bool = True                   # B13, OW-CAVE-05
    # B04, OW-CAVE-04's take-any-road caves; off is ZORA's own value (owner ruling, 2026-10-07):
    # the four take-any-road caves keep their PRG0 screens
    shuffle_take_any_road_caves: bool = True
    # Values drawn once (FL-OFF-03)
    change_sword_hearts: bool = True             # B10, FP-SWORD-01
    change_money_making_game: bool = True        # B11, FP-MMG-01
    change_bomb_upgrades: bool = True            # B12, FP-BOMB-01
    # Dungeon passes (FL-OFF-04)
    shuffle_dungeon_drops: bool = True           # B15, PS-DROP-01 to PS-DROP-03 and PS-XCHG-05
    shuffle_dungeon_text: bool = True            # B19, HT-TEXT-04
    add_money_or_life_rooms: bool = True         # B22, PS-MERCH-01
    change_money_or_life_toll: bool = True       # B23, PS-MERCH-02 and PS-MERCH-04
    shuffle_dungeon_palettes: bool = True        # B27, PS-COLOR-01 to PS-COLOR-03
    shuffle_hungry_goriya: bool = True           # B28, PS-GRUM-01 to PS-GRUM-03
    shuffle_overworld_monsters: bool = True      # B31, PS-OWM-01 and PS-OWM-02
    shuffle_bosses: bool = True                  # B34, PS-BOSS-01 to PS-BOSS-06
    shuffle_monsters_between_levels: bool = True  # B36, PS-MONLV-01 to PS-MONLV-06
    randomize_boss_groups: bool = True           # B40, PS-BGRP-01 to PS-BGRP-03
    shuffle_enemy_groups: bool = True            # B42, PS-EGRP-01 to PS-EGRP-06
    # Patches (FL-OFF-05); Book is an Atlas (B49) is a code patch, so the
    # serializer's switch: GameConfig.book_is_an_atlas
    speed_up_text: bool = True                   # B54, FP-TEXT-01
    # Option fields (FL-OFF-06)
    shuffle_start_screen: bool = True            # C04 at 1, OW-START-01
    change_most_enemy_hp: bool = True            # C09 at 1, PS-HP-01
    change_boss_hp: bool = True                  # C10 at 1, PS-HP-02
    exchange_rooms: bool = True                  # C14 at 2, PS-XCHG-01 to PS-XCHG-05


# Every flag-switched step on (the MVP baseline): the default where none are given.
ALL_STEPS_ON = FlagSteps()
