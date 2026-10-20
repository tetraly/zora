"""Which alternative values a generation produces (flags-behavior.md FL-ALT-02
to FL-ALT-04; owner ruling 2026-10-05: supported after the MVP).

One field per value, named after the function that produces it; each
function has one call site in generation_pass.py, which tests its field.
The defaults are the MVP baseline values: no alternative value, today's
output.
"""
from dataclasses import dataclass

from ..flags.fields import CaveShuffle, DungeonLayoutSource, HitPointChange, ItemShuffleScope, WoodenSwordState
from ..model.enums import Item


@dataclass(frozen=True)
class AlternativeValues:
    # C16 (after its random index is drawn, FL-DEP-04): the heart containers a new file starts with,
    # C16 + 1; 3 is the MVP baseline (FP-START-01), 4 FL-ALT-02, the rest FL-ALT-07
    starting_hearts: int = 3
    # C20 and C21 (FL-ALT-03, FL-ALT-05): the white-sword cave's heart counts, 4 + C20 to 6 - C21,
    # swapped when the lowest is above the highest (FL-DEP-03)
    white_sword_hearts: range = range(4, 7)
    generate_community_hint_text: bool = False           # C03 at 2, FL-ALT-04
    show_every_helpful_hint: bool = False                # C03 at 1, HT-HINT-04
    # C06 (after its random index is drawn, PS-ITEM-11): 0 no deal (PS-ITEM-10), 1 the fifteen places
    # (PS-ITEM-09), 2 within each dungeon (PS-ITW-01 to PS-ITW-07); 3, full, is the MVP baseline
    item_shuffle: ItemShuffleScope = ItemShuffleScope.FULL
    mix_overworld_quest: bool = False                    # C01 at 2, OW-MIX-01 to OW-MIX-10
    mix_overworld_quest_second_variant: bool = False     # C01 at 3, OW-QST-01 and OW-QST-02
    second_quest_overworld: bool = False                 # C01 at 1, OW-QST-03 to OW-QST-05
    full_start_shuffle: bool = False                     # C04 at 2, OW-START-02
    start_on_wood_sword_screen: bool = False             # C04 at 3, OW-START-03
    force_overworld_block: bool = False                  # B81 on (or "?" come up on), OW-CAVE-08
    wood_sword_cave_behind_blocks: bool = False          # B03 on (or "?" come up on), OW-CAVE-07
    # B57-B78 and B85 with C17 (FP-START-02): the start items the seed keeps, drawn with the plan
    start_items: tuple[Item, ...] = ()
    # C18 (FL-ALT-06): the start pieces, one bit per level 1-8, drawn with the start items
    start_triforce_pieces: int = 0
    # C11, C13, C26 and C27 (PS-ITEM-12): the item pinned to the Armos slot, the white-sword cave and
    # level 9's first and second pool places, as indices of the option list (0 pins nothing, 16 Non-Heart)
    armos_pin: int = 0
    white_sword_pin: int = 0
    level_9_pins: tuple[int, int] = (0, 0)
    # C07 (after its random index is drawn, FL-DEP-04; FP-WOOD-01): the wooden-sword state
    wooden_sword_state: WoodenSwordState = WoodenSwordState.NORMAL
    # C02 (after a random index is drawn, SH-SRC-10): which sets are shapes and which vanilla,
    # SH-SRC-07; 3, both sets shapes, is the MVP baseline
    dungeon_quest: DungeonLayoutSource = DungeonLayoutSource.GENERATED_SHAPES
    important_items_in_level_9: bool = False             # B25 on (or "?" come up on), VA-REJ-08
    remove_most_open_stairs: bool = False                # B30 on (or "?" come up on), PS-OSTAIR
    book_to_understand_npcs: bool = False             # B48 on (or "?" come up on), HT-BOOK
    # C05 (after its random index is drawn and FL-DEP-02 rule 1's coin): the cave walk's parts,
    # OW-CAVE-09; 3, both parts, is the MVP baseline
    cave_shuffle: CaveShuffle = CaveShuffle.ALL_CAVES
    # C09 and C10 (after a random index is drawn, FL-DEP-04): 1, a walk of up to 2, is the MVP
    # baseline; 2 a walk of up to 4 (PS-HP-01, PS-HP-02); 3 all zero (PS-HP-04, PS-HP-05). 0 turns
    # the pass off (FlagSteps)
    enemy_hit_points: HitPointChange = HitPointChange.UP_TO_2
    boss_hit_points: HitPointChange = HitPointChange.UP_TO_2
    ganon_hit_points_zero: bool = False                  # B41 on (or "?" come up on), PS-HP-06

    @property
    def shuffle_items_within_levels(self) -> bool:
        """C06 = 2: PS-ITW's two deals."""
        return self.item_shuffle is ItemShuffleScope.WITHIN_EACH_DUNGEON

    @property
    def item_deal(self) -> ItemShuffleScope:
        """The scope the item shuffle deals by. PS-ITEM-10's exception: under Mixed Quest (C02 = 2,
        drawn or chosen, SH-SRC-10) None (C06 = 0) deals anyway, as Item Only (C06 = 1)."""
        if self.item_shuffle is ItemShuffleScope.NONE and self.dungeon_quest is DungeonLayoutSource.MIXED:
            return ItemShuffleScope.DUNGEON_ITEMS_ONLY
        return self.item_shuffle

    @property
    def second_quest_secrets(self) -> bool:
        """Every overworld quest but the first (C01 = 1, 2, 3): the second quest's secret positions
        and recorder secrets are in play (screen 60 relaid, the eleven-screen recorder set)."""
        return self.mix_overworld_quest or self.mix_overworld_quest_second_variant or self.second_quest_overworld


# Every field at its MVP baseline value: the default where none are given.
MVP_VALUES = AlternativeValues()

