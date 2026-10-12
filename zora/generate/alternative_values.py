"""Which alternative values a generation produces (flags-behavior.md FL-ALT-02
to FL-ALT-04; owner ruling 2026-10-05: supported after the MVP).

One field per value, named after the function that produces it; each
function has one call site in generation_pass.py, which tests its field.
The defaults are the MVP baseline values: no alternative value, today's
output.
"""
from dataclasses import dataclass

from ..flags.fields import DungeonLayoutSource
from ..model.enums import Item


@dataclass(frozen=True)
class AlternativeValues:
    start_with_four_hearts: bool = False                 # C16 at 3, FL-ALT-02
    change_sword_hearts_from_five_hearts: bool = False   # C20 at 1, FL-ALT-03
    generate_community_hint_text: bool = False           # C03 at 2, FL-ALT-04
    show_every_helpful_hint: bool = False                # C03 at 1, HT-HINT-04
    shuffle_items_within_levels: bool = False            # C06 at 2, PS-ITW-01 to PS-ITW-07
    mix_overworld_quest: bool = False                    # C01 at 2, OW-MIX-01 to OW-MIX-10
    mix_overworld_quest_second_variant: bool = False     # C01 at 3, OW-QST-01 and OW-QST-02
    second_quest_overworld: bool = False                 # C01 at 1, OW-QST-03 to OW-QST-05
    full_start_shuffle: bool = False                     # C04 at 2, OW-START-02
    start_on_wood_sword_screen: bool = False             # C04 at 3, OW-START-03
    force_overworld_block: bool = False                  # B81 on (or "?" come up on), OW-CAVE-08
    wood_sword_cave_behind_blocks: bool = False          # B03 on (or "?" come up on), OW-CAVE-07
    # B57-B78 and B85 with C17 (FP-START-02): the start items the seed keeps, drawn with the plan
    start_items: tuple[Item, ...] = ()
    # C02 (after a random index is drawn, SH-SRC-10): which sets are shapes and which vanilla,
    # SH-SRC-07; 3, both sets shapes, is the MVP baseline
    dungeon_quest: DungeonLayoutSource = DungeonLayoutSource.GENERATED_SHAPES
    important_items_in_level_9: bool = False             # B25 on (or "?" come up on), VA-REJ-08

    @property
    def second_quest_secrets(self) -> bool:
        """Every overworld quest but the first (C01 = 1, 2, 3): the second quest's secret positions
        and recorder secrets are in play (screen 60 relaid, the eleven-screen recorder set)."""
        return self.mix_overworld_quest or self.mix_overworld_quest_second_variant or self.second_quest_overworld


# Every field at its MVP baseline value: the default where none are given.
MVP_VALUES = AlternativeValues()

